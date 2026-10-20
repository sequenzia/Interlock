"""The interlock entry point: subcommands are the modules' commands, console supervises children."""

import subprocess
import sys
from pathlib import Path
from typing import Any, get_args

import pytest
import typer
from backend import autolabel, baseline_llm, cli, evaluate, label, run_episode, train
from backend.cli import ConsoleOptions
from backend.episode import OPERATORS, OperatorName
from backend.spike import jev_spike
from typer.testing import CliRunner

runner = CliRunner()


def parse(name: str, *argv: str) -> dict[str, Any]:
    """What ``interlock <name> argv`` hands the module's command, parsed but not run."""
    command = typer.main.get_command(cli.app).commands[name]
    return command.make_context(name, list(argv)).params


def test_subcommands_are_the_modules_commands():
    registered = {c.name: c.callback for c in cli.app.registered_commands}
    assert registered == {
        "run": run_episode.command,
        "eval": evaluate.command,
        "train": train.command,
        "spike": jev_spike.command,
        "label": label.command,
        "autolabel": autolabel.command,
        "baseline": baseline_llm.command,
        "console": cli.console,
    }


def test_run_flags_are_the_module_flags():
    params = parse("run", "--shield", "off", "--seed", "3", "--jev", "mock", "--zone-at-step", "10")
    assert (params["shield"], params["seed"], params["jev"], params["zone_at_step"]) == (
        "off",
        3,
        "mock",
        10,
    )
    assert (params["rules"], params["operator"], params["t_allow"], params["t_block"]) == (
        "all",
        "simulated",
        0.3,
        0.7,
    )
    assert params["floor_s"] == 2.0 and parse("run", "--floor-s", "0")["floor_s"] == 0.0


def test_operator_choices_are_the_operators():
    assert set(get_args(OperatorName)) == set(OPERATORS)


@pytest.mark.parametrize(
    "main",
    [
        cli.main,
        run_episode.main,
        evaluate.main,
        train.main,
        jev_spike.main,
        label.main,
        autolabel.main,
        baseline_llm.main,
    ],
)
def test_help_exits_zero(main):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


def test_no_subcommand_is_a_usage_error():
    with pytest.raises(SystemExit) as exc:
        cli.main([])
    assert exc.value.code == 2


def test_eval_without_a_mode_is_a_usage_error():
    result = runner.invoke(cli.app, ["eval"])
    assert result.exit_code == 2
    assert "--mode, --sweep, --all or --report" in result.stderr


def test_unknown_rule_is_a_usage_error():
    result = runner.invoke(cli.app, ["run", "--jev", "mock", "--rules", "speed_limit,nope"])
    assert result.exit_code == 2
    assert "unknown rule ids ['nope']" in result.stderr


def test_console_flags_become_options(monkeypatch):
    seen: list[ConsoleOptions] = []
    monkeypatch.setattr(cli, "run_console", lambda opts: seen.append(opts) or 0)
    result = runner.invoke(
        cli.app,
        [
            "console",
            "--port",
            "8100",
            "--ui-port",
            "5200",
            "--no-ui",
            "--reload",
            "--open",
            "--jev",
            "mock",
            "--seed",
            "7",
            "--escalation-timeout",
            "0",
            "--model-path",
            "models/other.zip",
            "--floor-s",
            "0",
            "--cache",
            "/tmp/empty.jsonl",
        ],
    )
    assert result.exit_code == 0, result.output
    assert runner.invoke(cli.app, ["console"]).exit_code == 0
    assert seen == [
        ConsoleOptions(
            port=8100,
            ui_port=5200,
            ui=False,
            reload=True,
            open_browser=True,
            jev="mock",
            seed=7,
            escalation_timeout=0.0,
            model_path=Path("models/other.zip"),
            floor_s=0.0,
            cache=Path("/tmp/empty.jsonl"),
        ),
        ConsoleOptions(),
    ]


def test_console_exit_code_is_the_supervisors(monkeypatch):
    monkeypatch.setattr(cli, "run_console", lambda opts: 3)
    assert runner.invoke(cli.app, ["console"]).exit_code == 3


