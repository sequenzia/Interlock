# Interlock: Shielded RL with Jev

Interlock is a runtime safety shield demo. A Stable-Baselines3 DQN drives in
highway-env on task reward alone. Jev, TypeSafe's decision model, judges each
candidate action against plain-English operator rules. Code allows, falls back or
escalates to a human. A React console shows the road, the rules, the approval
queue and the decision log. Built as a demo for a presentation
around Oct 23, 2026.

## Source of truth

- `internal/project-brief.md`: intent, concept, talk.
- `internal/build-plan.md`: decisions, schedule, module contracts, protocol,
  log schema, spike checklist. Read this before touching any module.
- `internal/jev-spike-results.md`: written on Day 1; holds measured Jev
  behavior. Do not assume Jev behavior that is not recorded there.
- `internal/decision-models-research.md`: public facts about Jev and the
  decision-model category as of Oct 16. Vendor claims, not measured behavior.
- `internal/eval/latest.json` and `internal/plots/`: the Day 5 evaluation.
  Plan section 10 holds the results table and the reading of it.

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
- The project is Interlock. "Shield" stays the lowercase technical term for
  the mechanism. Never use it as a name in the header, page title or packages.

## Conventions

- Python: ruff for format and lint, pytest, type hints on every function.
- TypeScript: strict mode, kebab-case filenames, one Zustand store with
  slices for steps, constraints, queue and metrics. Zustand selectors must
  return stable references: never `?? []` or `?? {}` inside a selector.
- Keep the headless CLI working at all times; the server and UI sit on top
  of it, not beside it. `backend/episode.py` holds the per-step loop both share.
  `backend/cli.py` is the `interlock` command. Each subcommand calls a module's
  `add_arguments` and `run_cli`, so new flags go in the module, never in the
  dispatcher, and `python -m backend.<module>` stays equivalent.
- Context7 is disabled in this project. Read library docs from the official
  sites: highway-env.farama.org, stable-baselines3.readthedocs.io,
  docs.typesafe.ai.
- Conventional Commits. Do not commit or push unless asked.

## Commands

Update this section as modules land.

```
uv sync --all-groups                                 # backend deps (+ pytest, ruff) and the interlock command
uv run pytest                                        # backend tests
uv run ruff format backend tests && uv run ruff check backend tests
uv run interlock --help                              # every subcommand takes its module's flags
uv run interlock train                               # 20k-step DQN to models/dqn_highway_20k.zip
uv run interlock train --timesteps 100000            # long run
uv run interlock train --eval-only models/dqn_highway_20k.zip   # greedy rollouts over --eval-seeds
uv run interlock train --eval-only models/dqn_highway_20k.zip --promote  # copy to dqn_highway.zip
uv run interlock spike                               # Day 1 Jev spike, writes internal/jev-spike-results.md
uv run interlock spike --dry-run                     # validate every spike request offline, no key needed
uv run interlock run --shield on                     # headless shielded episode, logs to backend/logs/runs/
uv run interlock run --shield off --seed 3           # shadow mode on another seed
uv run interlock run --jev mock --zone-at-step 10    # offline, drop the work zone mid-episode
uv run interlock run --rules speed_limit --operator approve --max-steps 20
uv run interlock eval --seeds 0-19 --mode on         # one configuration, writes backend/logs/eval/<stamp>_<label>/
uv run interlock eval --seeds 0-19 --all --concurrency 2  # off + 5-pair sweep + report, ~8 min, ~$0.75 live
uv run interlock eval --report                       # rebuild internal/eval/latest.json and internal/plots/*.png
uv run interlock console                             # uvicorn on :8000 + Vite on :5173, live Jev if key present
uv run interlock console --jev mock --escalation-timeout 0   # offline, wait for the operator
uv run interlock console --jev mock --cache /tmp/empty.jsonl  # empty cache: every step escalates
uv run interlock console --reload --open             # dev loop; --no-ui runs the server alone
uv run uvicorn backend.server:app --reload           # server by itself; python -m backend.<module> also still works
cd frontend && pnpm install && pnpm dev              # console by itself on :5173, proxies /ws to :8000
cd frontend && pnpm typecheck && pnpm build          # strict tsc, then Vite production build
cd frontend && pnpm test:e2e                         # Playwright smoke test: own mock backend on :8001, Vite on :5174
```
