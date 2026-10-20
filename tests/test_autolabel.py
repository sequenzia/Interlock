import argparse
import json
from pathlib import Path
from typing import Any

import pytest
from backend.autolabel import LABELER, add_arguments, answer, cut_in, dense_traffic, run_cli
from backend.constraints import PRESET_CUT_IN, PRESET_DENSE_TRAFFIC, PRESETS
from backend.label import Label, label_key, load_labels
from backend.metrics import calibration

DENSE, CUT = PRESETS[PRESET_DENSE_TRAFFIC], PRESETS[PRESET_CUT_IN]


def facts(
    action: str = "IDLE",
    *,
    lane: int = 2,
    lane_after: int | None = None,
    target: float = 30.0,
    target_after: float | None = None,
    vehicles: int = 5,
    headway: float | None = 3.0,
    ttc: float | None = None,
    behind_gap: float | None = 40.0,
    behind_closing: float | None = -5.0,
    ahead_gap: float | None = 60.0,
    tailgated: bool = False,
) -> dict[str, Any]:
    """The slice of a candidate's facts the standards read; dense, roomy and calm by default."""
    return {
        "ego": {"lane": lane, "lane_count": 4, "speed_mps": target, "target_speed_mps": target},
        "action": {
            "name": action,
            "lane_after": lane if lane_after is None else lane_after,
            "target_speed_after_mps": target if target_after is None else target_after,
        },
        "lane_after_action": {
            "vehicle_behind_gap_m": behind_gap,
            "vehicle_behind_closing_speed_mps": behind_closing,
            "vehicle_ahead_gap_m": ahead_gap,
            "headway_s": headway,
            "time_to_collision_ahead_s": ttc,
            "being_tailgated": tailgated,
        },
        "traffic": {"vehicles_within_50_m": vehicles},
    }


def dense(f: dict[str, Any]) -> bool:
    return dense_traffic(f, 15.0, 5.0)


def test_dense_traffic_standard() -> None:
    assert not dense(facts("FASTER", vehicles=3, headway=0.5))  # not dense: anything goes
    assert dense(facts("FASTER"))  # even at the cap, where it changes nothing
    assert dense(facts("FASTER", target=25.0, target_after=30.0))
    change = {"lane_after": 1}
    assert dense(facts("LANE_LEFT", **change, behind_gap=10.0))
    assert dense(facts("LANE_LEFT", **change, ahead_gap=12.0))
    assert not dense(facts("LANE_LEFT", **change, behind_gap=20.0))
    assert dense(facts("LANE_LEFT", **change, behind_gap=20.0, headway=1.5))
    assert dense(facts("LANE_LEFT", **change, behind_gap=20.0, ttc=4.0))
    empty = {"behind_gap": None, "behind_closing": None, "ahead_gap": None, "headway": None}
    assert not dense(facts("LANE_LEFT", **change, **empty))
    assert dense(facts("IDLE", headway=1.5))
    assert dense(facts("IDLE", ttc=3.0))
    assert not dense(facts("IDLE", headway=1.5, target=20.0))  # no real SLOWER to take instead
    assert not dense(facts("IDLE", headway=2.5, ttc=6.0))
    assert dense(facts("LANE_RIGHT", lane=4, lane_after=4, headway=1.5))  # a no-op, judged as IDLE
    assert not dense(facts("LANE_RIGHT", lane=4, lane_after=4, headway=2.3))  # the guide's example
    assert not dense(facts("SLOWER", target=30.0, target_after=25.0, headway=1.0))
    assert not dense(facts("SLOWER", target=20.0, target_after=20.0, headway=1.0))


def test_cut_in_standard() -> None:
    def cut(f: dict[str, Any]) -> bool:
        return cut_in(f, 15.0, 5.0)

    assert not cut(facts("IDLE", behind_gap=3.0, behind_closing=5.0))
    assert not cut(facts("LANE_LEFT", lane_after=1, behind_gap=None, behind_closing=None))
    assert not cut(facts("LANE_LEFT", lane_after=1, behind_gap=3.0, behind_closing=-5.0))
    assert cut(facts("LANE_LEFT", lane_after=1, behind_gap=10.0, behind_closing=3.0))
    assert not cut(facts("LANE_LEFT", lane_after=1, behind_gap=20.0, behind_closing=3.0))
    assert cut(
        facts("LANE_LEFT", lane_after=1, behind_gap=30.0, behind_closing=-1.0, tailgated=True)
    )
    assert not cut(facts("LANE_RIGHT", lane=4, lane_after=4, behind_gap=5.0, behind_closing=5.0))


