"""Metrics computed from JSONL records only, so eval and replay share one source.

Episode metrics, aggregates over seeds, and calibration of Jev's p(violation)
against the ground-truth checkers. Plan section 10.
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable
from typing import Any

from backend.label import label_key, rule_group

Record = dict[str, Any]
Check = tuple[float, bool, str]  # p, label, calibration group


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def executed_candidate(record: Record) -> Record | None:
    return next((c for c in record["candidates"] if c["action"] == record["executed"]), None)


def episode_metrics(records: list[Record]) -> dict[str, Any]:
    """One episode's counters from its records."""
    if not records:
        raise ValueError("no records")
    first = records[0]
    decisions: dict[str, int] = {}
    violations: dict[str, int] = {}
    human: dict[str, int] = {}
    sources: dict[str, int] = {}
    live_latencies: list[float] = []
    total_reward = 0.0
    crashed = False
    tokens = 0
    cost = 0.0
    all_blocked = 0
    conflicts = 0
    floored = 0
    floor_all = 0
    for r in records:
        decisions[r["decision"]] = decisions.get(r["decision"], 0) + 1
        all_blocked += bool(r.get("all_blocked"))
        conflicts += r.get("escalation_reason") == "no_compliant_action"
        floor = r.get("floor") or {}  # logs before Oct 17 have no floor block
        if floor.get("applied") and floor.get("removed"):
            floored += 1
            floor_all += len(floor["removed"]) >= len(r["candidates"])
        total_reward += r["reward"]
        crashed = crashed or r["crashed"]
        if r["human"]:
            human[r["human"]["decision"]] = human.get(r["human"]["decision"], 0) + 1
        executed = executed_candidate(r)
        for check in executed["checks"] if executed else []:
            if check["ground_truth"]:
                violations[check["constraint_id"]] = violations.get(check["constraint_id"], 0) + 1
        judge = r["judge"]
        sources[judge["source"]] = sources.get(judge["source"], 0) + 1
        if judge["source"] == "live":
            live_latencies.append(judge["latency_ms"])
        tokens += judge.get("input_tokens", 0)
        cost += judge.get("cost_usd", 0.0)
    steps = len(records)
    escalations = decisions.get("escalate", 0)
    return {
        "run_id": first["run_id"],
        "seed": first["seed"],
        "shield_on": first["shield_on"],
        "thresholds": first["thresholds"],
        "steps": steps,
        "return": round(total_reward, 3),
        "crashed": crashed,
        "violations": violations,
        "violations_total": sum(violations.values()),
        "decisions": decisions,
        "escalations": escalations,
        "escalation_rate": round(escalations / steps, 4),
        "all_blocked": all_blocked,
        "conflicts": conflicts,
        "conflict_rate": round(conflicts / steps, 4),
        "floored": floored,
        "floor_all": floor_all,
        "human": human,
        "judge_sources": sources,
        "live_steps": len(live_latencies),
        "latency_ms_p50": round(_percentile(live_latencies, 0.5), 1),
        "latency_ms_p95": round(_percentile(live_latencies, 0.95), 1),
        "input_tokens": tokens,
        "cost_usd": round(cost, 6),
    }


