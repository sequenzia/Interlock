# CLI internals

`backend/cli.py` is the `interlock` command that `uv sync` installs through `[project.scripts]` in `pyproject.toml`. It is a thin [Typer](https://typer.tiangolo.com) app: seven subcommands are the `command` functions of existing modules, registered under their names, and one subcommand, `console`, lives here and supervises two child processes. The user-facing flag reference is in [Command line](../../user-guide/cli.md).

## The command contract

Every module behind a subcommand exposes one function and a two-line `main`:

```python
def command(
    shield: Annotated[Literal["on", "off"], typer.Option(help="...")] = "on",
    seed: Annotated[int, typer.Option(help="episode seed")] = 0,
    quiet: Annotated[bool, typer.Option("--quiet", help="...")] = False,
    ...
) -> None:
    """One headless episode, shield on or off, printed step by step and logged as JSONL.

    ```
    interlock run --shield off --seed 3
    ```
    """


def main(argv: Sequence[str] | None = None) -> None:
    run_standalone(command, argv)
```

The signature is the flag list. A parameter named `zone_at_step` is the option `--zone-at-step`; its annotation is the type and, for a `Literal` or a `StrEnum`, the choices (`Literal["on", "off"]` renders as `<on|off>`); its default is the default. A `bool` declared as `typer.Option("--quiet")` is a flag with no `--no-quiet` twin, and a `list[Path] | None` option is repeatable. The docstring is the help page: the first line is the summary shown in `interlock --help`, and the fenced block holds the examples.

`backend/cli.py` registers each module's `command` under its subcommand name. The module's `main` runs the same function as an app of its own through `backend/cli_support.py`, so these two invocations parse identical flags and run identical code:

```bash
uv run interlock run --shield off --seed 3
uv run python -m backend.run_episode --shield off --seed 3
```

| Subcommand | Module | Summary in `--help` |
| --- | --- | --- |
| `run` | `backend.run_episode` | one headless episode, shield on or off, printed step by step and logged as JSONL |
| `eval` | `backend.evaluate` | batch evaluation over seeds: before/after, threshold sweep, report and plots |
| `train` | `backend.train` | train the DQN on task reward alone, or evaluate a checkpoint with greedy rollouts |
| `spike` | `backend.spike.jev_spike` | the Day 1 Jev checklist: measure how Jev judges hand-written driving facts |
| `label` | `backend.label` | hand-label candidates against a rule that has no checker, for calibration |
| `autolabel` | `backend.autolabel` | label the fuzzy presets by the fixed standard, for calibration only |
| `baseline` | `backend.baseline_llm` | chat-LLM baseline on logged checks: the judge's own questions, scored the same way |
| `console` | none (`cli.console`) | start the WebSocket server and the Vite dev server for the React console |

!!! note "Where new flags go"
    A new flag is a new parameter of the module's `command`, never anything in `cli.py`. The dispatcher has no knowledge of individual flags, and `tests/test_cli.py` asserts that `interlock run` parses the module's defaults (`rules="all"`, `operator="simulated"`, thresholds 0.3 and 0.7).

### Exit codes

A command returns nothing on success. A usage error either raises `typer.BadParameter`, which prints the usage line and the message (an unknown id in `--rules`), or prints a hint to stderr and raises `typer.Exit(2)` (`eval` with none of `--mode`, `--sweep`, `--all`, `--report`; `label` or `autolabel` with no records; a missing API key). The spike raises `typer.Exit(1)` on an SDK error. `console` passes the supervisor's return value through `typer.Exit`. Bare `interlock` prints the help and exits 2; `--help` and `-h` exit 0 on the top level and on every module.

### `backend/cli_support.py`

The settings every app shares. `new_app` builds a `typer.Typer` with Markdown help, so docstrings can hold fenced examples; `-h` as an alias of `--help`; and `pretty_exceptions_show_locals=False`, so a traceback never prints the environment, which carries `TYPESAFE_API_KEY`. Shell completion is on only for the top-level `interlock` app. `standalone_app(command)` wraps one command as an app of its own and `run_standalone(command, argv)` runs it, which is what every module's `main` does. `repo_relative(path)` renders a default path relative to the repo root for `show_default`, so help says `models/dqn_highway.zip` rather than an absolute path.

## The console subcommand

`console` has no module behind it. It turns flags into the server's environment variables, starts uvicorn and Vite as children, and stops both together.

### Flags to options

The `console` command takes `--port` (8000), `--ui-port` (5173), `--no-ui`, `--reload`, `--open`, and six flags that map onto server variables. It packs them into a frozen `ConsoleOptions` dataclass (`ui` is the opposite of `--no-ui`, `open_browser` is `--open`), which every helper below takes. `tests/test_cli.py` builds that dataclass directly for the helper tests and checks once, through Typer's test runner, that every flag lands in the right field.

| Flag | Variable |
| --- | --- |
| `--jev auto|live|mock` | `JEV_MODE` |
| `--seed N` | `SEED` |
| `--escalation-timeout S` | `ESCALATION_TIMEOUT_S` |
| `--floor-s S` | `FLOOR_S` |
| `--model-path PATH` | `MODEL_PATH` |
| `--cache PATH` | `JEV_CACHE_PATH` |

`server_env(opts)` copies `os.environ` and overlays only the fields that are not `None`. A variable exported in the shell still applies when its flag is absent, and a flag wins when both exist. `tests/test_cli.py` pins both directions.

### Child commands

`server_command(opts)` returns `[sys.executable, "-m", "uvicorn", "backend.server:app", "--port", <port>]` plus `--reload` when asked. It runs with `cwd=REPO_DIR`.

`ui_command(opts)` returns `[frontend/node_modules/.bin/vite, "--port", <ui-port>]` plus `--open` when asked. It runs with `cwd=FRONTEND_DIR` and `ui_env(opts)`, which sets `SHIELD_BACKEND=http://127.0.0.1:<port>`. `frontend/vite.config.ts` reads that variable as the proxy target for `/ws`, `/health` and `/eval`, so the console stays same-origin in the browser.

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
| `test_subcommands_are_the_modules_commands` | Each subcommand is registered to its module's `command`; `console` is `cli.console` |
| `test_run_flags_are_the_module_flags` | `interlock run` parses `run_episode.command`'s flags and defaults |
| `test_operator_choices_are_the_operators` | The `--operator` choices are exactly the `OPERATORS` keys |
| `test_help_exits_zero` | `--help` exits 0 for `cli.main` and every module's `main` |
| `test_no_subcommand_is_a_usage_error` | Bare `interlock` exits 2 |
| `test_eval_without_a_mode_is_a_usage_error` | `interlock eval` with no mode flag exits 2 with a hint |
| `test_unknown_rule_is_a_usage_error` | `interlock run --rules nope` exits 2 and names the id |
| `test_console_flags_become_options` | Every `console` flag lands in its `ConsoleOptions` field; no flags give the defaults |
| `test_console_exit_code_is_the_supervisors` | `run_console`'s return value is the process exit code |
| `test_console_flags_become_server_environment` | Options set only the variables that were given |
| `test_console_shell_environment_passes_through_unless_a_flag_overrides` | Shell variables apply; flags override them |
| `test_console_commands_carry_ports_reload_and_open` | Ports, `--reload`, `--open` and `SHIELD_BACKEND` are wired |
| `test_console_refuses_without_node_modules` | Exit 2 with a `pnpm install` hint |
| `test_console_stops_the_other_child_when_one_exits` | A child exiting with 3 stops the other and returns 3 |
| `test_console_reports_a_signalled_child_shell_style` | A child killed by `SIGTERM` returns 143 |
| `test_reap_escalates_to_sigkill_for_a_child_that_ignores_sigterm` | The grace period ladder reaches `SIGKILL` |

The child-process tests monkeypatch `VITE_BIN`, `server_command` and `ui_command` to small Python one-liners, so they run without Node or a checkpoint. Module tests that need the flags, such as `tests/test_autolabel.py`, drive `standalone_app(command)` through `typer.testing.CliRunner`; tests that only need the logic call `command(...)` as a plain function.

## Adding a subcommand

Give the new module a `command` function with Typer-annotated parameters and a `main` that calls `run_standalone`, import it in `backend/cli.py`, and add one `app.command("name")(module.command)` line. Add the module to the dispatch assertion and the `test_help_exits_zero` list in `tests/test_cli.py`, and a line to the Commands section of `CLAUDE.md`. See [Extending Interlock](../extending.md).
