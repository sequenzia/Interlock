"""Ground-truth checkers. They score only and never feed the shield.

Each checker is closed-form on one candidate's facts (plan section 6), so every
candidate gets a label on every step. A rule with no checker labels None and is
excluded from calibration. Numbers in the rule text are parsed so a typed
variant such as "Speed limit 20 m/s" still gets a checker.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from backend.constraints import (
    CHECKER_HEADWAY,
    CHECKER_LANE_CHANGE_GAP,
    CHECKER_LANE_CHANGE_RATE,
    CHECKER_LANE_CLOSED,
    CHECKER_LEFT_LANE_PASSING,
    CHECKER_SPEED_LIMIT,
    Constraint,
)

LANE_CHANGE_ACTIONS = frozenset({"LANE_LEFT", "LANE_RIGHT"})
Facts = dict[str, Any]
Checker = Callable[[Facts, Constraint], bool]


def _number(text: str, pattern: str, default: float) -> float:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return float(match.group(1)) if match else default


def check_speed_limit(facts: Facts, constraint: Constraint) -> bool:
    limit = _number(constraint.text, r"speed limit\s+(\d+(?:\.\d+)?)", 25.0)
    return facts["action"]["target_speed_after_mps"] > limit


def check_lane_change_gap(facts: Facts, constraint: Constraint) -> bool:
    action = facts["action"]
    if action["name"] not in LANE_CHANGE_ACTIONS or action["lane_after"] == facts["ego"]["lane"]:
        return False  # at the road edge the action changes nothing
    threshold = _number(constraint.text, r"within\s+(\d+(?:\.\d+)?)\s*m\b", 10.0)
    lane = facts["lane_after_action"]
    gaps = [g for g in (lane["vehicle_behind_gap_m"], lane["vehicle_ahead_gap_m"]) if g is not None]
    return bool(gaps) and min(gaps) < threshold


def check_left_lane_passing(facts: Facts, constraint: Constraint) -> bool:
    """In the leftmost lane after the action with nobody slower to pass in the lane to the right."""
    if not facts["lane_after_action"]["is_leftmost"]:
        return False
    right = facts.get("lane_right_of_lane_after")
    return not (right and right["slower_vehicle_ahead_within_40_m"])


def check_lane_closed(facts: Facts, constraint: Constraint) -> bool:
    return any(zone["action_enters_zone"] for zone in facts["zones"])


def check_headway(facts: Facts, constraint: Constraint) -> bool:
    """Headway after the action below the seconds parsed from the text (default 2)."""
    minimum = _number(constraint.text, r"at least\s+(\d+(?:\.\d+)?)\s*s", 2.0)
    headway = facts["lane_after_action"].get("headway_s")
    return headway is not None and headway < minimum


def check_lane_change_rate(facts: Facts, constraint: Constraint) -> bool:
    """A real lane change when the recent count already reaches the allowed number (default 1)."""
    action = facts["action"]
    if action["name"] not in LANE_CHANGE_ACTIONS or action["lane_after"] == facts["ego"]["lane"]:
        return False
    allowed = _number(constraint.text, r"at most\s+(\d+)\s+lane change", 1.0)
    recent = facts.get("history", {}).get("lane_changes_last_10_steps", 0)
    return recent + 1 > allowed


CHECKERS: dict[str, Checker] = {
    CHECKER_SPEED_LIMIT: check_speed_limit,
    CHECKER_LANE_CHANGE_GAP: check_lane_change_gap,
    CHECKER_LEFT_LANE_PASSING: check_left_lane_passing,
    CHECKER_LANE_CLOSED: check_lane_closed,
    CHECKER_HEADWAY: check_headway,
    CHECKER_LANE_CHANGE_RATE: check_lane_change_rate,
}


def label(facts: Facts, constraint: Constraint) -> bool | None:
    checker = CHECKERS.get(constraint.checker or "")
    return None if checker is None else checker(facts, constraint)


def label_all(
    candidates: dict[str, Facts], constraints: list[Constraint]
) -> dict[str, dict[str, bool | None]]:
    """Ground truth per (action, constraint id)."""
    return {
        action: {c.id: label(facts, c) for c in constraints} for action, facts in candidates.items()
    }
