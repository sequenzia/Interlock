"""Batch evaluation: before/after, threshold sweep, calibration, plots. Plan section 10.

    uv run python -m backend.evaluate --seeds 0-19 --mode off
    uv run python -m backend.evaluate --seeds 0-19 --mode on --t-allow 0.2 --t-block 0.8
    uv run python -m backend.evaluate --seeds 0-19 --sweep          # five threshold pairs, shield on
    uv run python -m backend.evaluate --seeds 0-19 --all            # off, the sweep, then the report
    uv run python -m backend.evaluate --report                      # newest run per configuration

Each configuration writes backend/logs/eval/<stamp>_<label>/ with one JSONL per
seed and a metrics.json. The report aggregates the newest run per label into
internal/eval/latest.json (feeds the metrics tab) and internal/plots/*.png.
The simulated operator answers escalations with the ground-truth checkers.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from backend.constraints import CHECKER_LANE_CLOSED, PRESETS, ConstraintStore
from backend.episode import EpisodeRunner, simulated_operator
from backend.jev_client import DEFAULT_MODEL, JevClient, make_client
from backend.logger import JsonlLogger, read_log
from backend.metrics import aggregate, calibration, episode_metrics
from backend.paths import DEFAULT_MODEL_PATH, ENV_FILE, INTERNAL_DIR, LOGS_DIR
from backend.policy import Policy
from backend.shield import Thresholds
from backend.train import parse_seed_range

EVAL_DIR = LOGS_DIR / "eval"
REPORT_PATH = INTERNAL_DIR / "eval" / "latest.json"
PLOTS_DIR = INTERNAL_DIR / "plots"
SWEEP: list[tuple[float, float]] = [(0.1, 0.9), (0.2, 0.8), (0.3, 0.7), (0.4, 0.6), (0.5, 0.5)]
DEFAULT_THRESHOLDS = Thresholds()
STANDING_RULES = [r for r in PRESETS if r != CHECKER_LANE_CLOSED]


def config_label(shield_on: bool, thresholds: Thresholds, zone_at_step: int | None) -> str:
    label = f"{'on' if shield_on else 'off'}_ta{thresholds.t_allow:.2f}_tb{thresholds.t_block:.2f}"
    return f"{label}_zone{zone_at_step}" if zone_at_step is not None else label


async def run_config(
    policy: Policy,
    judge: JevClient,
    seeds: list[int],
    *,
    shield_on: bool,
    thresholds: Thresholds,
    out_dir: Path,
    zone_at_step: int | None = None,
    rules: list[str] | None = None,
    concurrency: int = 3,
    max_steps: int | None = None,
    quiet: bool = False,
) -> dict[str, Any]:
    """Run every seed under one configuration; write per-seed JSONL and metrics.json."""
    out_dir.mkdir(parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(concurrency)
    started = time.perf_counter()

    async def one(seed: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        async with semaphore:
            store = ConstraintStore()
            store.add_presets(STANDING_RULES if rules is None else rules)
            path = out_dir / f"seed{seed}.jsonl"
            logger = JsonlLogger(path)
            runner = EpisodeRunner(
                policy=policy,
                judge=judge,
                store=store,
                thresholds=thresholds,
                shield_on=shield_on,
                operator=simulated_operator,
                operator_name="simulated",
                logger=logger,
                source=judge.mode,
            )
            try:
                await runner.run(seed, max_steps=max_steps, zone_at_step=zone_at_step)
            finally:
                logger.close()
                runner.close()
            records = read_log(path)
            metrics = episode_metrics(records)
            if not quiet:
                print(
                    f"  seed {seed:>2} | steps {metrics['steps']:>2} | violations {metrics['violations_total']:>2} | "
                    f"return {metrics['return']:>6.2f} | escalations {metrics['escalations']:>2} | "
                    f"{'crash' if metrics['crashed'] else 'ok   '} | ${metrics['cost_usd']:.4f}",
                    flush=True,
                )
            return metrics, records

    results = await asyncio.gather(*(one(seed) for seed in seeds))
    episodes = [m for m, _ in results]
    all_records = [r for _, records in results for r in records]
    report = {
        "label": out_dir.name.split("_", 1)[1] if "_" in out_dir.name else out_dir.name,
        "shield_on": shield_on,
        "thresholds": {"t_allow": thresholds.t_allow, "t_block": thresholds.t_block},
        "zone_at_step": zone_at_step,
        "seeds": seeds,
        "jev_mode": judge.mode,
        "model": DEFAULT_MODEL,
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "wall_seconds": round(time.perf_counter() - started, 1),
        "episodes": episodes,
        "aggregate": aggregate(episodes),
        "calibration": calibration(all_records),
    }
    (out_dir / "metrics.json").write_text(json.dumps(report, indent=1))
    return report


def new_run_dir(root: Path, label: str) -> Path:
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S")
    return root / f"{stamp}_{label}"


def newest_runs(root: Path) -> dict[str, Path]:
    """Newest run directory per configuration label."""
    found: dict[str, Path] = {}
    for metrics_path in sorted(root.glob("*/metrics.json")):
        label = json.loads(metrics_path.read_text())["label"]
        found[label] = metrics_path.parent  # sorted by stamp, so the last one wins
    return found


def build_report(
    root: Path = EVAL_DIR,
    report_path: Path = REPORT_PATH,
    plots_dir: Path = PLOTS_DIR,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
) -> dict[str, Any]:
    """Aggregate the newest run per label into latest.json and the three plots."""
    from backend import plots  # matplotlib import stays out of the hot path

    runs = newest_runs(root)
    if not runs:
        raise SystemExit(f"no eval runs under {root}")
    loaded = {
        label: json.loads((path / "metrics.json").read_text()) for label, path in runs.items()
    }
    off_label = config_label(False, thresholds, None)
    on_label = config_label(True, thresholds, None)
    sweep_points = []
    for label, rep in sorted(loaded.items()):
        if rep["shield_on"] and rep["zone_at_step"] is None:
            agg = rep["aggregate"]
            sweep_points.append(
                {
                    "label": label,
                    "t_allow": rep["thresholds"]["t_allow"],
                    "t_block": rep["thresholds"]["t_block"],
                    "violations_per_episode": agg["violations_per_episode"],
                    "escalation_rate": agg["escalation_rate"],
                    "all_blocked_rate": agg["all_blocked_rate"],
                    "crash_rate": agg["crash_rate"],
                    "mean_return": agg["mean_return"],
                    "cost_per_episode_usd": agg["cost_per_episode_usd"],
                    "human": agg["human"],
                }
            )
    sweep_points.sort(key=lambda p: p["t_allow"])
    all_records = [
        r
        for path in runs.values()
        for jsonl in sorted(path.glob("seed*.jsonl"))
        for r in read_log(jsonl)
    ]
    cal = calibration(all_records)
    report: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "thresholds_default": {"t_allow": thresholds.t_allow, "t_block": thresholds.t_block},
        "runs": {label: str(path) for label, path in runs.items()},
        "before_after": {
            "off": loaded.get(off_label),
            "on": loaded.get(on_label),
        },
        "sweep": sweep_points,
        "calibration": cal,
        "plots": {},
    }
    plots_dir.mkdir(parents=True, exist_ok=True)
    before, after = report["before_after"]["off"], report["before_after"]["on"]
    if before and after:
        report["plots"]["before_after"] = str(
            plots.plot_before_after(before, after, plots_dir / "before_after.png")
        )
    if sweep_points:
        report["plots"]["tradeoff"] = str(
            plots.plot_tradeoff(sweep_points, plots_dir / "tradeoff.png")
        )
    if cal["overall"]["n"]:
        report["plots"]["calibration"] = str(
            plots.plot_calibration(cal, plots_dir / "calibration.png")
        )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=1))
    return report


def print_summary(report: dict[str, Any]) -> None:
    agg = report["aggregate"]
    print(
        f"{report['label']}: {agg['episodes']} episodes | violations/episode {agg['violations_per_episode']:.2f} | "
        f"return {agg['mean_return']:.2f} | crash {agg['crash_rate']:.0%} | escalation {agg['escalation_rate']:.1%} | "
        f"all-blocked {agg['all_blocked_rate']:.1%} | p50 {agg['latency_ms_p50']:.0f} ms | ${agg['cost_usd']:.3f} | "
        f"{report['wall_seconds']:.0f} s",
        flush=True,
    )


async def main_async(args: argparse.Namespace) -> int:
    load_dotenv(ENV_FILE)
    if args.report and not (args.mode or args.sweep or args.all):
        report = build_report(args.out)
        print(json.dumps({k: v for k, v in report.items() if k in ("runs", "plots")}, indent=1))
        return 0
    jev_mode = args.jev
    if jev_mode == "auto":
        jev_mode = "live" if os.environ.get("TYPESAFE_API_KEY") else "mock"
    seeds = parse_seed_range(args.seeds)
    policy = Policy.load(args.model_path)
    judge = make_client(jev_mode)  # type: ignore[arg-type]
    print(
        f"eval: jev {jev_mode} | seeds {seeds[0]}-{seeds[-1]} ({len(seeds)}) | concurrency {args.concurrency} | out {args.out}"
    )
    configs: list[tuple[bool, Thresholds]] = []
    if args.all:
        configs.append((False, DEFAULT_THRESHOLDS))
        configs.extend((True, Thresholds(a, b)) for a, b in SWEEP)
    else:
        if args.mode:
            configs.append((args.mode == "on", Thresholds(args.t_allow, args.t_block)))
        if args.sweep:
            configs.extend((True, Thresholds(a, b)) for a, b in SWEEP)
    try:
        for shield_on, thresholds in configs:
            label = config_label(shield_on, thresholds, args.zone_at_step)
            print(f"\n== {label} ==", flush=True)
            report = await run_config(
                policy,
                judge,
                seeds,
                shield_on=shield_on,
                thresholds=thresholds,
                out_dir=new_run_dir(args.out, label),
                zone_at_step=args.zone_at_step,
                concurrency=args.concurrency,
                max_steps=args.max_steps,
            )
            print_summary(report)
    finally:
        await judge.close()
    if args.report or args.all:
        report = build_report(args.out)
        print("\nreport:", REPORT_PATH, "| plots:", ", ".join(report["plots"]))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--seeds", default="0-19")
    parser.add_argument(
        "--mode",
        choices=["off", "on", "shadow"],
        default=None,
        help="shadow is an alias of off: the judge and checkers run either way",
    )
    parser.add_argument("--t-allow", type=float, default=DEFAULT_THRESHOLDS.t_allow)
    parser.add_argument("--t-block", type=float, default=DEFAULT_THRESHOLDS.t_block)
    parser.add_argument(
        "--sweep", action="store_true", help="shield on over the five threshold pairs"
    )
    parser.add_argument("--all", action="store_true", help="off, then the sweep, then the report")
    parser.add_argument(
        "--report",
        action="store_true",
        help="aggregate the newest run per label into latest.json and plots",
    )
    parser.add_argument("--zone-at-step", type=int, default=None)
    parser.add_argument("--jev", choices=["auto", "live", "mock"], default="auto")
    parser.add_argument(
        "--concurrency",
        type=int,
        default=3,
        help="episodes in flight; keeps under the API rate limit",
    )
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--out", type=Path, default=EVAL_DIR)
    args = parser.parse_args()
    if args.mode == "shadow":
        args.mode = "off"
    if not (args.mode or args.sweep or args.all or args.report):
        parser.error("choose --mode, --sweep, --all or --report")
    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
