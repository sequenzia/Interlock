"""The unshielded twin: the shield-off run of the same seed, shown beside the live one.

With the shield off the policy's top action always executes, so the trajectory
depends only on the seed and the checkpoint, and any shield-off log for a seed
is its twin. The server loads one on reset and replay load, scores each step's
executed action against the rules the console has on, and sends a compact
per-step strip; it re-sends the strip whenever that scored rule set changes, so
the twin's count and the live count always answer the same question. No Jev
cost, no new state beyond the records. Plan section 16.5.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend import checkers
from backend.constraints import Constraint
from backend.logger import read_log
from backend.paths import LOGS_DIR

RUNS_DIR = LOGS_DIR / "runs"
EVAL_DIR = LOGS_DIR / "eval"

ScoringKey = tuple[tuple[str, str, str], ...]


def find_twin_log(
    seed: int, runs_dir: Path | None = None, eval_dir: Path | None = None
) -> Path | None:
    """The newest shield-off log for ``seed``: an eval off run first, then ``runs/``.

    Eval off runs carry the seven standing rules over the full episode; a headless
    ``interlock run --shield off --seed N`` lands in ``runs/`` and is the fallback.
    """
    runs_dir = RUNS_DIR if runs_dir is None else runs_dir
    eval_dir = EVAL_DIR if eval_dir is None else eval_dir
    if eval_dir.exists():
        for run in sorted(eval_dir.glob("*_off*"), reverse=True):
            path = run / f"seed{seed}.jsonl"
            if path.exists():
                return path
    if runs_dir.exists():
        matches = sorted(runs_dir.glob(f"*_seed{seed}_off.jsonl"), reverse=True)
        if matches:
            return matches[0]
    return None


def twin_records(seed: int, path: Path | None) -> list[dict[str, Any]]:
    """The records of a usable shield-off log for ``seed``; empty for no log, a shielded log or another seed."""
    if path is None:
        return []
    records = read_log(path)
    if not records or records[0]["shield_on"] or records[0]["seed"] != seed:
        return []
    return records


def scored_rules(constraints: list[Constraint]) -> list[Constraint]:
    """Enabled rules that carry a ground-truth checker: the only ones either count can see."""
    return [c for c in constraints if c.enabled and c.checker in checkers.CHECKERS]


def scoring_key(constraints: list[Constraint]) -> ScoringKey:
    """Everything the twin's count depends on. Unchanged key, no need to re-send the strip."""
    return tuple((c.id, c.text, c.checker or "") for c in scored_rules(constraints))


def twin_steps(records: list[dict[str, Any]], rules: list[Constraint]) -> list[dict[str, Any]]:
    """One compact entry per record: scene, executed action, violations of ``rules`` and crash flag.

    The executed candidate's logged facts are re-scored by the checkers, so the count
    follows the rules passed in rather than the rules the log was written under.
    """
    steps = []
    so_far = 0
    for r in records:
        executed = next((c for c in r["candidates"] if c["action"] == r["executed"]), None)
        facts = executed.get("facts") if executed else None
        violations = (
            0 if facts is None else sum(1 for c in rules if checkers.label(facts, c) is True)
        )
        so_far += violations
        steps.append(
            {
                "step": r["step"],
                "ego": r["ego"],
                "vehicles": r["vehicles"],
                "executed": r["executed"],
                "violations": violations,
                "violations_so_far": so_far,
                "crashed": bool(r["crashed"]),
            }
        )
    return steps


def empty_twin(seed: int) -> dict[str, Any]:
    return {
        "type": "twin",
        "seed": seed,
        "run_id": None,
        "rules": 0,
        "rule_ids": [],
        "steps": [],
        "violations_total": 0,
        "crashed_at": None,
    }


def twin_message(
    seed: int, records: list[dict[str, Any]], constraints: list[Constraint]
) -> dict[str, Any]:
    """The ``twin`` message for ``seed`` from ``records``, scored against ``constraints``."""
    if not records:
        return empty_twin(seed)
    rules = scored_rules(constraints)
    steps = twin_steps(records, rules)
    return {
        "type": "twin",
        "seed": seed,
        "run_id": records[0]["run_id"],
        "rules": len(rules),
        "rule_ids": [c.id for c in rules],
        "steps": steps,
        "violations_total": steps[-1]["violations_so_far"],
        "crashed_at": next((s["step"] for s in steps if s["crashed"]), None),
    }
