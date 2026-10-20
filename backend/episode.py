"""One episode of the shielded loop, driven step by step. Plan section 5.1.

The headless CLI in run_episode.py and the WebSocket server both sit on
EpisodeRunner. Shield off still runs facts, Jev and the checkers in shadow and
executes the policy's top action unconditionally, so before and after numbers
come from the same code path.
"""

from __future__ import annotations

import statistics
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from backend import checkers
from backend import facts as fact_extractor
from backend.constraints import ConstraintStore
from backend.env import ACTION_INDEX, make_env
from backend.jev_client import JevClient
from backend.logger import JsonlLogger, build_record, make_run_id
from backend.policy import Policy
from backend.shield import (
    DEFAULT_FLOOR_S,
    Answer,
    Decision,
    EscalationReason,
    Floor,
    Thresholds,
    decide,
    floor_decision,
    resolve,
    under_floor,
    violation_probability,
)


@dataclass(frozen=True)
class Escalation:
    """Queue item for the operator. Plan section 5.6."""

    id: str
    step: int
    action: str  # the proposed top action
    sentences: list[str]
    constraint_id: str | None
    constraint_text: str | None
    p: float
    q_rank: int
    fallback: str
    fallback_kind: str
    judge_unavailable: bool
    reason: EscalationReason
    candidates: list[dict[str, Any]]  # every ranked action: action, rank, p, constraint_id, noop
    ground_truth: (
        bool | None
    )  # proposed action breaks any enabled rule; for the simulated operator, never shown
    violations_by_action: dict[str, int | None]  # true labels per candidate; never shown


Operator = Callable[[Escalation], Awaitable[Answer]]


async def simulated_operator(escalation: Escalation) -> Answer:
    """Answers with the ground-truth checker.

    Uncertain: deny a true or unknown violation, approve otherwise. No compliant
    action: override with the candidate that breaks the fewest rules, ties to the
    policy's ranking, approving when that is the proposal; no labels at all denies.
    """
    if escalation.reason == "no_compliant_action":
        counts = {a: n for a, n in escalation.violations_by_action.items() if n is not None}
        if not counts:
            return Answer("deny")
        fewest = min(counts.values())
        action = next(
            c["action"] for c in escalation.candidates if counts.get(c["action"]) == fewest
        )
        return Answer("approve") if action == escalation.action else Answer("override", action)
    return Answer("deny") if escalation.ground_truth in (True, None) else Answer("approve")


async def always_approve(escalation: Escalation) -> Answer:
    return Answer("approve")


async def always_deny(escalation: Escalation) -> Answer:
    return Answer("deny")


OperatorName = Literal["simulated", "approve", "deny"]
OPERATORS: dict[OperatorName, Operator] = {
    "simulated": simulated_operator,
    "approve": always_approve,
    "deny": always_deny,
}


@dataclass
class StepResult:
    record: dict[str, Any]
    escalation: Escalation | None
    terminated: bool
    truncated: bool

    @property
    def done(self) -> bool:
        return self.terminated or self.truncated


@dataclass
class Totals:
    steps: int = 0
    reward: float = 0.0
    crashed: bool = False
    decisions: dict[str, int] = field(default_factory=dict)
    conflicts: int = 0  # escalations with no compliant action
    floored: int = 0  # steps where the floor removed at least one candidate
    violations: dict[str, int] = field(
        default_factory=dict
    )  # constraint id -> executed-action violations
    human: dict[str, int] = field(default_factory=dict)
    sources: dict[str, int] = field(default_factory=dict)
    latencies_ms: list[float] = field(default_factory=list)
    input_tokens: int = 0
    cost_usd: float = 0.0


