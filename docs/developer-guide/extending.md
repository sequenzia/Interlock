# Extending Interlock

Recipes for the changes people actually make, each with the files to touch and the order to touch them in. Every recipe ends at the test that proves it. Before opening a pull request, run the review checklist at the bottom.

## Add a preset rule with a checker

A preset is a rule text the operator can add with one click, paired with a ground-truth checker that scores it. The checker never influences the shield.

1. `backend/constraints.py`: add a `CHECKER_<NAME>` constant and an entry in `PRESETS`. Order in `PRESETS` is the order of the chips in the console. Add a branch to `infer_checker` so a typed variant of the text still gets the checker.
2. `backend/checkers.py`: write `check_<name>(facts, constraint) -> bool` as a closed-form test on one candidate's facts, parsing any number out of `constraint.text` with `_number` so "Speed limit 20 m/s" style variants work. Register it in `CHECKERS`.
3. If the rule needs a fact the extractor does not produce, add it first (next recipe).
4. `backend/plots.py`: add the checker to `CHECKER_LABEL` and `CHECKER_SERIES`; the calibration plot skips checkers without a color.
5. `frontend/src/components/metrics-view.tsx`: add it to `CHECKER_LABEL` and `CHECKER_COLOR` for the same reason.
6. Tests: `tests/test_constraints.py` (inference) and `tests/test_checkers.py` (one crafted facts case each way).

The console needs no change: the preset chips come from the `hello` message, which the server builds from `PRESETS`. Note that `interlock run --rules all` and `interlock eval` use every preset except `lane_closed` as a standing rule, so a new preset joins the evaluation automatically.

## Add a fact

1. `backend/facts.py`: compute the value in `facts_for_action` (or a helper) from the simulator objects, with the unit in the field name (`gap_m`, `speed_mps`). Round with `_r`.
2. `sentences()` in the same file: render it as a plain sentence, since the operator sees the sentences and Jev sees the JSON.
3. `tests/test_facts.py`: assert it from a live `make_env()` state.

!!! warning "Facts are part of the cache key"
    `cache_key` hashes the model, the full state, the instructions and the criteria. Any change to the facts shape invalidates every cached answer, so the next run calls Jev for every question, the warm cache shipped in the Docker image stops matching, and the evaluation numbers need a fresh `interlock eval --all`. Add only facts a rule needs. See [Facts](backend/facts.md) and [Jev integration](backend/jev-integration.md).

## Add a field to the log record

The record is the contract between the backend, the console, replay and the eval. The order is fixed by CLAUDE.md:

1. [Log record](contracts/log-record.md): describe the field first.
2. `backend/logger.py`: add it to `build_record`.
3. `backend/episode.py`: pass it from `step()`.
4. `frontend/src/types.ts`: add it to `LogRecord`.
5. `tests/test_logger.py`: add the key to `PLAN_KEYS`; the suite fails until this matches.
6. If it feeds a counter: `episode_metrics` in `backend/metrics.py` and `replay_metrics` in `backend/server.py`, which must agree because replay recomputes metrics from records alone.
7. If it is displayed: `inspector-drawer.tsx` or `format.ts`.

Logged runs under `backend/logs/runs/` were written without the field. Replay streams them unchanged, so either make the TypeScript field optional or accept that old runs no longer replay.

## Add a WebSocket command

1. `backend/server.py`: add a `case` to the `match` in `Session.handle`. Raise `ValueError` for bad input; the surrounding `except` turns `KeyError`, `ValueError` and `TypeError` into an `error` message for that client. Broadcast whatever state changed (`self.state()`, `self.constraints_msg()`).
2. `frontend/src/types.ts`: add the variant to `ClientMessage`.
3. The component: call `send({ type: ... })` from the handler.
4. `tests/test_server.py`: open `client.websocket_connect("/ws")`, `drain_greeting`, send the JSON, and `recv_until` the expected broadcast.

## Add a server-to-client message

1. `backend/server.py`: a `Session` method that returns `{"type": ..., ...}`, broadcast from the places that change it, and sent in `connect()` if a late joiner needs it.
2. `frontend/src/types.ts`: add the variant to `ServerMessage`.
3. `frontend/src/store.ts`: a field and an action in the right slice.
4. `frontend/src/ws-client.ts`: a `case` in `apply()` that calls the action.
5. `tests/test_server.py`: assert the frame with `recv_until`.

