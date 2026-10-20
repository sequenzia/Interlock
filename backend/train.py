"""Train the task-reward-only DQN and evaluate checkpoints.

Recipe from the HighwayEnv docs, recorded in internal/build-plan.md section 12.
The policy is trained on env reward alone and never sees an operator rule.
Behind ``interlock train``; ``python -m backend.train`` takes the same flags.
"""

from __future__ import annotations

import json
import shutil
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Any

import numpy as np
import typer
from stable_baselines3 import DQN

from backend.cli_support import run_standalone
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


def command(
    timesteps: Annotated[int, typer.Option(help="training steps")] = 20_000,
    seed: Annotated[int, typer.Option(help="training seed")] = 0,
    out: Annotated[
        Path | None, typer.Option(help="checkpoint path (default `models/dqn_highway_<N>k.zip`)")
    ] = None,
    eval_seeds: Annotated[
        str, typer.Option(help='seeds for the post-training rollout, e.g. "0-19"')
    ] = "0-19",
    eval_only: Annotated[
        Path | None, typer.Option(help="skip training and evaluate this checkpoint")
    ] = None,
    promote: Annotated[
        bool, typer.Option("--promote", help="also copy the checkpoint to models/dqn_highway.zip")
    ] = False,
) -> None:
    """Train the DQN on task reward alone, or evaluate a checkpoint with greedy rollouts.

    ```
    interlock train                                        # 20k steps
    interlock train --timesteps 100000                     # long run
    interlock train --eval-only models/dqn_highway_20k.zip
    interlock train --promote                              # also copy to dqn_highway.zip
    ```

    Writes the checkpoint and a `.eval.json` next to it with the rollout summary.
    """
    seeds = parse_seed_range(eval_seeds)
    if eval_only is not None:
        checkpoint = eval_only
    else:
        checkpoint = out or MODELS_DIR / f"dqn_highway_{timesteps // 1000}k.zip"
        train(timesteps, checkpoint, seed)

    summary = evaluate_checkpoint(checkpoint, seeds)
    print(json.dumps({k: v for k, v in summary.items() if k != "per_episode"}, indent=2))
    report = checkpoint.with_suffix(".eval.json")
    report.write_text(json.dumps(summary, indent=2))
    print(f"wrote {report}")

    if promote:
        shutil.copyfile(checkpoint, DEFAULT_MODEL_PATH)
        print(f"promoted {checkpoint.name} to {DEFAULT_MODEL_PATH}")


def main(argv: Sequence[str] | None = None) -> None:
    """``python -m backend.train``: the ``interlock train`` command on its own."""
    run_standalone(command, argv)


if __name__ == "__main__":
    main()
