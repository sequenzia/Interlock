from typing import Any

from backend.checkers import label, label_all
from backend.constraints import (
    CHECKER_LANE_CHANGE_GAP,
    CHECKER_LANE_CLOSED,
    CHECKER_LEFT_LANE_PASSING,
    CHECKER_SPEED_LIMIT,
    PRESETS,
    Constraint,
)

SPEED = Constraint("c1", PRESETS[CHECKER_SPEED_LIMIT], checker=CHECKER_SPEED_LIMIT)
GAP = Constraint("c2", PRESETS[CHECKER_LANE_CHANGE_GAP], checker=CHECKER_LANE_CHANGE_GAP)
PASSING = Constraint("c3", PRESETS[CHECKER_LEFT_LANE_PASSING], checker=CHECKER_LEFT_LANE_PASSING)
CLOSED = Constraint("c4", PRESETS[CHECKER_LANE_CLOSED], checker=CHECKER_LANE_CLOSED)
FREE_TEXT = Constraint("c5", "Be courteous to trucks")


def facts(
    action: str = "IDLE",
    lane: int = 2,
    lane_after: int | None = None,
    target_after: float = 25.0,
    behind: float | None = 40.0,
    ahead: float | None = 60.0,
    right_slower: bool | None = None,
    enters_zone: bool | None = None,
) -> dict[str, Any]:
    lane_after = lane if lane_after is None else lane_after
    f: dict[str, Any] = {
        "ego": {"lane": lane, "lane_count": 4, "speed_mps": 25.0, "target_speed_mps": 25.0},
        "action": {
            "name": action,
            "lane_after": lane_after,
            "target_speed_after_mps": target_after,
        },
        "lane_after_action": {
            "is_leftmost": lane_after == 1,
            "is_rightmost": lane_after == 4,
            "vehicle_behind_gap_m": behind,
            "vehicle_ahead_gap_m": ahead,
        },
        "zones": [] if enters_zone is None else [{"lane": 3, "action_enters_zone": enters_zone}],
    }
    if right_slower is not None:
        f["lane_right_of_lane_after"] = {"slower_vehicle_ahead_within_40_m": right_slower}
    return f


def test_speed_limit_is_on_target_speed_after_action() -> None:
    assert label(facts("FASTER", target_after=30.0), SPEED) is True
    assert label(facts("IDLE", target_after=25.0), SPEED) is False
    assert label(facts("SLOWER", target_after=25.0), SPEED) is False
    lower = Constraint("c9", "Speed limit 20 m/s", checker=CHECKER_SPEED_LIMIT)
    assert label(facts("IDLE", target_after=25.0), lower) is True


def test_gap_rule_only_fires_on_real_lane_changes() -> None:
    assert label(facts("LANE_LEFT", lane=3, lane_after=2, behind=6.0), GAP) is True
    assert label(facts("LANE_LEFT", lane=3, lane_after=2, behind=40.0, ahead=9.9), GAP) is True
    assert label(facts("LANE_LEFT", lane=3, lane_after=2, behind=10.0, ahead=10.0), GAP) is False
    assert label(facts("IDLE", lane=3, behind=2.0), GAP) is False
    assert label(facts("LANE_LEFT", lane=1, lane_after=1, behind=2.0), GAP) is False  # at the edge
    assert label(facts("LANE_RIGHT", lane=3, lane_after=4, behind=None, ahead=None), GAP) is False


def test_passing_rule_needs_someone_slower_to_the_right() -> None:
    assert label(facts("IDLE", lane=1, right_slower=False), PASSING) is True
    assert label(facts("IDLE", lane=1, right_slower=True), PASSING) is False
    assert label(facts("LANE_LEFT", lane=2, lane_after=1, right_slower=True), PASSING) is False
    assert label(facts("LANE_LEFT", lane=2, lane_after=1, right_slower=False), PASSING) is True
    assert label(facts("IDLE", lane=2), PASSING) is False


def test_lane_closed_reads_the_zone_entry_fact() -> None:
    assert label(facts("IDLE", lane=3, enters_zone=True), CLOSED) is True
    assert label(facts("LANE_LEFT", lane=3, lane_after=2, enters_zone=False), CLOSED) is False
    assert label(facts("IDLE", lane=3), CLOSED) is False


def test_free_text_rule_has_no_label() -> None:
    assert label(facts(), FREE_TEXT) is None


def test_label_all_covers_every_pair() -> None:
    grid = label_all(
        {"FASTER": facts("FASTER", target_after=30.0), "IDLE": facts()}, [SPEED, FREE_TEXT]
    )
    assert grid == {"FASTER": {"c1": True, "c5": None}, "IDLE": {"c1": False, "c5": None}}
