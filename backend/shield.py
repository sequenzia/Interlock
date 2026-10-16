"""Allow, fallback or escalate. Plan section 5.2.

Pure functions of the ranked actions and the p grid from the judge. No
simulator and no Jev here, so every branch is unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

DecisionKind = Literal["allow", "fallback", "escalate", "all_blocked"]
PGrid = dict[str, dict[str, float]]  # action -> constraint id -> p(violation)


@dataclass(frozen=True)
class Thresholds:
    t_allow: float = 0.2
    t_block: float = 0.8

    def __post_init__(self) -> None:
        if not 0.0 <= self.t_allow <= self.t_block <= 1.0:
            raise ValueError(
                f"need 0 <= t_allow <= t_block <= 1, got {self.t_allow}, {self.t_block}"
            )


@dataclass(frozen=True)
class Decision:
    kind: DecisionKind
    proposed: str  # the policy's top-ranked action
    executed: str  # what runs; for an unresolved escalation, the proposed action
    fired_constraint: str | None  # constraint with the highest p on the proposed action
    p_proposed: float
    p_viol: dict[str, float]  # max p over constraints, per action
    fallback: str  # what the fallback path would execute
    fallback_all_blocked: bool  # the fallback came from the SLOWER / IDLE last resort
    all_blocked: bool = False  # the executed action came from that last resort


def violation_probability(p_for_action: dict[str, float]) -> tuple[float, str | None]:
    """Max over enabled constraints, and which constraint it was. No constraints means 0."""
    if not p_for_action:
        return 0.0, None
    constraint_id = max(p_for_action, key=lambda cid: p_for_action[cid])
    return p_for_action[constraint_id], constraint_id


def fallback_action(ranked: list[str], p: PGrid, thresholds: Thresholds) -> tuple[str, bool]:
    """First lower-ranked action that is confidently safe, else SLOWER or IDLE flagged all-blocked."""
    for action in ranked[1:]:
        if violation_probability(p.get(action, {}))[0] < thresholds.t_allow:
            return action, False
    slower_p = violation_probability(p.get("SLOWER", {}))[0]
    return ("SLOWER" if slower_p <= thresholds.t_block else "IDLE"), True


def decide(ranked: list[str], p: PGrid, thresholds: Thresholds) -> Decision:
    top = ranked[0]
    p_viol = {action: violation_probability(p.get(action, {}))[0] for action in ranked}
    p_top, fired = violation_probability(p.get(top, {}))
    fallback, fallback_blocked = fallback_action(ranked, p, thresholds)
    if p_top < thresholds.t_allow:
        return Decision("allow", top, top, fired, p_top, p_viol, fallback, fallback_blocked)
    if p_top > thresholds.t_block:
        kind: DecisionKind = "all_blocked" if fallback_blocked else "fallback"
        return Decision(
            kind, top, fallback, fired, p_top, p_viol, fallback, fallback_blocked, fallback_blocked
        )
    return Decision("escalate", top, top, fired, p_top, p_viol, fallback, fallback_blocked)


def resolve(decision: Decision, approved: bool) -> Decision:
    """Apply the operator's answer to an escalation. Approve runs the proposed action, deny the fallback."""
    if decision.kind != "escalate":
        raise ValueError(f"only escalations are resolved, got {decision.kind}")
    if approved:
        return replace(decision, executed=decision.proposed)
    return replace(decision, executed=decision.fallback, all_blocked=decision.fallback_all_blocked)
