# CLI internals

`backend/cli.py` is the `interlock` command that `uv sync` installs through `[project.scripts]` in `pyproject.toml`. It is a thin dispatcher: four subcommands hand their flags to an existing module, and one subcommand, `console`, supervises two child processes. The user-facing flag reference is in [Command line](../../user-guide/cli.md).

## The dispatcher pattern

Every headless module exposes the same two functions:

```python
def add_arguments(parser: argparse.ArgumentParser) -> None: ...
def run_cli(args: argparse.Namespace) -> int: ...
```

`build_parser()` creates one subparser per subcommand, calls the module's `add_arguments` on it, and sets `func=module.run_cli` as the default. The module's own `main()` builds a standalone parser with the same `add_arguments`, so these two invocations parse identical flags and run identical code:

```bash
uv run interlock run --shield off --seed 3
uv run python -m backend.run_episode --shield off --seed 3
```

| Subcommand | Module | Summary in `--help` |
| --- | --- | --- |
| `run` | `backend.run_episode` | one headless episode, shield on or off, logged as JSONL |
| `eval` | `backend.evaluate` | batch evaluation: before/after, threshold sweep, report and plots |
| `train` | `backend.train` | train the DQN on task reward alone, or evaluate a checkpoint |
| `spike` | `backend.spike.jev_spike` | the Jev checklist, writes measured behaviour to a markdown file |
| `console` | none (`cli.run_console`) | start the WebSocket server and the React console together |

!!! note "Where new flags go"
    A new flag belongs in the module's `add_arguments`, never in `cli.py`. The dispatcher has no knowledge of individual flags, and `tests/test_cli.py` asserts that `interlock run` parses the module's defaults (`rules="all"`, `operator="simulated"`, thresholds 0.2 and 0.8).

`main(argv)` parses, pulls `args.func`, and exits with its return code. No subcommand is a usage error (exit 2); `--help` on the top level and on every module exits 0.

## The console subcommand

`console` has no module behind it. It turns flags into the server's environment variables, starts uvicorn and Vite as children, and stops both together.

### Flags to environment

`add_console_arguments` defines `--port` (8000), `--ui-port` (5173), `--no-ui`, `--reload`, `--open`, and five flags that map onto server variables:

| Flag | Variable |
| --- | --- |
| `--jev auto|live|mock` | `JEV_MODE` |
| `--seed N` | `SEED` |
| `--escalation-timeout S` | `ESCALATION_TIMEOUT_S` |
| `--model-path PATH` | `MODEL_PATH` |
| `--cache PATH` | `JEV_CACHE_PATH` |

`server_env(args)` copies `os.environ` and overlays only the flags that were given. A variable exported in the shell still applies when its flag is absent, and a flag wins when both exist. `tests/test_cli.py` pins both directions.

### Child commands

`server_command(args)` returns `[sys.executable, "-m", "uvicorn", "backend.server:app", "--port", <port>]` plus `--reload` when asked. It runs with `cwd=REPO_DIR`.

`ui_command(args)` returns `[frontend/node_modules/.bin/vite, "--port", <ui-port>]` plus `--open` when asked. It runs with `cwd=FRONTEND_DIR` and `ui_env(args)`, which sets `SHIELD_BACKEND=http://127.0.0.1:<port>`. `frontend/vite.config.ts` reads that variable as the proxy target for `/ws`, `/health` and `/eval`, so the console stays same-origin in the browser.

### `run_console` lifecycle

1. Unless `--no-ui`, check that the Vite binary exists. If not, print "Run `cd frontend && pnpm install` first" to stderr and return 2.
2. Install a `SIGTERM` handler that terminates the children and raises `KeyboardInterrupt`, so a `kill` of the parent unwinds through the same path as Ctrl-C.
3. Start the server, then the console, and print where each listens.
4. Poll every `POLL_S` (0.25 s). If any child has exited, print which one and its code, terminate the rest, and return that code. A child killed by a signal reports as `128 + signal`, shell style; the test checks `128 + 15` for a child that sends itself `SIGTERM`.
5. On `KeyboardInterrupt`, ignore further `SIGINT` and return 130.
6. In `finally`, restore the previous `SIGTERM` handler and `reap` the children.

### Why `SIGINT` is ignored after the first Ctrl-C

The terminal delivers Ctrl-C to the whole foreground process group, so uvicorn and Vite are already shutting down when the parent sees `KeyboardInterrupt`. Two things would go wrong if the parent reacted to a second `SIGINT`: `uv run` forwards a duplicate signal to this process, and a human's second Ctrl-C reaches the children directly anyway (uvicorn force-quits on its own second signal). So the parent lets the grace period, not a repeated signal, decide when to escalate. Sending `SIGTERM` to uvicorn too early would skip the lifespan shutdown that closes the Jev client and the JSONL log.

### `reap`

```text
wait up to STOP_GRACE_S (10 s) for every child to exit on its own
  if some remain: SIGTERM them, wait again
    if some still remain: SIGKILL them, wait once more
```

`wait_all` returns early with `False` if a Ctrl-C lands while waiting, which moves straight to the next escalation. `tests/test_cli.py` runs `reap` against one child that ignores `SIGTERM` and one that does not, and asserts return codes of `-9` and `-15`.

## What the tests pin

| Test | Guarantee |
| --- | --- |
| `test_subcommands_dispatch_to_their_modules` | Each subcommand's `func` is the module's `run_cli`; `console` is `cli.run_console` |
| `test_run_flags_are_the_module_flags` | `interlock run` exposes exactly `run_episode`'s flags and defaults |
| `test_help_exits_zero` | `--help` exits 0 for `cli.main` and every module's `main` |
| `test_no_subcommand_is_a_usage_error` | Bare `interlock` exits 2 |
| `test_eval_without_a_mode_is_a_usage_error` | `interlock eval` with no mode flag exits 2 with a hint |
| `test_console_flags_become_server_environment` | Flags set only the variables that were given |
| `test_console_shell_environment_passes_through_unless_a_flag_overrides` | Shell variables apply; flags override them |
| `test_console_commands_carry_ports_reload_and_open` | Ports, `--reload`, `--open` and `SHIELD_BACKEND` are wired |
| `test_console_refuses_without_node_modules` | Exit 2 with a `pnpm install` hint |
| `test_console_stops_the_other_child_when_one_exits` | A child exiting with 3 stops the other and returns 3 |
| `test_console_reports_a_signalled_child_shell_style` | A child killed by `SIGTERM` returns 143 |
| `test_reap_escalates_to_sigkill_for_a_child_that_ignores_sigterm` | The grace period ladder reaches `SIGKILL` |

The child-process tests monkeypatch `VITE_BIN`, `server_command` and `ui_command` to small Python one-liners, so they run without Node or a checkpoint.

## Adding a subcommand

Give the new module `add_arguments` and `run_cli`, import it in `backend/cli.py`, and add one `add("name", module, "summary")` line in `build_parser`. Add a dispatch assertion to `tests/test_cli.py` and a line to the Commands section of `CLAUDE.md`. See [Extending Interlock](../extending.md).
