from backend.spike.jev_spike import (
    FACT_SETS,
    RULES,
    STEP_CANDIDATES,
    build,
    lane_after,
    question,
    shape_a_state,
    target_after,
    to_sentences,
)

OPEN = {"behind": 45.0, "closing": 0.0, "ahead": 60.0, "ahead_speed": 26.0}
CLEAR = {"ahead": 60.0, "ahead_speed": 26.0}


def test_lane_after_clamps_to_road_edges() -> None:
    assert lane_after("LANE_LEFT", 1) == 1
    assert lane_after("LANE_LEFT", 3) == 2
    assert lane_after("LANE_RIGHT", 4) == 4
    assert lane_after("IDLE", 2) == 2


def test_target_after_follows_the_mdp_speed_grid() -> None:
    assert target_after("FASTER", 25.0) == 30.0
    assert target_after("FASTER", 30.0) == 30.0
    assert target_after("SLOWER", 20.0) == 20.0
    assert target_after("IDLE", 24.0) == 24.0  # off-grid probe speeds pass through


def test_build_matches_plan_schema() -> None:
    f = build("LANE_LEFT", lane=2, speed=29.6, target=30.0, after=OPEN, current=CLEAR)
    assert set(f) == {"ego", "action", "lane_after_action", "current_lane", "zones"}
    assert f["ego"] == {"lane": 2, "lane_count": 4, "speed_mps": 29.6, "target_speed_mps": 30.0}
    assert f["action"]["lane_after"] == 1
    assert f["lane_after_action"]["is_leftmost"] is True
    assert f["lane_after_action"]["slower_vehicle_ahead_within_40_m"] is False
    assert f["zones"] == []


def test_slower_vehicle_flag_needs_both_gap_and_speed() -> None:
    near_slow = build(
        "IDLE", lane=2, speed=25.0, after=OPEN, current={"ahead": 18.0, "ahead_speed": 20.0}
    )
    near_fast = build(
        "IDLE", lane=2, speed=25.0, after=OPEN, current={"ahead": 18.0, "ahead_speed": 26.0}
    )
    far_slow = build(
        "IDLE", lane=2, speed=25.0, after=OPEN, current={"ahead": 60.0, "ahead_speed": 20.0}
    )
    assert near_slow["current_lane"]["slower_vehicle_ahead_within_40_m"] is True
    assert near_fast["current_lane"]["slower_vehicle_ahead_within_40_m"] is False
    assert far_slow["current_lane"]["slower_vehicle_ahead_within_40_m"] is False


def test_every_fact_set_has_a_label_for_every_rule() -> None:
    for name, (facts, expected) in FACT_SETS.items():
        assert set(expected) == set(RULES), name
        assert facts["ego"]["lane_count"] == 4, name


def test_question_is_positive_with_rule_verbatim() -> None:
    q = question(RULES["gap"])
    assert RULES["gap"] in q.instructions
    assert q.criteria is not None
    assert "true" in q.criteria and "false" in q.criteria
    dumped = q.model_dump(by_alias=True, exclude_none=True)
    assert dumped["type"] == "noul"
    assert dumped["criteria"]["true"].startswith("The action, once executed")


def test_sentences_cover_every_fact_block() -> None:
    facts, _ = FACT_SETS["zone_enter"]
    text = "\n".join(to_sentences(facts))
    assert "Ego speed: 25.0 m/s" in text
    assert "Candidate action IDLE" in text
    assert "work zone" in text and "enters the zone: yes" in text
    no_zone = "\n".join(to_sentences(FACT_SETS["speed_violation"][0]))
    assert "Operator zones: none." in no_zone


def test_shape_a_state_names_every_candidate() -> None:
    state = shape_a_state()
    assert set(state["candidates"]) == set(STEP_CANDIDATES)
    assert "action_enters_zone" not in state["shared"]["zones"][0]
    assert state["candidates"]["LANE_RIGHT"]["action"]["enters_zone"] is True
