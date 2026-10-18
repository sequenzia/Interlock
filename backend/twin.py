"""The unshielded twin: the shield-off run of the same seed, shown beside the live one.

With the shield off the policy's top action always executes, so the trajectory
depends only on the seed and the checkpoint, and any shield-off log for a seed
is its twin. The server looks one up on connect, reset and replay load and
sends a compact per-step strip; the console draws it under the road view and
scrubs it with the live run. No Jev cost, no new state beyond the records.
Plan section 16.5.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.logger import read_log
from backend.paths import LOGS_DIR

RUNS_DIR = LOGS_DIR / "runs"
EVAL_DIR = LOGS_DIR / "eval"


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


def twin_steps(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One compact entry per record: scene, executed action, violations and crash flag."""
    steps = []
    so_far = 0
    for r in records:
        executed = next((c for c in r["candidates"] if c["action"] == r["executed"]), None)
        checks = executed["checks"] if executed else []
        violations = sum(1 for c in checks if c["ground_truth"])
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
        "steps": [],
        "violations_total": 0,
        "crashed_at": None,
    }


def twin_message(seed: int, path: Path | None) -> dict[str, Any]:
    """The ``twin`` message for ``seed`` from ``path``; empty when there is no usable log."""
    if path is None:
        return empty_twin(seed)
    records = read_log(path)
    if not records or records[0]["shield_on"] or records[0]["seed"] != seed:
        return empty_twin(seed)
    steps = twin_steps(records)
    return {
        "type": "twin",
        "seed": seed,
        "run_id": records[0]["run_id"],
        "rules": sum(1 for c in records[0]["constraints"] if c["enabled"]),
        "steps": steps,
        "violations_total": steps[-1]["violations_so_far"],
        "crashed_at": next((s["step"] for s in steps if s["crashed"]), None),
    }
