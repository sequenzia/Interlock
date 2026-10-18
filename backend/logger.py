"""JSONL decision log. One record per step (plan section 7).

The record is the contract between backend, UI and eval. Change it in the plan
first, then here, then in the frontend types.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.paths import LOGS_DIR
from backend.shield import Decision, Thresholds


def make_run_id(seed: int, shield_on: bool, now: datetime | None = None) -> str:
    stamp = (now or datetime.now(UTC)).strftime("%Y-%m-%dT%H-%M-%S")
    return f"{stamp}_seed{seed}_{'on' if shield_on else 'off'}"


def default_log_path(run_id: str) -> Path:
    return LOGS_DIR / "runs" / f"{run_id}.jsonl"


def build_record(
    *,
    run_id: str,
    episode: int,
    step: int,
    seed: int,
    source: str,
    shield_on: bool,
    thresholds: Thresholds,
    snapshot: dict[str, Any],
    zones: list[dict[str, Any]],
    constraints: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    decision: Decision,
    escalated: bool,
    human: dict[str, Any] | None,
    fallback: dict[str, str],
    floor: dict[str, Any],
    judge: dict[str, Any],
    reward: float,
    crashed: bool,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "episode": episode,
        "step": step,
        "seed": seed,
        "source": source,
        "shield_on": shield_on,
        "thresholds": {"t_allow": thresholds.t_allow, "t_block": thresholds.t_block},
        "ego": snapshot["ego"],
        "vehicles": snapshot["vehicles"],
        "zones": zones,
        "constraints": constraints,
        "candidates": candidates,
        "decision": decision.kind,
        "executed": decision.executed,
        "fired_constraint": decision.fired_constraint,
        "escalated": escalated,
        "human": human,
        "all_blocked": decision.all_blocked,
        "escalation_reason": decision.reason,
        "fallback": fallback,
        "floor": floor,
        "judge": judge,
        "reward": round(float(reward), 4),
        "crashed": bool(crashed),
    }


class JsonlLogger:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = path.open("a")

    def write(self, record: dict[str, Any]) -> None:
        self._fh.write(json.dumps(record, separators=(",", ":")) + "\n")
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()

    def __enter__(self) -> JsonlLogger:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def read_log(path: Path) -> list[dict[str, Any]]:
    with path.open() as fh:
        return [json.loads(line) for line in fh if line.strip()]