def aggregate(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Means over seeds plus pooled rates; the before/after table reads this."""
    if not episodes:
        raise ValueError("no episodes")
    steps = sum(e["steps"] for e in episodes)
    per_constraint: dict[str, int] = {}
    for e in episodes:
        for cid, n in e["violations"].items():
            per_constraint[cid] = per_constraint.get(cid, 0) + n
    violations = [e["violations_total"] for e in episodes]
    returns = [e["return"] for e in episodes]
    return {
        "episodes": len(episodes),
        "steps": steps,
        "violations_per_episode": round(statistics.mean(violations), 3),
        "violations_per_episode_std": round(statistics.pstdev(violations), 3),
        "violations_per_step": round(sum(violations) / steps, 4),
        "violations_by_constraint": per_constraint,
        "mean_return": round(statistics.mean(returns), 3),
        "mean_return_std": round(statistics.pstdev(returns), 3),
        "crash_rate": round(sum(e["crashed"] for e in episodes) / len(episodes), 3),
        "mean_steps": round(steps / len(episodes), 1),
        "escalation_rate": round(sum(e["escalations"] for e in episodes) / steps, 4),
        "all_blocked_rate": round(sum(e["all_blocked"] for e in episodes) / steps, 4),
        "conflict_rate": round(sum(e.get("conflicts", 0) for e in episodes) / steps, 4),
        "floored_rate": round(sum(e.get("floored", 0) for e in episodes) / steps, 4),
        "floor_all_rate": round(sum(e.get("floor_all", 0) for e in episodes) / steps, 4),
        "human": {
            k: sum(e["human"].get(k, 0) for e in episodes) for k in ("approve", "deny", "override")
        },
        "live_steps": sum(e["live_steps"] for e in episodes),
        "latency_ms_p50": round(
            statistics.median([e["latency_ms_p50"] for e in episodes if e["live_steps"]] or [0.0]),
            1,
        ),
        "latency_ms_p95": round(
            max([e["latency_ms_p95"] for e in episodes if e["live_steps"]] or [0.0]), 1
        ),
        "cost_usd": round(sum(e["cost_usd"] for e in episodes), 6),
        "cost_per_episode_usd": round(sum(e["cost_usd"] for e in episodes) / len(episodes), 6),
    }


def _collect(
    records: Iterable[Record], labels: dict[str, bool] | None
) -> tuple[list[Check], dict[str, str]]:
    """Labeled checks across all candidates, and each group's label source.

    A rule with a checker is grouped by checker id and labeled by it. A rule
    without one is grouped by its preset id or a slug of its text and labeled
    by hand when ``labels`` holds its facts-plus-rule key; otherwise skipped.
    """
    out: list[Check] = []
    sources: dict[str, str] = {}
    for r in records:
        by_id = {c["id"]: c for c in r["constraints"]}
        for cand in r["candidates"]:
            for check in cand["checks"]:
                c = by_id.get(check["constraint_id"])
                if c is None:
                    continue
                truth = check["ground_truth"]
                if c.get("checker"):
                    group, source = c["checker"], "checker"
                else:
                    group, source = rule_group(c["text"]), "human"
                    if truth is None and labels:
                        truth = labels.get(label_key(cand["facts"], c["text"]))
                if truth is None:
                    continue
                out.append((float(check["p_violation"]), bool(truth), group))
                sources[group] = source
    return out, sources


def collect_checks(records: Iterable[Record], labels: dict[str, bool] | None = None) -> list[Check]:
    """Every (p, label, group) with a label, from the checkers or from hand labels."""
    return _collect(records, labels)[0]


def reliability(checks: list[Check], bins: int = 10) -> dict[str, Any]:
    """Equal-width bins of p; observed violation rate per bin; ECE and Brier."""
    n = len(checks)
    rows = []
    ece = 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        members = [(p, y) for p, y, _ in checks if lo <= p < hi or (b == bins - 1 and p == 1.0)]
        if not members:
            rows.append({"lo": lo, "hi": hi, "count": 0, "mean_p": None, "observed": None})
            continue
        mean_p = sum(p for p, _ in members) / len(members)
        observed = sum(1 for _, y in members if y) / len(members)
        ece += (len(members) / n) * abs(observed - mean_p) if n else 0.0
        rows.append(
            {
                "lo": lo,
                "hi": hi,
                "count": len(members),
                "mean_p": round(mean_p, 4),
                "observed": round(observed, 4),
            }
        )
    brier = sum((p - (1.0 if y else 0.0)) ** 2 for p, y, _ in checks) / n if n else 0.0
    positives = sum(1 for _, y, _ in checks if y)
    at_half = sum(1 for p, y, _ in checks if (p > 0.5) == y) / n if n else 0.0
    return {
        "n": n,
        "positives": positives,
        "bins": rows,
        "ece": round(ece, 4),
        "brier": round(brier, 4),
        "accuracy_at_0_5": round(at_half, 4),
    }


def calibration(
    records: Iterable[Record], bins: int = 10, labels: dict[str, bool] | None = None
) -> dict[str, Any]:
    """Reliability overall and per group; each group records whether a checker or a person labeled it."""
    checks, sources = _collect(records, labels)
    by_group: dict[str, list[Check]] = {}
    for item in checks:
        by_group.setdefault(item[2], []).append(item)
    return {
        "overall": reliability(checks, bins),
        "by_checker": {
            name: {**reliability(items, bins), "label_source": sources[name]}
            for name, items in sorted(by_group.items())
        },
    }
