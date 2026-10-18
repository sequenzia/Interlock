# Repository layout

The repository has four top-level areas: the Python backend, the React console,
trained models, and planning material. Tests, the docs source and the
deployment files sit next to them.

```text
interlock/
  backend/            Python package: simulator, policy, shield, judge, server, CLI, eval
  frontend/           Vite + React + TypeScript console, Playwright smoke test
  models/             DQN checkpoints (gitignored except README.md)
  tests/              pytest suite
  docs/               this site (MkDocs Material)
  internal/           planning history, the evaluation report and plots
  CLAUDE.md           working agreement for the repo: rules, conventions, commands
  README.md           overview, results, getting started, deployment
  pyproject.toml      uv project, dependency groups, ruff and pytest settings
  uv.lock             locked dependencies, CPU-only torch on Linux
  mkdocs.yml          docs navigation and theme
  Dockerfile          backend image for the always-on container
  fly.toml            Fly.io machine configuration
  .dockerignore       allowlist of what enters the image
  .github/workflows/  docs.yml publishes this site to GitHub Pages
```

## backend/

Every module has a docstring that names its role. Flags for a subcommand live
in that module's `add_arguments`, so `python -m backend.<module>` and
`interlock <command>` stay equivalent.

| File | Role |
| --- | --- |
| `env.py` | `make_env()` for `highway-fast-v0` with the demo overrides, `ACTION_NAMES` and `ACTION_INDEX` derived from highway-env. |
| `train.py` | DQN training recipe, greedy checkpoint evaluation, `parse_seed_range`. Behind `interlock train`. |
| `policy.py` | `Policy` wraps the loaded DQN: Q-values and `ranked_actions()`. |
| `paths.py` | Repo-relative paths: models, logs, internal, the default checkpoint, the env file. |
| `facts.py` | State plus one candidate action to JSON facts and plain sentences; the render snapshot. |
| `constraints.py` | `Constraint`, `Zone`, `PRESETS`, `infer_checker`, `ConstraintStore` with the zone lifecycle. |
| `jev_client.py` | `build_question`, `cache_key`, `JevCache`, `LiveJudge`, `JevClient` (shape B with cache), `make_client`. |
| `shield.py` | `Thresholds`, `Decision`, `decide`, `fallback_action`, `resolve`. Pure functions. |
| `checkers.py` | One closed-form checker per preset rule, `label` and `label_all`. Scoring only. |
| `logger.py` | `build_record`, `JsonlLogger`, `read_log`, `make_run_id`, `default_log_path`. |
| `episode.py` | `EpisodeRunner`, `Escalation`, the three built-in operators, `StepResult`, `Totals`. |
| `run_episode.py` | Headless episode with per-step output. Behind `interlock run`. |
| `server.py` | `Session`, `create_app`, `session_from_env`, replay helpers. The WebSocket server. |
| `twin.py` | Finds the shield-off log for a seed and builds the `twin` message the console draws under the road view. |
| `metrics.py` | `episode_metrics`, `aggregate`, `collect_checks`, `reliability`, `calibration`. Records in, numbers out. |
| `evaluate.py` | `run_config`, `build_report`, the sweep. Behind `interlock eval`. |
| `label.py` | Hand labels for rules without a checker, keyed by facts and rule text. Behind `interlock label`. |
| `baseline_llm.py` | Chat-LLM baseline: the judge's questions on logged checks, sent to Claude models for one structured JSON number. Behind `interlock baseline`. |
| `plots.py` | Three matplotlib figures from the report JSON. |
| `cli.py` | The `interlock` entry point and the `console` subcommand that supervises uvicorn and Vite. |
| `spike/jev_spike.py` | The offline-checkable Jev probe behind `interlock spike`; writes raw requests under `backend/logs/spike/`. |
| `.env.example` | Template for `backend/.env`, which holds `TYPESAFE_API_KEY` and is gitignored. |
| `logs/` | Runtime output, gitignored: `runs/` (console and CLI episodes), `eval/` (one directory per configuration), `spike/`, `labels/` (hand labels per rule), `jev_cache.jsonl`, `baseline_cache.jsonl` (chat-model replies). |

## frontend/

| Path | Role |
| --- | --- |
| `src/main.tsx` | Mounts `App` in StrictMode. |
| `src/app.tsx` | Layout, the global keyboard handler, the error toast, the console/metrics switch. |
| `src/store.ts` | The single Zustand store with five slices and the selectors. |
| `src/ws-client.ts` | The one WebSocket, reconnect with backoff, message to store mapping, `send()`. |
| `src/types.ts` | TypeScript mirror of the log record, the protocol and the evaluation report. |
| `src/backend-url.ts` | `httpUrl()` and `wsUrl()` from `VITE_BACKEND_URL`, same-origin when unset. |
| `src/format.ts` | Formatting helpers and the decision label, class and color maps. |
| `src/styles.css` | Tailwind import, theme font, the shared `panel`, `btn`, `chip` and `badge` classes. |
| `src/components/` | `status-strip`, `road-view`, `twin-strip`, `decision-strip`, `inspector-drawer`, `approval-queue`, `constraint-panel`, `metrics-view`. |
| `e2e/smoke.spec.ts` | Two Playwright tests against a mock backend on port 8001 and Vite on 5174. |
| `vite.config.ts` | React and Tailwind plugins, the dev proxy to `SHIELD_BACKEND`. |
| `playwright.config.ts` | Starts its own backend and Vite for the smoke test. |
| `package.json` | pnpm scripts: `dev`, `build`, `typecheck`, `preview`, `test:e2e`. |
| `.vercel/project.json` | Links the directory to the Vercel project `interlock-console`. |

## models/

| File | Role |
| --- | --- |
| `dqn_highway.zip` | The checkpoint `Policy.load()` uses by default. Promoted by `interlock train --promote`. |
| `dqn_highway_20k.zip`, `dqn_highway_100k.zip` | Named training runs, each with a `.eval.json` next to it. |
| `README.md` | The only committed file in the directory. |

## tests/

One file per backend module plus the CLI and the spike's fact builders. The
[testing page](testing.md) maps each file to what it covers and explains the
shared fixtures.

## internal/

Planning history, the Jev spike output, research notes, and the evaluation
outputs `internal/eval/latest.json` and `internal/plots/*.png`. The server
reads `latest.json` for the metrics tab and the Docker image carries it. The
rest is background for the project and is not part of this site.

## What is gitignored

`backend/.env`, everything under `backend/logs/` except `.gitkeep`, everything
under `models/` except its README, the Python and frontend build caches,
`frontend/node_modules/`, `frontend/dist/` and Playwright's result folders. The
Docker build context is an allowlist in `.dockerignore`, so a new runtime file
the server reads has to be added there and copied in the `Dockerfile`.
