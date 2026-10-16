"""Turn simulator state plus one candidate action into facts Jev can judge.

All geometry happens here, in code. Jev receives precomputed JSON with units in
the field names (plan section 5.4); the UI receives the same facts rendered as
sentences. Facts come from the simulator's vehicle objects, never from the
normalized observation the policy sees. Lanes are numbered from the left
starting at 1.
"""

from __future__ import annotations

from typing import Any

from backend.constraints import Zone

ACTION_MEANING: dict[str, str] = {
    "LANE_LEFT": "move one lane to the left",
    "IDLE": "keep the current lane and target speed",
    "LANE_RIGHT": "move one lane to the right",
    "FASTER": "raise the target speed by 5 m/s",
    "SLOWER": "lower the target speed by 5 m/s",
}

NEIGHBOUR_RANGE_M = 200.0  # vehicles farther away are reported as absent
SLOWER_AHEAD_RANGE_M = 40.0
STEP_SECONDS = 1.0  # policy_frequency 1

Facts = dict[str, Any]


def _r(value: float) -> float:
    return round(float(value), 1)


def lane_number(lane_index: tuple[str, str, int]) -> int:
    return int(lane_index[2]) + 1


def _lane_tuple(ego: Any, lane: int) -> tuple[str, str, int]:
    return (ego.lane_index[0], ego.lane_index[1], lane - 1)


def lane_after(action: str, lane: int, lane_count: int) -> int:
    if action == "LANE_LEFT":
        return max(1, lane - 1)
    if action == "LANE_RIGHT":
        return min(lane_count, lane + 1)
    return lane


def target_speed_after(ego: Any, action: str) -> float:
    index = int(ego.speed_index)
    if action == "FASTER":
        index += 1
    elif action == "SLOWER":
        index -= 1
    index = max(0, min(len(ego.target_speeds) - 1, index))
    return float(ego.target_speeds[index])


def _gaps(road: Any, ego: Any, lane: int) -> tuple[Any, float | None, Any, float | None]:
    """Nearest vehicle ahead and behind in ``lane`` with bumper-to-bumper gaps."""
    front, rear = road.neighbour_vehicles(ego, _lane_tuple(ego, lane))
    ahead_gap = behind_gap = None
    if front is not None:
        ahead_gap = max(0.0, float(front.position[0] - ego.position[0]) - ego.LENGTH)
        if ahead_gap > NEIGHBOUR_RANGE_M:
            front, ahead_gap = None, None
    if rear is not None:
        behind_gap = max(0.0, float(ego.position[0] - rear.position[0]) - ego.LENGTH)
        if behind_gap > NEIGHBOUR_RANGE_M:
            rear, behind_gap = None, None
    return front, ahead_gap, rear, behind_gap


def _slower_ahead(ego: Any, front: Any, ahead_gap: float | None) -> bool:
    return (
        front is not None
        and ahead_gap is not None
        and ahead_gap <= SLOWER_AHEAD_RANGE_M
        and front.speed < ego.speed
    )


def _ahead_block(road: Any, ego: Any, lane: int) -> Facts:
    front, ahead_gap, _, _ = _gaps(road, ego, lane)
    return {
        "vehicle_ahead_gap_m": None if ahead_gap is None else _r(ahead_gap),
        "vehicle_ahead_speed_mps": None if front is None else _r(front.speed),
        "slower_vehicle_ahead_within_40_m": _slower_ahead(ego, front, ahead_gap),
    }


def _lane_block(road: Any, ego: Any, lane: int, lane_count: int) -> Facts:
    front, ahead_gap, rear, behind_gap = _gaps(road, ego, lane)
    return {
        "is_leftmost": lane == 1,
        "is_rightmost": lane == lane_count,
        "vehicle_behind_gap_m": None if behind_gap is None else _r(behind_gap),
        "vehicle_behind_closing_speed_mps": None if rear is None else _r(rear.speed - ego.speed),
        "vehicle_ahead_gap_m": None if ahead_gap is None else _r(ahead_gap),
        "vehicle_ahead_speed_mps": None if front is None else _r(front.speed),
        "slower_vehicle_ahead_within_40_m": _slower_ahead(ego, front, ahead_gap),
    }


def _zone_facts(ego: Any, zones: list[Zone], new_lane: int) -> list[Facts]:
    x = float(ego.position[0])
    x_after = x + float(ego.speed) * STEP_SECONDS
    out = []
    for zone in zones:
        if zone.end_m < x:
            continue  # already passed, irrelevant to the decision
        out.append(
            {
                "name": zone.name,
                "lane": zone.lane,
                "starts_in_m": _r(max(0.0, zone.start_m - x)),
                "ends_in_m": _r(zone.end_m - x),
                "action_enters_zone": new_lane == zone.lane
                and zone.start_m <= x_after <= zone.end_m,
            }
        )
    return out


