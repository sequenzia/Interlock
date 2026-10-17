from backend.constraints import Zone
from backend.env import ACTION_NAMES, make_env
from backend.facts import (
    action_meaning,
    facts_for_action,
    for_candidates,
    lane_after,
    lane_history,
    sentences,
    snapshot,
    target_speed_after,
)


def test_lane_after_clamps() -> None:
    assert lane_after("LANE_LEFT", 1, 4) == 1
    assert lane_after("LANE_RIGHT", 4, 4) == 4
    assert lane_after("LANE_RIGHT", 2, 4) == 3
    assert lane_after("FASTER", 2, 4) == 2


def test_facts_follow_the_plan_schema_from_live_state() -> None:
    env = make_env()
    env.reset(seed=0)
    ego = env.unwrapped.vehicle
    f = facts_for_action(env, "FASTER", zones=[])
    assert set(f) >= {"ego", "action", "lane_after_action", "current_lane", "zones"}
    assert f["ego"] == {"lane": 4, "lane_count": 4, "speed_mps": 25.0, "target_speed_mps": 25.0}
    assert f["action"] == {
        "name": "FASTER",
        "meaning": "raise the target speed by 5 m/s",
        "lane_after": 4,
        "target_speed_after_mps": 30.0,
    }
    assert f["lane_after_action"]["is_rightmost"] is True
    assert target_speed_after(ego, "SLOWER") == 20.0
    assert target_speed_after(ego, "IDLE") == 25.0
    assert "lane_right_of_lane_after" not in f
    assert f["history"] == {"lane_changes_last_10_steps": 0, "steps_in_current_lane": 0}
    assert f["traffic"]["vehicles_within_50_m"] >= 0
    with_history = facts_for_action(
        env,
        "FASTER",
        zones=[],
        history={"lane_changes_last_10_steps": 2, "steps_in_current_lane": 3},
    )
    assert with_history["history"] == {"lane_changes_last_10_steps": 2, "steps_in_current_lane": 3}
    env.close()


def test_headway_ttc_tailgating_and_density_follow_the_geometry() -> None:
    env = make_env()
    env.reset(seed=0)
    u = env.unwrapped
    ego = u.vehicle
    f = facts_for_action(env, "FASTER", zones=[])  # target 30 m/s after the action
    la = f["lane_after_action"]
    front, rear = u.road.neighbour_vehicles(ego, ego.lane_index)
    gap = la["vehicle_ahead_gap_m"]
    assert front is not None and gap is not None
    assert la["headway_s"] == round(gap / 30.0, 1)
    closing = 30.0 - float(front.speed)
    assert la["time_to_collision_ahead_s"] == (round(gap / closing, 1) if closing > 0 else None)
    behind = la["vehicle_behind_gap_m"]
    expected_tailgated = (
        rear is not None and behind is not None and behind < 10.0 and float(rear.speed) > ego.speed
    )
    assert la["being_tailgated"] is expected_tailgated
    x = float(ego.position[0])
    expected_density = sum(
        1 for v in u.road.vehicles if v is not ego and abs(float(v.position[0]) - x) <= 50.0
    )
    assert f["traffic"]["vehicles_within_50_m"] == expected_density
    env.close()


def test_lane_history_counts_changes_and_steps_in_lane() -> None:
    assert lane_history([], 2) == {"lane_changes_last_10_steps": 0, "steps_in_current_lane": 0}
    assert lane_history([2, 2, 2], 2) == {
        "lane_changes_last_10_steps": 0,
        "steps_in_current_lane": 3,
    }
    assert lane_history([1, 2, 2], 3) == {
        "lane_changes_last_10_steps": 2,
        "steps_in_current_lane": 0,
    }
    assert lane_history([3, 3, 2, 2], 2) == {
        "lane_changes_last_10_steps": 1,
        "steps_in_current_lane": 2,
    }
    old = [1, 2] + [2] * 10  # the change from 1 to 2 is older than ten transitions
    assert lane_history(old, 2)["lane_changes_last_10_steps"] == 0
    assert lane_history(old, 2)["steps_in_current_lane"] == 11


def test_gaps_match_the_simulator_geometry() -> None:
    env = make_env()
    env.reset(seed=0)
    u = env.unwrapped
    ego = u.vehicle
    f = facts_for_action(env, "LANE_LEFT", zones=[])
    front, rear = u.road.neighbour_vehicles(
        ego, (ego.lane_index[0], ego.lane_index[1], ego.lane_index[2] - 1)
    )
    expected_gap = round(float(front.position[0] - ego.position[0]) - ego.LENGTH, 1)
    assert f["action"]["lane_after"] == 3
    assert f["lane_after_action"]["vehicle_ahead_gap_m"] == expected_gap
    assert f["lane_after_action"]["vehicle_ahead_speed_mps"] == round(float(front.speed), 1)
    assert rear is None and f["lane_after_action"]["vehicle_behind_gap_m"] is None
    assert f["lane_after_action"]["vehicle_behind_closing_speed_mps"] is None
    env.close()


def test_leftmost_lane_after_adds_the_lane_to_the_right() -> None:
    env = make_env({"initial_lane_id": 1})
    env.reset(seed=0)
    f = facts_for_action(env, "LANE_LEFT", zones=[])
    assert f["ego"]["lane"] == 2 and f["action"]["lane_after"] == 1
    assert set(f["lane_right_of_lane_after"]) == {
        "vehicle_ahead_gap_m",
        "vehicle_ahead_speed_mps",
        "slower_vehicle_ahead_within_40_m",
    }
    assert f["lane_right_of_lane_after"] == f["current_lane"]
    env.close()


