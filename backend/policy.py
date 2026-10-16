"""Load the trained DQN and rank all five actions by Q-value.

The shield needs the whole ranking, not just the argmax: when the top action is
blocked, the next-best action is already in hand. Q-values come straight from
``model.q_net`` on the observation tensor (plan section 12).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch as th
from stable_baselines3 import DQN

from backend.env import ACTION_NAMES
from backend.paths import DEFAULT_MODEL_PATH


@dataclass(frozen=True)
class RankedAction:
    name: str
    index: int
    q: float
    rank: int


class Policy:
    """Thin wrapper over an SB3 DQN exposing Q-values and a stable ranking."""

    def __init__(self, model: DQN) -> None:
        self.model = model

    @classmethod
    def load(cls, path: Path = DEFAULT_MODEL_PATH) -> Policy:
        return cls(DQN.load(path, device="cpu"))

    def q_values(self, obs: np.ndarray) -> np.ndarray:
        """Q-value per action index, in ACTION_NAMES order."""
        obs_tensor, _ = self.model.policy.obs_to_tensor(obs)
        with th.no_grad():
            q = self.model.q_net(obs_tensor)
        return q.squeeze(0).cpu().numpy().astype(float)

    def ranked_actions(self, obs: np.ndarray) -> list[RankedAction]:
        """All five actions sorted by Q-value, best first. Ties keep action-index order."""
        q = self.q_values(obs)
        order = sorted(range(len(q)), key=lambda i: (-q[i], i))
        return [
            RankedAction(name=ACTION_NAMES[i], index=i, q=float(q[i]), rank=rank)
            for rank, i in enumerate(order)
        ]
