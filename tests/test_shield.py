import pytest
from backend.shield import Thresholds, decide, fallback_action, resolve, violation_probability

RANKED = ["FASTER", "LANE_LEFT", "IDLE", "SLOWER", "LANE_RIGHT"]
TH = Thresholds()


def grid(**p_by_action: float) -> dict[str, dict[str, float]]:
    """One constraint per action with the given p; missing actions get p 0."""
    return {a: {"c1": p_by_action.get(a, 0.0)} for a in RANKED}


def test_no_constraints_allows_the_top_action() -> None:
    d = decide(RANKED, {}, TH)
    assert (d.kind, d.executed, d.fired_constraint, d.p_proposed) == ("allow", "FASTER", None, 0.0)


def test_confident_safe_allows() -> None:
    d = decide(RANKED, grid(FASTER=0.19), TH)
    assert d.kind == "allow" and d.executed == "FASTER"


def test_confident_violation_falls_back_to_first_safe_lower_rank() -> None:
    d = decide(RANKED, grid(FASTER=0.95, LANE_LEFT=0.5, IDLE=0.05), TH)
    assert (d.kind, d.proposed, d.executed, d.fired_constraint) == (
        "fallback",
        "FASTER",
        "IDLE",
        "c1",
    )
    assert d.all_blocked is False


def test_fired_constraint_is_the_max_over_constraints() -> None:
    p = {"FASTER": {"c1": 0.3, "c2": 0.9}, "IDLE": {"c1": 0.0, "c2": 0.0}}
    d = decide(["FASTER", "IDLE"], p, TH)
    assert d.fired_constraint == "c2" and d.p_proposed == 0.9 and d.executed == "IDLE"


def test_all_blocked_prefers_slower_then_idle() -> None:
    d = decide(RANKED, grid(FASTER=0.9, LANE_LEFT=0.5, IDLE=0.5, SLOWER=0.5, LANE_RIGHT=0.5), TH)
    assert (d.kind, d.executed, d.all_blocked) == ("all_blocked", "SLOWER", True)
    d = decide(RANKED, grid(FASTER=0.9, LANE_LEFT=0.5, IDLE=0.5, SLOWER=0.85, LANE_RIGHT=0.5), TH)
    assert (d.kind, d.executed, d.all_blocked) == ("all_blocked", "IDLE", True)


@pytest.mark.parametrize("p_top", [0.2, 0.5, 0.8])
def test_uncertain_band_is_inclusive_and_escalates(p_top: float) -> None:
    d = decide(RANKED, grid(FASTER=p_top, LANE_LEFT=0.1), TH)
    assert d.kind == "escalate" and d.executed == "FASTER" and d.fallback == "LANE_LEFT"


def test_resolve_approve_and_deny() -> None:
    d = decide(RANKED, grid(FASTER=0.5, LANE_LEFT=0.1), TH)
    assert resolve(d, approved=True).executed == "FASTER"
    denied = resolve(d, approved=False)
    assert (
        denied.executed == "LANE_LEFT" and denied.all_blocked is False and denied.kind == "escalate"
    )


def test_resolve_deny_can_land_in_all_blocked() -> None:
    d = decide(RANKED, grid(FASTER=0.5, LANE_LEFT=0.5, IDLE=0.5, SLOWER=0.5, LANE_RIGHT=0.5), TH)
    denied = resolve(d, approved=False)
    assert denied.executed == "SLOWER" and denied.all_blocked is True


def test_resolve_rejects_non_escalations() -> None:
    with pytest.raises(ValueError):
        resolve(decide(RANKED, grid(), TH), approved=True)


def test_thresholds_validate() -> None:
    with pytest.raises(ValueError):
        Thresholds(0.9, 0.1)
    Thresholds(0.5, 0.5)


def test_helpers() -> None:
    assert violation_probability({}) == (0.0, None)
    assert violation_probability({"a": 0.2, "b": 0.7}) == (0.7, "b")
    assert fallback_action(RANKED, grid(FASTER=0.9), TH) == ("LANE_LEFT", False)
