import asyncio
import json
import random
from pathlib import Path
from typing import Any

from backend.baseline_llm import (
    FORMAT,
    BaselineCache,
    Item,
    Reply,
    build_messages,
    collect_items,
    command,
    parse_probability,
    run_models,
    stratified_sample,
    summarize,
)
from backend.label import Label, label_key

RULE = "Speed limit 25 m/s"
FUZZY = "Drive conservatively in dense traffic"


def facts(action: str, speed_after: float) -> dict[str, Any]:
    return {
        "ego": {"lane": 2, "lane_count": 4, "speed_mps": 25.0, "target_speed_mps": 25.0},
        "action": {"name": action, "lane_after": 2, "target_speed_after_mps": speed_after},
        "lane_after_action": {"time_to_collision_ahead_s": None},
    }


def record(step: int, p_faster: float, p_idle: float) -> dict[str, Any]:
    return {
        "step": step,
        "constraints": [
            {"id": "c1", "text": RULE, "enabled": True, "checker": "speed_limit"},
            {"id": "c2", "text": FUZZY, "enabled": True, "checker": None},
        ],
        "candidates": [
            {
                "action": "FASTER",
                "facts": facts("FASTER", 30.0),
                "checks": [
                    {"constraint_id": "c1", "p_violation": p_faster, "ground_truth": True},
                    {"constraint_id": "c2", "p_violation": 0.4, "ground_truth": None},
                ],
            },
            {
                "action": "IDLE",
                "facts": facts("IDLE", 25.0 + step),  # distinct per step
                "checks": [
                    {"constraint_id": "c1", "p_violation": p_idle, "ground_truth": False},
                    {"constraint_id": "c2", "p_violation": 0.2, "ground_truth": None},
                ],
            },
        ],
    }


def test_collect_items_dedupes_states_and_takes_hand_labels_for_fuzzy_rules() -> None:
    records = [record(0, 0.9, 0.1), record(1, 0.95, 0.05)]  # FASTER facts repeat across steps
    items = collect_items(records, labels=None)
    assert [(i.action, i.group, i.label, i.jev_p) for i in items] == [
        ("FASTER", "speed_limit", True, 0.9),
        ("IDLE", "speed_limit", False, 0.1),
        ("IDLE", "speed_limit", False, 0.05),
    ]
    hand = {label_key(facts("FASTER", 30.0), FUZZY): Label(True, "human")}
    with_hand = collect_items(records, labels=hand)
    fuzzy = [i for i in with_hand if i.group == "dense_traffic"]
    assert len(fuzzy) == 1 and fuzzy[0].label is True and fuzzy[0].rule_text == FUZZY


def test_stratified_sample_spreads_over_rule_and_label_then_tops_up() -> None:
    items = [
        Item(f"k{i}", "speed_limit" if i < 40 else "headway", RULE, "IDLE", {}, i % 4 == 0, 0.5)
        for i in range(60)
    ]
    sample = stratified_sample(items, 20, random.Random(0))
    assert len(sample) == 20
    counts: dict[tuple[str, bool], int] = {}
    for item in sample:
        counts[(item.group, item.label)] = counts.get((item.group, item.label), 0) + 1
    assert all(v >= 5 for v in counts.values()) and len(counts) == 4  # quota 5 per stratum
    assert len({i.key for i in sample}) == 20
    assert stratified_sample(items, 0, random.Random(0)) == []
    assert len(stratified_sample(items[:3], 20, random.Random(0))) == 3


def test_messages_carry_the_judge_question_verbatim_and_the_facts_json() -> None:
    item = Item("k", "speed_limit", RULE, "FASTER", facts("FASTER", 30.0), True, 0.9)
    system, user = build_messages(item)
    assert "JSON object with one field, probability" in system
    assert FORMAT["schema"]["required"] == ["probability"]
    assert FORMAT["schema"]["additionalProperties"] is False
    assert f'would violate this operator rule: "{RULE}"' in user
    assert "True when:" in user and "False when:" in user
    assert '"target_speed_after_mps": 30.0' in user and "Candidate action: FASTER" in user


