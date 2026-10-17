# Troubleshooting

Symptoms, their usual cause, and the fix. Most of these are visible in the status strip or in the server's log line at startup, which reads `session: jev <mode>, model <file>, escalation timeout <s>`.

## Starting up

| Symptom | Cause | Fix |
| --- | --- | --- |
| `Policy.load` fails, or `docker build` fails at `COPY models/dqn_highway.zip` | the checkpoint is not committed and has not been trained | `uv run interlock train --timesteps 100000 --promote`, or pass `--model-path` / `MODEL_PATH` for an existing zip. See [Install](install.md). |
| `interlock console` prints `.../frontend/node_modules/.bin/vite not found. Run cd frontend && pnpm install first.` and exits with code 2 | frontend dependencies are not installed | `cd frontend && pnpm install` |
| Port 8000 or 5173 already in use | another console, a stale uvicorn, or the Playwright test still running | stop it, or use `--port` and `--ui-port`; the e2e test uses 8001 and 5174 on purpose |
| pygame or SDL display errors on a headless machine | highway-env imports pygame | export `SDL_VIDEODRIVER=dummy` and `SDL_AUDIODRIVER=dummy`, as the Dockerfile does |
| `interlock spike` exits with code 2 saying the key is not set | the spike calls the API | add the key to `backend/.env`, or use `--dry-run` |

## Judge mode

| Symptom | Cause | Fix |
| --- | --- | --- |
| The strip says `jev mock` when you expected live | `TYPESAFE_API_KEY` is not in `backend/.env`, or `JEV_MODE=mock` is exported | set the key, or pass `--jev live`; `auto` picks live only when the key is present |
| Every step escalates with "judge unavailable" | mock mode with a cold cache (`--cache /tmp/empty.jsonl` does this deliberately), or live mode with the network down | add the key for live mode; in live mode check connectivity. The 0.5 is a placeholder, answer the card yourself. See [Approval queue](console/approval-queue.md). |
| The strip shows `cache` for every step | the warm cache already has every answer for this seed and rule set | expected; type a new rule or change seed to see live calls |
| A rule you typed says "no checker, not scored" | the text matched none of the preset patterns | expected; the shield still enforces it, it is simply excluded from violation counts and calibration. See [Rules and zones](console/rules-and-zones.md). |

## In the console

| Symptom | Cause | Fix |
| --- | --- | --- |
| "not connected to the server" toast | a command was sent while the socket was closed | wait for the green dot; the client reconnects with backoff up to five seconds. If it never does, the server is down. |
| The "step" button is greyed out | the episode is playing, an escalation is open, or the episode is over | pause, answer the card, or reset |
| "waiting on operator" is shown and the episode does not advance | an escalation is open; with a timeout of 0 the server waits for an answer indefinitely | answer the card in this browser or any other on the same URL; a refresh re-sends the open escalation on connect |
| Rules, zones, thresholds and the shield toggle are disabled | the session is in replay | press "back to live" |
| The timeline is empty after a refresh | the session was reset, or the server restarted | expected; a refresh mid-episode restores the history, a new episode starts at zero |
| The metrics tab says "No evaluation yet" | no report at `internal/eval/latest.json` | `uv run interlock eval --seeds 0-19 --all`; see [Evaluation and results](evaluation.md) |
| Error toast: `set_thresholds: need 0 <= t_allow <= t_block <= 1` | a threshold command that inverted the band | the sliders prevent this; a hand-written client should keep allow at or below block |
| Error toast: `resolve: no open escalation ...` | the card was answered elsewhere or timed out first | nothing to do |

## Hosted

| Symptom | Cause | Fix |
| --- | --- | --- |
| The console loads, the socket connects, but the metrics tab fails with a CORS error on `/eval/latest` | `CONSOLE_ORIGINS` on the backend does not include the console's origin | add the exact origin (scheme and host, no path) to `CONSOLE_ORIGINS` and redeploy the backend. See [Deployment](deployment.md). |
| The socket never connects from the hosted console | the backend URL is http while the console is https, so the browser refuses the mixed `ws` connection | the backend must be reachable over https; `VITE_BACKEND_URL` then yields `wss` automatically |
| The hosted console shows a different episode than you started | someone else on the URL pressed reset or play | one session per backend; share the URL deliberately |
| The Fly machine is stopped or the session resets between visits | auto-stop is on or more than one machine exists | `auto_stop_machines = "off"` and `min_machines_running = 1` in `fly.toml`, and deploy with `--ha=false` |
| `fly deploy` builds without the checkpoint or cache | the files are gitignored but ship through the build context; the build runs from a directory without them | run `fly deploy` from the repository root with `models/dqn_highway.zip` present |

## Headless runs

| Symptom | Cause | Fix |
| --- | --- | --- |
| `interlock run` exits with code 2 and `unknown rule ids` | `--rules` names something other than the four checker ids | use `speed_limit`, `lane_change_gap`, `left_lane_passing`, `lane_closed`, `all` or `none` |
| `interlock eval` exits with code 2 saying to choose a mode | none of `--mode`, `--sweep`, `--all`, `--report` was given | pick one |
| The eval is slow or hits rate limits | too many episodes in flight | `--concurrency 2` |

## Tests

| Symptom | Cause | Fix |
| --- | --- | --- |
| `pnpm test:e2e` cannot start its backend | the e2e config launches `uv run uvicorn` on port 8001 from the repo root | make sure `uv sync --all-groups` ran and ports 8001 and 5174 are free |
| Playwright complains about a missing browser | browsers are installed separately | `cd frontend && pnpm exec playwright install chromium` |

If none of these match, the per-step JSONL under `backend/logs/runs/` and the server log line tell you exactly what the shield saw. The record format is on the [Log record](../developer-guide/contracts/log-record.md) page.