def test_console_flags_become_server_environment(monkeypatch):
    keys = ("JEV_MODE", "SEED", "ESCALATION_TIMEOUT_S", "MODEL_PATH", "JEV_CACHE_PATH", "FLOOR_S")
    for key in keys:
        monkeypatch.delenv(key, raising=False)
    assert not set(keys) & set(cli.server_env(ConsoleOptions()))
    assert cli.server_env(ConsoleOptions(floor_s=0.0))["FLOOR_S"] == "0.0"

    env = cli.server_env(
        ConsoleOptions(
            jev="mock",
            escalation_timeout=0.0,
            seed=7,
            model_path=Path("models/other.zip"),
            cache=Path("/tmp/empty.jsonl"),
        )
    )
    assert env["JEV_MODE"] == "mock"
    assert float(env["ESCALATION_TIMEOUT_S"]) == 0.0
    assert env["SEED"] == "7"
    assert env["MODEL_PATH"] == "models/other.zip"
    assert env["JEV_CACHE_PATH"] == "/tmp/empty.jsonl"


def test_console_shell_environment_passes_through_unless_a_flag_overrides(monkeypatch):
    monkeypatch.setenv("JEV_MODE", "mock")
    assert cli.server_env(ConsoleOptions())["JEV_MODE"] == "mock"
    assert cli.server_env(ConsoleOptions(jev="live"))["JEV_MODE"] == "live"


def test_console_commands_carry_ports_reload_and_open():
    opts = ConsoleOptions(port=8100, ui_port=5200, reload=True, open_browser=True)
    server = cli.server_command(opts)
    assert server[:4] == [sys.executable, "-m", "uvicorn", "backend.server:app"]
    assert server[server.index("--port") + 1] == "8100"
    assert "--reload" in server
    assert "--reload" not in cli.server_command(ConsoleOptions())

    ui = cli.ui_command(opts)
    assert ui[0] == str(cli.VITE_BIN)
    assert ui[ui.index("--port") + 1] == "5200"
    assert "--open" in ui
    assert "--open" not in cli.ui_command(ConsoleOptions())
    assert cli.ui_env(opts)["SHIELD_BACKEND"] == "http://127.0.0.1:8100"


def test_console_refuses_without_node_modules(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "VITE_BIN", tmp_path / "missing" / "vite")
    assert cli.run_console(ConsoleOptions()) == 2
    assert "pnpm install" in capsys.readouterr().err


def test_console_stops_the_other_child_when_one_exits(monkeypatch):
    sleeper = [sys.executable, "-c", "import time; time.sleep(60)"]
    quitter = [sys.executable, "-c", "import sys; sys.exit(3)"]
    started: list[subprocess.Popen] = []
    real_popen = subprocess.Popen

    def recording_popen(*args, **kwargs):
        proc = real_popen(*args, **kwargs)
        started.append(proc)
        return proc

    monkeypatch.setattr(cli, "VITE_BIN", Path(sys.executable))
    monkeypatch.setattr(cli, "server_command", lambda opts: sleeper)
    monkeypatch.setattr(cli, "ui_command", lambda opts: quitter)
    monkeypatch.setattr(subprocess, "Popen", recording_popen)

    assert cli.run_console(ConsoleOptions()) == 3
    assert len(started) == 2
    assert all(proc.poll() is not None for proc in started), "the sleeper was not stopped"


def test_console_reports_a_signalled_child_shell_style(monkeypatch):
    sleeper = [sys.executable, "-c", "import time; time.sleep(60)"]
    suicide = [sys.executable, "-c", "import os, signal; os.kill(os.getpid(), signal.SIGTERM)"]
    monkeypatch.setattr(cli, "VITE_BIN", Path(sys.executable))
    monkeypatch.setattr(cli, "server_command", lambda opts: suicide)
    monkeypatch.setattr(cli, "ui_command", lambda opts: sleeper)
    assert cli.run_console(ConsoleOptions()) == 128 + 15


def test_reap_escalates_to_sigkill_for_a_child_that_ignores_sigterm():
    stubborn = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)",
        ]
    )
    polite = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    cli.reap([stubborn, polite], grace_s=0.5)
    assert stubborn.returncode == -9
    assert polite.returncode == -15
