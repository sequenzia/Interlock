import pytest
from backend.constraints import (
    CHECKER_LANE_CHANGE_GAP,
    CHECKER_LANE_CLOSED,
    CHECKER_LEFT_LANE_PASSING,
    CHECKER_SPEED_LIMIT,
    PRESETS,
    ConstraintStore,
    infer_checker,
)


def test_presets_infer_their_checker() -> None:
    for checker_id, text in PRESETS.items():
        assert infer_checker(text) == checker_id


def test_typed_variants_still_get_a_checker() -> None:
    assert infer_checker("speed limit 20 m/s") == CHECKER_SPEED_LIMIT
    assert (
        infer_checker("No lane change if a vehicle is within 15 m in the target lane")
        == CHECKER_LANE_CHANGE_GAP
    )
    assert infer_checker("Left lane is for passing only") == CHECKER_LEFT_LANE_PASSING
    assert infer_checker("Lane 2 is closed for roadworks") == CHECKER_LANE_CLOSED
    assert infer_checker("Be courteous to trucks") is None


def test_store_ids_toggle_remove_and_enabled() -> None:
    store = ConstraintStore()
    a = store.add("Speed limit 25 m/s")
    b = store.add("Be courteous to trucks")
    assert (a.id, b.id) == ("c1", "c2")
    assert a.checker == CHECKER_SPEED_LIMIT and b.checker is None
    store.toggle("c1", False)
    assert [c.id for c in store.enabled()] == ["c2"]
    store.remove("c2")
    assert [c.id for c in store.constraints] == ["c1"]
    assert store.add("x").id == "c3"  # ids never reused
    with pytest.raises(KeyError):
        store.get("c2")


def test_add_rejects_empty_text() -> None:
    with pytest.raises(ValueError):
        ConstraintStore().add("   ")


def test_drop_zone_uses_absolute_coordinates_and_arms_the_rule() -> None:
    store = ConstraintStore()
    zone = store.drop_zone(ego_x_m=500.0)
    assert (zone.lane, zone.start_m, zone.end_m) == (3, 620.0, 820.0)
    assert store.snapshot()["zones"] == [zone.to_dict()]
    rule = store.zone_rule()
    assert (
        rule is not None and rule.enabled and rule.text == "Lane 3 is closed ahead for a work zone"
    )
    assert rule.checker == CHECKER_LANE_CLOSED
    store.clear_zones()
    assert store.zones == [] and rule.enabled is False


def test_passing_the_last_zone_retires_the_rule() -> None:
    store = ConstraintStore()
    store.add_presets()
    rule = store.zone_rule()
    assert rule is not None
    first = store.drop_zone(ego_x_m=0.0, ahead_m=10.0, length_m=20.0)  # 10 to 30
    second = store.drop_zone(ego_x_m=0.0, ahead_m=100.0, length_m=20.0)  # 100 to 120
    assert len(store.constraints) == 4  # the existing preset rule is reused, not duplicated
    assert store.retire_passed_zones(5.0) == []
    assert store.retire_passed_zones(31.0) == [first] and rule.enabled
    assert store.retire_passed_zones(121.0) == [second] and rule.enabled is False
    assert store.zones == []
    store.drop_zone(ego_x_m=200.0)
    assert rule.enabled is True


def test_add_presets_in_order() -> None:
    store = ConstraintStore()
    added = store.add_presets()
    assert [c.checker for c in added] == list(PRESETS)
    assert [c.text for c in added] == list(PRESETS.values())
