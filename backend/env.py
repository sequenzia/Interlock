"""Environment factory: highway-fast-v0 with the demo configuration.

The reward is left at the highway-env default (collision -1, high speed 0.4
over 20 to 30 m/s, right lane 0.1), so the policy never sees an operator rule.
See internal/build-plan.md section 12.
"""

from __future__ import annotations

from typing import Any

import gymnasium as gym
import highway_env  # noqa: F401  (registers the highway-* environments)
from highway_env.envs.common.action import DiscreteMetaAction

ENV_ID = "highway-fast-v0"

# Index to name, straight from highway-env so the two can never drift apart.
ACTION_NAMES: tuple[str, ...] = tuple(
    DiscreteMetaAction.ACTIONS_ALL[i] for i in sorted(DiscreteMetaAction.ACTIONS_ALL)
)
ACTION_INDEX: dict[str, int] = {name: i for i, name in enumerate(ACTION_NAMES)}

DEFAULT_CONFIG: dict[str, Any] = {
    "lanes_count": 4,
    "duration": 60,
    "vehicles_count": 30,
    "policy_frequency": 1,
}


def make_env(
    config: dict[str, Any] | None = None,
    render_mode: str | None = None,
) -> gym.Env:
    """Create highway-fast-v0 with the demo overrides applied.

    Callers seed on reset: ``env.reset(seed=seed)``. Keeping the seed out of the
    factory means every episode in an eval run is seeded explicitly and visibly.
    """
    merged = {**DEFAULT_CONFIG, **(config or {})}
    return gym.make(ENV_ID, render_mode=render_mode, config=merged)
