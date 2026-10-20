"""Hand-label candidate actions against a rule that has no checker. Plan 16.2, A5.

    interlock label --run backend/logs/eval/<stamp>_on_ta0.30_tb0.70 --rule dense_traffic
    interlock label --run backend/logs/runs/<run_id>.jsonl --rule "plenty of room" --sample 100

A label is keyed by a hash of the candidate's facts and the rule text, like
the Jev cache, so it applies to every run that shows the same state and the
same rule. Labels land in backend/logs/labels/<group>.jsonl and feed the
calibration of rules the checkers cannot score (metrics.collect_checks).
Jev's probability is hidden while labeling unless --show-p is given, so the
label is the operator's judgment, not the judge's. Each row names its labeler,
``human`` here and ``autolabel`` for the fixed standard in backend/autolabel.py,
and the report shows that name as the rule's label source.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.constraints import PRESETS
from backend.logger import read_log
from backend.paths import LOGS_DIR

LABELS_DIR = LOGS_DIR / "labels"
BINS = 10
ANSWERS = ("y", "n", "s", "q")


def label_key(facts: dict[str, Any], rule_text: str) -> str:
    canonical = json.dumps(
        {"facts": facts, "rule": rule_text},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


def rule_group(text: str) -> str:
    """Calibration group for a rule: its preset id when the text is a preset, else a slug."""
    for preset_id, preset_text in PRESETS.items():
        if text == preset_text:
            return preset_id
    return slug(text)


@dataclass(frozen=True)
class Label:
    """One answer: whether the action violates the rule, and who said so."""

    violation: bool
    labeler: str


def load_labels(directory: Path = LABELS_DIR) -> dict[str, Label]:
    """Every label under the directory, keyed by content hash; a later line wins."""
    labels: dict[str, Label] = {}
    if not directory.exists():
        return labels
    for path in sorted(directory.glob("*.jsonl")):
        with path.open() as fh:
            for line in fh:
                if line.strip():
                    row = json.loads(line)
                    labels[row["key"]] = Label(bool(row["label"]), str(row.get("labeler", "human")))
    return labels


@dataclass(frozen=True)
class Item:
    run_id: str
    seed: int
    step: int
    action: str
    rank: int
    rule_id: str
    rule_text: str
    facts: dict[str, Any]
    sentences: list[str]
    p: float
    key: str


def read_records(run: Path) -> list[dict[str, Any]]:
    """A single JSONL log, or every seed*.jsonl in an eval run directory."""
    if run.is_dir():
        paths = sorted(run.glob("seed*.jsonl"), key=lambda p: int(p.stem[4:]))
    else:
        paths = [run]
    return [r for path in paths for r in read_log(path)]


def find_rule(record: dict[str, Any], rule: str) -> dict[str, Any] | None:
    """Match a constraint by id, by preset id, or by a case-insensitive substring of its text."""
    needle = rule.lower()
    preset_text = PRESETS.get(rule)
    for c in record["constraints"]:
        if c["id"] == rule or c["text"] == preset_text or needle in c["text"].lower():
            return c
    return None


def collect_items(
    records: Iterable[dict[str, Any]], rule: str, unlabeled_only: bool = True
) -> list[Item]:
    """Every (step, candidate) pair checked against the rule, by default only those no checker scored."""
    items: list[Item] = []
    for r in records:
        c = find_rule(r, rule)
        if c is None:
            continue
        for cand in r["candidates"]:
            check = next((k for k in cand["checks"] if k["constraint_id"] == c["id"]), None)
            if check is None or (unlabeled_only and check["ground_truth"] is not None):
                continue
            items.append(
                Item(
                    run_id=r["run_id"],
                    seed=r["seed"],
                    step=r["step"],
                    action=cand["action"],
                    rank=cand["rank"],
                    rule_id=c["id"],
                    rule_text=c["text"],
                    facts=cand["facts"],
                    sentences=cand["sentences"],
                    p=float(check["p_violation"]),
                    key=label_key(cand["facts"], c["text"]),
                )
            )
    return items


def sample_items(items: list[Item], n: int, rng: random.Random, done: set[str]) -> list[Item]:
    """Up to n distinct items not yet labeled, spread across ten bins of p so labels cover the range."""
    fresh: dict[str, Item] = {}
    for item in items:
        if item.key not in done and item.key not in fresh:
            fresh[item.key] = item
    bins: list[list[Item]] = [[] for _ in range(BINS)]
    for item in fresh.values():
        bins[min(int(item.p * BINS), BINS - 1)].append(item)
    for b in bins:
        rng.shuffle(b)
    out: list[Item] = []
    while len(out) < n and any(bins):
        for b in bins:
            if b and len(out) < n:
                out.append(b.pop())
    return out


def render(item: Item, index: int, total: int, show_p: bool) -> str:
    lines = [
        "",
        f"[{index}/{total}] seed {item.seed} step {item.step}, candidate {item.action} (rank {item.rank + 1})",
        f'Rule: "{item.rule_text}"',
        *(f"  {s}" for s in item.sentences),
    ]
    if show_p:
        lines.append(f"  Jev p(violation) = {item.p:.2f}")
    lines.append("Violation? [y]es / [n]o / [s]kip / [q]uit: ")
    return "\n".join(lines)


def label_session(
    items: Sequence[Item],
    ask: Callable[[str], str],
    out_path: Path,
    *,
    show_p: bool = False,
    labeler: str = "human",
) -> int:
    """Prompt for each item and append one JSONL row per answer. Returns the number labeled."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    labeled = 0
    with out_path.open("a") as fh:
        for index, item in enumerate(items, 1):
            prompt = render(item, index, len(items), show_p)
            while True:
                answer = ask(prompt).strip().lower()[:1]
                if answer in ANSWERS:
                    break
                prompt = "answer y, n, s or q: "
            if answer == "q":
                break
            if answer == "s":
                continue
            fh.write(
                json.dumps(
                    {
                        "key": item.key,
                        "rule": item.rule_text,
                        "label": answer == "y",
                        "run_id": item.run_id,
                        "seed": item.seed,
                        "step": item.step,
                        "action": item.action,
                        "p_violation": item.p,
                        "labeler": labeler,
                        "ts": time.time(),
                    }
                )
                + "\n"
            )
            fh.flush()
            labeled += 1
    return labeled


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Flags shared by ``python -m backend.label`` and ``interlock label``."""
    parser.add_argument(
        "--run", type=Path, required=True, help="a JSONL log or an eval run directory"
    )
    parser.add_argument(
        "--rule", required=True, help="constraint id, preset id, or a substring of the rule text"
    )
    parser.add_argument(
        "--sample", type=int, default=50, help="how many pairs to label (default 50)"
    )
    parser.add_argument("--seed", type=int, default=0, help="sampling seed (default 0)")
    parser.add_argument(
        "--labels",
        type=Path,
        default=None,
        help="output file (default backend/logs/labels/<group>.jsonl)",
    )
    parser.add_argument(
        "--show-p", action="store_true", help="show Jev's probability while labeling"
    )
    parser.add_argument(
        "--include-scored", action="store_true", help="also offer pairs a checker already labeled"
    )


def run_cli(args: argparse.Namespace) -> int:
    records = read_records(args.run)
    if not records:
        print(f"no records under {args.run}", file=sys.stderr)
        return 2
    items = collect_items(records, args.rule, unlabeled_only=not args.include_scored)
    if not items:
        print(f"no candidate checks for rule {args.rule!r} in {args.run}", file=sys.stderr)
        return 2
    rule_text = items[0].rule_text
    out_path = args.labels or LABELS_DIR / f"{rule_group(rule_text)}.jsonl"
    done = set(load_labels(LABELS_DIR))
    sample = sample_items(items, args.sample, random.Random(args.seed), done)
    distinct = len({i.key for i in items})
    print(
        f'rule "{rule_text}": {len(items)} checks, {distinct} distinct states, '
        f"{len({i.key for i in items} & done)} already labeled, {len(sample)} to label now. "
        f"Labels go to {out_path}."
    )
    labeled = label_session(sample, input, out_path, show_p=args.show_p)
    print(f"\nlabeled {labeled}. Rebuild the report with: uv run interlock eval --report")
    return 0


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    add_arguments(parser)
    sys.exit(run_cli(parser.parse_args(argv)))


if __name__ == "__main__":
    main()
