import asyncio
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from backend.env import make_env
from backend.evaluate import build_report, config_label, new_run_dir, newest_runs, run_config
from backend.jev_client import JevCache, JevClient
from backend.label import load_labels
from backend.policy import Policy
from backend.shield import Thresholds
from backend.train import build_model


@pytest.fixture(scope="module")
def policy() -> Iterator[Policy]:
    env = make_env()
    yield Policy(build_model(env, seed=0))
    env.close()


def test_config_labels() -> None:
    assert config_label(False, Thresholds(), None) == "off"
    assert config_label(False, Thresholds(), None, 0.0) == "off"  # no floor off either
    assert config_label(True, Thresholds(), None, 0.0) == "on_ta0.30_tb0.70_nofloor"
    assert config_label(True, Thresholds(), 10, 0.0) == "on_ta0.30_tb0.70_nofloor_zone10"
    assert config_label(True, Thresholds(), None, 1.0) == "on_ta0.30_tb0.70_floor1"
    assert config_label(True, Thresholds(), None, 2.0) == "on_ta0.30_tb0.70"
    assert config_label(False, Thresholds(0.2, 0.8), 10) == "off_zone10"
    assert config_label(True, Thresholds(0.3, 0.7), 10) == "on_ta0.30_tb0.70_zone10"


def test_newest_runs_recomputes_labels_and_keeps_the_newest_per_label(tmp_path: Path) -> None:
    runs = (
        ("2026-10-17T23-31-12", "off_ta0.20_tb0.80", False),  # stored label from before
        ("2026-10-18T02-02-22", "off_ta0.30_tb0.70", False),
        ("2026-10-18T02-06-19", "on_ta0.30_tb0.70", True),  # before the floor: no floor_s field
        ("2026-10-18T05-00-00", "on_ta0.30_tb0.70_floor1", True, 1.0),
        ("2026-10-18T05-10-00", "on_ta0.30_tb0.70", True, 2.0),
    )
    for stamp, label, shield_on, *floor in runs:
        d = tmp_path / f"{stamp}_{label}"
        d.mkdir()
        metrics = {
            "label": label,
            "shield_on": shield_on,
            "thresholds": {"t_allow": 0.3, "t_block": 0.7},
            "zone_at_step": None,
        }
        if floor:
            metrics["floor_s"] = floor[0]
        (d / "metrics.json").write_text(json.dumps(metrics))
    assert {k: v.name for k, v in newest_runs(tmp_path).items()} == {
        "off": "2026-10-18T02-02-22_off_ta0.30_tb0.70",
        "on_ta0.30_tb0.70_nofloor": "2026-10-18T02-06-19_on_ta0.30_tb0.70",
        "on_ta0.30_tb0.70_floor1": "2026-10-18T05-00-00_on_ta0.30_tb0.70_floor1",
        "on_ta0.30_tb0.70": "2026-10-18T05-10-00_on_ta0.30_tb0.70",
    }


def test_run_config_and_report_end_to_end(
    policy: Policy, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    judge = JevClient(live=None, cache=JevCache(None))
    # Labels collected under backend/logs/labels/ match these seeded states and
    # would add the fuzzy rules to the pool, so the report reads an empty directory.
    monkeypatch.setattr("backend.evaluate.load_labels", lambda: load_labels(tmp_path / "labels"))
    root = tmp_path / "eval"
    seeds = [0, 1]
    # The baseline passes another pair, which the off label leaves out.
    for shield_on, thresholds in ((False, Thresholds(0.2, 0.8)), (True, Thresholds())):
        out_dir = new_run_dir(root, config_label(shield_on, thresholds, None))
        report = asyncio.run(
            run_config(
                policy,
                judge,
                seeds,
                shield_on=shield_on,
                thresholds=thresholds,
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
    nofloor = asyncio.run(
        run_config(
            policy,
            judge,
            seeds,
            shield_on=True,
            thresholds=Thresholds(),
            floor_s=0.0,
            out_dir=new_run_dir(root, config_label(True, Thresholds(), None, 0.0)),
            max_steps=4,
            quiet=True,
        )
    )
    assert nofloor["label"] == "on_ta0.30_tb0.70_nofloor" and nofloor["floor_s"] == 0.0

    latest = build_report(root, report_path=tmp_path / "latest.json", plots_dir=tmp_path / "plots")
    assert latest["thresholds_default"] == {"t_allow": 0.3, "t_block": 0.7}
    assert latest["before_after"]["off"]["label"] == "off"
    assert latest["before_after"]["on"]["label"] == "on_ta0.30_tb0.70"
    assert [p["t_allow"] for p in latest["sweep"]] == [0.3, 0.5]  # no-floor runs stay out
    rows = latest["floor"]["rows"]  # only the pair that has more than one floor
    assert latest["floor"]["floor_s"] == 2.0 and [r["t_allow"] for r in rows] == [0.3]
    assert {k: v["label"] for k, v in rows[0]["by_floor"].items()} == {
        "0": "on_ta0.30_tb0.70_nofloor",
        "2": "on_ta0.30_tb0.70",
    }
    assert latest["baseline"] is None
    pooled = latest["calibration"]["overall"]["n"]
    per_run = 2 * 4 * 5 * 5  # 2 seeds, 4 steps, 5 candidates, five scored rules
    assert (
        pooled == 3 * per_run
    )  # off, on at the default floor, on at 0.5/0.5; not the no-floor run
    assert latest["calibration"]["overall"]["n"] > 0
    assert set(latest["plots"]) == {"before_after", "tradeoff", "calibration"}
    for png in latest["plots"].values():
        assert Path(png).exists() and Path(png).stat().st_size > 10_000
    assert json.loads((tmp_path / "latest.json").read_text())["sweep"] == latest["sweep"]