def test_cache_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "cache.jsonl"
    cache = BaselineCache(path)
    assert cache.get("m", "k") is None
    cache.put("m", "k", Reply(0.42, 120.0, 900, 12, "live"))
    again = BaselineCache(path)
    assert again.get("m", "k") == Reply(0.42, 120.0, 900, 12, "cache")


def test_run_models_and_summarize_compare_jev_with_each_model() -> None:
    items = [
        Item("a", "speed_limit", RULE, "FASTER", {}, True, 0.9),
        Item("b", "speed_limit", RULE, "IDLE", {}, False, 0.1),
        Item("c", "headway", "Keep 2 s", "IDLE", {}, True, 0.6),
        Item("d", "headway", "Keep 2 s", "SLOWER", {}, False, 0.3),
    ]
    answers = {"a": 0.95, "b": 0.2, "c": 0.4, "d": 0.1}

    async def fake(model: str, item: Item) -> Reply:
        if model == "bad" and item.key == "c":
            return Reply(None, 5.0, 0, 0, "failed")
        return Reply(answers[item.key], 100.0, 500, 10, "live")

    replies = asyncio.run(run_models(items, ["good", "bad"], fake, concurrency=2))
    assert len(replies["good"]) == 4 and replies["bad"][2].p is None
    prices = {"good": {"input_per_mtok": 1.0, "output_per_mtok": 5.0}}
    s = summarize(items, replies, prices)
    assert s["checks"] == 4 and s["strata"] == {
        "speed_limit": {"violation": 1, "ok": 1},
        "headway": {"violation": 1, "ok": 1},
    }
    assert s["jev"]["overall"]["accuracy_at_0_5"] == 1.0 and set(s["jev"]["by_group"]) == {
        "speed_limit",
        "headway",
    }
    good = s["models"]["good"]
    assert good["overall"]["accuracy_at_0_5"] == 0.75  # c scored 0.4 on a violation
    assert (good["answered"], good["failed"], good["live"], good["latency_ms_p50"]) == (
        4,
        0,
        4,
        100.0,
    )
    assert good["input_tokens"] == 2000 and good["cost_usd"] == round(2000 / 1e6 + 40 / 1e6 * 5, 4)
    bad = s["models"]["bad"]
    assert bad["answered"] == 3 and bad["failed"] == 1 and bad["cost_usd"] is None


def test_dry_run_samples_from_the_newest_runs_and_sends_nothing(tmp_path: Path, capsys) -> None:
    run = tmp_path / "2026-10-18T05-00-00_on_ta0.30_tb0.70"
    run.mkdir()
    (run / "metrics.json").write_text(
        json.dumps(
            {
                "label": "on_ta0.30_tb0.70",
                "shield_on": True,
                "thresholds": {"t_allow": 0.3, "t_block": 0.7},
                "zone_at_step": None,
                "floor_s": 2.0,
            }
        )
    )
    with (run / "seed0.jsonl").open("w") as fh:
        for step in range(3):
            fh.write(json.dumps(record(step, 0.9, 0.1)) + "\n")
    command(
        checks=10, models="m1", runs=tmp_path, seed=0, concurrency=1, prices=None,
        out=tmp_path / "baseline.json", cache=tmp_path / "cache.jsonl", dry_run=True,
    )  # fmt: skip
    out = capsys.readouterr().out
    assert "4 distinct labeled checks, 4 sampled" in out and "json_schema" in out
    assert "tool_choice" not in out
    assert not (tmp_path / "baseline.json").exists()


def test_prices_come_from_the_default_file_when_present_and_blanks_fail_loudly(
    tmp_path: Path, monkeypatch
) -> None:
    import pytest
    from backend import baseline_llm

    monkeypatch.setattr(baseline_llm, "DEFAULT_PRICES_PATH", tmp_path / "prices.json")
    assert baseline_llm.load_prices(None) is None
    (tmp_path / "prices.json").write_text(
        json.dumps({"_note": "x", "m1": {"input_per_mtok": 1, "output_per_mtok": "5"}})
    )
    assert baseline_llm.load_prices(None) == {"m1": {"input_per_mtok": 1.0, "output_per_mtok": 5.0}}
    other = tmp_path / "other.json"
    other.write_text(json.dumps({"m2": {"input_per_mtok": 2, "output_per_mtok": 4}}))
    assert baseline_llm.load_prices(other) == {
        "m2": {"input_per_mtok": 2.0, "output_per_mtok": 4.0}
    }
    blank = tmp_path / "blank.json"
    blank.write_text(json.dumps({"m1": {"input_per_mtok": None, "output_per_mtok": 5}}))
    with pytest.raises(ValueError, match="m1 needs numeric"):
        baseline_llm.load_prices(blank)
    example = json.loads(Path("backend/prices.example.json").read_text())
    with pytest.raises(ValueError):  # the shipped example is deliberately unfilled
        baseline_llm.load_prices(Path("backend/prices.example.json"))
    assert set(example) >= {"claude-haiku-5-5", "claude-sonnet-5-5"}


