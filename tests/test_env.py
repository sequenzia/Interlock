from backend.env import ACTION_INDEX, ACTION_NAMES, make_env


def test_action_names_match_plan() -> None:
    assert ACTION_NAMES == ("LANE_LEFT", "IDLE", "LANE_RIGHT", "FASTER", "SLOWER")
    assert ACTION_INDEX["SLOWER"] == 4


def test_make_env_applies_demo_config() -> None:
    env = make_env()
    cfg = env.unwrapped.config
    assert cfg["lanes_count"] == 4
    assert cfg["duration"] == 60
    assert cfg["vehicles_count"] == 30
    assert cfg["policy_frequency"] == 1
    assert env.action_space.n == 5
    env.close()


def test_make_env_overrides_merge() -> None:
    env = make_env({"vehicles_count": 5})
    assert env.unwrapped.config["vehicles_count"] == 5
    assert env.unwrapped.config["lanes_count"] == 4
    env.close()


def test_seeded_reset_is_reproducible() -> None:
    a = make_env()
    b = make_env()
    obs_a, _ = a.reset(seed=7)
    obs_b, _ = b.reset(seed=7)
    assert (obs_a == obs_b).all()
    assert len(a.unwrapped.road.network.graph["0"]["1"]) == 4
    a.close()
    b.close()