def test_answer_skips_states_the_loose_thresholds_do_not_settle() -> None:
    change = facts("LANE_LEFT", lane_after=1, behind_gap=15.5)
    assert answer(PRESET_DENSE_TRAFFIC, change) == "s"
    assert answer(PRESET_DENSE_TRAFFIC, facts("LANE_LEFT", lane_after=1, behind_gap=13.0)) == "y"
    assert answer(PRESET_DENSE_TRAFFIC, facts("LANE_LEFT", lane_after=1, behind_gap=17.0)) == "n"
    assert answer(PRESET_DENSE_TRAFFIC, facts("IDLE", ttc=5.2)) == "s"
    assert answer(PRESET_DENSE_TRAFFIC, facts("IDLE", ttc=4.4)) == "y"
    assert answer(PRESET_DENSE_TRAFFIC, facts("IDLE", ttc=5.6)) == "n"
    assert (
        answer(PRESET_CUT_IN, facts("LANE_LEFT", lane_after=1, behind_gap=15.0, behind_closing=2.0))
        == "s"
    )
    assert (
        answer(PRESET_CUT_IN, facts("LANE_LEFT", lane_after=1, behind_gap=5.0, behind_closing=2.0))
        == "y"
    )
    assert answer(PRESET_DENSE_TRAFFIC, facts("FASTER")) == "y"


def record(step: int, candidates: list[tuple[str, dict[str, Any], float]]) -> dict[str, Any]:
    return {
        "run_id": "r",
        "seed": 0,
        "step": step,
        "constraints": [
            {"id": "c1", "text": DENSE, "enabled": True, "checker": None},
            {"id": "c2", "text": CUT, "enabled": True, "checker": None},
        ],
        "candidates": [
            {
                "action": a,
                "rank": i,
                "facts": f,
                "sentences": [a],
                "checks": [
                    {"constraint_id": "c1", "p_violation": p, "ground_truth": None},
                    {"constraint_id": "c2", "p_violation": p / 2, "ground_truth": None},
                ],
            }
            for i, (a, f, p) in enumerate(candidates)
        ],
    }


def test_run_cli_labels_each_state_once_and_reruns_add_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    faster, idle = facts("FASTER"), facts("IDLE", headway=1.5)
    records = [
        record(0, [("FASTER", faster, 0.9), ("IDLE", idle, 0.6)]),
        record(1, [("FASTER", faster, 0.9)]),  # the same state again
    ]
    run = tmp_path / "run"
    run.mkdir()
    (run / "seed0.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))
    parser = argparse.ArgumentParser()
    add_arguments(parser)
    labels_dir = tmp_path / "labels"
    base = ["--run", str(run), "--labels-dir", str(labels_dir)]

    assert run_cli(parser.parse_args([*base, "--dry-run"])) == 0
    assert not labels_dir.exists()
    out = capsys.readouterr().out
    assert "dense_traffic: 2 states, 2 y, 0 n, 0 skipped" in out
    assert "cut_in: 2 states, 0 y, 2 n, 0 skipped" in out and "labeled" not in out

    assert run_cli(parser.parse_args(base)) == 0
    assert "labeled 4." in capsys.readouterr().out
    labels = load_labels(labels_dir)
    assert labels == {
        label_key(faster, DENSE): Label(True, LABELER),
        label_key(idle, DENSE): Label(True, LABELER),
        label_key(faster, CUT): Label(False, LABELER),
        label_key(idle, CUT): Label(False, LABELER),
    }
    rows = [
        json.loads(line) for line in (labels_dir / "dense_traffic.jsonl").read_text().splitlines()
    ]
    assert [r["action"] for r in rows] == ["FASTER", "IDLE"] and {r["labeler"] for r in rows} == {
        LABELER
    }

    assert (
        run_cli(parser.parse_args(base)) == 0
    )  # everything is labeled: nothing offered, nothing written
    out = capsys.readouterr().out
    assert "dense_traffic: nothing left to label" in out and "labeled 0." in out

    unsettled = facts("LANE_LEFT", lane_after=1, behind_gap=15.5, behind_closing=2.0)
    (run / "seed1.jsonl").write_text(json.dumps(record(0, [("LANE_LEFT", unsettled, 0.4)])) + "\n")
    assert (
        run_cli(parser.parse_args(base)) == 0
    )  # a skipped state is offered again and skipped again
    out = capsys.readouterr().out
    assert "dense_traffic: 1 states, 0 y, 0 n, 1 skipped" in out and "labeled 0." in out
    assert len(load_labels(labels_dir)) == 4 and label_key(unsettled, DENSE) not in load_labels(
        labels_dir
    )

    cal = calibration(records, labels=labels)["by_checker"]
    assert cal["dense_traffic"]["n"] == 3 and cal["dense_traffic"]["label_source"] == LABELER
    assert cal["cut_in"]["positives"] == 0 and cal["cut_in"]["label_source"] == LABELER


def test_run_cli_with_no_records_fails(tmp_path: Path) -> None:
    parser = argparse.ArgumentParser()
    add_arguments(parser)
    (tmp_path / "empty.jsonl").write_text("")
    assert run_cli(parser.parse_args(["--run", str(tmp_path / "empty.jsonl")])) == 2
