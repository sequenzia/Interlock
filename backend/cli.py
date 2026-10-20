"""Interlock command line: one entry point over the headless modules and the console.

```
interlock run --shield on --seed 3                   # headless shielded episode
interlock run --shield off --seed 3                  # shadow mode on the same seed
interlock eval --seeds 0-19 --all --concurrency 2    # off, five threshold pairs, report
interlock train --timesteps 100000 --promote         # DQN on task reward alone
interlock spike --dry-run                            # Day 1 Jev checklist, offline
interlock label --run <eval dir> --rule dense_traffic   # hand-label a fuzzy rule
interlock autolabel --dry-run                        # the fuzzy rules by the fixed standard
interlock baseline --dry-run                         # chat-LLM baseline, send nothing
interlock console                                    # server on :8000, console on :5173
interlock console --jev mock --escalation-timeout 0  # offline, wait for the operator
```

Every subcommand but `console` is a module's `command` registered under its
name, so `python -m backend.<module>` takes the same flags and new flags belong
in the module, never here. `console` starts uvicorn and Vite as children, turns
its flags into the server's environment variables, and stops both on Ctrl-C or
when either one exits. Inside the uv environment the command is `uv run
interlock`; with `.venv/bin` on PATH it is just `interlock`.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import Annotated, Any

import typer

from backend import autolabel, baseline_llm, evaluate, label, run_episode, train
from backend.cli_support import new_app
from backend.jev_client import JevMode
from backend.paths import REPO_DIR
from backend.spike import jev_spike

FRONTEND_DIR = REPO_DIR / "frontend"
VITE_BIN = FRONTEND_DIR / "node_modules" / ".bin" / "vite"
DEFAULT_SERVER_PORT = 8000
DEFAULT_UI_PORT = 5173
STOP_GRACE_S = 10.0
POLL_S = 0.25

app = new_app(name="interlock", help=__doc__, add_completion=True, no_args_is_help=True)
app.command("run")(run_episode.command)
app.command("eval")(evaluate.command)
app.command("train")(train.command)
app.command("spike")(jev_spike.command)
app.command("label")(label.command)
app.command("autolabel")(autolabel.command)
app.command("baseline")(baseline_llm.command)


@dataclass(frozen=True)
class ConsoleOptions:
    """The console flags. A server field left ``None`` keeps whatever the shell exported."""

    port: int = DEFAULT_SERVER_PORT
    ui_port: int = DEFAULT_UI_PORT
    ui: bool = True
    reload: bool = False
    open_browser: bool = False
    jev: JevMode | None = None
    seed: int | None = None
    escalation_timeout: float | None = None
    model_path: Path | None = None
    floor_s: float | None = None
    cache: Path | None = None


def server_command(opts: ConsoleOptions) -> list[str]:
    cmd = [sys.executable, "-m", "uvicorn", "backend.server:app", "--port", str(opts.port)]
    if opts.reload:
        cmd.append("--reload")
    return cmd


def server_env(opts: ConsoleOptions) -> dict[str, str]:
    """The shell's environment plus the flags that were given, as backend.server reads them."""
    overrides: dict[str, Any] = {
        "JEV_MODE": opts.jev,
        "SEED": opts.seed,
        "ESCALATION_TIMEOUT_S": opts.escalation_timeout,
        "MODEL_PATH": opts.model_path,
        "JEV_CACHE_PATH": opts.cache,
        "FLOOR_S": opts.floor_s,
    }
    env = dict(os.environ)
    env.update({key: str(value) for key, value in overrides.items() if value is not None})
    return env


def ui_command(opts: ConsoleOptions) -> list[str]:
    cmd = [str(VITE_BIN), "--port", str(opts.ui_port)]
    if opts.open_browser:
        cmd.append("--open")
    return cmd


def ui_env(opts: ConsoleOptions) -> dict[str, str]:
    """vite.config.ts reads SHIELD_BACKEND as the proxy target for /ws, /health and /eval."""
    return {**os.environ, "SHIELD_BACKEND": f"http://127.0.0.1:{opts.port}"}


def terminate(procs: Iterable[subprocess.Popen[bytes]]) -> None:
    for proc in procs:
        if proc.poll() is None:
            proc.terminate()


def wait_all(procs: Sequence[subprocess.Popen[bytes]], timeout_s: float) -> bool:
    """True once every child has exited. A Ctrl-C while waiting returns False early."""
    deadline = time.monotonic() + timeout_s
    try:
        for proc in procs:
            proc.wait(timeout=max(0.0, deadline - time.monotonic()))
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        return False
    return True


def reap(procs: Iterable[subprocess.Popen[bytes]], grace_s: float) -> None:
    """Wait for children that are already stopping, SIGTERM the rest, SIGKILL any straggler."""
    procs = list(procs)
    if wait_all(procs, grace_s):
        return
    terminate(procs)
    if wait_all(procs, grace_s):
        return
    for proc in procs:
        if proc.poll() is None:
            proc.kill()
    wait_all(procs, grace_s)


