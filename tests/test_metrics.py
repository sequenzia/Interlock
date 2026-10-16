from backend.metrics import aggregate, calibration, collect_checks, episode_metrics, reliability


def record(
    step: int,
    decision: str,
    executed: str,
    checks: list[tuple[str, float, bool | None]],
    **over: object,
) -> dict:
    base = {
        "run_id": "r",
        "seed": 3,
        "shield_on": True,
        "thresholds": {"t_allow": 0.2, "t_block": 0.8},
        "constraints": [
            {"id": "c1", "text": "Speed limit 25 m/s", "enabled": True, "checker": "speed_limit"},
            {"id": "c5", "text": "free", "enabled": True, "checker": None},
        ],
        "candidates": [
            {
                "action": "FASTER",
                "rank": 0,
                "checks": [
                    {"constraint_id": cid, "p_violation": p, "ground_truth": gt}
                    for cid, p, gt in checks
                ],
            },
            {
                "action": "IDLE",
                "rank": 1,
                "checks": [{"constraint_id": "c1", "p_violation": 0.05, "ground_truth": False}],
            },
        ],
        "decision": decision,
        "executed": executed,
        "human": None,
        "judge": {
            "source": "live",
            "latency_ms": 150.0,
            "input_tokens": 1000,
            "cost_usd": 0.000042,
        },
        "reward": 0.8,
        "crashed": False,
    }
    base.update(over)
    return {"step": step, **base}


def test_episode_metrics_counts_executed_violations_and_rates() -> None:
    records = [
        record(0, "allow", "FASTER", [("c1", 0.9, True)]),
        record(1, "fallback", "IDLE", [("c1", 0.9, True)]),
        record(
            2,
            "escalate",
            "FASTER",
            [("c1", 0.5, True)],
            human={"decision": "approve", "latency_ms": 10, "operator": "simulated"},
        ),
        record(
            3,
            "all_blocked",
            "IDLE",
            [("c1", 0.9, True)],
            judge={"source": "cache", "latency_ms": 0.2, "input_tokens": 0, "cost_usd": 0.0},
            crashed=True,
        ),
    ]
    m = episode_metrics(records)
    assert m["steps"] == 4 and m["violations"] == {"c1": 2} and m["violations_total"] == 2
    assert m["decisions"] == {"allow": 1, "fallback": 1, "escalate": 1, "all_blocked": 1}
    assert m["escalations"] == 1 and m["escalation_rate"] == 0.25 and m["all_blocked"] == 1
    assert m["human"] == {"approve": 1} and m["crashed"] is True
    assert m["judge_sources"] == {"live": 3, "cache": 1} and m["live_steps"] == 3
    assert m["latency_ms_p50"] == 150.0 and m["input_tokens"] == 3000
    assert m["return"] == 3.2


def test_aggregate_pools_rates_over_episodes() -> None:
    a = episode_metrics(
        [
            record(0, "allow", "FASTER", [("c1", 0.9, True)]),
            record(1, "escalate", "IDLE", [("c1", 0.5, False)]),
        ]
    )
    b = episode_metrics([record(0, "allow", "IDLE", [("c1", 0.1, False)])])
    agg = aggregate([a, b])
    assert agg["episodes"] == 2 and agg["steps"] == 3
    assert agg["violations_per_episode"] == 0.5 and agg["violations_by_constraint"] == {"c1": 1}
    assert agg["escalation_rate"] == round(1 / 3, 4) and agg["crash_rate"] == 0.0
    assert agg["human"] == {"approve": 0, "deny": 0}
    assert agg["cost_usd"] == round(3 * 0.000042, 6)


def test_calibration_bins_and_ece() -> None:
    records = [
        record(0, "allow", "FASTER", [("c1", 0.95, True), ("c5", 0.4, None)]),
        record(1, "allow", "FASTER", [("c1", 0.92, True)]),
        record(2, "allow", "FASTER", [("c1", 0.91, False)]),
        record(3, "allow", "FASTER", [("c1", 0.03, False)]),
    ]
    checks = collect_checks(records)
    # the free-text rule has no label; the IDLE candidate adds a 0.05 False per record
    assert len(checks) == 8 and all(c[2] == "speed_limit" for c in checks)
    rel = reliability(checks)
    assert rel["n"] == 8 and rel["positives"] == 2
    top = rel["bins"][9]
    assert top["count"] == 3 and top["observed"] == round(2 / 3, 4)
    assert rel["bins"][0]["count"] == 5 and rel["bins"][0]["observed"] == 0.0
    assert 0 < rel["ece"] < 0.2 and 0 < rel["brier"] < 0.2 and rel["accuracy_at_0_5"] == 0.875
    cal = calibration(records)
    assert set(cal["by_checker"]) == {"speed_limit"} and cal["overall"]["n"] == 8
