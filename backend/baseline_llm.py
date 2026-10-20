"""Chat-LLM baseline for the judge, offline. Plan section 16.3.

Behind ``interlock baseline``; ``python -m backend.baseline_llm`` takes the same flags.
Samples labeled (candidate action, rule) checks from the newest eval runs,
stratified by rule and label, sends each chat model the identical facts JSON
and question text the judge saw, and asks for one probability of violation
as a structured JSON object (output_config.format; the forced tool call this
replaced is rejected by Claude Sonnet 5.5). Thinking stays at each model's
default. Jev's answers for the same checks come from the logs, so Jev costs
nothing. Latency and tokens are recorded; prices are never
hardcoded: cost appears only when backend/prices.json exists (copy
backend/prices.example.json and fill it from the pricing page) or --prices
names another file. Answers are cached
under backend/logs/baseline_cache.jsonl, so a re-run with the same sample is
free. Writes internal/eval/baseline.json, which `interlock eval --report`
folds into latest.json and plots.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import statistics
import sys
import time
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer
from dotenv import load_dotenv

from backend.cli_support import repo_relative, run_standalone
from backend.evaluate import EVAL_DIR, newest_runs
from backend.jev_client import build_question, question_dict
from backend.label import Label, label_key, load_labels, rule_group
from backend.logger import read_log
from backend.metrics import Check, reliability
from backend.paths import BACKEND_DIR, ENV_FILE, INTERNAL_DIR, LOGS_DIR

DEFAULT_MODELS = ("claude-haiku-5-5", "claude-sonnet-5-5")
BASELINE_PATH = INTERNAL_DIR / "eval" / "baseline.json"
DEFAULT_PRICES_PATH = BACKEND_DIR / "prices.json"  # gitignored; see prices.example.json
CACHE_PATH = LOGS_DIR / "baseline_cache.jsonl"
MAX_TOKENS = 4096  # the JSON is a dozen tokens; the model's own thinking counts against this too
FORMAT: dict[str, Any] = {  # structured output: the reply is this object and nothing else
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {"probability": {"type": "number"}},  # bounds are not in the schema subset
        "required": ["probability"],
        "additionalProperties": False,
    },
}
SYSTEM = (
    "You judge candidate actions for an autonomous driving shield. You receive the state as "
    "JSON, computed by code with units in the field names, and one operator rule. Answer with "
    "the probability, from 0 to 1, that executing the candidate action would violate the rule, "
    "as a JSON object with one field, probability. Judge only the action named."
)


@dataclass(frozen=True)
class Item:
    """One labeled check: a candidate's facts, the rule, the label and Jev's answer."""

    key: str  # hash of facts and rule text; the cache and the hand labels use the same key
    group: str  # calibration group: checker id, or preset id for a hand-labeled rule
    rule_text: str
    action: str
    facts: dict[str, Any]
    label: bool
    jev_p: float


@dataclass(frozen=True)
class Reply:
    p: float | None  # None when the call failed after retries
    latency_ms: float
    input_tokens: int
    output_tokens: int
    source: str  # live, cache or failed

    def to_dict(self) -> dict[str, Any]:
        return {
            "p": self.p,
            "latency_ms": self.latency_ms,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }


Ask = Callable[[str, Item], Awaitable[Reply]]


def collect_items(records: Iterable[dict[str, Any]], labels: dict[str, Label] | None) -> list[Item]:
    """Every labeled check with its facts, one per distinct state and rule.

    Mirrors ``metrics._collect``: checker rules are labeled by the checker, rules
    without one by hand labels keyed like the Jev cache. A state judged in several
    runs appears once, with the first run's probability.
    """
    out: dict[str, Item] = {}
    for r in records:
        by_id = {c["id"]: c for c in r["constraints"]}
        for cand in r["candidates"]:
            for check in cand["checks"]:
                c = by_id.get(check["constraint_id"])
                if c is None:
                    continue
                key = label_key(cand["facts"], c["text"])
                if key in out:
                    continue
                truth = check["ground_truth"]
                group = c["checker"] if c.get("checker") else rule_group(c["text"])
                if truth is None and labels and key in labels:
                    truth = labels[key].violation
                if truth is None:
                    continue
                out[key] = Item(
                    key=key,
                    group=group,
                    rule_text=c["text"],
                    action=cand["action"],
                    facts=cand["facts"],
                    label=bool(truth),
                    jev_p=float(check["p_violation"]),
                )
    return list(out.values())


def stratified_sample(items: list[Item], n: int, rng: random.Random) -> list[Item]:
    """About ``n`` items spread evenly over (rule, label) strata, topped up from the rest."""
    strata: dict[tuple[str, bool], list[Item]] = {}
    for item in items:
        strata.setdefault((item.group, item.label), []).append(item)
    if not strata or n <= 0:
        return []
    quota = max(1, n // len(strata))
    chosen: list[Item] = []
    leftovers: list[Item] = []
    for key in sorted(strata):
        members = list(strata[key])
        rng.shuffle(members)
        chosen.extend(members[:quota])
        leftovers.extend(members[quota:])
    rng.shuffle(leftovers)
    chosen.extend(leftovers[: max(0, n - len(chosen))])
    return chosen


def build_messages(item: Item) -> tuple[str, str]:
    """The system prompt and the user turn: the judge's own question text plus the facts."""
    q = question_dict(build_question(item.rule_text))
    user = (
        f"Question: {q['instructions']}\n"
        f"True when: {q['criteria']['true']}\n"
        f"False when: {q['criteria']['false']}\n\n"
        f"Candidate action: {item.action}\n"
        f"State:\n```json\n{json.dumps(item.facts, indent=1)}\n```"
    )
    return SYSTEM, user


