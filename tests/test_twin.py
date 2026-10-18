import json
from pathlib import Path
from typing import Any

from backend.twin import find_twin_log, twin_message, twin_steps


def record(
    step: int, seed: int, shield_on: bool, violated: bool, crashed: bool = False
) -> dict[str, Any]:
    return {
        "run_id": f"r{seed}",
        "step": step,
        "seed": seed,
        "shield_on": shield_on,
        "ego": {"lane": 2, "speed_mps": 25.0, "x_m": 100.0 + step},
        "vehicles": [{"id": 1, "lane": 1, "x_m": 90.0, "speed_mps": 20.0}],
        "constraints": [
            {"id": "c1", "text": "Speed limit 25 m/s", "enabled": True, "checker": "speed_limit"},
            {"id": "c2", "text": "Lane 3 is closed", "enabled": False, "checker": "lane_closed"},
        ],
        "candidates": [
            {"action": "FASTER", "checks": [{"constraint_id": "c1", "ground_truth": violated}]},
            {"action": "IDLE", "checks": [{"constraint_id": "c1", "ground_truth": False}]},
        ],
        "executed": "FASTER",
        "crashed": crashed,
    }


def write(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def test_find_prefers_the_newest_eval_off_run_then_runs(tmp_path: Path) -> None:
    runs, ev = tmp_path / "runs", tmp_path / "eval"
    assert find_twin_log(3, runs, ev) is None
    write(runs / "2026-10-17T01-00-00_seed3_off.jsonl", [record(0, 3, False, False)])
    write(runs / "2026-10-18T01-00-00_seed3_off.jsonl", [record(0, 3, False, False)])
    write(runs / "2026-10-18T02-00-00_seed3_on.jsonl", [record(0, 3, True, False)])
    assert find_twin_log(3, runs, ev) == runs / "2026-10-18T01-00-00_seed3_off.jsonl"
    write(
        ev / "2026-10-17T23-31-12_off_ta0.20_tb0.80" / "seed3.jsonl", [record(0, 3, False, False)]
    )
    write(ev / "2026-10-18T03-19-36_off" / "seed3.jsonl", [record(0, 3, False, False)])
    write(ev / "2026-10-18T04-00-00_on_ta0.30_tb0.70" / "seed3.jsonl", [record(0, 3, True, False)])
    assert find_twin_log(3, runs, ev) == ev / "2026-10-18T03-19-36_off" / "seed3.jsonl"
    assert find_twin_log(4, runs, ev) is None  # no seed 4 anywhere


def test_twin_message_is_compact_and_counts_violations_and_the_crash(tmp_path: Path) -> None:
    path = tmp_path / "seed3.jsonl"
    rows = [
        record(0, 3, False, True),
        record(1, 3, False, False),
        record(2, 3, False, True, crashed=True),
    ]
    write(path, rows)
    msg = twin_message(3, path)
    assert (msg["type"], msg["seed"], msg["run_id"], msg["rules"]) == ("twin", 3, "r3", 1)
    assert [s["violations_so_far"] for s in msg["steps"]] == [1, 1, 2]
    assert msg["violations_total"] == 2 and msg["crashed_at"] == 2
    assert set(msg["steps"][0]) == {
        "step", "ego", "vehicles", "executed", "violations", "violations_so_far", "crashed"
    }  # fmt: skip
    assert "candidates" not in json.dumps(msg)
    assert twin_steps([]) == []


def test_twin_message_is_empty_without_a_usable_log(tmp_path: Path) -> None:
    assert twin_message(3, None)["steps"] == []
    on = tmp_path / "on.jsonl"
    write(on, [record(0, 3, True, False)])
    assert twin_message(3, on)["steps"] == []  # a shielded log is not a twin
    other = tmp_path / "other.jsonl"
    write(other, [record(0, 4, False, False)])
    assert twin_message(3, other)["steps"] == []  # wrong seed
    empty = tmp_path / "empty.jsonl"
    empty.write_text("")
    assert twin_message(3, empty)["run_id"] is None
