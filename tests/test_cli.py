"""The interlock entry point: subcommands reuse their module's flags, console supervises children."""

import subprocess
import sys
from pathlib import Path

import pytest
from backend import cli, evaluate, run_episode, train
from backend.spike import jev_spike


def parse(*argv: str):
    return cli.build_parser().parse_args(list(argv))


def test_subcommands_dispatch_to_their_modules():
    assert parse("run", "--seed", "3").func is run_episode.run_cli
    assert parse("eval", "--mode", "on").func is evaluate.run_cli
    assert parse("train", "--timesteps", "5").func is train.run_cli
    assert parse("spike", "--dry-run").func is jev_spike.run_cli
    assert parse("console").func is cli.run_console


def test_run_flags_are_the_module_flags():
    args = parse("run", "--shield", "off", "--seed", "3", "--jev", "mock", "--zone-at-step", "10")
    assert (args.shield, args.seed, args.jev, args.zone_at_step) == ("off", 3, "mock", 10)
    assert (args.rules, args.operator, args.t_allow, args.t_block) == ("all", "simulated", 0.2, 0.8)


@pytest.mark.parametrize(
    "main", [cli.main, run_episode.main, evaluate.main, train.main, jev_spike.main]
)
def test_help_exits_zero(main):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


def test_no_subcommand_is_a_usage_error():
    with pytest.raises(SystemExit) as exc:
        cli.main([])
    assert exc.value.code == 2


def test_eval_without_a_mode_is_a_usage_error(capsys):
    assert evaluate.run_cli(parse("eval")) == 2
    assert "--mode, --sweep, --all or --report" in capsys.readouterr().err


def test_console_flags_become_server_environment(monkeypatch):
    for key in ("JEV_MODE", "SEED", "ESCALATION_TIMEOUT_S", "MODEL_PATH", "JEV_CACHE_PATH"):
        monkeypatch.delenv(key, raising=False)
    bare = cli.server_env(parse("console"))
    assert not {"JEV_MODE", "SEED", "ESCALATION_TIMEOUT_S", "MODEL_PATH", "JEV_CACHE_PATH"} & set(
        bare
    )

    env = cli.server_env(
        parse(
            "console",
            "--jev",
            "mock",
            "--escalation-timeout",
            "0",
            "--seed",
            "7",
            "--model-path",
            "models/other.zip",
            "--cache",
            "/tmp/empty.jsonl",
        )
    )
    assert env["JEV_MODE"] == "mock"
    assert float(env["ESCALATION_TIMEOUT_S"]) == 0.0
    assert env["SEED"] == "7"
    assert env["MODEL_PATH"] == "models/other.zip"
    assert env["JEV_CACHE_PATH"] == "/tmp/empty.jsonl"


def test_console_shell_environment_passes_through_unless_a_flag_overrides(monkeypatch):
    monkeypatch.setenv("JEV_MODE", "mock")
    assert cli.server_env(parse("console"))["JEV_MODE"] == "mock"
    assert cli.server_env(parse("console", "--jev", "live"))["JEV_MODE"] == "live"


def test_console_commands_carry_ports_reload_and_open():
    args = parse("console", "--port", "8100", "--ui-port", "5200", "--reload", "--open")
    server = cli.server_command(args)
    assert server[:4] == [sys.executable, "-m", "uvicorn", "backend.server:app"]
    assert server[server.index("--port") + 1] == "8100"
    assert "--reload" in server
    assert "--reload" not in cli.server_command(parse("console"))

    ui = cli.ui_command(args)
    assert ui[0] == str(cli.VITE_BIN)
    assert ui[ui.index("--port") + 1] == "5200"
    assert "--open" in ui
    assert "--open" not in cli.ui_command(parse("console"))
    assert cli.ui_env(args)["SHIELD_BACKEND"] == "http://127.0.0.1:8100"


def test_console_refuses_without_node_modules(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "VITE_BIN", tmp_path / "missing" / "vite")
    assert cli.run_console(parse("console")) == 2
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
    monkeypatch.setattr(cli, "server_command", lambda args: sleeper)
    monkeypatch.setattr(cli, "ui_command", lambda args: quitter)
    monkeypatch.setattr(subprocess, "Popen", recording_popen)

    assert cli.run_console(parse("console")) == 3
    assert len(started) == 2
    assert all(proc.poll() is not None for proc in started), "the sleeper was not stopped"


def test_console_reports_a_signalled_child_shell_style(monkeypatch):
    sleeper = [sys.executable, "-c", "import time; time.sleep(60)"]
    suicide = [sys.executable, "-c", "import os, signal; os.kill(os.getpid(), signal.SIGTERM)"]
    monkeypatch.setattr(cli, "VITE_BIN", Path(sys.executable))
    monkeypatch.setattr(cli, "server_command", lambda args: suicide)
    monkeypatch.setattr(cli, "ui_command", lambda args: sleeper)
    assert cli.run_console(parse("console")) == 128 + 15


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
