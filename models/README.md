# models/

Trained Stable-Baselines3 DQN checkpoints land here. Everything in this
directory except this file is gitignored.

- `dqn_highway_20k.zip`: 20k-step run from `uv run python -m backend.train`
- `dqn_highway_100k.zip`: 100k-step run, `--timesteps 100000`
- `dqn_highway.zip`: whichever checkpoint `backend.policy` loads by default

Recreate with `uv run python -m backend.train`. See `internal/build-plan.md`
section 12 for the recipe and the selection rule.
