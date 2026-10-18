import pytest
from backend.shield import (
    Answer,
    Fallback,
    Thresholds,
    decide,
    fallback_action,
    floor_decision,
    resolve,
    under_floor,
    violation_probability,
)

RANKED = ["FASTER", "LANE_LEFT", "IDLE", "SLOWER", "LANE_RIGHT"]
TH = Thresholds()


def grid(**p_by_action: float) -> dict[str, dict[str, float]]:
    """One constraint per action with the given p; missing actions get p 0."""
    return {a: {"c1": p_by_action.get(a, 0.0)} for a in RANKED}


def test_no_constraints_allows_the_top_action() -> None:
    d = decide(RANKED, {}, TH)
    assert (d.kind, d.executed, d.fired_constraint, d.p_proposed) == ("allow", "FASTER", None, 0.0)
    assert d.reason is None


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
    assert d.fallback_kind == "safe" and d.all_blocked is False and d.reason is None


def test_fired_constraint_is_the_max_over_constraints() -> None:
    p = {"FASTER": {"c1": 0.3, "c2": 0.9}, "IDLE": {"c1": 0.0, "c2": 0.0}}
    d = decide(["FASTER", "IDLE"], p, TH)
    assert d.fired_constraint == "c2" and d.p_proposed == 0.9 and d.executed == "IDLE"


def test_nothing_confidently_safe_escalates_as_no_compliant_action() -> None:
    d = decide(RANKED, grid(FASTER=0.9, LANE_LEFT=0.5, IDLE=0.3, SLOWER=0.5, LANE_RIGHT=0.5), TH)
    assert (d.kind, d.reason, d.executed) == ("escalate", "no_compliant_action", "FASTER")
    assert (d.fallback, d.fallback_kind, d.all_blocked) == ("IDLE", "least_bad", False)


def test_least_bad_skips_noops_and_confident_violations_and_ties_to_rank() -> None:
    p = grid(FASTER=0.9, LANE_LEFT=0.3, IDLE=0.5, SLOWER=0.5, LANE_RIGHT=0.85)
    assert fallback_action(RANKED, p, TH) == Fallback("LANE_LEFT", "least_bad")
    noop = frozenset({"LANE_LEFT"})
    assert fallback_action(RANKED, p, TH, noop) == Fallback("IDLE", "least_bad")


def test_last_resort_prefers_slower_then_idle() -> None:
    p = grid(FASTER=0.9, LANE_LEFT=0.85, IDLE=0.85, SLOWER=0.5, LANE_RIGHT=0.85)
    assert fallback_action(RANKED, p, TH) == Fallback("SLOWER", "least_bad")
    assert fallback_action(RANKED, p, TH, frozenset({"SLOWER"})) == Fallback(
        "SLOWER", "last_resort"
    )
    p = grid(FASTER=0.9, LANE_LEFT=0.85, IDLE=0.85, SLOWER=0.85, LANE_RIGHT=0.85)
    assert fallback_action(RANKED, p, TH) == Fallback("IDLE", "last_resort")
    d = decide(RANKED, p, TH)
    assert d.kind == "escalate" and d.reason == "no_compliant_action"
    assert d.fallback_kind == "last_resort" and d.all_blocked is False


@pytest.mark.parametrize("p_top", [TH.t_allow, 0.5, TH.t_block])
def test_uncertain_band_is_inclusive_and_escalates(p_top: float) -> None:
    d = decide(RANKED, grid(FASTER=p_top, LANE_LEFT=0.1), TH)
    assert (d.kind, d.reason, d.executed, d.fallback) == (
        "escalate",
        "uncertain",
        "FASTER",
        "LANE_LEFT",
    )


def test_resolve_approve_deny_and_override() -> None:
    d = decide(RANKED, grid(FASTER=0.5, LANE_LEFT=0.1), TH)
    assert resolve(d, Answer("approve")).executed == "FASTER"
    denied = resolve(d, Answer("deny"))
    assert (
        denied.executed == "LANE_LEFT" and denied.all_blocked is False and denied.kind == "escalate"
    )
    assert resolve(d, Answer("override", "SLOWER")).executed == "SLOWER"
    with pytest.raises(ValueError):
        resolve(d, Answer("override", "BRAKE"))
    with pytest.raises(ValueError):
        resolve(d, Answer("override"))


