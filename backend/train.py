"""Train the task-reward-only DQN and evaluate checkpoints.

Recipe from the HighwayEnv docs, recorded in internal/build-plan.md section 12.
The policy is trained on env reward alone and never sees an operator rule.

    uv run python -m backend.train                         # 20k steps
    uv run python -m backend.train --timesteps 100000      # long run
    uv run python -m backend.train --eval-only models/dqn_highway_20k.zip
    uv run python -m backend.train --promote               # also copy to dqn_highway.zip
    uv run interlock train --promote                       # same flags via backend/cli.py
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
from stable_baselines3 import DQN

from backend.env import make_env
from backend.paths import DEFAULT_MODEL_PATH, MODELS_DIR


def build_model(env: Any, seed: int) -> DQN:
    """DQN hyperparameters from the HighwayEnv quickstart."""
    return DQN(
        "MlpPolicy",
        env,
        policy_kwargs={"net_arch": [256, 256]},
        learning_rate=5e-4,
        buffer_size=15000,
        learning_starts=200,
        batch_size=32,
        gamma=0.8,
        train_freq=1,
        gradient_steps=1,
        target_update_interval=50,
        exploration_fraction=0.7,
        verbose=1,
        seed=seed,
        device="cpu",
    )


def train(timesteps: int, out: Path, seed: int) -> Path:
    """Train for ``timesteps`` and save the checkpoint to ``out``."""
    env = make_env()
    model = build_model(env, seed)
    started = time.perf_counter()
    model.learn(total_timesteps=timesteps, progress_bar=False)
    elapsed = time.perf_counter() - started
    out.parent.mkdir(parents=True, exist_ok=True)
    model.save(out)
    env.close()
    print(f"saved {out} after {timesteps} steps in {elapsed / 60:.1f} min")
    return out


def run_episode(model: DQN, seed: int) -> dict[str, Any]:
    """Drive one greedy episode and report return, crash, mean speed and length."""
    env = make_env()
    obs, _ = env.reset(seed=seed)
    total_reward = 0.0
    speeds: list[float] = []
    crashed = False
    steps = 0
    done = False
    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, reward, terminated, truncated, info = env.step(int(action))
        total_reward += float(reward)
        speeds.append(float(info["speed"]))
        crashed = bool(info["crashed"])
        steps += 1
        done = terminated or truncated
    env.close()
    return {
        "seed": seed,
        "return": round(total_reward, 3),
        "crashed": crashed,
        "mean_speed_mps": round(float(np.mean(speeds)), 2),
        "steps": steps,
    }


def evaluate_checkpoint(path: Path, seeds: list[int]) -> dict[str, Any]:
    """Greedy rollouts over ``seeds``; the selection rule in the plan reads this."""
    model = DQN.load(path, device="cpu")
    episodes = [run_episode(model, seed) for seed in seeds]
    return {
        "model": str(path),
        "episodes": len(episodes),
        "mean_return": round(float(np.mean([e["return"] for e in episodes])), 3),
        "crash_rate": round(float(np.mean([e["crashed"] for e in episodes])), 3),
        "mean_speed_mps": round(float(np.mean([e["mean_speed_mps"] for e in episodes])), 2),
        "mean_steps": round(float(np.mean([e["steps"] for e in episodes])), 1),
        "per_episode": episodes,
    }


def parse_seed_range(text: str) -> list[int]:
    """Parse ``"0-19"`` or ``"3,7,11"`` into a list of ints."""
    seeds: list[int] = []
    for part in text.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-", 1)
            seeds.extend(range(int(lo), int(hi) + 1))
        elif part:
            seeds.append(int(part))
    return seeds


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Flags shared by ``python -m backend.train`` and ``interlock train``."""
    parser.add_argument("--timesteps", type=int, default=20_000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="checkpoint path (default models/dqn_highway_<N>k.zip)",
    )
    parser.add_argument(
        "--eval-seeds", default="0-19", help='seeds for the post-training rollout, e.g. "0-19"'
    )
    parser.add_argument(
        "--eval-only", type=Path, default=None, help="skip training and evaluate this checkpoint"
    )
    parser.add_argument(
        "--promote", action="store_true", help="also copy the checkpoint to models/dqn_highway.zip"
    )


def run_cli(args: argparse.Namespace) -> int:
    seeds = parse_seed_range(args.eval_seeds)
    if args.eval_only is not None:
        checkpoint = args.eval_only
    else:
        checkpoint = args.out or MODELS_DIR / f"dqn_highway_{args.timesteps // 1000}k.zip"
        train(args.timesteps, checkpoint, args.seed)

    summary = evaluate_checkpoint(checkpoint, seeds)
    print(json.dumps({k: v for k, v in summary.items() if k != "per_episode"}, indent=2))
    report = checkpoint.with_suffix(".eval.json")
    report.write_text(json.dumps(summary, indent=2))
    print(f"wrote {report}")

    if args.promote:
        shutil.copyfile(checkpoint, DEFAULT_MODEL_PATH)
        print(f"promoted {checkpoint.name} to {DEFAULT_MODEL_PATH}")
    return 0


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    add_arguments(parser)
    sys.exit(run_cli(parser.parse_args(argv)))


if __name__ == "__main__":
    main()
