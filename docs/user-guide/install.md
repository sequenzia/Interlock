# Install

Interlock is a Python backend plus a Vite console. Both run on a laptop. Live judging needs a TypeSafe API key; everything else works offline in mock mode.

## Requirements

| Tool | Needed for | Notes |
| --- | --- | --- |
| Python 3.12 via [uv](https://docs.astral.sh/uv/) | backend, CLI, tests, docs | `uv` installs the interpreter from `.python-version` |
| Node 20 or newer with [pnpm](https://pnpm.io/) | the console | pnpm is the only supported package manager for `frontend/` |
| A TypeSafe API key | live judging | without it every run is mock mode |
| Docker | the backend container only | not needed to run locally |
| `flyctl` and the Vercel CLI | hosting only | see [Deployment](deployment.md) |

Context7 or other documentation proxies are not involved; library docs come from the official sites.

## Backend

```bash
git clone git@github.com:sequenzia/interlock.git
cd interlock
uv sync --all-groups
```

`uv sync --all-groups` installs the runtime dependencies, the `dev` group (pytest, ruff) and the `docs` group (MkDocs Material). It also installs the `interlock` command inside the environment, so every command below starts with `uv run`.

### The API key

```bash
cp backend/.env.example backend/.env
```

Open `backend/.env` and set `TYPESAFE_API_KEY`. The file is gitignored. The key is read from that file by the CLI and the server, is never written to a log or a record, and must never be committed or passed on a command line.

!!! note "No key is fine"
    With the key unset the backend picks mock mode automatically. Mock mode serves cached answers and escalates anything it has not seen. See [Concepts](concepts.md).

### The model checkpoint

The trained DQN is not committed. The backend loads `models/dqn_highway.zip` by default and refuses to start without it.

Train one yourself. The 100k-step run takes about 25 minutes on a laptop and `--promote` copies it to the default path:

```bash
uv run interlock train --timesteps 100000 --promote
```

Or point at an existing checkpoint with `--model-path` on `interlock run` and `interlock eval`, or `MODEL_PATH` / `--model-path` for the console. Training details are on the [Training and policy](../developer-guide/backend/training.md) page.

## Console

```bash
cd frontend
pnpm install
cd ..
```

The Playwright smoke test additionally needs a browser:

```bash
cd frontend && pnpm exec playwright install chromium
```

## Verify

```bash
uv run pytest
uv run interlock --help
cd frontend && pnpm typecheck
```

The test suite runs offline with an untrained policy and the mock judge, so it passes without a key and without a checkpoint. `interlock --help` lists the eight subcommands: `run`, `eval`, `train`, `spike`, `label`, `autolabel`, `baseline`, `console`.

## Documentation site

The site you are reading builds from `docs/` with MkDocs Material, installed by the `docs` group:

```bash
uv run mkdocs serve -a 127.0.0.1:8080
uv run mkdocs build --strict
```

Port 8000 belongs to the backend, so the docs server is bound to 8080.

## Next

Follow the [Quickstart](quickstart.md) for your first headless run and your first console session.
