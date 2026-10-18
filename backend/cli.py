"""Interlock command line: one entry point over the headless modules and the console.

    interlock run --shield on --seed 3                   # headless shielded episode
    interlock run --shield off --seed 3                  # shadow mode on the same seed
    interlock eval --seeds 0-19 --all --concurrency 2    # off, five threshold pairs, report
    interlock train --timesteps 100000 --promote         # DQN on task reward alone
    interlock spike --dry-run                            # Day 1 Jev checklist, offline
    interlock label --run <eval dir> --rule dense_traffic  # hand-label a fuzzy rule
    interlock console                                    # server on :8000, console on :5173
    interlock console --jev mock --escalation-timeout 0  # offline, wait for the operator
    interlock console --reload --open                    # dev loop, open the browser

Each subcommand takes exactly the flags of its module: ``interlock run`` and
``uv run python -m backend.run_episode`` are interchangeable, and new flags
belong in the module's ``add_arguments``, never here. ``console`` is the one
subcommand with no module behind it. It starts uvicorn and Vite as children,
turns its flags into the server's environment variables, and stops both on
Ctrl-C or when either one exits. Inside the uv environment the command is
``uv run interlock``; with ``.venv/bin`` on PATH it is just ``interlock``.
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from types import FrameType, ModuleType
from typing import Any

from backend import evaluate, label, run_episode, train
from backend.paths import REPO_DIR
from backend.spike import jev_spike

FRONTEND_DIR = REPO_DIR / "frontend"
VITE_BIN = FRONTEND_DIR / "node_modules" / ".bin" / "vite"
DEFAULT_SERVER_PORT = 8000
DEFAULT_UI_PORT = 5173
STOP_GRACE_S = 10.0
POLL_S = 0.25

Command = Callable[[argparse.Namespace], int]

CONSOLE_DOC = """Start the WebSocket server and the Vite dev server for the React console.

    interlock console                                      # live Jev when the key is present
    interlock console --jev mock --escalation-timeout 0    # offline, escalations wait for the operator
    interlock console --jev mock --cache /tmp/empty.jsonl  # empty cache: every step escalates
    interlock console --reload --open                      # dev loop, open the browser
    interlock console --no-ui                              # server only, run `pnpm dev` yourself

Flags map onto the server's environment variables (JEV_MODE, SEED,
ESCALATION_TIMEOUT_S, MODEL_PATH, JEV_CACHE_PATH); anything exported in the
shell still applies when the flag is absent. Vite proxies /ws, /health and
/eval to the server port. Ctrl-C stops both processes. If either exits on its
own, the other is stopped and its exit code is returned.
"""


def add_console_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--port", type=int, default=DEFAULT_SERVER_PORT, help="server port (default 8000)"
    )
    parser.add_argument(
        "--ui-port", type=int, default=DEFAULT_UI_PORT, help="Vite port (default 5173)"
    )
    parser.add_argument(
        "--no-ui", action="store_true", help="server only; start the console yourself"
    )
    parser.add_argument(
        "--reload", action="store_true", help="restart the server when backend/*.py changes"
    )
    parser.add_argument(
        "--open", action="store_true", help="open the console in the browser once Vite is up"
    )
    parser.add_argument(
        "--jev",
        choices=["auto", "live", "mock"],
        default=None,
        help="sets JEV_MODE (default: live when the key is present, else mock)",
    )
    parser.add_argument("--seed", type=int, default=None, help="sets SEED for the first episode")
    parser.add_argument(
        "--escalation-timeout",
        type=float,
        default=None,
        metavar="S",
        help="sets ESCALATION_TIMEOUT_S; 0 waits for the operator (default 20)",
    )
    parser.add_argument(
        "--model-path",
        type=Path,
        default=None,
        help="sets MODEL_PATH (default models/dqn_highway.zip)",
    )
    parser.add_argument(
        "--cache",
        type=Path,
        default=None,
        help="sets JEV_CACHE_PATH; an empty file makes every step escalate",
    )


def server_command(args: argparse.Namespace) -> list[str]:
    cmd = [sys.executable, "-m", "uvicorn", "backend.server:app", "--port", str(args.port)]
    if args.reload:
        cmd.append("--reload")
    return cmd


def server_env(args: argparse.Namespace) -> dict[str, str]:
    """The shell's environment plus the flags that were given, as backend.server reads them."""
    overrides: dict[str, Any] = {
        "JEV_MODE": args.jev,
        "SEED": args.seed,
        "ESCALATION_TIMEOUT_S": args.escalation_timeout,
        "MODEL_PATH": args.model_path,
        "JEV_CACHE_PATH": args.cache,
    }
    env = dict(os.environ)
    env.update({key: str(value) for key, value in overrides.items() if value is not None})
    return env


def ui_command(args: argparse.Namespace) -> list[str]:
    cmd = [str(VITE_BIN), "--port", str(args.ui_port)]
    if args.open:
        cmd.append("--open")
    return cmd


def ui_env(args: argparse.Namespace) -> dict[str, str]:
    """vite.config.ts reads SHIELD_BACKEND as the proxy target for /ws, /health and /eval."""
    return {**os.environ, "SHIELD_BACKEND": f"http://127.0.0.1:{args.port}"}


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


def run_console(args: argparse.Namespace) -> int:
    if not args.no_ui and not VITE_BIN.exists():
        print(f"{VITE_BIN} not found. Run `cd frontend && pnpm install` first.", file=sys.stderr)
        return 2
    children: dict[str, subprocess.Popen[bytes]] = {}

    def on_sigterm(signum: int, frame: FrameType | None) -> None:
        terminate(children.values())
        raise KeyboardInterrupt

    previous = signal.signal(signal.SIGTERM, on_sigterm)
    try:
        children["server"] = subprocess.Popen(
            server_command(args), cwd=REPO_DIR, env=server_env(args)
        )
        where = f"server http://127.0.0.1:{args.port}"
        if not args.no_ui:
            children["console"] = subprocess.Popen(
                ui_command(args), cwd=FRONTEND_DIR, env=ui_env(args)
            )
            where += f", console http://127.0.0.1:{args.ui_port}"
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="interlock",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    def add(name: str, module: ModuleType, summary: str) -> None:
        sub = commands.add_parser(
            name,
            help=summary,
            description=module.__doc__,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        module.add_arguments(sub)
        sub.set_defaults(func=module.run_cli)

    add("run", run_episode, "one headless episode, shield on or off, logged as JSONL")
    add("eval", evaluate, "batch evaluation: before/after, threshold sweep, report and plots")
    add("train", train, "train the DQN on task reward alone, or evaluate a checkpoint")
    add("spike", jev_spike, "Day 1 Jev checklist, writes internal/jev-spike-results.md")
    add("label", label, "hand-label candidates against a rule with no checker, for calibration")
    console = commands.add_parser(
        "console",
        help="start the WebSocket server and the React console together",
        description=CONSOLE_DOC,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_console_arguments(console)
    console.set_defaults(func=run_console)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    command: Command = args.func
    sys.exit(command(args))


if __name__ == "__main__":
    main()
