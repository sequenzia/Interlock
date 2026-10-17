# Deployment

Interlock deploys as two things built from one repository: a static console and one always-on backend container. The documentation site is a third, static, build.

## Why the backend is one container

The server is one stateful process. The simulator, the loaded DQN, the rule list and any open escalation live in memory, and the step loop runs between client messages while the episode is playing. That rules out serverless hosting for the backend, Vercel functions included: instances there are stateless, scale to zero when idle, and close WebSockets at the function's maximum duration. So the backend runs as exactly one always-on container on any host that accepts a Dockerfile, and the console points at it.

The console has no state of its own and is a plain Vite build.

## Secrets

`TYPESAFE_API_KEY` lives in `backend/.env` locally, which is gitignored and excluded from the Docker build context. In production it is injected by the host as an environment variable or a secret. It is never written to a file in the repository, never logged, and never passed on a command line in a way that lands in shell history (the Fly step below pipes it).

## Environment variables

The container reads the same variables as `uv run uvicorn backend.server:app`:

| Variable | Default | Meaning |
| --- | --- | --- |
| `TYPESAFE_API_KEY` | unset | live judging; unset means mock mode |
| `JEV_MODE` | `auto` | `live`, `mock`, or `auto` (live when the key is set) |
| `ESCALATION_TIMEOUT_S` | `20` | seconds before an unanswered escalation is denied; `0` waits forever |
| `SEED` | `0` | seed of the first episode |
| `MODEL_PATH` | `models/dqn_highway.zip` | DQN checkpoint |
| `JEV_CACHE_PATH` | `backend/logs/jev_cache.jsonl` | answer cache |
| `CONSOLE_ORIGINS` | unset | comma-separated console origins allowed to fetch `/health` and `/eval/latest` cross-origin; unset keeps the server same-origin only |
| `PORT` | `8000` | listen port inside the container |

`CONSOLE_ORIGINS` matters only for the HTTP fetches. Browsers do not apply CORS to the WebSocket upgrade, so `/ws` works from any origin regardless.

## Backend: build and check locally

```bash
docker build --platform linux/amd64 -t interlock-backend .
docker run --rm -p 8000:8000 --env-file backend/.env -e ESCALATION_TIMEOUT_S=0 interlock-backend
curl http://127.0.0.1:8000/health
```

The image carries the lock file, `backend/`, `models/dqn_highway.zip`, the eval report for the metrics tab, and the warm Jev cache when `backend/logs/jev_cache.jsonl` exists, so demo seeds answer from cache. The build fails if the checkpoint is missing. On Linux the lock resolves a CPU-only torch wheel so the image skips the CUDA libraries. Details are on [Deployment internals](../developer-guide/deployment-internals.md).

## Backend: Fly.io

`fly.toml` at the repository root describes one always-on `shared-cpu-2x` machine with auto-stop off, so the in-memory session survives idle minutes. `fly deploy` builds the Dockerfile remotely from this directory, so the gitignored checkpoint and cache ship without being committed.

```bash
brew install flyctl && fly auth login                          # once
fly apps create interlock-backend                              # once; pick another name if taken and update fly.toml
grep '^TYPESAFE_API_KEY=' backend/.env | fly secrets import    # the key stays out of shell history
fly deploy --ha=false                                          # one machine: the session is one process
curl https://interlock-backend.fly.dev/health
```

`ESCALATION_TIMEOUT_S = "0"` and `CONSOLE_ORIGINS` are set under `[env]` in `fly.toml`. `--ha=false` matters: a second machine would be a second, unrelated session.

## Console: Vercel

Deploy from `frontend/` once the backend has a public https URL:

```bash
cd frontend
vercel link --project interlock-console       # once; the project root is frontend/
vercel env add VITE_BACKEND_URL production    # https://<backend host>, no trailing slash
vercel --prod
```

`VITE_BACKEND_URL` is read at build time. Fetches go to that origin and the WebSocket to the same host as `wss`. Unset, which is the local and test case, everything stays on the page's own origin behind the Vite proxy.

## Order of operations

1. Deploy the backend and note its https URL.
2. Set `VITE_BACKEND_URL` to that URL and deploy the console.
3. Add the console's production aliases to `CONSOLE_ORIGINS` in `fly.toml` and run `fly deploy --ha=false` again.

Until step 3 the console connects and runs, but the metrics tab's fetch of `/eval/latest` is blocked by the browser.

## The live deployment

| Piece | URL |
| --- | --- |
| Console | <https://interlock-console-pied.vercel.app> |
| Backend | <https://interlock-backend.fly.dev> |

!!! warning "One session per backend"
    Every browser on the console URL shares the episode and the controls: play, reset, rules and approvals. Share the URL only when that is the demo you want. A read-only viewer mode does not exist.

## The documentation site

This site is built with MkDocs Material from `docs/` and published to GitHub Pages by `.github/workflows/docs.yml` on every push to `main` that touches the docs. The workflow installs only the `docs` dependency group, so it never downloads torch.

One-time setup in the GitHub repository: Settings, Pages, set **Source** to **GitHub Actions**. The site then appears at <https://sequenzia.github.io/interlock/>.

Locally:

```bash
uv run mkdocs serve -a 127.0.0.1:8080
uv run mkdocs build --strict
```
