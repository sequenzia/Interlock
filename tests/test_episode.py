import asyncio
from pathlib import Path

import pytest
from backend.constraints import ConstraintStore
from backend.env import make_env
from backend.episode import OPERATORS, EpisodeRunner, Escalation, simulated_operator
from backend.jev_client import JevCache, JevClient
from backend.logger import JsonlLogger, read_log
from backend.policy import Policy
from backend.shield import Thresholds
from backend.train import build_model

from tests.test_logger import PLAN_KEYS


@pytest.fixture(scope="module")
def policy() -> Policy:
    env = make_env()
    model = build_model(env, seed=0)
    yield Policy(model)
    env.close()


def make_runner(
    policy: Policy, tmp_path: Path, shield_on: bool, rules: bool = True, operator: str = "simulated"
) -> EpisodeRunner:
    store = ConstraintStore()
    if rules:
        store.add_presets()
    return EpisodeRunner(
        policy=policy,
        judge=JevClient(live=None, cache=JevCache(None)),
        store=store,
        thresholds=Thresholds(),
        shield_on=shield_on,
        operator=OPERATORS[operator],
        operator_name=operator,
        logger=JsonlLogger(tmp_path / "run.jsonl"),
        source="mock",
    )


def test_mock_shield_on_escalates_every_step_and_logs(policy: Policy, tmp_path: Path) -> None:
    runner = make_runner(policy, tmp_path, shield_on=True)
    summary = asyncio.run(runner.run(seed=0, max_steps=4))
    runner.close()
    records = read_log(tmp_path / "run.jsonl")
    assert len(records) == 4 and summary["steps"] == 4
    assert all(set(r) == PLAN_KEYS for r in records)
    assert all(r["decision"] == "escalate" and r["escalated"] for r in records)
    assert all(r["escalation_reason"] == "no_compliant_action" for r in records)  # p 0.5 everywhere
    assert all(r["fallback"]["kind"] == "least_bad" for r in records)
    assert all(r["judge"]["source"] == "unavailable" for r in records)
    assert all(r["human"]["operator"] == "simulated" for r in records)
    assert summary["decisions"] == {"escalate": 4} and summary["conflicts"] == 4
    assert sum(summary["human"].values()) == 4
    assert summary["judge_sources"] == {"unavailable": 4}
    for r in records:
        assert [c["rank"] for c in r["candidates"]] == [0, 1, 2, 3, 4]
        assert len(r["candidates"][0]["checks"]) == 4
        assert r["ego"]["lane"] in (1, 2, 3, 4) and len(r["vehicles"]) == 30


def test_simulated_operator_overrides_conflicts_with_the_fewest_violations(
    policy: Policy, tmp_path: Path
) -> None:
    runner = make_runner(policy, tmp_path, shield_on=True)
    asyncio.run(runner.run(seed=0, max_steps=6))
    runner.close()
    for r in read_log(tmp_path / "run.jsonl"):
        counts = {
            c["action"]: sum(bool(k["ground_truth"]) for k in c["checks"]) for c in r["candidates"]
        }
        top = r["candidates"][0]["action"]
        if counts[top] == min(counts.values()):
            assert r["human"]["decision"] == "approve" and r["executed"] == top
        else:
            assert r["human"]["decision"] == "override" and r["executed"] == r["human"]["action"]
            assert counts[r["executed"]] == min(counts.values())


def escalation(
    reason: str, ground_truth: bool | None, by_action: dict[str, int | None]
) -> Escalation:
    return Escalation(
        id="e",
        step=0,
        action="FASTER",
        sentences=[],
        constraint_id="c1",
        constraint_text="Speed limit 25 m/s",
        p=0.5,
        q_rank=0,
        fallback="IDLE",
        fallback_kind="least_bad",
        judge_unavailable=False,
        reason=reason,  # type: ignore[arg-type]
        candidates=[
            {"action": a, "rank": i, "p": 0.5, "constraint_id": "c1", "noop": False}
            for i, a in enumerate(by_action)
        ],
        ground_truth=ground_truth,
        violations_by_action=by_action,
    )


def test_simulated_operator_paths() -> None:
    uncertain = {"FASTER": 1, "IDLE": 0}
    assert (
        asyncio.run(simulated_operator(escalation("uncertain", True, uncertain))).decision == "deny"
    )
    assert (
        asyncio.run(simulated_operator(escalation("uncertain", None, uncertain))).decision == "deny"
    )
    assert (
        asyncio.run(simulated_operator(escalation("uncertain", False, uncertain))).decision
        == "approve"
    )
    conflict = {"FASTER": 1, "IDLE": 1, "LANE_RIGHT": 0, "SLOWER": 0}
    answer = asyncio.run(simulated_operator(escalation("no_compliant_action", True, conflict)))
    assert (answer.decision, answer.action) == ("override", "LANE_RIGHT")  # fewest, then rank
    tie = {"FASTER": 1, "IDLE": 1}
    assert (
        asyncio.run(simulated_operator(escalation("no_compliant_action", True, tie))).decision
        == "approve"
    )
    unknown = {"FASTER": None, "IDLE": None}
    assert (
        asyncio.run(simulated_operator(escalation("no_compliant_action", None, unknown))).decision
        == "deny"
    )


def test_shield_off_runs_in_shadow(policy: Policy, tmp_path: Path) -> None:
    runner = make_runner(policy, tmp_path, shield_on=False)
    summary = asyncio.run(runner.run(seed=0, max_steps=4))
    runner.close()
    records = read_log(tmp_path / "run.jsonl")
    assert summary["shield_on"] is False and summary["decisions"] == {"allow": 4}
    for r in records:
        assert r["executed"] == r["candidates"][0]["action"] and r["human"] is None
        assert r["escalation_reason"] is None and r["fallback"]["kind"] == "least_bad"
        assert len(r["candidates"][0]["checks"]) == 4  # judge and checkers still ran


def test_no_rules_means_allow(policy: Policy, tmp_path: Path) -> None:
    runner = make_runner(policy, tmp_path, shield_on=True, rules=False)
    summary = asyncio.run(runner.run(seed=1, max_steps=3))
    runner.close()
    assert summary["decisions"] == {"allow": 3} and summary["judge_sources"] == {"cache": 3}


def test_zone_drop_mid_episode_appears_in_facts(policy: Policy, tmp_path: Path) -> None:
    runner = make_runner(policy, tmp_path, shield_on=True)
    asyncio.run(runner.run(seed=0, max_steps=4, zone_at_step=2))
    runner.close()
    records = read_log(tmp_path / "run.jsonl")
    assert records[1]["zones"] == [] and records[2]["zones"][0]["lane"] == 3
    assert records[2]["candidates"][0]["facts"]["zones"][0]["starts_in_m"] == 120.0


def test_passed_zone_retires_its_rule_during_the_episode(policy: Policy, tmp_path: Path) -> None:
    runner = make_runner(policy, tmp_path, shield_on=True, rules=False)
    runner.reset(seed=0)
    runner.store.drop_zone(runner.ego_x_m, ahead_m=5.0, length_m=10.0)
    rule = runner.store.zone_rule()
    assert rule is not None and rule.enabled
    asyncio.run(runner.step())
    assert runner.store.zones and rule.enabled
    for _ in range(3):  # 25 m/s clears a 15 m zone within the next steps
        asyncio.run(runner.step())
    runner.close()
    assert runner.store.zones == [] and rule.enabled is False
    records = read_log(tmp_path / "run.jsonl")
    assert records[0]["constraints"][0]["enabled"] is True
    assert records[-1]["constraints"][0]["enabled"] is False
