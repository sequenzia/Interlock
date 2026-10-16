import asyncio
from pathlib import Path
from typing import Any

import pytest
from backend.constraints import Constraint
from backend.jev_client import (
    JevCache,
    JevClient,
    LiveAnswer,
    LiveJudge,
    build_question,
    cache_key,
    make_client,
)
from typesafe_sdk import Noul

SPEED = Constraint("c1", "Speed limit 25 m/s", checker="speed_limit")
GAP = Constraint(
    "c2", "No lane change if a vehicle is within 10 m in the target lane", checker="lane_change_gap"
)
FACTS = {
    "FASTER": {"ego": {"speed_mps": 25.0}, "action": {"name": "FASTER"}},
    "IDLE": {"ego": {"speed_mps": 25.0}, "action": {"name": "IDLE"}},
}


class FakeJudge:
    """Scripted stand-in for LiveJudge: returns canned p or None to simulate an outage."""

    def __init__(self, p_by_action: dict[str, float] | None) -> None:
        self.p_by_action = p_by_action
        self.calls: list[tuple[Any, list[str]]] = []

    async def ask(self, state: Any, questions: dict[str, Noul]) -> LiveAnswer | None:
        self.calls.append((state, list(questions)))
        if self.p_by_action is None:
            return None
        p = self.p_by_action[state["action"]["name"]]
        return LiveAnswer(
            p=dict.fromkeys(questions, p),
            model="jev-test",
            input_tokens=100,
            raw_response={"ok": True},
            latency_ms=12.0,
        )

    async def close(self) -> None:
        pass


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def test_question_is_positive_with_rule_verbatim() -> None:
    q = build_question(SPEED.text)
    dumped = q.model_dump(by_alias=True, exclude_none=True)
    assert dumped["type"] == "noul" and SPEED.text in dumped["instructions"]
    assert set(dumped["criteria"]) == {"true", "false"}


def test_cache_key_depends_on_state_rule_and_model() -> None:
    base = cache_key("jev-latest", FACTS["FASTER"], build_question(SPEED.text))
    assert base == cache_key("jev-latest", FACTS["FASTER"], build_question(SPEED.text))
    assert base != cache_key("jev-latest", FACTS["IDLE"], build_question(SPEED.text))
    assert base != cache_key("jev-latest", FACTS["FASTER"], build_question(GAP.text))
    assert base != cache_key("jev-1.13.0", FACTS["FASTER"], build_question(SPEED.text))


def test_mock_mode_miss_is_unavailable_at_half() -> None:
    client = JevClient(live=None, cache=JevCache(None))
    result = run(client.check(FACTS, [SPEED, GAP]))
    assert result.p == {"FASTER": {"c1": 0.5, "c2": 0.5}, "IDLE": {"c1": 0.5, "c2": 0.5}}
    assert result.source == "unavailable" and result.judge_unavailable
    assert result.input_tokens == 0 and result.cost_usd == 0.0
    assert [e.source for e in result.exchanges] == ["unavailable", "unavailable"]


def test_live_answers_are_cached_and_replayed(tmp_path: Path) -> None:
    cache_path = tmp_path / "cache.jsonl"
    judge = FakeJudge({"FASTER": 0.9, "IDLE": 0.1})
    client = JevClient(live=judge, cache=JevCache(cache_path))  # type: ignore[arg-type]
    first = run(client.check(FACTS, [SPEED, GAP]))
    assert first.p["FASTER"]["c1"] == 0.9 and first.p["IDLE"]["c2"] == 0.1
    assert first.source == "live" and first.model == "jev-test"
    assert first.input_tokens == 200 and first.cost_usd > 0
    assert len(judge.calls) == 2 and cache_path.exists()

    replay = JevClient(live=None, cache=JevCache(cache_path))
    second = run(replay.check(FACTS, [SPEED, GAP]))
    assert second.p == first.p and second.source == "cache" and second.exchanges == []

    partial = JevClient(live=judge, cache=JevCache(cache_path))  # type: ignore[arg-type]
    new_rule = Constraint("c3", "Keep the left lane for passing only")
    third = run(partial.check(FACTS, [SPEED, new_rule]))
    assert third.sources["FASTER"] == {"c1": "cache", "c3": "live"}
    assert judge.calls[-1][1] == ["c3"]  # only the miss went to the network


def test_outage_after_a_warm_cache_is_mixed_but_flagged() -> None:
    cache = JevCache(None)
    warm = JevClient(live=FakeJudge({"FASTER": 0.9, "IDLE": 0.1}), cache=cache)  # type: ignore[arg-type]
    run(warm.check(FACTS, [SPEED]))
    down = JevClient(live=FakeJudge(None), cache=cache)  # type: ignore[arg-type]
    result = run(down.check(FACTS, [SPEED, GAP]))
    assert result.p["FASTER"] == {"c1": 0.9, "c2": 0.5}
    assert result.sources["FASTER"] == {"c1": "cache", "c2": "unavailable"}
    assert result.source == "unavailable"


def test_no_constraints_means_nothing_to_ask() -> None:
    result = run(JevClient(live=None, cache=JevCache(None)).check(FACTS, []))
    assert result.p == {"FASTER": {}, "IDLE": {}} and result.source == "cache"


def test_make_client_modes(tmp_path: Path) -> None:
    assert make_client("mock", cache_path=tmp_path / "c.jsonl").mode == "mock"


def test_live_judge_constructs_and_closes_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key-not-real")
    judge = LiveJudge()
    run(judge.close())
