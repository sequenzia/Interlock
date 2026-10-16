import asyncio
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from backend.env import make_env
from backend.evaluate import build_report, config_label, new_run_dir, run_config
from backend.jev_client import JevCache, JevClient
from backend.policy import Policy
from backend.shield import Thresholds
from backend.train import build_model


@pytest.fixture(scope="module")
def policy() -> Iterator[Policy]:
    env = make_env()
    yield Policy(build_model(env, seed=0))
    env.close()


def test_config_labels() -> None:
    assert config_label(False, Thresholds(), None) == "off_ta0.20_tb0.80"
    assert config_label(True, Thresholds(0.3, 0.7), 10) == "on_ta0.30_tb0.70_zone10"


def test_run_config_and_report_end_to_end(policy: Policy, tmp_path: Path) -> None:
    judge = JevClient(live=None, cache=JevCache(None))
    root = tmp_path / "eval"
    seeds = [0, 1]
    for shield_on in (False, True):
        out_dir = new_run_dir(root, config_label(shield_on, Thresholds(), None))
        report = asyncio.run(
            run_config(
                policy,
                judge,
                seeds,
                shield_on=shield_on,
                thresholds=Thresholds(),
                out_dir=out_dir,
                max_steps=4,
                quiet=True,
            )
        )
        assert [e["seed"] for e in report["episodes"]] == seeds
        assert report["aggregate"]["episodes"] == 2 and report["aggregate"]["steps"] == 8
        assert (out_dir / "metrics.json").exists() and len(list(out_dir.glob("seed*.jsonl"))) == 2
        if shield_on:
            assert report["aggregate"]["escalation_rate"] == 1.0  # mock judge: every step escalates
        else:
            assert report["aggregate"]["escalation_rate"] == 0.0
    out = asyncio.run(
        run_config(
            policy,
            judge,
            seeds,
            shield_on=True,
            thresholds=Thresholds(0.5, 0.5),
            out_dir=new_run_dir(root, config_label(True, Thresholds(0.5, 0.5), None)),
            max_steps=4,
            quiet=True,
        )
    )
    assert out["label"] == "on_ta0.50_tb0.50"

    latest = build_report(root, report_path=tmp_path / "latest.json", plots_dir=tmp_path / "plots")
    assert latest["before_after"]["off"]["label"] == "off_ta0.20_tb0.80"
    assert latest["before_after"]["on"]["label"] == "on_ta0.20_tb0.80"
    assert [p["t_allow"] for p in latest["sweep"]] == [0.2, 0.5]
    assert latest["calibration"]["overall"]["n"] > 0
    assert set(latest["plots"]) == {"before_after", "tradeoff", "calibration"}
    for png in latest["plots"].values():
        assert Path(png).exists() and Path(png).stat().st_size > 10_000
    assert json.loads((tmp_path / "latest.json").read_text())["sweep"] == latest["sweep"]