def run_console(opts: ConsoleOptions) -> int:
    """Supervise the server and the console; the return value is the process exit code."""
    if opts.ui and not VITE_BIN.exists():
        print(f"{VITE_BIN} not found. Run `cd frontend && pnpm install` first.", file=sys.stderr)
        return 2
    children: dict[str, subprocess.Popen[bytes]] = {}

    def on_sigterm(signum: int, frame: FrameType | None) -> None:
        terminate(children.values())
        raise KeyboardInterrupt

    previous = signal.signal(signal.SIGTERM, on_sigterm)
    try:
        children["server"] = subprocess.Popen(
            server_command(opts), cwd=REPO_DIR, env=server_env(opts)
        )
        where = f"server http://127.0.0.1:{opts.port}"
        if opts.ui:
            children["console"] = subprocess.Popen(
                ui_command(opts), cwd=FRONTEND_DIR, env=ui_env(opts)
            )
            where += f", console http://127.0.0.1:{opts.ui_port}"
        print(f"interlock console: {where}. Ctrl-C stops everything.", flush=True)
        while True:
            for name, proc in children.items():
                code = proc.poll()
                if code is not None:
                    print(
                        f"interlock console: {name} exited with code {code}, stopping the rest",
                        file=sys.stderr,
                        flush=True,
                    )
                    terminate(children.values())
                    return code if code >= 0 else 128 - code
            time.sleep(POLL_S)
    except KeyboardInterrupt:
        # The terminal's SIGINT reached both children too, so they are already stopping.
        # Ignore further SIGINTs here: `uv run` forwards a duplicate to this process, and a
        # human's second Ctrl-C goes straight to the children anyway (uvicorn force-quits
        # on its own second signal). The grace period, not a repeated signal, decides when
        # the parent sends SIGTERM, which would make uvicorn skip the lifespan shutdown
        # that closes the Jev client and the log.
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        return 130
    finally:
        signal.signal(signal.SIGTERM, previous)
        reap(children.values(), STOP_GRACE_S)


@app.command("console")
def console(
    port: Annotated[int, typer.Option(help="server port")] = DEFAULT_SERVER_PORT,
    ui_port: Annotated[int, typer.Option(help="Vite port")] = DEFAULT_UI_PORT,
    no_ui: Annotated[
        bool, typer.Option("--no-ui", help="server only; start the console yourself")
    ] = False,
    reload: Annotated[
        bool, typer.Option("--reload", help="restart the server when `backend/*.py` changes")
    ] = False,
    open_browser: Annotated[
        bool, typer.Option("--open", help="open the console in the browser once Vite is up")
    ] = False,
    jev: Annotated[
        JevMode | None,
        typer.Option(help="sets JEV_MODE (default: live when the key is present, else mock)"),
    ] = None,
    seed: Annotated[int | None, typer.Option(help="sets SEED for the first episode")] = None,
    escalation_timeout: Annotated[
        float | None,
        typer.Option(
            metavar="S", help="sets ESCALATION_TIMEOUT_S; 0 waits for the operator (default 20)"
        ),
    ] = None,
    model_path: Annotated[
        Path | None, typer.Option(help="sets MODEL_PATH (default models/dqn_highway.zip)")
    ] = None,
    floor_s: Annotated[
        float | None,
        typer.Option(
            metavar="S", help="sets FLOOR_S, the time to collision floor (default 2.0; 0 disables)"
        ),
    ] = None,
    cache: Annotated[
        Path | None,
        typer.Option(help="sets JEV_CACHE_PATH; an empty file makes every step escalate"),
    ] = None,
) -> None:
    """Start the WebSocket server and the Vite dev server for the React console.

    ```
    interlock console                                      # live Jev when the key is present
    interlock console --jev mock --escalation-timeout 0    # offline, escalations wait for the operator
    interlock console --jev mock --cache /tmp/empty.jsonl  # empty cache: every step escalates
    interlock console --reload --open                      # dev loop, open the browser
    interlock console --no-ui                              # server only, run `pnpm dev` yourself
    ```

    Flags map onto the server's environment variables; anything exported in the shell still
    applies when the flag is absent. Vite proxies /ws, /health and /eval to the server port.
    Ctrl-C stops both processes. If either exits on its own, the other is stopped and its exit
    code is returned.
    """
    code = run_console(
        ConsoleOptions(
            port=port,
            ui_port=ui_port,
            ui=not no_ui,
            reload=reload,
            open_browser=open_browser,
            jev=jev,
            seed=seed,
            escalation_timeout=escalation_timeout,
            model_path=model_path,
            floor_s=floor_s,
            cache=cache,
        )
    )
    if code:
        raise typer.Exit(code)


def main(argv: Sequence[str] | None = None) -> None:
    """The ``interlock`` script; ``argv`` defaults to the process arguments."""
    app(args=argv)


if __name__ == "__main__":
    main()
