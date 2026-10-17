# Development setup

This page gets a working tree ready for changing code: the toolchain, the install, the commands you run every day and where the runtime artifacts land. For the user-facing install path see [Install](../user-guide/install.md).

## Toolchain

| Tool | Version | Role |
| --- | --- | --- |
| uv | 0.9 | Python environment, lock file, the `interlock` script |
| Python | 3.12, pinned by `.python-version` | Backend, tests, docs |
| Node | 20 or newer | Frontend build |
| pnpm | current | Frontend package manager |
| ruff | from the `dev` group | Format and lint for `backend/` and `tests/` |
| pytest | from the `dev` group | Backend test suite |
| TypeScript | 7, strict mode | Frontend type checking through `tsc` |
| Vite | 8 | Frontend dev server and production build |
| Playwright | from `frontend/package.json` | Smoke test against a mock backend |

Check what is present before installing anything: `which uv node pnpm` and `brew list`.

## Install

```bash
uv sync --all-groups
cd frontend && pnpm install && cd ..
cp backend/.env.example backend/.env        # add TYPESAFE_API_KEY for live judging
```

`uv sync --all-groups` creates `.venv`, installs the project dependencies plus the `dev` group (pytest, ruff) and the `docs` group (mkdocs-material), and installs the project itself in editable mode so the `interlock` console script resolves to `backend.cli:main`. The package is `backend/` at the repo root rather than `src/interlock/`; `[tool.uv.build-backend]` in `pyproject.toml` points the build backend at it. Nothing is ever built for distribution.

!!! note "CPU-only torch on Linux"
    `[tool.uv.sources]` takes torch from the PyTorch CPU index when `sys_platform == 'linux'`. macOS keeps the PyPI wheel. The lock holds both, so a Linux container skips the CUDA libraries. Keep that entry when bumping torch.

The API key lives only in `backend/.env`, which is gitignored. `python-dotenv` loads it in the CLI modules and in `backend/server.py`. It is never logged and never enters the Docker image.

### The checkpoint

`models/dqn_highway.zip` is gitignored. The test suite does not need it: the tests build an untrained DQN through `backend.train.build_model`. The console, `interlock run` and `interlock eval` do need it. Train and promote one with:

```bash
uv run interlock train --timesteps 100000 --promote
```

That takes about 25 minutes on a laptop. See [Training and policy](backend/training.md) for the recipe and the selection rule.

## Day-to-day commands

| Task | Command |
| --- | --- |
| Backend tests | `uv run pytest` |
| Format and lint | `uv run ruff format backend tests && uv run ruff check backend tests` |
| Frontend types | `cd frontend && pnpm typecheck` |
| Frontend build | `cd frontend && pnpm build` |
| Smoke test | `cd frontend && pnpm test:e2e` |
| Docs preview | `uv run mkdocs serve -a 127.0.0.1:8080` |
| Docs build | `uv run mkdocs build --strict` |

The docs preview binds to 8080 because 8000 belongs to the backend. `pnpm build` runs `tsc -p tsconfig.json` first, so a type error fails the build.

## The dev loop

One command starts the WebSocket server on 8000 and Vite on 5173, and Ctrl-C stops both:

```bash
uv run interlock console --reload --open
```

`--reload` restarts uvicorn when a file under `backend/` changes. `--open` opens the browser once Vite is up. Vite proxies `/ws`, `/health` and `/eval` to the server, so the console stays same-origin in development. The proxy target comes from the `SHIELD_BACKEND` environment variable, which the console command sets from `--port`; by hand it defaults to `http://127.0.0.1:8000`.

The two halves also run on their own:

```bash
uv run interlock console --no-ui                 # server only, console command still owns the flags
uv run uvicorn backend.server:app --reload       # server by itself
cd frontend && pnpm dev                          # console by itself on :5173
```

Every subcommand is a thin wrapper over a module, so `uv run python -m backend.run_episode --shield on` and `uv run interlock run --shield on` take the same flags. New flags go in the module's `add_arguments`, never in `backend/cli.py`. See [CLI internals](backend/cli.md).

## Working offline

Jev mode defaults to live when `TYPESAFE_API_KEY` is set and to mock otherwise. Mock mode answers only from the content cache at `backend/logs/jev_cache.jsonl`; a miss returns p = 0.5 flagged "unavailable", and the shield escalates it to the operator with a "judge unavailable" badge. That makes two offline setups useful:

```bash
uv run interlock console --jev mock --escalation-timeout 0     # warm cache, wait for the operator
uv run interlock console --jev mock --cache /tmp/empty.jsonl   # empty cache: every step escalates
```

The second one is the fastest way to exercise the approval queue and the inspector without spending a request. The Playwright smoke test uses the same trick with a cache path of its own. See [Jev integration](backend/jev-integration.md) for the cache key and the unavailable path.

## Logs and artifacts

Everything the code writes at runtime lands under `backend/logs/` and is gitignored apart from `.gitkeep`:

| Path | Written by |
| --- | --- |
| `backend/logs/runs/<run_id>.jsonl` | `interlock run` and the server, one file per episode; the replay picker lists this folder |
| `backend/logs/eval/<stamp>_<label>/` | `interlock eval`, one JSONL per seed plus `metrics.json` |
| `backend/logs/spike/<stamp>/` | `interlock spike`, every raw request and response |
| `backend/logs/jev_cache.jsonl` | the Jev client, append-only, loaded into memory at start |

`models/` is gitignored except its README. `internal/` holds the project's planning history and the evaluation report that the metrics tab reads; the docs do not depend on it.

## Library documentation

Context7 is disabled for this project in `.claude/settings.local.json`. Read library behaviour from the official sites instead:

- highway-env: https://highway-env.farama.org
- Stable-Baselines3: https://stable-baselines3.readthedocs.io
- TypeSafe and Jev: https://docs.typesafe.ai

Pins live in `pyproject.toml`: `highway-env>=1.12,<1.13`, `stable-baselines3>=2.9,<3`, `torch>=2.8`, `gymnasium>=1.0`.
