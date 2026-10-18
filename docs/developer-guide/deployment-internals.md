# Deployment internals

Interlock ships as three deployables from one repository: the backend container on Fly.io, the static console on Vercel, and this documentation on GitHub Pages. The operator's walkthrough is in [Deployment](../user-guide/deployment.md); this page explains the files that make it work and the constraints behind them.

## Why a container and not a function

The backend is one stateful process. The simulator, the loaded DQN, the Jev cache and any open escalation live in memory, and the play loop runs between messages. Serverless hosts are stateless, scale to zero when idle and close WebSockets at the function's maximum duration, so the backend cannot live there. It runs as one always-on container, and the console points at it. See [Server and session](backend/server.md) for the one-session-per-process design.

## The Dockerfile

```dockerfile
FROM python:3.12-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.9.21 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY backend ./backend
COPY models/dqn_highway.zip ./models/dqn_highway.zip
COPY internal/eval/latest.json ./internal/eval/latest.json
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev
ENV SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy MPLBACKEND=Agg PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "exec uv run --no-sync uvicorn backend.server:app --host 0.0.0.0 --port ${PORT}"]
```

Layer by layer:

| Layer | Purpose |
| --- | --- |
| Base and uv | `python:3.12-slim-bookworm` with the uv 0.9.21 binaries copied from the official image, so the container resolves the same lock as the laptop |
| `ENV` flags | Compile bytecode at install, copy instead of hard-link across layers, never download a Python, unbuffered logs |
| Dependency layer | Only the lock, `pyproject.toml` and `.python-version` are copied, then `uv sync --frozen --no-dev --no-install-project` with a cache mount. A code change does not re-download torch |
| Project layer | `backend/`, the promoted checkpoint, the eval report for the metrics tab, then a second `uv sync --frozen --no-dev` that installs the package itself. A missing `models/dqn_highway.zip` fails the build here, on purpose |
| Runtime env | highway-env imports pygame; `SDL_VIDEODRIVER=dummy` and `SDL_AUDIODRIVER=dummy` keep it headless. `MPLBACKEND=Agg` covers any matplotlib import. `PORT` defaults to 8000 |
| `CMD` | `exec` so uvicorn is PID 1 and receives signals; `--no-sync` so startup never touches the network; `--host 0.0.0.0` so Fly can reach it |

!!! note "The Jev cache ships when it exists"
    `backend/logs/jev_cache.jsonl` is inside the `backend/` copy because `.dockerignore` lets it through. When present, the demo seeds answer from cache without a network call. The shield-off logs come along the same way, `backend/logs/eval/*_off/seed*.jsonl` and `backend/logs/runs/*_off.jsonl`, so the unshielded twin shows for every seed the evaluation covered. The image carries a snapshot; appends inside the container stay in the container.

### `.dockerignore` is an allowlist

```text
*
!pyproject.toml
!uv.lock
!.python-version
!backend/
**/__pycache__
backend/.env
backend/logs/*
!backend/logs/.gitkeep
!backend/logs/jev_cache.jsonl
!backend/logs/runs/*_off.jsonl
!backend/logs/eval/*_off/seed*.jsonl
!models/dqn_highway.zip
!internal/eval/latest.json
```

Everything is excluded, then the needed files are let back in. `backend/.env` is excluded explicitly even though `backend/` is allowed, and `backend/logs/*` is dropped except the keep file and the cache. The rule that follows: a new runtime file the server reads must be added to `.dockerignore` and copied in the Dockerfile, or the container starts without it.

### CPU-only torch on Linux

`pyproject.toml` pins torch to the CPU index on Linux only:

```toml
[tool.uv.sources]
torch = [{ index = "pytorch-cpu", marker = "sys_platform == 'linux'" }]

[[tool.uv.index]]
name = "pytorch-cpu"
url = "https://download.pytorch.org/whl/cpu"
explicit = true
```

macOS keeps the PyPI wheel. Without this the image would grow by the CUDA libraries. Keep the source when bumping torch.

## Fly.io: `fly.toml`

