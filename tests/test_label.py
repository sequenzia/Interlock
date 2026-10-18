import json
import random
from pathlib import Path

from backend.constraints import PRESET_DENSE_TRAFFIC, PRESETS
from backend.label import (
    collect_items,
    label_key,
    label_session,
    load_labels,
    read_records,
    rule_group,
    sample_items,
    slug,
)

RULE = PRESETS[PRESET_DENSE_TRAFFIC]


def record(step: int, p_by_action: dict[str, float], checker: str | None = None, gt=None) -> dict:
    return {
        "run_id": "r",
        "seed": 1,
        "step": step,
        "constraints": [{"id": "c1", "text": RULE, "enabled": True, "checker": checker}],
        "candidates": [
            {
                "action": a,
                "rank": i,
                "facts": {"step": step, "action": a},
                "sentences": [f"{a} at step {step}"],
                "checks": [{"constraint_id": "c1", "p_violation": p, "ground_truth": gt}],
            }
            for i, (a, p) in enumerate(p_by_action.items())
        ],
    }


def test_key_is_order_independent_and_rule_sensitive() -> None:
    assert label_key({"a": 1, "b": 2}, "r") == label_key({"b": 2, "a": 1}, "r")
    assert label_key({"a": 1}, "r") != label_key({"a": 1}, "s")


def test_rule_group_and_slug() -> None:
    assert rule_group(RULE) == "dense_traffic"
    assert rule_group("Be courteous to trucks!") == "be-courteous-to-trucks"
    assert slug("  A  b ") == "a-b"


def test_collect_skips_checker_labeled_pairs_and_matches_rules_three_ways() -> None:
    recs = [record(0, {"IDLE": 0.2, "FASTER": 0.7}), record(1, {"IDLE": 0.4}, gt=False)]
    items = collect_items(recs, "dense_traffic")
    assert [(i.step, i.action, i.p) for i in items] == [(0, "IDLE", 0.2), (0, "FASTER", 0.7)]
    assert collect_items(recs, "c1") == items and collect_items(recs, "conservatively") == items
    assert len(collect_items(recs, "dense_traffic", unlabeled_only=False)) == 3
    assert collect_items(recs, "nope") == []
    assert items[0].key == label_key({"step": 0, "action": "IDLE"}, RULE)


def test_sample_spreads_over_bins_and_skips_done() -> None:
    recs = [record(s, {"IDLE": s / 20, "FASTER": 1 - s / 20}) for s in range(20)]
    items = collect_items(recs, "c1")
    done = {items[0].key}
    sample = sample_items(items, 10, random.Random(0), done)
    assert len(sample) == 10 and items[0].key not in {i.key for i in sample}
    assert len({min(int(i.p * 10), 9) for i in sample}) == 10  # one per bin before any repeats
    assert len({i.key for i in sample}) == 10
    assert len(sample_items(items, 100, random.Random(0), done)) == 39


def test_label_session_writes_rows_and_honours_skip_and_quit(tmp_path: Path) -> None:
    items = collect_items([record(0, {"IDLE": 0.2, "FASTER": 0.7, "SLOWER": 0.5})], "c1")
    answers = iter(["x", "y", "s", "q"])  # a bad answer re-prompts; then yes, skip, quit
    prompts: list[str] = []

    def ask(prompt: str) -> str:
        prompts.append(prompt)
        return next(answers)

    out = tmp_path / "labels" / "dense_traffic.jsonl"
    assert label_session(items, ask, out) == 1
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["label"] is True and rows[0]["action"] == "IDLE"
    assert rows[0]["key"] == items[0].key and rows[0]["rule"] == RULE
    assert "Jev p" not in prompts[0] and "IDLE at step 0" in prompts[0] and RULE in prompts[0]
    assert prompts[1].startswith("answer y, n, s or q")
    assert load_labels(tmp_path / "labels") == {items[0].key: True}
    assert label_session(items[:1], lambda _: "n", out, show_p=True) == 1
    assert load_labels(tmp_path / "labels") == {items[0].key: False}  # the later line wins
    assert load_labels(tmp_path / "missing") == {}


def test_read_records_takes_a_file_or_an_eval_directory(tmp_path: Path) -> None:
    (tmp_path / "seed10.jsonl").write_text(json.dumps(record(0, {"IDLE": 0.1})) + "\n")
    (tmp_path / "seed2.jsonl").write_text(json.dumps(record(1, {"IDLE": 0.1})) + "\n")
    assert [r["step"] for r in read_records(tmp_path)] == [1, 0]  # numeric seed order
    assert len(read_records(tmp_path / "seed2.jsonl")) == 1