def test_resolve_deny_can_land_in_all_blocked() -> None:
    p = grid(FASTER=0.5, LANE_LEFT=0.85, IDLE=0.85, SLOWER=0.5, LANE_RIGHT=0.85)
    d = decide(RANKED, p, TH, frozenset({"SLOWER"}))
    denied = resolve(d, Answer("deny"))
    assert denied.executed == "SLOWER" and denied.all_blocked is True


def test_resolve_rejects_non_escalations() -> None:
    with pytest.raises(ValueError):
        resolve(decide(RANKED, grid(), TH), Answer("approve"))


def test_thresholds_validate() -> None:
    with pytest.raises(ValueError):
        Thresholds(0.9, 0.1)
    Thresholds(0.5, 0.5)


def test_helpers() -> None:
    assert violation_probability({}) == (0.0, None)
    assert violation_probability({"a": 0.2, "b": 0.7}) == (0.7, "b")
    assert fallback_action(RANKED, grid(FASTER=0.9), TH) == Fallback("LANE_LEFT", "safe")


def ttc(**by_action: float | None) -> dict[str, dict]:
    """Facts stubs carrying only the time to collision the floor reads."""
    return {
        a: {"lane_after_action": {"time_to_collision_ahead_s": v}} for a, v in by_action.items()
    }


def test_under_floor_removes_closing_candidates_and_keeps_null_and_far_ones() -> None:
    facts = ttc(FASTER=0.6, LANE_LEFT=None, IDLE=1.0, SLOWER=4.2, LANE_RIGHT=0.99)
    assert under_floor(facts, 1.0) == ("FASTER", "LANE_RIGHT")  # strictly under, ranking order
    assert under_floor(facts, 0.0) == ()
    assert under_floor({"IDLE": {"lane_after_action": {}}}, 1.0) == ()


def test_last_resort_respects_the_executable_set() -> None:
    # SLOWER floored: the last resort falls through to IDLE
    fb = fallback_action(
        ["FASTER", "IDLE"], grid(FASTER=0.9, IDLE=0.9), TH, noop=frozenset({"IDLE"})
    )
    assert fb == Fallback("IDLE", "last_resort")
    # both floored: the executable action with the lowest p, ties to rank
    fb = fallback_action(["FASTER", "LANE_LEFT"], grid(FASTER=0.9, LANE_LEFT=0.9), TH)
    assert fb == Fallback("FASTER", "last_resort")
    fb = fallback_action(["FASTER", "LANE_LEFT"], grid(FASTER=0.9, LANE_LEFT=0.85), TH)
    assert fb == Fallback("LANE_LEFT", "last_resort")
    # nothing floored: unchanged behaviour, SLOWER unless it is itself a confident violation
    everything = grid(FASTER=0.9, LANE_LEFT=0.9, IDLE=0.9, SLOWER=0.9, LANE_RIGHT=0.9)
    assert fallback_action(RANKED, everything, TH) == Fallback("IDLE", "last_resort")
    slower_ok = {**everything, "SLOWER": {"c1": 0.6}}  # a no-op SLOWER is not least bad
    assert fallback_action(RANKED, slower_ok, TH, noop=frozenset({"SLOWER"})) == Fallback(
        "SLOWER", "last_resort"
    )


def test_decide_on_the_executable_set_never_names_a_floored_action() -> None:
    executable = ["LANE_LEFT", "IDLE"]  # FASTER, SLOWER and LANE_RIGHT are under the floor
    d = decide(executable, grid(FASTER=0.0, LANE_LEFT=0.95, IDLE=0.05), TH)
    assert (d.kind, d.proposed, d.executed, d.fallback) == ("fallback", "LANE_LEFT", "IDLE", "IDLE")
    assert set(d.p_viol) == set(executable)
    with pytest.raises(ValueError):
        resolve(
            decide(executable, grid(LANE_LEFT=0.5, IDLE=0.05), TH), Answer("override", "FASTER")
        )


def test_floor_decision_runs_slower_as_a_fallback() -> None:
    d = floor_decision(RANKED, grid(FASTER=0.9, SLOWER=0.95))
    assert (d.kind, d.proposed, d.executed, d.fired_constraint) == (
        "fallback",
        "FASTER",
        "SLOWER",
        "c1",
    )
    assert (d.fallback, d.fallback_kind, d.all_blocked, d.reason) == (
        "SLOWER",
        "last_resort",
        False,
        None,
    )
