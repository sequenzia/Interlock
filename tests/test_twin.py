import json
from pathlib import Path
from typing import Any

from backend.constraints import Constraint
from backend.twin import (
    find_twin_log,
    scored_rules,
    scoring_key,
    twin_message,
    twin_records,
    twin_steps,
)

SPEED = Constraint("c1", "Speed limit 25 m/s", True, "speed_limit")
HEADWAY = Constraint(
    "c2", "Keep at least 2 seconds of headway to the vehicle ahead", True, "headway"
)
FUZZY = Constraint("c3", "Drive conservatively in dense traffic", True, None)
DISABLED = Constraint("c4", "Speed limit 20 m/s", False, "speed_limit")


def facts(target_speed_after_mps: float, headway_s: float | None = None) -> dict[str, Any]:
    """Enough of the fact schema for the speed-limit and headway checkers."""
    return {
        "ego": {"lane": 2, "lane_count": 4, "speed_mps": 25.0, "target_speed_mps": 25.0},
        "action": {
            "name": "FASTER",
            "meaning": "raise the target speed by 5 m/s",
            "lane_after": 2,
            "target_speed_after_mps": target_speed_after_mps,
        },
        "lane_after_action": {"is_leftmost": False, "is_rightmost": False, "headway_s": headway_s},
        "zones": [],
    }


def record(
    step: int,
    seed: int,
    shield_on: bool,
    violated: bool,
    crashed: bool = False,
    headway_s: float | None = None,
) -> dict[str, Any]:
    """A log record whose executed FASTER breaks the 25 m/s limit when ``violated``.

    Carries what the server's replay path reads too, so the same rows serve as a
    replay run in the server tests.
    """
    return {
        "run_id": f"r{seed}",
        "step": step,
        "seed": seed,
        "shield_on": shield_on,
        "ego": {"lane": 2, "speed_mps": 25.0, "x_m": 100.0 + step},
        "vehicles": [{"id": 1, "lane": 1, "x_m": 90.0, "speed_mps": 20.0}],
        "zones": [],
        "constraints": [
            {"id": "c1", "text": "Speed limit 25 m/s", "enabled": True, "checker": "speed_limit"},
            {"id": "c2", "text": "Lane 3 is closed", "enabled": False, "checker": "lane_closed"},
        ],
        "candidates": [
            {
                "action": "FASTER",
                "facts": facts(30.0 if violated else 25.0, headway_s),
                "checks": [{"constraint_id": "c1", "ground_truth": violated}],
            },
            {
                "action": "IDLE",
                "facts": facts(25.0, headway_s),
                "checks": [{"constraint_id": "c1", "ground_truth": False}],
            },
        ],
        "decision": "allow",
        "executed": "FASTER",
        "escalation_reason": None,
        "human": None,
        "judge": {"cost_usd": 0.0},
        "reward": 1.0,
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


def test_twin_message_scores_the_logged_facts_against_the_rules_given(tmp_path: Path) -> None:
    path = tmp_path / "seed3.jsonl"
    rows = [
        record(0, 3, False, True),
        record(1, 3, False, False),
        record(2, 3, False, True, crashed=True, headway_s=1.0),
    ]
    write(path, rows)
    records = twin_records(3, path)

    msg = twin_message(3, records, [SPEED])
    assert (msg["type"], msg["seed"], msg["run_id"]) == ("twin", 3, "r3")
    assert (msg["rules"], msg["rule_ids"]) == (1, ["c1"])
    assert [s["violations_so_far"] for s in msg["steps"]] == [1, 1, 2]
    assert msg["violations_total"] == 2 and msg["crashed_at"] == 2
    assert set(msg["steps"][0]) == {
        "step", "ego", "vehicles", "executed", "violations", "violations_so_far", "crashed"
    }  # fmt: skip
    assert "candidates" not in json.dumps(msg) and "facts" not in json.dumps(msg)

    # The count follows the rules passed in, not the rules the log was written under:
    # a fuzzy rule and a disabled rule score nothing, headway adds the 1 s step.
    wider = twin_message(3, records, [SPEED, HEADWAY, FUZZY, DISABLED])
    assert (wider["rules"], wider["rule_ids"]) == (2, ["c1", "c2"])
    assert [s["violations"] for s in wider["steps"]] == [1, 0, 2]
    assert wider["violations_total"] == 3

    # No scored rule: the scene is still there, the count is zero.
    none = twin_message(3, records, [FUZZY])
    assert none["rules"] == 0 and none["rule_ids"] == [] and len(none["steps"]) == 3
    assert none["violations_total"] == 0 and none["crashed_at"] == 2
    assert twin_steps([], [SPEED]) == []


def test_scored_rules_and_the_scoring_key_follow_enabled_checker_rules_and_their_text() -> None:
    assert scored_rules([SPEED, FUZZY, DISABLED]) == [SPEED]
    assert scoring_key([SPEED, FUZZY, DISABLED]) == (("c1", "Speed limit 25 m/s", "speed_limit"),)
    assert scoring_key([FUZZY]) == ()
    retyped = Constraint("c1", "Speed limit 20 m/s", True, "speed_limit")
    assert scoring_key([retyped]) != scoring_key([SPEED])  # the checker parses the number
    assert scoring_key([Constraint("c9", "Speed limit 25 m/s", True, "no_such_checker")]) == ()


def test_twin_records_is_empty_without_a_usable_log(tmp_path: Path) -> None:
    assert twin_records(3, None) == []
    on = tmp_path / "on.jsonl"
    write(on, [record(0, 3, True, False)])
    assert twin_records(3, on) == []  # a shielded log is not a twin
    other = tmp_path / "other.jsonl"
    write(other, [record(0, 4, False, False)])
    assert twin_records(3, other) == []  # wrong seed
    empty = tmp_path / "empty.jsonl"
    empty.write_text("")
    assert twin_records(3, empty) == []
    msg = twin_message(3, [], [SPEED])
    assert msg["run_id"] is None and msg["steps"] == [] and msg["rules"] == 0
