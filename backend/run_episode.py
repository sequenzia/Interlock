"""Headless shielded episode. Plan section 5.1, Day 2 milestone.

Behind ``interlock run``; ``python -m backend.run_episode`` takes the same flags.
Jev mode defaults to live when TYPESAFE_API_KEY is set in backend/.env and to
mock otherwise. In mock mode every uncached question is "judge unavailable" at
p = 0.5, so the shield escalates and the chosen operator answers.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Any, Literal

import typer
from dotenv import load_dotenv

from backend.cli_support import repo_relative, run_standalone
from backend.constraints import CHECKER_LANE_CLOSED, PRESETS, ConstraintStore
from backend.episode import OPERATORS, EpisodeRunner, OperatorName, StepResult
from backend.jev_client import DEFAULT_MODEL, JevMode, make_client, resolve_jev_mode
from backend.logger import JsonlLogger, default_log_path, make_run_id
from backend.paths import DEFAULT_MODEL_PATH, ENV_FILE
from backend.policy import Policy
from backend.shield import DEFAULT_FLOOR_S, Thresholds


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


def command(
    shield: Annotated[
        Literal["on", "off"],
        typer.Option(help="off still judges in shadow and executes the policy's top action"),
    ] = "on",
    seed: Annotated[int, typer.Option(help="episode seed")] = 0,
    jev: Annotated[
        JevMode,
        typer.Option(help="auto is live when TYPESAFE_API_KEY is set in backend/.env, else mock"),
    ] = "auto",
    model: Annotated[str, typer.Option(help="Jev model id")] = DEFAULT_MODEL,
    model_path: Annotated[
        Path, typer.Option(help="DQN checkpoint", show_default=repo_relative(DEFAULT_MODEL_PATH))
    ] = DEFAULT_MODEL_PATH,
    rules: Annotated[
        str,
        typer.Option(
            help='comma list of preset ids, "all" (every preset but the zone rule) or "none"; '
            "the zone rule comes with --zone-at-step"
        ),
    ] = "all",
    zone_at_step: Annotated[
        int | None, typer.Option(help="drop the default work zone at this step")
    ] = None,
    t_allow: Annotated[float, typer.Option(help="allow threshold")] = Thresholds().t_allow,
    t_block: Annotated[float, typer.Option(help="block threshold")] = Thresholds().t_block,
    floor_s: Annotated[
        float,
        typer.Option(
            metavar="S",
            help="time to collision floor in seconds; candidates under it never run; 0 disables",
        ),
    ] = DEFAULT_FLOOR_S,
    operator: Annotated[
        OperatorName,
        typer.Option(help="who answers escalations; simulated answers from the checkers"),
    ] = "simulated",
    max_steps: Annotated[int | None, typer.Option(help="stop early")] = None,
    log: Annotated[
        Path | None, typer.Option(help="JSONL path (default `backend/logs/runs/<run_id>.jsonl`)")
    ] = None,
    quiet: Annotated[
        bool, typer.Option("--quiet", help="suppress the per-step lines, print only the summary")
    ] = False,
) -> None:
    """One headless episode, shield on or off, printed step by step and logged as JSONL.

    ```
    interlock run --shield on
    interlock run --shield off --seed 3                  # shadow mode, same seed
    interlock run --jev mock --zone-at-step 10           # offline, drop the work zone mid-episode
    interlock run --rules speed_limit --operator approve --max-steps 20
    ```

    Writes one JSONL file and prints a JSON summary. An unknown rule id exits with code 2.
    """
    load_dotenv(ENV_FILE)
    jev_mode = resolve_jev_mode(jev)

    store = ConstraintStore()
    # "all" is the standing rules, every preset but lane-closed, which arrives with a zone drop.
    standing = [r for r in PRESETS if r != CHECKER_LANE_CLOSED]
    rule_ids = standing if rules == "all" else [r for r in rules.split(",") if r]
    if rules != "none":
        unknown = [r for r in rule_ids if r not in PRESETS]
        if unknown:
            raise typer.BadParameter(
                f"unknown rule ids {unknown}; choose from {list(PRESETS)}", param_hint="--rules"
            )
        store.add_presets(rule_ids)

    shield_on = shield == "on"
    run_id = make_run_id(seed, shield_on)
    log_path = log or default_log_path(run_id)
    print(
        f"shield {shield} | seed {seed} | jev {jev_mode} | rules {[c.text for c in store.constraints]}"
        f" | thresholds {t_allow}/{t_block} | floor {floor_s:g} s | operator {operator}"
        f" | log {log_path}"
    )
    on_step = None if quiet else lambda result: print(format_step(result), flush=True)

    async def run_and_close() -> dict[str, Any]:
        judge = make_client(jev_mode, model=model)
        runner = EpisodeRunner(
            policy=Policy.load(model_path),
            judge=judge,
            store=store,
            thresholds=Thresholds(t_allow, t_block),
            floor_s=floor_s,
            shield_on=shield_on,
            operator=OPERATORS[operator],
            operator_name=operator,
            logger=JsonlLogger(log_path),
            source=jev_mode,
        )
        runner.run_id = run_id
        try:
            return await runner.run(
                seed, max_steps=max_steps, on_step=on_step, zone_at_step=zone_at_step
            )
        finally:
            runner.close()
            await judge.close()

    print(json.dumps(asyncio.run(run_and_close()), indent=2))


def main(argv: Sequence[str] | None = None) -> None:
    """``python -m backend.run_episode``: the ``interlock run`` command on its own."""
    run_standalone(command, argv)


if __name__ == "__main__":
    main()
