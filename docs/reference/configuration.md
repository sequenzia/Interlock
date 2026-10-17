# Configuration

Every knob in one place: environment variables, command-line flags, the constants that shape behaviour, and the files the system reads and writes. Narrative explanations live on the linked pages.

## Environment variables

Read from the process environment, with `backend/.env` loaded first by the server, `interlock run`, `interlock eval` and `interlock spike`.

| Variable | Default | Read by | Effect |
| --- | --- | --- | --- |
| `TYPESAFE_API_KEY` | unset | `typesafe_sdk` inside `LiveJudge`; presence checked by `session_from_env`, `run_episode`, `evaluate`, `jev_spike` | Authenticates live Jev calls. Unset with `JEV_MODE=auto` selects mock mode. Never committed, never logged |
| `JEV_MODE` | `auto` | `backend/server.py` `session_from_env`; `--jev` flags default to `auto` too | `live`, `mock`, or `auto` (live when the key is present) |
| `ESCALATION_TIMEOUT_S` | `20` | `session_from_env` | Seconds before an unanswered escalation is denied. `0` means wait for the operator indefinitely |
| `SEED` | `0` | `session_from_env` | Seed of the server's first episode |
| `MODEL_PATH` | `models/dqn_highway.zip` | `session_from_env` | DQN checkpoint the server loads |
| `JEV_CACHE_PATH` | `backend/logs/jev_cache.jsonl` | `session_from_env` | Content cache the judge reads at start and appends to. An empty file makes every step escalate in mock mode |
| `CONSOLE_ORIGINS` | unset | `console_origins_from_env` in `backend/server.py` | Comma-separated origins allowed to fetch `/health` and `/eval/latest` cross-origin, `GET` only. Unset keeps the server same-origin |
| `PORT` | `8000` | The Dockerfile `CMD` | Listen port inside the container |
| `SHIELD_BACKEND` | `http://127.0.0.1:8000` | `frontend/vite.config.ts` | Proxy target for `/ws`, `/health` and `/eval` in the Vite dev server. `interlock console` sets it from `--port`; the e2e config sets it to port 8001 |
| `VITE_BACKEND_URL` | unset | `frontend/src/backend-url.ts` at build time | Backend origin for a console served from another host. Unset means same-origin |
| `SDL_VIDEODRIVER`, `SDL_AUDIODRIVER` | `dummy` in the container | pygame via highway-env | Headless simulator |
| `MPLBACKEND` | `Agg` in the container | matplotlib | Headless plotting; `backend/plots.py` also selects `Agg` itself |

See [Server and session](../developer-guide/backend/server.md) and [Deployment internals](../developer-guide/deployment-internals.md).

## Command-line flags

All flags are defined in each module's `add_arguments`; `interlock <cmd>` and `python -m backend.<module>` take the same ones. See [CLI internals](../developer-guide/backend/cli.md) and [Command line](../user-guide/cli.md).

### `interlock run` (`backend/run_episode.py`)

| Flag | Default | Meaning |
| --- | --- | --- |
| `--shield on|off` | `on` | Off runs facts, Jev and checkers in shadow and executes the top action |
| `--seed N` | `0` | Episode seed |
| `--jev auto|live|mock` | `auto` | Judge mode |
| `--model ID` | `jev-1.13.0` | Jev model id |
| `--model-path PATH` | `models/dqn_highway.zip` | DQN checkpoint |
| `--rules LIST` | `all` | Comma list of preset ids, `all` (the three standing rules), or `none`. The zone rule arrives with `--zone-at-step` |
| `--zone-at-step N` | none | Drop the default work zone at this step |
| `--t-allow`, `--t-block` | `0.2`, `0.8` | Thresholds |
| `--operator simulated|approve|deny` | `simulated` | Who answers escalations |
| `--max-steps N` | none | Stop early |
| `--log PATH` | `backend/logs/runs/<run_id>.jsonl` | JSONL output |
| `--quiet` | off | Suppress the per-step line |

### `interlock eval` (`backend/evaluate.py`)

| Flag | Default | Meaning |
| --- | --- | --- |
| `--seeds RANGE` | `0-19` | `"0-19"` or `"3,7,11"` |
| `--mode off|on|shadow` | none | One configuration; `shadow` is an alias of `off` |
| `--t-allow`, `--t-block` | `0.2`, `0.8` | Thresholds for `--mode on` |
| `--sweep` | off | Shield on over the five threshold pairs |
| `--all` | off | Off, then the sweep, then the report |
| `--report` | off | Aggregate the newest run per label into the report and plots |
| `--zone-at-step N` | none | Applied to every configuration |
| `--jev auto|live|mock` | `auto` | |
| `--concurrency N` | `3` | Episodes in flight |
| `--max-steps N` | none | |
| `--model-path PATH` | `models/dqn_highway.zip` | |
| `--out DIR` | `backend/logs/eval` | Run directories root |

One of `--mode`, `--sweep`, `--all` or `--report` is required.

### `interlock train` (`backend/train.py`)

| Flag | Default | Meaning |
| --- | --- | --- |
| `--timesteps N` | `20000` | |
| `--seed N` | `0` | SB3 seed |
| `--out PATH` | `models/dqn_highway_<N>k.zip` | Checkpoint |
| `--eval-seeds RANGE` | `0-19` | Post-training greedy rollouts |
| `--eval-only PATH` | none | Skip training |
| `--promote` | off | Copy to `models/dqn_highway.zip` |

### `interlock spike` (`backend/spike/jev_spike.py`)

| Flag | Default | Meaning |
| --- | --- | --- |
| `--items LIST` | `1-8` | Checklist items, `"1,3,8"` or a range |
| `--repeats N` | `20` | Steps for the latency item |
| `--dry-run` | off | Build and validate every request without calling the API; no key needed |

