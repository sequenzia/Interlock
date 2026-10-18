"""Allow, fallback or escalate. Plan section 5.2.

Pure functions of the ranked actions and the p grid from the judge. No
simulator and no Jev here, so every branch is unit-testable.

The shield acts on its own only when it holds a confidently safe action. When
nothing is confidently safe it escalates with reason ``no_compliant_action``
so a jointly unsatisfiable state reaches a person instead of looping on a
no-op last resort (plan section 16.1).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any, Literal

DecisionKind = Literal["allow", "fallback", "escalate", "all_blocked"]
FallbackKind = Literal["safe", "least_bad", "last_resort"]
EscalationReason = Literal["uncertain", "no_compliant_action"]
OperatorDecision = Literal["approve", "deny", "override"]
PGrid = dict[str, dict[str, float]]  # action -> constraint id -> p(violation)
DEFAULT_FLOOR_S = 2.0  # time to collision ahead under which a candidate never runs; one step is 1 s


@dataclass(frozen=True)
class Thresholds:
    t_allow: float = 0.3
    t_block: float = 0.7

    def __post_init__(self) -> None:
        if not 0.0 <= self.t_allow <= self.t_block <= 1.0:
            raise ValueError(
                f"need 0 <= t_allow <= t_block <= 1, got {self.t_allow}, {self.t_block}"
            )


@dataclass(frozen=True)
class Fallback:
    """What deny would execute and how it was found."""

    action: str
    kind: FallbackKind


@dataclass(frozen=True)
class Answer:
    """The operator's answer to an escalation. An override names the action to run."""

    decision: OperatorDecision
    action: str | None = None


@dataclass(frozen=True)
class Floor:
    """What the physics floor did this step. Plan section 16.4."""

    applied: bool  # the executable set was filtered: shield on and a floor above 0
    removed: tuple[str, ...]  # candidates under the floor, in ranking order

    def to_dict(self) -> dict[str, Any]:
        return {"applied": self.applied, "removed": list(self.removed)}


@dataclass(frozen=True)
class Decision:
    kind: DecisionKind
    proposed: str  # the policy's top-ranked action
    executed: str  # what runs; for an unresolved escalation, the proposed action
    fired_constraint: str | None  # constraint with the highest p on the proposed action
    p_proposed: float
    p_viol: dict[str, float]  # max p over constraints, per action
    fallback: str  # what the fallback path would execute
    fallback_kind: FallbackKind
    reason: EscalationReason | None = None  # set on escalations only
    all_blocked: bool = False  # the executed action came from the last resort


def violation_probability(p_for_action: dict[str, float]) -> tuple[float, str | None]:
    """Max over enabled constraints, and which constraint it was. No constraints means 0."""
    if not p_for_action:
        return 0.0, None
    constraint_id = max(p_for_action, key=lambda cid: p_for_action[cid])
    return p_for_action[constraint_id], constraint_id


def fallback_action(
    ranked: list[str], p: PGrid, thresholds: Thresholds, noop: frozenset[str] = frozenset()
) -> Fallback:
    """Safe, then least bad, then the SLOWER / IDLE last resort.

    Safe is the first lower-ranked action confidently below ``t_allow``. Least bad
    is the lower-ranked action with the lowest violation probability that is not
    a confident violation and is not a no-op; ties go to the policy's ranking.
    """
    lower = ranked[1:]
    p_of = {action: violation_probability(p.get(action, {}))[0] for action in lower}
    for action in lower:
        if p_of[action] < thresholds.t_allow:
            return Fallback(action, "safe")
    eligible = [a for a in lower if a not in noop and p_of[a] <= thresholds.t_block]
    if eligible:
        return Fallback(min(eligible, key=lambda a: p_of[a]), "least_bad")
    slower_p = violation_probability(p.get("SLOWER", {}))[0]
    preferred = "SLOWER" if slower_p <= thresholds.t_block else "IDLE"
    for action in (preferred, "SLOWER", "IDLE"):  # the floor may have removed either
        if action in ranked:
            return Fallback(action, "last_resort")
    p_all = {action: violation_probability(p.get(action, {}))[0] for action in ranked}
    return Fallback(min(ranked, key=lambda a: (p_all[a], ranked.index(a))), "last_resort")


def decide(
    ranked: list[str], p: PGrid, thresholds: Thresholds, noop: frozenset[str] = frozenset()
) -> Decision:
    top = ranked[0]
    p_viol = {action: violation_probability(p.get(action, {}))[0] for action in ranked}
    p_top, fired = violation_probability(p.get(top, {}))
    fb = fallback_action(ranked, p, thresholds, noop)
    if p_top < thresholds.t_allow:
        return Decision("allow", top, top, fired, p_top, p_viol, fb.action, fb.kind)
    if fb.kind != "safe":
        return Decision(
            "escalate", top, top, fired, p_top, p_viol, fb.action, fb.kind, "no_compliant_action"
        )
    if p_top > thresholds.t_block:
        return Decision("fallback", top, fb.action, fired, p_top, p_viol, fb.action, fb.kind)
    return Decision("escalate", top, top, fired, p_top, p_viol, fb.action, fb.kind, "uncertain")


def under_floor(candidates: Mapping[str, Any], floor_s: float) -> tuple[str, ...]:
    """Candidates whose time to collision ahead after the action is under ``floor_s``.

    Reads ``lane_after_action.time_to_collision_ahead_s`` from the facts; null means
    nothing ahead or not closing, so the candidate stays. A floor of 0 removes nothing.
    """
    if floor_s <= 0:
        return ()
    removed = []
    for action, facts in candidates.items():
        ttc = facts.get("lane_after_action", {}).get("time_to_collision_ahead_s")
        if ttc is not None and ttc < floor_s:
            removed.append(action)
    return tuple(removed)


def floor_decision(ranked: list[str], p: PGrid) -> Decision:
    """Every candidate is under the floor: SLOWER runs as the physical last resort."""
    top = ranked[0]
    p_viol = {action: violation_probability(p.get(action, {}))[0] for action in ranked}
    p_top, fired = violation_probability(p.get(top, {}))
    return Decision("fallback", top, "SLOWER", fired, p_top, p_viol, "SLOWER", "last_resort")


def resolve(decision: Decision, answer: Answer) -> Decision:
    """Apply the operator's answer to an escalation.

    Approve runs the proposed action, deny the fallback, override the named candidate.
    """
    if decision.kind != "escalate":
        raise ValueError(f"only escalations are resolved, got {decision.kind}")
    if answer.decision == "approve":
        return replace(decision, executed=decision.proposed)
    if answer.decision == "deny":
        return replace(
            decision,
            executed=decision.fallback,
            all_blocked=decision.fallback_kind == "last_resort",
        )
    if answer.action not in decision.p_viol:
        raise ValueError(f"override needs one of {list(decision.p_viol)}, got {answer.action!r}")
    return replace(decision, executed=answer.action)