def test_parse_probability_reads_a_finished_structured_reply_and_nothing_else() -> None:
    assert parse_probability("end_turn", ['{"probability": 0.42}']) == 0.42
    assert parse_probability("end_turn", ['{"probability": 1.7}']) == 1.0  # clamped
    assert parse_probability("end_turn", ['{"probability": -2}']) == 0.0
    assert parse_probability("max_tokens", ['{"probab']) is None  # cut off: no guarantee
    assert parse_probability("refusal", []) is None
    assert parse_probability("end_turn", []) is None
    assert parse_probability("end_turn", ["not json"]) is None
    assert parse_probability("end_turn", ['{"p": 0.3}']) is None
    assert parse_probability("end_turn", ['{"probability": null}']) is None
    assert parse_probability("end_turn", ["[0.3]"]) is None


def test_ask_sends_structured_output_without_forced_tool_choice_and_caches(
    tmp_path: Path,
) -> None:
    from types import SimpleNamespace

    from backend.baseline_llm import MAX_TOKENS, AnthropicChat

    chat = AnthropicChat(BaselineCache(tmp_path / "cache.jsonl"), api_key="test-key")
    sent: dict[str, Any] = {}
    stop = {"reason": "end_turn"}

    async def fake_create(**kwargs: Any) -> Any:
        sent.clear()
        sent.update(kwargs)
        return SimpleNamespace(
            stop_reason=stop["reason"],
            content=[
                SimpleNamespace(type="thinking", thinking=""),
                SimpleNamespace(type="text", text='{"probability": 0.42}'),
            ],
            usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        )

    chat.client.messages.create = fake_create  # type: ignore[method-assign]
    item = Item("k", "speed_limit", RULE, "FASTER", facts("FASTER", 30.0), True, 0.9)
    reply = asyncio.run(chat.ask("m", item))
    assert (reply.p, reply.input_tokens, reply.output_tokens, reply.source) == (0.42, 10, 5, "live")
    assert sent["output_config"] == {"format": FORMAT} and sent["max_tokens"] == MAX_TOKENS
    assert "tool_choice" not in sent and "tools" not in sent
    assert BaselineCache(tmp_path / "cache.jsonl").get("m", "k") == Reply(
        0.42, reply.latency_ms, 10, 5, "cache"
    )
    stop["reason"] = "max_tokens"  # a cut-off reply is failed, counted, and never cached
    other = Item("k2", "speed_limit", RULE, "IDLE", facts("IDLE", 25.0), False, 0.1)
    failed = asyncio.run(chat.ask("m", other))
    assert (failed.p, failed.input_tokens, failed.source) == (None, 10, "failed")
    assert BaselineCache(tmp_path / "cache.jsonl").get("m", "k2") is None


def test_chat_client_sends_the_workspace_header_when_configured(monkeypatch) -> None:
    from backend.baseline_llm import AnthropicChat

    monkeypatch.delenv("ANTHROPIC_WORKSPACE_ID", raising=False)
    bare = AnthropicChat(BaselineCache(None), api_key="test-key")
    assert "anthropic-workspace-id" not in bare.client.default_headers
    monkeypatch.setenv("ANTHROPIC_WORKSPACE_ID", "wrkspc_123")
    scoped = AnthropicChat(BaselineCache(None), api_key="test-key")
    assert scoped.client.default_headers["anthropic-workspace-id"] == "wrkspc_123"
    explicit = AnthropicChat(BaselineCache(None), api_key="test-key", workspace_id="wrkspc_9")
    assert explicit.client.default_headers["anthropic-workspace-id"] == "wrkspc_9"