class BaselineCache:
    """Append-only JSONL of replies keyed by model and item key."""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self._rows: dict[tuple[str, str], Reply] = {}
        if path is not None and path.exists():
            with path.open() as fh:
                for line in fh:
                    if line.strip():
                        row = json.loads(line)
                        self._rows[(row["model"], row["key"])] = Reply(
                            row["p"],
                            row["latency_ms"],
                            row["input_tokens"],
                            row["output_tokens"],
                            "cache",
                        )

    def get(self, model: str, key: str) -> Reply | None:
        return self._rows.get((model, key))

    def put(self, model: str, key: str, reply: Reply) -> None:
        self._rows[(model, key)] = Reply(
            reply.p, reply.latency_ms, reply.input_tokens, reply.output_tokens, "cache"
        )
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as fh:
            fh.write(json.dumps({"model": model, "key": key, **reply.to_dict()}) + "\n")


def _fatal_errors() -> tuple[type[Exception], ...]:
    """Errors that will repeat on every call: a bad key, no workspace, an unknown model."""
    import anthropic

    return (
        anthropic.AuthenticationError,
        anthropic.PermissionDeniedError,
        anthropic.BadRequestError,
        anthropic.NotFoundError,
    )


def parse_probability(stop_reason: str | None, texts: Sequence[str]) -> float | None:
    """The clamped probability from a structured reply, or None when there is no such reply.

    Only a reply that ended on its own carries the schema guarantee: one cut off at
    MAX_TOKENS or stopped by a refusal may hold anything, so it counts as failed.
    """
    if stop_reason != "end_turn" or not texts:
        return None
    try:
        value = json.loads(texts[0])["probability"]
        return min(1.0, max(0.0, float(value)))
    except (ValueError, KeyError, TypeError):
        return None


class AnthropicChat:
    """Asks a Claude model for one probability per item as a structured JSON object."""

    def __init__(
        self,
        cache: BaselineCache,
        max_retries: int = 5,
        api_key: str | None = None,
        workspace_id: str | None = None,
    ) -> None:
        from anthropic import AsyncAnthropic  # imported here so tests never need the key

        # A key that is not scoped to a workspace must name one on every request.
        workspace_id = workspace_id or os.environ.get("ANTHROPIC_WORKSPACE_ID")
        headers = {"anthropic-workspace-id": workspace_id} if workspace_id else None
        self.client = AsyncAnthropic(
            api_key=api_key, max_retries=max_retries, default_headers=headers
        )
        self.cache = cache

    async def ask(self, model: str, item: Item) -> Reply:
        cached = self.cache.get(model, item.key)
        if cached is not None:
            return cached
        system, user = build_messages(item)
        started = time.perf_counter()
        FATAL = _fatal_errors()
        try:
            response = await self.client.messages.create(
                model=model,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={"format": FORMAT},
            )
        except FATAL as exc:  # the same request will fail 4,000 times; stop now
            raise SystemExit(f"{model}: {type(exc).__name__}: {exc}") from exc
        except Exception as exc:  # a transient failure must not sink a 2,000-call run
            print(f"  {model}: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
            return Reply(None, round((time.perf_counter() - started) * 1000, 1), 0, 0, "failed")
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        usage = response.usage
        p = parse_probability(
            response.stop_reason, [b.text for b in response.content if b.type == "text"]
        )
        if p is None:  # the tokens were spent all the same, so they count
            print(
                f"  {model}: no probability in the reply, stop_reason {response.stop_reason}",
                file=sys.stderr,
                flush=True,
            )
            return Reply(None, latency_ms, usage.input_tokens, usage.output_tokens, "failed")
        reply = Reply(p, latency_ms, usage.input_tokens, usage.output_tokens, "live")
        self.cache.put(model, item.key, reply)
        return reply

    async def close(self) -> None:
        await self.client.close()


async def run_models(
    items: list[Item], models: Sequence[str], ask: Ask, concurrency: int = 4
) -> dict[str, list[Reply]]:
    """Every item through every model, ``concurrency`` calls in flight per model."""
    semaphore = asyncio.Semaphore(concurrency)

    async def one(model: str, item: Item) -> Reply:
        async with semaphore:
            return await ask(model, item)

    out: dict[str, list[Reply]] = {}
    for model in models:
        out[model] = list(await asyncio.gather(*(one(model, item) for item in items)))
    return out


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * (len(ordered) - 1)))]


