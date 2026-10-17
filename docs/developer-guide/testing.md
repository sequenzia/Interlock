# Testing

The backend has a pytest suite that runs offline in about five seconds: 100 tests collected from 14 files under `tests/`, with no network, no API key and no trained checkpoint required. The frontend has a strict typecheck and a two-test Playwright smoke run against a mock backend. There are no live Jev tests and no frontend unit tests.

## Running

```bash
uv run pytest                                   # the whole suite
uv run pytest tests/test_shield.py -q           # one file
uv run pytest -k "escalation or replay"         # by name
uv run ruff format backend tests && uv run ruff check backend tests
cd frontend && pnpm typecheck
cd frontend && pnpm test:e2e
```

`pyproject.toml` sets `testpaths = ["tests"]` and relaxes the `ANN` rules for tests only, so test functions need no annotations.

## Suite map

| File | Covers |
| --- | --- |
| `test_env.py` | Action names match highway-env, the demo config and overrides, seeded reset reproducibility |
| `test_policy.py` | Ranking covers every action in Q order, the top rank equals SB3's greedy prediction, finite Q-values, the promoted checkpoint when present |
| `test_facts.py` | Lane clamping, the facts schema from live simulator state, gaps against the simulator geometry, the lane-to-the-right block, zone facts, snapshots and sentences, edge lane changes as no-ops |
| `test_spike_facts.py` | The spike's hand-written fact builder, the speed grid, positive question phrasing with the rule verbatim, shape A state keys |
| `test_constraints.py` | Preset checker inference including typed variants, ids and toggling, empty text rejection, zone drop and retirement |
| `test_checkers.py` | Each checker on crafted facts, free-text rules label `None`, `label_all` covers every pair |
| `test_jev_client.py` | Question text, cache key dependencies, mock-mode misses at 0.5, caching and replay of live answers, outage after a warm cache, no constraints means no request, `make_client` modes, the judge record |
| `test_shield.py` | Every branch of `decide`, `fallback_action` and `resolve`, inclusive band edges, threshold validation |
| `test_logger.py` | Run id format, the record has exactly the contract keys, JSONL round trip |
| `test_episode.py` | Mock shield-on escalates every step and logs, the simulated operator denies true violations, shield off in shadow, no rules means allow, a mid-episode zone drop appears in the facts, a passed zone retires its rule |
| `test_metrics.py` | Episode counters and rates, pooled aggregates, reliability bins and ECE |
| `test_evaluate.py` | Configuration labels and a full `run_config` plus `build_report` in a temp directory |
| `test_server.py` | Connect greeting, history for late joiners, the escalation round trip with the mock judge, play and pause, shield and threshold and speed and reset commands, constraint broadcasts, a step record over the socket, replay streaming, reset during an open escalation, `/eval/latest`, CORS with and without `CONSOLE_ORIGINS` |
| `test_cli.py` | Subcommand dispatch, module flags, `--help`, usage errors, console flags to environment, child process supervision and reaping |

## Shared patterns

**An untrained policy.** Module-scoped fixtures build `Policy(build_model(make_env(), seed=0))` from `backend.train`. The Q-values are arbitrary but deterministic, which is all the shield, the logger and the server need. Only `test_default_checkpoint_loads_and_ranks_when_present` touches `models/dqn_highway.zip`, and it calls `pytest.skip("no promoted checkpoint in models/")` when the file is absent.

**An offline judge.** `JevClient(live=None, cache=JevCache(None))` is mock mode with an in-memory cache: every question misses and comes back at p = 0.5 with source `unavailable`, so every shielded step escalates. `test_jev_client.py` adds a `FakeJudge` that stands in for `LiveJudge`: it returns scripted probabilities per action, records every `(state, questions)` call, and returns `None` when constructed with no table, which is how an outage after a warm cache is tested without a network.

**The server through TestClient.** `tests/test_server.py` builds `Session(policy, JevClient(...), escalation_timeout_s=None)` and wraps `create_app(session)` in FastAPI's `TestClient`. The fixture monkeypatches `server.RUNS_DIR` and `backend.logger.LOGS_DIR` to `tmp_path` so runs never land in `backend/logs/`. Two helpers keep the tests readable: `drain_greeting(ws)` consumes `hello`, `state`, `history` and `metrics` in order and returns the `hello`; `recv_until(ws, kind, **fields)` reads frames until one matches. The CORS tests set `CONSOLE_ORIGINS` with `monkeypatch.setenv`, build a fresh `create_app(session)` so the lifespan reads it, and check the `access-control-allow-origin` header on `/health` for a listed origin and for a stranger.

**The record contract guard.** `tests/test_logger.py` defines `PLAN_KEYS`, the exact top-level key set of a log record. `test_record_has_exactly_the_plan_keys_and_roundtrips` and the episode tests assert `set(record) == PLAN_KEYS`, so adding or renaming a field fails here first. See [Log record](contracts/log-record.md).

**Process supervision.** `tests/test_cli.py` tests `run_console` without Vite or uvicorn by monkeypatching `VITE_BIN`, `server_command` and `ui_command` to small `python -c` children: one sleeps, one exits with code 3 or kills itself with SIGTERM. The tests check that the survivor is stopped, that the exit code is passed through shell-style (`128 + 15` for a signalled child), and that `reap()` escalates from SIGTERM to SIGKILL for a child that ignores the first.

## The smoke test

`frontend/e2e/smoke.spec.ts` runs under `frontend/playwright.config.ts`, which starts its own stack so an open dev console on 8000 and 5173 is untouched:

- `uv run uvicorn backend.server:app --host 127.0.0.1 --port 8001` from the repo root with `JEV_MODE=mock`, `ESCALATION_TIMEOUT_S=0`, `SEED=0` and `JEV_CACHE_PATH=frontend/e2e/.cache/jev_cache.jsonl`, a cache path that holds nothing, so every question misses.
- `pnpm exec vite --port 5174 --strictPort` with `SHIELD_BACKEND=http://127.0.0.1:8001`.

The first test connects, sees `jev mock` and the empty rules message, adds the speed limit preset, steps once, waits for `waiting on operator` and the `judge unavailable` badge, denies, opens step 0 in the inspector, confirms `operator deny`, presses Escape, drops a work zone and checks the zone row and its `lane_closed` checker appear. The second test switches to the metrics view and accepts either the report's first tile or the "No evaluation yet" message, then returns to the console. Viewport is 1600 by 900, Chromium only, traces kept on failure under `frontend/test-results/`.

## What is not covered

- No test calls Jev. `test_live_judge_constructs_and_closes_without_network` only builds and closes a `LiveJudge`. Measured behaviour comes from `interlock spike` and `interlock eval`, which are tools, not tests.
- No frontend unit tests. The store, the selectors and `apply()` are exercised only through the smoke test and `pnpm typecheck`.
- The canvas in `road-view.tsx` is not asserted anywhere; the smoke test checks the panel title only.
- Training is not tested beyond `build_model`; `interlock train` is run by hand.
