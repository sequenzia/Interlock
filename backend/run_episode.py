"""Headless shielded episode. Plan section 5.1, Day 2 milestone.

    uv run python -m backend.run_episode --shield on
    uv run python -m backend.run_episode --shield off --seed 3
    uv run python -m backend.run_episode --shield on --jev mock --zone-at-step 10
    uv run python -m backend.run_episode --shield on --rules speed_limit,lane_change_gap

Jev mode defaults to live when TYPESAFE_API_KEY is set in backend/.env and to
mock otherwise. In mock mode every uncached question is "judge unavailable" at
p = 0.5, so the shield escalates and the chosen operator answers.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from backend.constraints import CHECKER_LANE_CLOSED, PRESETS, ConstraintStore
from backend.episode import OPERATORS, EpisodeRunner, StepResult
from backend.jev_client import DEFAULT_MODEL, make_client
from backend.logger import JsonlLogger, default_log_path, make_run_id
from backend.paths import DEFAULT_MODEL_PATH, ENV_FILE
from backend.policy import Policy
from backend.shield import Thresholds


def format_step(result: StepResult) -> str:
    r = result.record
    top = r["candidates"][0]
    p_top = max((c["p_violation"] for c in top["checks"]), default=0.0)
    outcome = r["decision"]
    if r["decision"] in ("fallback", "all_blocked") or (
        r["escalated"] and r["executed"] != top["action"]
    ):
        outcome += f" -> {r['executed']}"
    if r["escalated"]:
        outcome += f" [{r['human']['decision']}]"
    fired = (
        f" ({r['fired_constraint']})" if r["fired_constraint"] and r["decision"] != "allow" else ""
    )
    judge = r["judge"]
    flag = " JUDGE UNAVAILABLE" if judge["source"] == "unavailable" else ""
    return (
        f"step {r['step']:>3} | lane {r['ego']['lane']} {r['ego']['speed_mps']:>5.1f} m/s | "
        f"top {top['action']:<10} p={p_top:.2f} | {outcome}{fired} | r={r['reward']:.2f}"
        f" | {judge['source']} {judge['latency_ms']:.0f} ms{flag}"
        + ("  CRASH" if r["crashed"] else "")
    )


async def main_async(args: argparse.Namespace) -> int:
    load_dotenv(ENV_FILE)
    jev_mode = args.jev
    if jev_mode == "auto":
        jev_mode = "live" if os.environ.get("TYPESAFE_API_KEY") else "mock"

    store = ConstraintStore()
    # "all" is the three standing rules; the lane-closed rule arrives with a zone drop.
    standing = [r for r in PRESETS if r != CHECKER_LANE_CLOSED]
    rule_ids = standing if args.rules == "all" else [r for r in args.rules.split(",") if r]
    if args.rules != "none":
        unknown = [r for r in rule_ids if r not in PRESETS]
        if unknown:
            print(f"unknown rule ids {unknown}; choose from {list(PRESETS)}", file=sys.stderr)
            return 2
        store.add_presets(rule_ids)

    shield_on = args.shield == "on"
    run_id = make_run_id(args.seed, shield_on)
    log_path = args.log or default_log_path(run_id)
    judge = make_client(jev_mode, model=args.model)
    runner = EpisodeRunner(
        policy=Policy.load(args.model_path),
        judge=judge,
        store=store,
        thresholds=Thresholds(args.t_allow, args.t_block),
        shield_on=shield_on,
        operator=OPERATORS[args.operator],
        operator_name=args.operator,
        logger=JsonlLogger(log_path),
        source=jev_mode,
    )
    runner.run_id = run_id
    print(
        f"shield {args.shield} | seed {args.seed} | jev {jev_mode} | rules {[c.text for c in store.constraints]}"
        f" | thresholds {args.t_allow}/{args.t_block} | operator {args.operator} | log {log_path}"
    )
    on_step = None if args.quiet else lambda result: print(format_step(result), flush=True)
    try:
        summary = await runner.run(
            args.seed, max_steps=args.max_steps, on_step=on_step, zone_at_step=args.zone_at_step
        )
    finally:
        runner.close()
        await judge.close()
    print(json.dumps(summary, indent=2))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--shield", choices=["on", "off"], default="on")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--jev", choices=["auto", "live", "mock"], default="auto")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Jev model id")
    parser.add_argument(
        "--model-path", type=Path, default=DEFAULT_MODEL_PATH, help="DQN checkpoint"
    )
    parser.add_argument(
        "--rules",
        default="all",
        help='comma list of preset ids, "all" (three standing rules) or "none"; the zone rule comes with --zone-at-step',
    )
    parser.add_argument(
        "--zone-at-step", type=int, default=None, help="drop the default work zone at this step"
    )
    parser.add_argument("--t-allow", type=float, default=0.2)
    parser.add_argument("--t-block", type=float, default=0.8)
    parser.add_argument("--operator", choices=sorted(OPERATORS), default="simulated")
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument(
        "--log",
        type=Path,
        default=None,
        help="JSONL path (default backend/logs/runs/<run_id>.jsonl)",
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