def test_zone_facts_are_relative_to_the_ego_and_flag_entry() -> None:
    env = make_env()
    env.reset(seed=0)
    ego = env.unwrapped.vehicle
    x = float(ego.position[0])
    zones = [
        Zone("work zone", lane=4, start_m=x + 10.0, end_m=x + 210.0),
        Zone("old zone", lane=4, start_m=x - 300.0, end_m=x - 100.0),
    ]
    stay = facts_for_action(env, "IDLE", zones)
    assert stay["zones"] == [
        {
            "name": "work zone",
            "lane": 4,
            "starts_in_m": 10.0,
            "ends_in_m": 210.0,
            "action_enters_zone": True,
        }
    ]
    leave = facts_for_action(env, "LANE_LEFT", zones)
    assert leave["zones"][0]["action_enters_zone"] is False
    far = facts_for_action(env, "IDLE", [Zone("work zone", 4, x + 100.0, x + 300.0)])
    assert far["zones"][0]["action_enters_zone"] is False
    env.close()


def test_candidates_and_snapshot_and_sentences() -> None:
    env = make_env()
    env.reset(seed=0)
    all_facts = for_candidates(env, list(ACTION_NAMES), zones=[])
    assert set(all_facts) == set(ACTION_NAMES)
    snap = snapshot(env)
    assert snap["ego"]["lane"] == 4 and len(snap["vehicles"]) == 30
    assert {"id", "lane", "x_m", "speed_mps"} == set(snap["vehicles"][0])
    text = "\n".join(sentences(all_facts["LANE_LEFT"]))
    assert "LANE_LEFT: move one lane to the left" in text
    assert "no vehicle within 200 m behind" in text
    assert (
        "Headway:" in text
        and "Time to collision ahead:" in text
        and "Tailgated within 10 m:" in text
    )
    assert "Traffic:" in text and "Lane changes in the last 10 steps: 0" in text
    assert "Operator zones: none." in text
    env.close()


def test_sentences_with_vehicles_on_both_sides() -> None:
    f = {
        "ego": {"lane": 2, "lane_count": 4, "speed_mps": 25.0, "target_speed_mps": 25.0},
        "action": {
            "name": "LANE_LEFT",
            "meaning": "move one lane to the left",
            "lane_after": 1,
            "target_speed_after_mps": 25.0,
        },
        "lane_after_action": {
            "is_leftmost": True,
            "is_rightmost": False,
            "vehicle_behind_gap_m": 8.0,
            "vehicle_behind_closing_speed_mps": 4.0,
            "vehicle_ahead_gap_m": 42.0,
            "vehicle_ahead_speed_mps": 24.0,
            "slower_vehicle_ahead_within_40_m": False,
        },
        "current_lane": {
            "vehicle_ahead_gap_m": 15.0,
            "vehicle_ahead_speed_mps": 22.0,
            "slower_vehicle_ahead_within_40_m": True,
        },
        "lane_right_of_lane_after": {
            "vehicle_ahead_gap_m": 15.0,
            "vehicle_ahead_speed_mps": 22.0,
            "slower_vehicle_ahead_within_40_m": True,
        },
        "zones": [
            {
                "name": "work zone",
                "lane": 3,
                "starts_in_m": 120.0,
                "ends_in_m": 320.0,
                "action_enters_zone": False,
            }
        ],
    }
    text = "\n".join(sentences(f))
    assert "nearest vehicle behind is 8 m away, closing at 4 m/s" in text
    assert "nearest vehicle ahead is 42 m away at 24 m/s" in text
    assert "Lane to the right of lane 1" in text
    assert "starts 120 m ahead and ends 320 m ahead. This action enters it: no" in text
    assert "Headway" not in text  # a facts object without the Oct 17 fields still renders


def test_edge_lane_changes_are_described_as_no_ops() -> None:
    assert action_meaning("LANE_RIGHT", 4, 4).startswith("keep lane 4, already the rightmost")
    assert action_meaning("LANE_LEFT", 1, 4).startswith("keep lane 1, already the leftmost")
    assert action_meaning("LANE_LEFT", 2, 4) == "move one lane to the left"
    env = make_env()
    env.reset(seed=0)  # ego starts in lane 4
    f = facts_for_action(env, "LANE_RIGHT", zones=[])
    assert f["action"]["lane_after"] == 4 and "changes nothing" in f["action"]["meaning"]
    env.close()


def test_noop_actions_are_edge_lane_changes_and_speed_changes_at_the_range_end() -> None:
    from backend.facts import noop_actions

    def cand(action: str, lane: int, lane_after: int, target: float, after: float) -> dict:
        return {
            "ego": {"lane": lane, "target_speed_mps": target},
            "action": {"name": action, "lane_after": lane_after, "target_speed_after_mps": after},
        }

    candidates = {
        "LANE_LEFT": cand("LANE_LEFT", 1, 1, 20.0, 20.0),
        "LANE_RIGHT": cand("LANE_RIGHT", 1, 2, 20.0, 20.0),
        "SLOWER": cand("SLOWER", 1, 1, 20.0, 20.0),
        "FASTER": cand("FASTER", 1, 1, 20.0, 25.0),
        "IDLE": cand("IDLE", 1, 1, 20.0, 20.0),
    }
    assert noop_actions(candidates) == frozenset({"LANE_LEFT", "SLOWER"})
