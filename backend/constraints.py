"""Operator constraints: plain-English rules plus work-zone geometry.

Rule text is what Jev reads, verbatim. The optional checker id maps a rule to a
ground-truth checker in backend/checkers.py, which scores only and never feeds
the shield. Plan sections 5.6 and 6.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any

CHECKER_SPEED_LIMIT = "speed_limit"
CHECKER_LANE_CHANGE_GAP = "lane_change_gap"
CHECKER_LEFT_LANE_PASSING = "left_lane_passing"
CHECKER_LANE_CLOSED = "lane_closed"
CHECKER_HEADWAY = "headway"
CHECKER_LANE_CHANGE_RATE = "lane_change_rate"
PRESET_CUT_IN = "cut_in"
PRESET_DENSE_TRAFFIC = "dense_traffic"

# Preset id to the rule text as the operator types it. Order matters for the UI chips.
# The first six ids are also checker ids. The last two are fuzzy rules with no checker:
# Jev alone enforces them and hand labels score them (plan section 16.2).
PRESETS: dict[str, str] = {
    CHECKER_SPEED_LIMIT: "Speed limit 25 m/s",
    CHECKER_LANE_CHANGE_GAP: "No lane change if a vehicle is within 10 m in the target lane",
    CHECKER_LEFT_LANE_PASSING: "Keep the left lane for passing only",
    CHECKER_LANE_CLOSED: "Lane 3 is closed ahead for a work zone",
    CHECKER_HEADWAY: "Keep at least 2 seconds of headway to the vehicle ahead",
    CHECKER_LANE_CHANGE_RATE: "At most 1 lane change in any 10 seconds",
    PRESET_CUT_IN: "Leave plenty of room when moving in ahead of a faster vehicle",
    PRESET_DENSE_TRAFFIC: "Drive conservatively in dense traffic",
}
FUZZY_PRESETS = frozenset({PRESET_CUT_IN, PRESET_DENSE_TRAFFIC})


def preset_checker(preset_id: str) -> str | None:
    """The checker a preset carries: its own id, or None for a fuzzy preset."""
    return None if preset_id in FUZZY_PRESETS else preset_id


DEFAULT_ZONE_LANE = 3
DEFAULT_ZONE_AHEAD_M = 120.0
DEFAULT_ZONE_LENGTH_M = 200.0
DEFAULT_ZONE_NAME = "work zone"


@dataclass
class Constraint:
    id: str
    text: str
    enabled: bool = True
    checker: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Zone:
    """A closed stretch of one lane, in absolute road coordinates."""

    name: str
    lane: int  # 1-based, numbered from the left
    start_m: float
    end_m: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def infer_checker(text: str) -> str | None:
    """Pick a ground-truth checker for typed rule text, or None for a free-text rule."""
    normalized = " ".join(text.lower().split())
    for preset_id, preset in PRESETS.items():
        if normalized == preset.lower():
            return preset_checker(preset_id)
    if re.search(r"speed limit \d", normalized):
        return CHECKER_SPEED_LIMIT
    if "lane change" in normalized and re.search(r"within \d+(\.\d+)? ?m\b", normalized):
        return CHECKER_LANE_CHANGE_GAP
    if "passing only" in normalized:
        return CHECKER_LEFT_LANE_PASSING
    if re.search(r"lane \d is closed", normalized):
        return CHECKER_LANE_CLOSED
    if re.search(r"at least \d+(\.\d+)? ?s(ec(ond)?s?)? of headway", normalized):
        return CHECKER_HEADWAY
    if re.search(r"at most \d+ lane changes?", normalized):
        return CHECKER_LANE_CHANGE_RATE
    return None


class ConstraintStore:
    """Mutable set of rules and zones for one session. Ids are stable for the session."""

    def __init__(self) -> None:
        self._constraints: list[Constraint] = []
        self._zones: list[Zone] = []
        self._next_id = 1

    @property
    def constraints(self) -> list[Constraint]:
        return list(self._constraints)

    @property
    def zones(self) -> list[Zone]:
        return list(self._zones)

    def enabled(self) -> list[Constraint]:
        return [c for c in self._constraints if c.enabled]

    def add(self, text: str, checker: str | None = None) -> Constraint:
        text = " ".join(text.split())
        if not text:
            raise ValueError("rule text is empty")
        constraint = Constraint(
            id=f"c{self._next_id}",
            text=text,
            checker=infer_checker(text) if checker is None else checker,
        )
        self._next_id += 1
        self._constraints.append(constraint)
        return constraint

    def add_presets(self, preset_ids: Iterable[str] | None = None) -> list[Constraint]:
        ids = list(PRESETS) if preset_ids is None else list(preset_ids)
        return [self.add(PRESETS[pid], checker=preset_checker(pid)) for pid in ids]

    def get(self, constraint_id: str) -> Constraint:
        for c in self._constraints:
            if c.id == constraint_id:
                return c
        raise KeyError(constraint_id)

    def toggle(self, constraint_id: str, enabled: bool) -> Constraint:
        constraint = self.get(constraint_id)
        constraint.enabled = enabled
        return constraint

    def remove(self, constraint_id: str) -> None:
        constraint = self.get(constraint_id)
        self._constraints.remove(constraint)

    def drop_zone(
        self,
        ego_x_m: float,
        lane: int = DEFAULT_ZONE_LANE,
        ahead_m: float = DEFAULT_ZONE_AHEAD_M,
        length_m: float = DEFAULT_ZONE_LENGTH_M,
        name: str = DEFAULT_ZONE_NAME,
    ) -> Zone:
        """Place a zone ``ahead_m`` in front of the ego and put its rule in force.

        The zone and the lane-closed rule share a lifecycle: dropping a zone adds
        the rule (or re-enables it) and passing the last zone disables it again.
        Jev weights a rule that asserts a closure even when no zone is in the
        facts (spike results, Oct 16), so a stale rule would keep biasing lane 3.
        """
        start_m = ego_x_m + ahead_m
        zone = Zone(name=name, lane=lane, start_m=start_m, end_m=start_m + length_m)
        self._zones.append(zone)
        rule = self.zone_rule()
        if rule is None:
            self.add(f"Lane {lane} is closed ahead for a {name}", checker=CHECKER_LANE_CLOSED)
        else:
            rule.enabled = True
        return zone

    def zone_rule(self) -> Constraint | None:
        return next((c for c in self._constraints if c.checker == CHECKER_LANE_CLOSED), None)

    def retire_passed_zones(self, ego_x_m: float) -> list[Zone]:
        """Drop zones the ego has passed; disable the lane-closed rule once none remain."""
        passed = [z for z in self._zones if z.end_m < ego_x_m]
        if not passed:
            return []
        self._zones = [z for z in self._zones if z.end_m >= ego_x_m]
        rule = self.zone_rule()
        if not self._zones and rule is not None:
            rule.enabled = False
        return passed

    def clear_zones(self) -> None:
        self._zones.clear()
        rule = self.zone_rule()
        if rule is not None:
            rule.enabled = False

    def snapshot(self) -> dict[str, list[dict[str, Any]]]:
        return {
            "constraints": [c.to_dict() for c in self._constraints],
            "zones": [z.to_dict() for z in self._zones],
        }