def facts_for_action(env: Any, action: str, zones: list[Zone]) -> Facts:
    """Facts for one candidate action from the live simulator state."""
    u = env.unwrapped
    ego, road = u.vehicle, u.road
    lane_count = int(u.config["lanes_count"])
    lane = lane_number(ego.lane_index)
    new_lane = lane_after(action, lane, lane_count)
    facts: Facts = {
        "ego": {
            "lane": lane,
            "lane_count": lane_count,
            "speed_mps": _r(ego.speed),
            "target_speed_mps": _r(ego.target_speed),
        },
        "action": {
            "name": action,
            "meaning": ACTION_MEANING[action],
            "lane_after": new_lane,
            "target_speed_after_mps": target_speed_after(ego, action),
        },
        "lane_after_action": _lane_block(road, ego, new_lane, lane_count),
        "current_lane": _ahead_block(road, ego, lane),
        "zones": _zone_facts(ego, zones, new_lane),
    }
    if new_lane == 1 and lane_count > 1:
        facts["lane_right_of_lane_after"] = _ahead_block(road, ego, 2)
    return facts


def for_candidates(env: Any, actions: list[str], zones: list[Zone]) -> dict[str, Facts]:
    return {action: facts_for_action(env, action, zones) for action in actions}


def snapshot(env: Any) -> dict[str, Any]:
    """Render snapshot for the log record: ego plus every other vehicle."""
    u = env.unwrapped
    ego = u.vehicle
    return {
        "ego": {
            "lane": lane_number(ego.lane_index),
            "speed_mps": _r(ego.speed),
            "x_m": _r(ego.position[0]),
        },
        "vehicles": [
            {
                "id": i,
                "lane": lane_number(v.lane_index),
                "x_m": _r(v.position[0]),
                "speed_mps": _r(v.speed),
            }
            for i, v in enumerate(u.road.vehicles)
            if v is not ego
        ],
    }


def _gap_phrase(gap: float | None, speed: float | None, direction: str) -> str:
    if gap is None:
        return f"no vehicle within {NEIGHBOUR_RANGE_M:g} m {direction}"
    phrase = f"nearest vehicle {direction} is {gap:g} m away"
    return phrase if speed is None else f"{phrase} at {speed:g} m/s"


def sentences(f: Facts) -> list[str]:
    """Plain sentences for the operator UI, generated from the same facts Jev sees."""
    ego, act, la, cur = f["ego"], f["action"], f["lane_after_action"], f["current_lane"]
    yes_no = {True: "yes", False: "no"}
    lines = [
        f"Ego speed {ego['speed_mps']:g} m/s, target {ego['target_speed_mps']:g} m/s, "
        f"lane {ego['lane']} of {ego['lane_count']} (numbered from the left).",
        f"{act['name']}: {act['meaning']}. Lane after: {act['lane_after']}. "
        f"Target speed after: {act['target_speed_after_mps']:g} m/s.",
        f"Lane {act['lane_after']} after the action: "
        f"{_gap_phrase(la['vehicle_behind_gap_m'], None, 'behind')}"
        + (
            f", closing at {la['vehicle_behind_closing_speed_mps']:g} m/s"
            if la["vehicle_behind_closing_speed_mps"] is not None
            else ""
        )
        + f"; {_gap_phrase(la['vehicle_ahead_gap_m'], la['vehicle_ahead_speed_mps'], 'ahead')}. "
        f"Slower vehicle ahead within 40 m: {yes_no[la['slower_vehicle_ahead_within_40_m']]}.",
        f"Current lane {ego['lane']}: {_gap_phrase(cur['vehicle_ahead_gap_m'], cur['vehicle_ahead_speed_mps'], 'ahead')}. "
        f"Slower vehicle ahead within 40 m: {yes_no[cur['slower_vehicle_ahead_within_40_m']]}.",
    ]
    if "lane_right_of_lane_after" in f:
        right = f["lane_right_of_lane_after"]
        lines.append(
            f"Lane to the right of lane {act['lane_after']}: "
            f"{_gap_phrase(right['vehicle_ahead_gap_m'], right['vehicle_ahead_speed_mps'], 'ahead')}. "
            f"Slower vehicle ahead within 40 m: {yes_no[right['slower_vehicle_ahead_within_40_m']]}."
        )
    for z in f["zones"]:
        lines.append(
            f"Zone '{z['name']}' in lane {z['lane']} starts {z['starts_in_m']:g} m ahead and ends "
            f"{z['ends_in_m']:g} m ahead. This action enters it: {yes_no[z['action_enters_zone']]}."
        )
    if not f["zones"]:
        lines.append("Operator zones: none.")
    return lines