See [WebSocket protocol](contracts/websocket-protocol.md) and [Socket client](frontend/socket-client.md).

## Add a CLI subcommand

1. Write `backend/<name>.py` with `add_arguments(parser)`, `run_cli(args) -> int` and a `main(argv)` that builds its own parser, so `python -m backend.<name>` keeps working.
2. `backend/cli.py`: one line in `build_parser`, `add("<name>", module, "summary")`. The dispatcher never grows flags of its own.
3. `tests/test_cli.py`: assert `parse("<name>").func is module.run_cli` and add `module.main` to the `test_help_exits_zero` parametrize list.

See [CLI internals](backend/cli.md).

## Change defaults

- **Thresholds.** `Thresholds` in `backend/shield.py` holds the defaults (0.3 and 0.7, moved from 0.2 and 0.8 on Oct 17 after the sweep) and validates `0 <= t_allow <= t_block <= 1`. `run_episode.add_arguments` and `backend/evaluate.py` read their flag defaults from `Thresholds()`, and `evaluate.py` adds the `SWEEP` list. The console reads thresholds from every `state` message, so it needs nothing.
- **Environment config.** `DEFAULT_CONFIG` in `backend/env.py` (`lanes_count` 4, `duration` 60, `vehicles_count` 30, `policy_frequency` 1) is sent in `hello`, so the road view's lane count and the timeline's length follow it. The policy was trained on this configuration; changing it means retraining with `interlock train` and re-running the evaluation. `facts.STEP_SECONDS` assumes `policy_frequency` 1.

## Swap the environment

The shield is domain-agnostic; the extractor is not. What depends on highway-env:

| Piece | Dependency |
| --- | --- |
| `backend/env.py` | `highway-fast-v0`, `ACTION_NAMES` from `DiscreteMetaAction.ACTIONS_ALL` |
| `backend/facts.py` | `env.unwrapped.vehicle` and `.road`, `road.neighbour_vehicles`, `lane_index`, `speed_index`, `target_speeds`, `position`, `LENGTH` |
| `backend/checkers.py` | Facts shape, lanes numbered from the left starting at 1 |
| `backend/constraints.py` | Zones as a lane plus a longitudinal interval |
| `frontend/src/components/road-view.tsx` | Straight multi-lane road, `ego.x_m`, `vehicles[].lane` |
| `backend/train.py` | The DQN recipe and `info["crashed"]`, `info["speed"]` |

What does not: `shield.py`, `jev_client.py`, `logger.py`, `metrics.py`, `evaluate.py`, `server.py`, the store, the queue, the timeline, the inspector and the metrics tab. A new domain means a new `facts.py`, new checkers and presets, a new render snapshot and road view, and a policy that exposes a ranking over discrete actions.

## Use a different Jev model

`DEFAULT_MODEL` in `backend/jev_client.py` is pinned to `jev-1.13.0`. `interlock run --model <id>` overrides it per run; the server and the eval use the default. The model id is part of the cache key, so a new model starts with a cold cache and every cached probability is re-asked. Re-run `interlock eval --all` before quoting numbers.

## Review checklist

The non-negotiables from CLAUDE.md, phrased as questions for a diff:

- Does any geometry, counting or comparison happen in a Jev question instead of in `facts.py`? It must not.
- Can a checker result reach `decide()`, `resolve()` or the operator callback? It must not, in any mode.
- Is there a code path that produces a probability without a judge answer or a cache hit? The only allowed value is 0.5 flagged `unavailable`, which escalates.
- Are the Jev instructions and criteria still positive assertions with the rule text verbatim?
- Did the log record change without the contract page, `logger.py`, `types.ts` and `PLAN_KEYS` moving together?
- Could `TYPESAFE_API_KEY` reach a log, a record, the image or a commit?
- Does `python -m backend.<module>` still work for every module behind a subcommand?
- Does a new runtime file the server reads appear in `.dockerignore` and the `Dockerfile`?
