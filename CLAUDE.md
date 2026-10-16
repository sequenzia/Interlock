# Shielded RL with Jev

A runtime safety shield demo. A Stable-Baselines3 DQN drives in highway-env on
task reward alone. Jev, TypeSafe's decision model, judges each candidate
action against plain-English operator rules. Code allows, falls back or
escalates to a human. A React console shows the road, the rules, the approval
queue and the decision log. Built as a demo for a presentation
around Oct 23, 2026.

## Source of truth

- `internal/project-brief.md`: intent, concept, talk.
- `internal/build-plan.md`: decisions, schedule, module contracts, protocol,
  log schema, spike checklist. Read this before touching any module.
- `internal/jev-spike-results.md`: written on Day 1; holds measured Jev
  behavior. Do not assume Jev behavior that is not recorded there.

## Stack

- Backend: Python 3.12 via uv, highway-env 1.12, Gymnasium 1.3, SB3 2.9,
  FastAPI with WebSocket, `typesafe-sdk` for Jev. Pin versions in
  `pyproject.toml` once training works.
- Frontend: Vite, React, TypeScript strict, Tailwind, Zustand, Recharts,
  Canvas 2D road view, Playwright smoke test. Package manager is pnpm.
- Layout: `backend/`, `frontend/`, `models/`, `internal/`. See the plan for
  the module list.

## Non-negotiable rules

- Geometry stays in code. Facts sent to Jev are precomputed JSON with units
  in the field names. Never ask Jev to count, compare numbers or do multi-hop.
- Ground-truth checkers in `backend/checkers.py` score only. They never feed
  the shield's decision, including in mock or offline mode.
- When Jev is unreachable and a question is not cached, the shield escalates
  with p = 0.5 flagged "judge unavailable". Never fake a judgment.
- The JSONL log record in the plan is the contract between backend, UI and
  eval. Change it in the plan first, then in `backend/logger.py`, then in
  the frontend types.
- Jev questions are positive assertions with the rule text verbatim. No
  negation in instructions or criteria.
- `TYPESAFE_API_KEY` comes from `backend/.env`, which is gitignored. Never
  commit it, never log it.
- No em dashes in docs, slides, UI copy or commit messages.

## Conventions

- Python: ruff for format and lint, pytest, type hints on every function.
- TypeScript: strict mode, kebab-case filenames, one Zustand store with
  slices for steps, constraints, queue and metrics.
- Keep the headless CLI working at all times; the server and UI sit on top
  of it, not beside it. `backend/episode.py` holds the per-step loop both share.
- Context7 is disabled in this project. Read library docs from the official
  sites: highway-env.farama.org, stable-baselines3.readthedocs.io,
  docs.typesafe.ai.
- Conventional Commits. Do not commit or push unless asked.

## Commands

Update this section as modules land.

```
uv sync --all-groups                                 # backend deps (+ pytest, ruff)
uv run pytest                                        # backend tests
uv run ruff format backend tests && uv run ruff check backend tests
uv run python -m backend.train                       # 20k-step DQN to models/dqn_highway_20k.zip
uv run python -m backend.train --timesteps 100000    # long run
uv run python -m backend.train --eval-only models/dqn_highway_20k.zip   # greedy rollouts over --eval-seeds
uv run python -m backend.train --eval-only models/dqn_highway_20k.zip --promote  # copy to dqn_highway.zip
uv run python -m backend.spike.jev_spike             # Day 1 Jev spike, writes internal/jev-spike-results.md
uv run python -m backend.spike.jev_spike --dry-run   # validate every spike request offline, no key needed
uv run python -m backend.run_episode --shield on     # headless shielded episode, logs to backend/logs/runs/
uv run python -m backend.run_episode --shield off --seed 3            # shadow mode on another seed
uv run python -m backend.run_episode --jev mock --zone-at-step 10     # offline, drop the work zone mid-episode
uv run python -m backend.run_episode --rules speed_limit --operator approve --max-steps 20
uv run python -m backend.evaluate --seeds 0-19 --mode on
uv run uvicorn backend.server:app --reload           # WebSocket server
cd frontend && pnpm dev                              # console on Vite
cd frontend && pnpm test:e2e                         # Playwright smoke test
```
