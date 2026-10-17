from datetime import UTC, datetime
from pathlib import Path

from backend.logger import JsonlLogger, build_record, make_run_id, read_log
from backend.shield import Thresholds, decide

PLAN_KEYS = {
    "run_id", "episode", "step", "seed", "source", "shield_on", "thresholds", "ego", "vehicles",
    "zones", "constraints", "candidates", "decision", "executed", "fired_constraint", "escalated",
    "human", "all_blocked", "escalation_reason", "fallback", "judge", "reward", "crashed",
}  # fmt: skip


def test_run_id_format() -> None:
    now = datetime(2026, 10, 18, 14, 2, 11, tzinfo=UTC)
    assert make_run_id(7, True, now) == "2026-10-18T14-02-11_seed7_on"
    assert make_run_id(7, False, now).endswith("_off")


def test_record_has_exactly_the_plan_keys_and_roundtrips(tmp_path: Path) -> None:
    decision = decide(
        ["FASTER", "IDLE"], {"FASTER": {"c1": 0.91}, "IDLE": {"c1": 0.02}}, Thresholds()
    )
    record = build_record(
        run_id="r",
        episode=0,
        step=41,
        seed=7,
        source="live",
        shield_on=True,
        thresholds=Thresholds(),
        snapshot={"ego": {"lane": 2, "speed_mps": 29.6, "x_m": 812.4}, "vehicles": []},
        zones=[],
        constraints=[
            {"id": "c1", "text": "Speed limit 25 m/s", "enabled": True, "checker": "speed_limit"}
        ],
        candidates=[
            {"action": "FASTER", "rank": 0, "q": 1.92, "facts": {}, "sentences": [], "checks": []}
        ],
        decision=decision,
        escalated=False,
        human=None,
        fallback={"action": decision.fallback, "kind": decision.fallback_kind},
        judge={
            "model": "jev-latest",
            "source": "live",
            "latency_ms": 140,
            "input_tokens": 1210,
            "cost_usd": 0.0,
        },
        reward=0.83,
        crashed=False,
    )
    assert set(record) == PLAN_KEYS
    assert (record["decision"], record["executed"], record["fired_constraint"]) == (
        "fallback",
        "IDLE",
        "c1",
    )
    assert record["fallback"] == {"action": "IDLE", "kind": "safe"}
    assert record["escalation_reason"] is None
    path = tmp_path / "run.jsonl"
    with JsonlLogger(path) as log:
        log.write(record)
        log.write({**record, "step": 42})
    assert [r["step"] for r in read_log(path)] == [41, 42]