| Key | Value | Why |
| --- | --- | --- |
| `app` | `interlock-backend` | The Fly app name; the URL is `https://interlock-backend.fly.dev` |
| `primary_region` | `iad` | One region, one machine |
| `[build] dockerfile` | `Dockerfile` | `fly deploy` builds remotely from this directory with `.dockerignore` applied, so the gitignored checkpoint and cache ship without a commit |
| `[env] ESCALATION_TIMEOUT_S` | `"0"` | Wait for the operator, never default-deny in a live session |
| `[env] CONSOLE_ORIGINS` | the two Vercel production aliases | CORS for the console's fetches |
| `[http_service] internal_port` | 8000 | Matches `PORT` |
| `force_https` | true | The console connects over `wss` |
| `auto_stop_machines` | `"off"` | The session lives in memory; never scale to zero |
| `auto_start_machines`, `min_machines_running` | true, 1 | One machine, always up |
| `[http_service.concurrency]` | `connections`, soft limit 200 | Every browser on the console holds one WebSocket |
| `[[http_service.checks]]` | `GET /health`, 15 s interval, 5 s timeout, 30 s grace | torch and highway-env take a few seconds to import |
| `[[vm]]` | `shared-cpu-2x`, 2 GB | Enough for the DQN on CPU and the simulator |

The API key is a Fly secret and never appears in the file:

```bash
grep '^TYPESAFE_API_KEY=' backend/.env | fly secrets import
fly deploy --ha=false
```

`--ha=false` matters: Fly otherwise starts two machines for high availability, and two machines would be two unrelated sessions behind one URL.

!!! warning "The machine is always on"
    With auto-stop off the machine bills continuously while it exists. Destroy the app when the deployment is no longer needed.

## Vercel: the console

- The Vercel project is `interlock-console`, rooted at `frontend/`. `frontend/.vercel/project.json` holds the link.
- `VITE_BACKEND_URL` is a build-time variable read by `frontend/src/backend-url.ts`. Set, every fetch goes to that origin and the socket to the same host as `wss`. Unset, the page stays same-origin, which is the local Vite proxy and the Playwright e2e mock backend.
- The build is `tsc` then `vite build`; the output is static.

### CORS scope

`CONSOLE_ORIGINS` adds `CORSMiddleware` for `GET` only. Browsers do not apply CORS to the WebSocket upgrade, so the variable covers exactly `/health` and `/eval/latest`. Unset, the server is same-origin only, which is what the Vite proxy needs locally.

### Order of operations

1. Deploy the backend and note its `https` URL.
2. Put that URL in `VITE_BACKEND_URL` on Vercel and deploy the console.
3. Put the console's production aliases in `CONSOLE_ORIGINS` under `[env]` in `fly.toml` and run `fly deploy` again.

## GitHub Pages: the docs

`.github/workflows/docs.yml` builds this site on every push to `main` that touches `docs/**`, `mkdocs.yml`, `pyproject.toml`, `uv.lock` or the workflow itself, and on manual dispatch.

- `uv sync --only-group docs` installs mkdocs-material from the `docs` dependency group and nothing else. The project and its runtime dependencies are omitted, so torch is never downloaded in CI.
- `uv run --no-sync mkdocs build --strict` fails the job on a broken link or a missing page.
- `actions/upload-pages-artifact` uploads `site/` and `actions/deploy-pages` publishes it.
- The repository's Pages source must be set to GitHub Actions, once, in the repository settings.

Locally the same commands are `uv run mkdocs serve -a 127.0.0.1:8080` and `uv run mkdocs build --strict`. Port 8000 belongs to the backend.

## What lives where in production

| State | Location | Survives a redeploy |
| --- | --- | --- |
| The promoted checkpoint | Image layer | Yes, rebuilt from the build context |
| The eval report for the metrics tab | Image layer | Yes |
| The Jev cache as shipped | Image layer | Yes, as a snapshot |
| Cache appends from live questions | Container filesystem | No |
| Run logs under `backend/logs/runs/` | Container filesystem | No |
| The API key | Fly secret | Yes |
| The open episode and escalation | Process memory | No; a restart starts a fresh session |

Run logs written in production are therefore available to the replay picker only until the next deploy or restart. That is acceptable for a demo; a persistent volume would be the next step if logs mattered.
