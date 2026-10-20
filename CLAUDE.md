# Interlock: Shielded RL with Jev

Interlock is a runtime safety shield demo. A Stable-Baselines3 DQN drives in
highway-env on task reward alone. Jev, TypeSafe's decision model, judges each
candidate action against plain-English operator rules. Code allows, falls back or
escalates to a human. A React console shows the road, the rules, the approval
queue and the decision log. Built as a demo for a presentation
around Oct 23, 2026.

## Source of truth

- `internal/project-brief.md`: intent, concept, talk.
- `internal/interlock-summary.md`: two-page summary of what Interlock is, what
  it does and why it matters. Written Oct 17.
- `internal/build-plan.md`: decisions, schedule, module contracts, protocol,
  log schema, spike checklist. Read this before touching any module.
- `internal/jev-spike-results.md`: written on Day 1; holds measured Jev
  behavior. Do not assume Jev behavior that is not recorded there.
  `internal/jev-spike-recheck-oct17.md` repeats items 2 and 3 after the Oct 17
  fact schema change and compares them with Day 1.
- `internal/hand-labeling.md`: how to hand-label the two fuzzy rules, the
  keys, a consistent standard per rule, and where the labels land. Labeled
  Oct 19 by `interlock autolabel`, that standard pinned in code by Claude,
  over the whole calibration pool; the last section records how the loose
  words were pinned. The label files are committed.
- `internal/decision-models-research.md`: public facts about Jev and the
  decision-model category as of Oct 16. Vendor claims, not measured behavior.
- `internal/experiment-tracker.md`: the Oct 19 assessment of adding Weights &
  Biases, deferred to after the talk, with the phased plan to add it.
- `internal/eval/latest.json` and `internal/plots/`: the Day 5 evaluation.
  Plan section 10 holds the results table and the reading of it.
- `docs/` and `mkdocs.yml`: the public documentation site (MkDocs Material),
  published to GitHub Pages by `.github/workflows/docs.yml`. It covers code,
  usage and results only; it never quotes or links the files under `internal/`.
  When a contract, flag, message or screen changes, update its page in `docs/`.

## Stack

- Backend: Python 3.12 via uv, highway-env 1.12, Gymnasium 1.3, SB3 2.9,
  FastAPI with WebSocket, Typer for the `interlock` command, `typesafe-sdk`
  for Jev. Pin versions in `pyproject.toml` once training works.
- Frontend: Vite, React, TypeScript strict, Tailwind, Zustand, Recharts,
  Canvas 2D road view, Playwright smoke test. Package manager is pnpm.
- Layout: `backend/`, `frontend/`, `models/`, `internal/`. See the plan for
  the module list.

## Non-negotiable rules

- Geometry stays in code. Facts sent to Jev are precomputed JSON with units
  in the field names. Never ask Jev to count, compare numbers or do multi-hop.
- Ground-truth checkers in `backend/checkers.py` score only. They never feed
  the shield's decision, including in mock or offline mode. The same holds for
  the labels under `backend/logs/labels/`, by hand or by `interlock autolabel`,
  which exist only for calibration.
- When Jev is unreachable and a question is not cached, the shield escalates
  with p = 0.5 flagged "judge unavailable". Never fake a judgment.
- The shield acts on its own only with a confidently safe action. When no
  candidate is below the allow threshold it escalates with reason
  `no_compliant_action` and offers every candidate; it never silently runs a
  last resort. Plan section 16.1 records why.
- The physics floor is code, not a rule. A candidate whose time to collision
  ahead is under `FLOOR_S` (default 2.0 s) never runs with the shield on, and
  no console message changes the floor. Plan section 16.4.
- The JSONL log record in the plan is the contract between backend, UI and
  eval. Change it in the plan first, then in `backend/logger.py`, then in
  the frontend types.
- Jev questions are positive assertions with the rule text verbatim. No
  negation in instructions or criteria.
- `TYPESAFE_API_KEY` and `ANTHROPIC_API_KEY` (with `ANTHROPIC_WORKSPACE_ID` when
  the key is not workspace-scoped) come from `backend/.env`, which is
  gitignored. Never commit them, never log them.
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
  `backend/cli.py` is the `interlock` command, a Typer app. Each subcommand is a
  module's `command` function, whose parameters are its flags, so new flags go
  in the module, never in the dispatcher, and `python -m backend.<module>` stays
  equivalent. `backend/cli_support.py` holds the Typer settings every app shares.
- Context7 is disabled in this project. Read library docs from the official
  sites: highway-env.farama.org, stable-baselines3.readthedocs.io,
  docs.typesafe.ai.
