import numpy as np
import pytest
from backend.env import ACTION_NAMES, make_env
from backend.policy import Policy
from backend.train import build_model


@pytest.fixture(scope="module")
def policy() -> Policy:
    # An untrained DQN is enough: Q-values are arbitrary but deterministic.
    env = make_env()
    model = build_model(env, seed=0)
    yield Policy(model)
    env.close()


def test_ranking_covers_every_action_once_in_q_order(policy: Policy) -> None:
    env = make_env()
    obs, _ = env.reset(seed=3)
    ranked = policy.ranked_actions(obs)
    assert [r.name for r in sorted(ranked, key=lambda r: r.index)] == list(ACTION_NAMES)
    assert [r.rank for r in ranked] == [0, 1, 2, 3, 4]
    qs = [r.q for r in ranked]
    assert qs == sorted(qs, reverse=True)
    env.close()


def test_top_ranked_matches_sb3_greedy_prediction(policy: Policy) -> None:
    env = make_env()
    obs, _ = env.reset(seed=5)
    for _ in range(5):
        action, _ = policy.model.predict(obs, deterministic=True)
        assert policy.ranked_actions(obs)[0].index == int(action)
        obs, _, terminated, truncated, _ = env.step(int(action))
        if terminated or truncated:
            break
    env.close()


def test_q_values_are_finite_floats(policy: Policy) -> None:
    env = make_env()
    obs, _ = env.reset(seed=1)
    q = policy.q_values(obs)
    assert q.shape == (5,)
    assert np.isfinite(q).all()
    env.close()


def test_default_checkpoint_loads_and_ranks_when_present() -> None:
    from backend.paths import DEFAULT_MODEL_PATH

    if not DEFAULT_MODEL_PATH.exists():
        pytest.skip("no promoted checkpoint in models/")
    trained = Policy.load()
    env = make_env()
    obs, _ = env.reset(seed=0)
    ranked = trained.ranked_actions(obs)
    assert len(ranked) == 5
    assert ranked[0].q >= ranked[-1].q
    env.close()