### `interlock console` (`backend/cli.py`)

| Flag | Default | Effect |
| --- | --- | --- |
| `--port N` | `8000` | uvicorn port; also sets `SHIELD_BACKEND` for Vite |
| `--ui-port N` | `5173` | Vite port |
| `--no-ui` | off | Server only |
| `--reload` | off | uvicorn `--reload` |
| `--open` | off | Vite `--open` |
| `--jev auto|live|mock` | inherit | Sets `JEV_MODE` |
| `--seed N` | inherit | Sets `SEED` |
| `--escalation-timeout S` | inherit | Sets `ESCALATION_TIMEOUT_S` |
| `--model-path PATH` | inherit | Sets `MODEL_PATH` |
| `--cache PATH` | inherit | Sets `JEV_CACHE_PATH` |

"Inherit" means the shell's variable applies when the flag is absent.

## Constants worth knowing

| Constant | Value | File | Meaning |
| --- | --- | --- | --- |
| `Thresholds()` | `t_allow 0.2`, `t_block 0.8` | `backend/shield.py` | Defaults; validated `0 <= t_allow <= t_block <= 1` |
| `DEFAULT_STEPS_PER_SEC` | `2.0` | `backend/server.py` | Play speed; `set_speed` clamps to 0.1 to 10 |
| `DEFAULT_ESCALATION_TIMEOUT_S` | `20.0` | `backend/server.py` | |
| `DEFAULT_MODEL` | `jev-1.13.0` | `backend/jev_client.py` | Pinned Jev model |
| `USD_PER_INPUT_TOKEN` | `0.042 / 1_000_000` | `backend/jev_client.py` | Cost accounting; output tokens are free |
| `UNAVAILABLE_P` | `0.5` | `backend/jev_client.py` | Placeholder when the judge cannot answer |
| `LiveJudge` retry | `max_retries=2`, `timeout=10.0` s | `backend/jev_client.py` | SDK retry policy |
| `DEFAULT_CACHE_PATH` | `backend/logs/jev_cache.jsonl` | `backend/jev_client.py` | |
| `NEIGHBOUR_RANGE_M` | `200.0` | `backend/facts.py` | Vehicles farther away are reported as absent |
| `SLOWER_AHEAD_RANGE_M` | `40.0` | `backend/facts.py` | Window for "slower vehicle ahead" |
| `STEP_SECONDS` | `1.0` | `backend/facts.py` | One policy step, for zone entry prediction |
| `DEFAULT_ZONE_LANE`, `DEFAULT_ZONE_AHEAD_M`, `DEFAULT_ZONE_LENGTH_M`, `DEFAULT_ZONE_NAME` | `3`, `120.0`, `200.0`, `"work zone"` | `backend/constraints.py` | The drop-zone preset |
| `DEFAULT_CONFIG` | `lanes_count 4`, `duration 60`, `vehicles_count 30`, `policy_frequency 1` | `backend/env.py` | highway-fast-v0 overrides |
| `SWEEP` | `(0.1, 0.9) (0.2, 0.8) (0.3, 0.7) (0.4, 0.6) (0.5, 0.5)` | `backend/evaluate.py` | Threshold pairs |
| `STANDING_RULES` | the presets except `lane_closed` | `backend/evaluate.py`, `backend/run_episode.py` | What `--rules all` means |
| eval `--concurrency` | `3` | `backend/evaluate.py` | |
| `STOP_GRACE_S`, `POLL_S` | `10.0`, `0.25` | `backend/cli.py` | Console child supervision |
| `MAX_STEPS` | `2000` | `frontend/src/store.ts` | Step history kept in the browser |
| `SPEEDS` | `0.5, 1, 2, 4` | `frontend/src/components/status-strip.tsx` | Speed menu |
| `VIEW_M`, `EGO_OFFSET_M` | `240`, `70` | `frontend/src/components/road-view.tsx` | Metres across the canvas and the ego's offset from the left edge |
| Reconnect backoff | `500` ms doubling to `5000` ms | `frontend/src/ws-client.ts` | |
| Ports | server `8000`, Vite `5173`, e2e server `8001`, e2e Vite `5174`, docs `8080` recommended | | Port 8000 belongs to the backend, so serve the docs elsewhere |

## Files and directories

| Path | Role | Git |
| --- | --- | --- |
| `backend/.env` | `TYPESAFE_API_KEY` and optional `CONSOLE_ORIGINS`; copy from `backend/.env.example` | ignored |
| `models/dqn_highway.zip` | The promoted checkpoint `Policy.load` opens by default | ignored |
| `models/dqn_highway_<N>k.zip`, `*.eval.json` | Training outputs | ignored |
| `backend/logs/runs/<run_id>.jsonl` | One file per headless or console episode; the replay picker lists these | ignored |
| `backend/logs/eval/<stamp>_<label>/` | Per-seed JSONL and `metrics.json` per configuration | ignored |
| `backend/logs/spike/<stamp>/` | Raw spike requests and responses | ignored |
| `backend/logs/jev_cache.jsonl` | Append-only Jev content cache | ignored, shipped in the image when present |
| `internal/eval/latest.json` | The aggregated eval report served at `/eval/latest` | tracked |
| `internal/plots/*.png` | The three eval figures | tracked |
| `frontend/e2e/.cache/jev_cache.jsonl` | The e2e test's own empty cache | ignored by `frontend/.gitignore` |
| `site/` | mkdocs build output | build artifact, not meant to be committed |

See [Repository layout](../developer-guide/repository-layout.md) for the source tree.