- Conventional Commits. Do not commit or push unless asked.

## Deployment

- The console is a static Vite build on Vercel with `frontend/` as the project
  root. `VITE_BACKEND_URL` is read at build time by `frontend/src/backend-url.ts`;
  unset means same-origin, which the Vite proxy and the e2e test rely on.
- The backend is one stateful process and runs as one always-on container from
  the root `Dockerfile`, never as a serverless function: the session lives in
  memory and the loop runs between messages. `CONSOLE_ORIGINS` lists the
  console origins for CORS on the HTTP routes; the WebSocket upgrade is exempt.
- The backend host is Fly.io: `fly.toml` runs one always-on machine with
  auto-stop off at https://interlock-backend.fly.dev. `CONSOLE_ORIGINS` lives
  under its `[env]`; the API key is a Fly secret and never goes in the file.
  The console is the Vercel project `interlock-console` at
  https://interlock-demo.vercel.app.
- Linux installs CPU-only torch through `[tool.uv.sources]` in `pyproject.toml`.
  Keep that when bumping torch, or the image grows by the CUDA libraries.
- The docs site deploys to GitHub Pages at https://sequenzia.github.io/interlock/
  from `.github/workflows/docs.yml` on pushes to `main` that touch `docs/`,
  `mkdocs.yml`, `pyproject.toml` or `uv.lock`. The job installs only the uv
  `docs` group (`uv sync --only-group docs`), so torch never enters the runner.
  Pages must be set to the GitHub Actions source once in the repo settings.
- `.dockerignore` is an allowlist. A new runtime file the server reads must be
  added there and copied in the `Dockerfile`. It lets the shield-off logs
  through (`backend/logs/eval/*_off/seed*.jsonl`, `backend/logs/runs/*_off.jsonl`)
  so the deployed console can draw the unshielded twin.

## Commands

Update this section as modules land.

```
uv sync --all-groups                                 # backend deps (+ pytest, ruff, mkdocs) and the interlock command
uv run pytest                                        # backend tests
uv run ruff format backend tests && uv run ruff check backend tests
uv run interlock --help                              # every subcommand takes its module's flags
uv run interlock train                               # 20k-step DQN to models/dqn_highway_20k.zip
uv run interlock train --timesteps 100000            # long run
uv run interlock train --eval-only models/dqn_highway_20k.zip   # greedy rollouts over --eval-seeds
uv run interlock train --eval-only models/dqn_highway_20k.zip --promote  # copy to dqn_highway.zip
uv run interlock label --run backend/logs/eval/<stamp>_on_ta0.30_tb0.70 --rule dense_traffic   # hand-label a fuzzy rule, then eval --report
uv run interlock autolabel --dry-run                 # the fuzzy rules by the fixed standard: the split per rule, nothing written
uv run interlock autolabel                           # label every pooled state, then eval --report; a rerun adds nothing
uv run interlock baseline --dry-run                  # sample 2,000 logged checks, print one chat request, send nothing
uv run interlock baseline --models claude-haiku-5-5,claude-sonnet-5-5   # chat-LLM baseline; needs ANTHROPIC_API_KEY, reads backend/prices.json if present, then eval --report
uv run interlock spike                               # Day 1 Jev spike, writes internal/jev-spike-results.md
uv run interlock spike --dry-run                     # validate every spike request offline, no key needed
uv run interlock run --shield on                     # headless shielded episode, logs to backend/logs/runs/
uv run interlock run --shield off --seed 3           # shadow mode on another seed; also warms the unshielded twin for seed 3
uv run interlock run --jev mock --zone-at-step 10    # offline, drop the work zone mid-episode
uv run interlock run --rules speed_limit --operator approve --max-steps 20
uv run interlock run --floor-s 0                     # no physics floor (default 2 s); eval and console take the same flag
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
uv run mkdocs serve -a 127.0.0.1:8080                # docs site with live reload; port 8000 belongs to the backend
uv run mkdocs build --strict                         # what the GitHub Pages workflow runs; fails on a broken link
docker build --platform linux/amd64 -t interlock-backend .   # backend image: lock, backend/, model, eval report, Jev cache
docker run --rm -p 8000:8000 --env-file backend/.env -e ESCALATION_TIMEOUT_S=0 interlock-backend
fly deploy --ha=false                                # backend on Fly.io per fly.toml, one machine; key via: grep '^TYPESAFE_API_KEY=' backend/.env | fly secrets import
cd frontend && vercel link && vercel env add VITE_BACKEND_URL production && vercel --prod   # console on Vercel
```