def judge_summary(
    checks: list[Check], replies: list[Reply] | None, price: dict[str, float] | None
) -> dict[str, Any]:
    """Reliability overall and per rule, plus latency, tokens and cost when known."""
    groups = sorted({g for _, _, g in checks})
    out: dict[str, Any] = {
        "overall": reliability(checks),
        "by_group": {g: reliability([c for c in checks if c[2] == g]) for g in groups},
    }
    if replies is None:
        return out
    live = [r.latency_ms for r in replies if r.source == "live"]
    input_tokens = sum(r.input_tokens for r in replies)
    output_tokens = sum(r.output_tokens for r in replies)
    out.update(
        {
            "answered": sum(r.p is not None for r in replies),
            "failed": sum(r.source == "failed" for r in replies),
            "live": len(live),
            "cached": sum(r.source == "cache" for r in replies),
            "latency_ms_p50": round(statistics.median(live), 1) if live else None,
            "latency_ms_p95": round(_percentile(live, 0.95), 1) if live else None,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": None
            if price is None
            else round(
                input_tokens / 1e6 * price["input_per_mtok"]
                + output_tokens / 1e6 * price["output_per_mtok"],
                4,
            ),
        }
    )
    return out


def summarize(
    items: list[Item],
    replies_by_model: dict[str, list[Reply]],
    prices: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    """The baseline block: the same checks judged by Jev (from the logs) and by each model."""
    strata: dict[str, dict[str, int]] = {}
    for item in items:
        strata.setdefault(item.group, {"violation": 0, "ok": 0})
        strata[item.group]["violation" if item.label else "ok"] += 1
    out: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "checks": len(items),
        "strata": strata,
        "jev": judge_summary([(i.jev_p, i.label, i.group) for i in items], None, None),
        "models": {},
    }
    for model, replies in replies_by_model.items():
        checks = [
            (r.p, i.label, i.group) for r, i in zip(replies, items, strict=True) if r.p is not None
        ]
        out["models"][model] = judge_summary(
            checks, replies, (prices or {}).get(model) if prices else None
        )
    return out


def load_prices(path: Path | None) -> dict[str, dict[str, float]] | None:
    """Per-model USD per million tokens from ``path``, or from backend/prices.json when present.

    Returns None when there is no file. Raises ValueError when an entry is not a
    pair of numbers, so a copied example with blanks fails loudly instead of
    pricing a run at zero.
    """
    if path is None:
        if not DEFAULT_PRICES_PATH.exists():
            return None
        path = DEFAULT_PRICES_PATH
    raw = json.loads(path.read_text())
    prices: dict[str, dict[str, float]] = {}
    for model, entry in raw.items():
        if model.startswith("_"):
            continue  # notes
        try:
            prices[model] = {
                "input_per_mtok": float(entry["input_per_mtok"]),
                "output_per_mtok": float(entry["output_per_mtok"]),
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"{path}: {model} needs numeric input_per_mtok and output_per_mtok"
            ) from exc
    return prices


def load_items(root: Path, labels: dict[str, Label] | None) -> list[Item]:
    """Labeled checks from every seed log of the newest run per label under ``root``."""
    records: list[dict[str, Any]] = []
    for path in newest_runs(root).values():
        for log in sorted(path.glob("seed*.jsonl")):
            records.extend(read_log(log))
    return collect_items(records, labels)


