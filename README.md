# Shielded RL with Jev

A runtime safety shield demo. A Stable-Baselines3 DQN drives in highway-env on
task reward alone. Jev, TypeSafe's decision model, judges each candidate action
against plain-English operator rules. Code allows, falls back or escalates to a
human operator.

The one-line pitch: the policy was trained once; the rules changed live, in
plain English.

## Setup

```
uv sync --all-groups
cp backend/.env.example backend/.env   # then add TYPESAFE_API_KEY
uv run pytest
```

See `CLAUDE.md` for the command list and `internal/build-plan.md` for the
design, schedule and module contracts.