class EpisodeRunner:
    def __init__(
        self,
        *,
        policy: Policy,
        judge: JevClient,
        store: ConstraintStore,
        thresholds: Thresholds | None = None,
        floor_s: float = DEFAULT_FLOOR_S,
        shield_on: bool = True,
        operator: Operator | None = None,
        operator_name: str = "simulated",
        logger: JsonlLogger | None = None,
        env_config: dict[str, Any] | None = None,
        source: str = "live",
    ) -> None:
        self.policy = policy
        self.judge = judge
        self.store = store
        self.thresholds = thresholds or Thresholds()
        self.floor_s = floor_s
        self.shield_on = shield_on
        self.operator = operator or simulated_operator
        self.operator_name = operator_name
        self.logger = logger
        self.source = source
        self.env = make_env(env_config)
        self.seed = 0
        self.episode = 0
        self.run_id = ""
        self.step_index = 0
        self.totals = Totals()
        self._obs: Any = None
        self._lanes: deque[int] = deque(maxlen=2 * fact_extractor.HISTORY_STEPS)

    def reset(self, seed: int) -> dict[str, Any]:
        self.seed = seed
        self.run_id = make_run_id(seed, self.shield_on)
        self.step_index = 0
        self.totals = Totals()
        self._lanes.clear()
        self._obs, _ = self.env.reset(seed=seed)
        return fact_extractor.snapshot(self.env)

    @property
    def ego_x_m(self) -> float:
        return float(self.env.unwrapped.vehicle.position[0])

    async def step(self) -> StepResult:
        self.store.retire_passed_zones(self.ego_x_m)
        ranked = self.policy.ranked_actions(self._obs)
        names = [r.name for r in ranked]
        lane = fact_extractor.lane_number(self.env.unwrapped.vehicle.lane_index)
        history = fact_extractor.lane_history(list(self._lanes), lane)
        self._lanes.append(lane)
        candidates = fact_extractor.for_candidates(self.env, names, self.store.zones, history)
        enabled = self.store.enabled()
        check = await self.judge.check(candidates, enabled)
        labels = checkers.label_all(candidates, enabled)
        noop = fact_extractor.noop_actions(candidates)
        floor = Floor(
            applied=self.shield_on and self.floor_s > 0,
            removed=under_floor(candidates, self.floor_s),
        )
        executable = [a for a in names if a not in floor.removed] if floor.applied else names
        if executable:
            decision = decide(executable, check.p, self.thresholds, noop)
        else:
            decision = floor_decision(names, check.p)

        escalation: Escalation | None = None
        human: dict[str, Any] | None = None
        escalated = False
        if not self.shield_on:
            decision = replace(
                decision, kind="allow", executed=decision.proposed, all_blocked=False, reason=None
            )
        elif decision.kind == "escalate":
            escalated = True
            escalation = self._escalation(
                decision, candidates, labels, check.p, noop, check.judge_unavailable
            )
            started = time.perf_counter()
            answer = await self.operator(escalation)
            human = {
                "decision": answer.decision,
                "action": answer.action,
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                "operator": self.operator_name,
            }
            decision = resolve(decision, answer)

        snapshot = fact_extractor.snapshot(self.env)
        self._obs, reward, terminated, truncated, info = self.env.step(
            ACTION_INDEX[decision.executed]
        )
        record = build_record(
            run_id=self.run_id,
            episode=self.episode,
            step=self.step_index,
            seed=self.seed,
            source=self.source,
            shield_on=self.shield_on,
            thresholds=self.thresholds,
            snapshot=snapshot,
            zones=[z.to_dict() for z in self.store.zones],
            constraints=[c.to_dict() for c in self.store.constraints],
            candidates=[
                {
                    "action": r.name,
                    "rank": r.rank,
                    "q": round(r.q, 4),
                    "facts": candidates[r.name],
                    "sentences": fact_extractor.sentences(candidates[r.name]),
                    "checks": [
                        {
                            "constraint_id": c.id,
                            "p_violation": check.p[r.name][c.id],
                            "ground_truth": labels[r.name][c.id],
                        }
                        for c in enabled
                    ],
                }
                for r in ranked
            ],
            decision=decision,
            escalated=escalated,
            human=human,
            fallback={"action": decision.fallback, "kind": decision.fallback_kind},
            floor=floor.to_dict(),
            judge=check.judge_record(),
            reward=float(reward),
            crashed=bool(info["crashed"]),
        )
        if self.logger is not None:
            self.logger.write(record)
        self._account(
            record, labels[decision.executed], check.latency_ms, check.input_tokens, check.cost_usd
        )
        self.step_index += 1
        return StepResult(record, escalation, bool(terminated), bool(truncated))

    def _escalation(
        self,
        decision: Decision,
        candidates: dict[str, Any],
        labels: dict[str, dict[str, bool | None]],
        p: dict[str, dict[str, float]],
        noop: frozenset[str],
        judge_unavailable: bool,
    ) -> Escalation:
        cid = decision.fired_constraint
        proposed_labels = [v for v in labels[decision.proposed].values() if v is not None]
        ground_truth = any(proposed_labels) if proposed_labels else None
        ranked_candidates = []
        violations_by_action: dict[str, int | None] = {}
        for rank, action in enumerate(decision.p_viol):
            worst_p, worst_cid = violation_probability(p.get(action, {}))
            ranked_candidates.append(
                {
                    "action": action,
                    "rank": rank,
                    "p": worst_p,
                    "constraint_id": worst_cid,
                    "noop": action in noop,
                }
            )
            known = [v for v in labels[action].values() if v is not None]
            violations_by_action[action] = sum(known) if known else None
        return Escalation(
            id=f"{self.run_id}-{self.step_index}",
            step=self.step_index,
            action=decision.proposed,
            sentences=fact_extractor.sentences(candidates[decision.proposed]),
            constraint_id=cid,
            constraint_text=self.store.get(cid).text if cid else None,
            p=decision.p_proposed,
            q_rank=0,
            fallback=decision.fallback,
            fallback_kind=decision.fallback_kind,
            judge_unavailable=judge_unavailable,
            reason=decision.reason or "uncertain",
            candidates=ranked_candidates,
            ground_truth=ground_truth,
            violations_by_action=violations_by_action,
        )

    def _account(
        self,
        record: dict[str, Any],
        executed_labels: dict[str, bool | None],
        latency_ms: float,
        tokens: int,
        cost: float,
    ) -> None:
        t = self.totals
        t.steps += 1
        t.reward += record["reward"]
        t.crashed = t.crashed or record["crashed"]
        t.decisions[record["decision"]] = t.decisions.get(record["decision"], 0) + 1
        if record["escalation_reason"] == "no_compliant_action":
            t.conflicts += 1
        if record["floor"]["applied"] and record["floor"]["removed"]:
            t.floored += 1
        for cid, violated in executed_labels.items():
            if violated:
                t.violations[cid] = t.violations.get(cid, 0) + 1
        if record["human"] is not None:
            key = record["human"]["decision"]
            t.human[key] = t.human.get(key, 0) + 1
        src = record["judge"]["source"]
        t.sources[src] = t.sources.get(src, 0) + 1
        t.latencies_ms.append(latency_ms)
        t.input_tokens += tokens
        t.cost_usd += cost

    def summary(self) -> dict[str, Any]:
        t = self.totals
        lat = sorted(t.latencies_ms)
        return {
            "run_id": self.run_id,
            "seed": self.seed,
            "shield_on": self.shield_on,
            "judge_mode": self.judge.mode,
            "steps": t.steps,
            "return": round(t.reward, 3),
            "crashed": t.crashed,
            "decisions": dict(sorted(t.decisions.items())),
            "conflicts": t.conflicts,
            "floored": t.floored,
            "violations": {
                cid: t.violations.get(cid, 0) for cid in [c.id for c in self.store.constraints]
            },
            "violations_total": sum(t.violations.values()),
            "human": dict(sorted(t.human.items())),
            "judge_sources": dict(sorted(t.sources.items())),
            "latency_ms_p50": round(statistics.median(lat), 1) if lat else 0.0,
            "latency_ms_p95": round(lat[min(len(lat) - 1, int(0.95 * (len(lat) - 1)))], 1)
            if lat
            else 0.0,
            "input_tokens": t.input_tokens,
            "cost_usd": round(t.cost_usd, 6),
        }

    async def run(
        self,
        seed: int,
        max_steps: int | None = None,
        on_step: Callable[[StepResult], None] | None = None,
        zone_at_step: int | None = None,
    ) -> dict[str, Any]:
        """Headless loop: reset, step until done, optionally dropping the default zone mid-episode."""
        self.reset(seed)
        while True:
            if zone_at_step is not None and self.step_index == zone_at_step:
                self.store.drop_zone(self.ego_x_m)
            result = await self.step()
            if on_step is not None:
                on_step(result)
            if result.done or (max_steps is not None and self.step_index >= max_steps):
                return self.summary()

    def close(self) -> None:
        self.env.close()