def print_summary(summary: dict[str, Any]) -> None:
    jev = summary["jev"]["overall"]
    print(
        f"{summary['checks']} checks | jev: ECE {jev['ece']:.3f} Brier {jev['brier']:.3f} "
        f"acc {jev['accuracy_at_0_5']:.1%}"
    )
    for model, s in summary["models"].items():
        o = s["overall"]
        cost = "n/a" if s["cost_usd"] is None else f"${s['cost_usd']:.3f}"
        p50 = "n/a" if s["latency_ms_p50"] is None else f"{s['latency_ms_p50']:.0f} ms"
        print(
            f"{model}: ECE {o['ece']:.3f} Brier {o['brier']:.3f} acc {o['accuracy_at_0_5']:.1%} | "
            f"answered {s['answered']} failed {s['failed']} | p50 {p50} | "
            f"tokens {s['input_tokens']} in {s['output_tokens']} out | cost {cost}"
        )


def command(
    checks: Annotated[int, typer.Option(help="checks to sample")] = 2000,
    models: Annotated[str, typer.Option(help="comma list of model ids")] = ",".join(DEFAULT_MODELS),
    runs: Annotated[
        Path, typer.Option(help="eval runs root", show_default=repo_relative(EVAL_DIR))
    ] = EVAL_DIR,
    seed: Annotated[int, typer.Option(help="sampling seed")] = 0,
    concurrency: Annotated[int, typer.Option(help="calls in flight per model")] = 4,
    prices: Annotated[
        Path | None,
        typer.Option(
            help="JSON `{model: {input_per_mtok, output_per_mtok}}` in USD; "
            "default backend/prices.json when it exists"
        ),
    ] = None,
    out: Annotated[
        Path, typer.Option(help="where the block goes", show_default=repo_relative(BASELINE_PATH))
    ] = BASELINE_PATH,
    cache: Annotated[
        Path, typer.Option(help="reply cache JSONL", show_default=repo_relative(CACHE_PATH))
    ] = CACHE_PATH,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="sample, print the strata and one request, send nothing"),
    ] = False,
) -> None:
    """Chat-LLM baseline on logged checks: the judge's own questions, scored the same way.

    ```
    interlock baseline --checks 2000 --models claude-haiku-5-5,claude-sonnet-5-5
    interlock baseline --dry-run                      # sample, print one request, send nothing
    interlock baseline --prices other-prices.json     # prices from somewhere else
    ```

    Needs ANTHROPIC_API_KEY in backend/.env unless `--dry-run`. Writes
    `internal/eval/baseline.json`, which `interlock eval --report` folds into the report.
    """
    load_dotenv(ENV_FILE)
    items = load_items(runs, load_labels())
    if not items:
        typer.echo(f"no labeled checks under {runs}", err=True)
        raise typer.Exit(2)
    sample = stratified_sample(items, checks, random.Random(seed))
    model_ids = [m for m in models.split(",") if m]
    strata: dict[str, dict[str, int]] = {}
    for item in sample:
        strata.setdefault(item.group, {"violation": 0, "ok": 0})
        strata[item.group]["violation" if item.label else "ok"] += 1
    print(
        f"{len(items)} distinct labeled checks, {len(sample)} sampled: {json.dumps(strata)}",
        flush=True,
    )
    if dry_run:
        system, user = build_messages(sample[0])
        print(
            f"\nmodels: {model_ids}\n\nsystem:\n{system}\n\nuser:\n{user}\n\n"
            f"output format:\n{json.dumps(FORMAT)}"
        )
        return
    if not os.environ.get("ANTHROPIC_API_KEY"):
        typer.echo("ANTHROPIC_API_KEY is not set; put it in backend/.env", err=True)
        raise typer.Exit(2)
    try:
        price_table = load_prices(prices)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc
    if price_table is None:
        print("no prices file: tokens will be reported, cost will read n/a")
    chat = AnthropicChat(BaselineCache(cache))

    async def run_and_close() -> dict[str, list[Reply]]:
        try:  # close on the loop that opened the connections
            return await run_models(sample, model_ids, chat.ask, concurrency)
        finally:
            await chat.close()

    replies = asyncio.run(run_and_close())
    result = summarize(sample, replies, price_table)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1))
    print_summary(result)
    print(f"\nwrote {out}. Fold it into the report with: uv run interlock eval --report")


def main(argv: Sequence[str] | None = None) -> None:
    """``python -m backend.baseline_llm``: the ``interlock baseline`` command on its own."""
    run_standalone(command, argv)


if __name__ == "__main__":
    main()
