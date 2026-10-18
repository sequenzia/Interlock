import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from backend import server as server_module
from backend.env import make_env
from backend.jev_client import JevCache, JevClient
from backend.policy import Policy
from backend.server import Session, create_app
from backend.train import build_model
from fastapi.testclient import TestClient

from tests.test_logger import PLAN_KEYS


@pytest.fixture(scope="module")
def policy() -> Iterator[Policy]:
    env = make_env()
    yield Policy(build_model(env, seed=0))
    env.close()


@pytest.fixture
def client(policy: Policy, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(server_module, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr("backend.logger.LOGS_DIR", tmp_path)
    monkeypatch.setattr("backend.twin.RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr("backend.twin.EVAL_DIR", tmp_path / "eval")
    session = Session(policy, JevClient(live=None, cache=JevCache(None)), escalation_timeout_s=None)
    with TestClient(create_app(session)) as c:
        yield c


def drain_greeting(ws: Any) -> dict[str, Any]:
    """Consume hello, state and metrics sent on connect; return the hello."""
    hello = ws.receive_json()
    assert hello["type"] == "hello"
    assert ws.receive_json()["type"] == "state"
    assert ws.receive_json()["type"] == "history"
    assert ws.receive_json()["type"] == "metrics"
    assert ws.receive_json()["type"] == "twin"
    return hello


def recv_until(ws: Any, kind: str, limit: int = 40, **fields: Any) -> dict[str, Any]:
    """Next message of ``kind`` whose top-level fields match ``fields``."""
    for _ in range(limit):
        msg = ws.receive_json()
        if msg["type"] == kind and all(msg.get(k) == v for k, v in fields.items()):
            return msg
    raise AssertionError(f"no {kind} message matching {fields} within {limit} messages")


def test_hello_state_and_metrics_on_connect(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello"
        assert hello["config"]["lanes_count"] == 4 and len(hello["presets"]) == 8
        assert hello["presets"][0] == {
            "id": "speed_limit",
            "checker": "speed_limit",
            "text": "Speed limit 25 m/s",
        }
        assert (
            hello["presets"][-1]["checker"] is None
            and hello["presets"][-1]["id"] == "dense_traffic"
        )
        assert hello["constraints"] == [] and hello["zones"] == []
        state = ws.receive_json()
        assert state["type"] == "state"
        assert state["playing"] is False and state["step"] == 0 and state["source"] == "live"
        assert state["judge_mode"] == "mock" and state["thresholds"] == {
            "t_allow": 0.3,
            "t_block": 0.7,
        }
        assert state["floor_s"] == 2.0
        assert ws.receive_json() == {"type": "history", "records": []}
        assert ws.receive_json()["type"] == "metrics"
        twin = ws.receive_json()
        assert twin["type"] == "twin" and twin["seed"] == 0 and twin["steps"] == []
    assert client.get("/health").json()["ok"] is True


def test_step_without_rules_streams_a_record(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        drain_greeting(ws)
        ws.send_json({"type": "step"})
        step = recv_until(ws, "step")
        assert set(step["record"]) == PLAN_KEYS and step["record"]["decision"] == "allow"
        metrics = recv_until(ws, "metrics")
        assert metrics["steps"] == 1


def test_constraint_commands_broadcast_the_full_list(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        drain_greeting(ws)
        ws.send_json({"type": "add_constraint", "text": "Speed limit 25 m/s"})
        msg = recv_until(ws, "constraints")
        assert [c["checker"] for c in msg["constraints"]] == ["speed_limit"]
        cid = msg["constraints"][0]["id"]
        ws.send_json({"type": "toggle_constraint", "id": cid, "enabled": False})
        assert recv_until(ws, "constraints")["constraints"][0]["enabled"] is False
        ws.send_json({"type": "drop_zone"})
        msg = recv_until(ws, "constraints")
        assert len(msg["zones"]) == 1 and msg["zones"][0]["lane"] == 3
        assert any(c["checker"] == "lane_closed" and c["enabled"] for c in msg["constraints"])
        ws.send_json({"type": "remove_constraint", "id": cid})
        assert all(c["id"] != cid for c in recv_until(ws, "constraints")["constraints"])
        ws.send_json({"type": "remove_constraint", "id": "nope"})
        assert "nope" in recv_until(ws, "error")["message"]


def test_escalation_round_trip_with_mock_judge(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        drain_greeting(ws)
        ws.send_json({"type": "add_constraint", "text": "Speed limit 25 m/s"})
        recv_until(ws, "constraints")
        ws.send_json({"type": "step"})
        esc = recv_until(ws, "escalation")["escalation"]
        assert esc["judge_unavailable"] is True and esc["p"] == 0.5 and "ground_truth" not in esc
        state = recv_until(ws, "state")
        assert state["paused_on_escalation_id"] == esc["id"]
        ws.send_json({"type": "resolve", "escalation_id": esc["id"], "decision": "approve"})
        step = recv_until(ws, "step")["record"]
        assert step["escalated"] is True and step["human"] == {
            **step["human"],
            "decision": "approve",
            "operator": "ui",
        }
        assert step["executed"] == esc["action"]
        state = recv_until(ws, "state")
        assert state["paused_on_escalation_id"] is None and state["step"] == 1


def test_override_executes_a_named_candidate_and_rejects_others(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        drain_greeting(ws)
        ws.send_json({"type": "add_constraint", "text": "Speed limit 25 m/s"})
        recv_until(ws, "constraints")
        ws.send_json({"type": "step"})
        esc = recv_until(ws, "escalation")["escalation"]
        assert esc["reason"] == "no_compliant_action" and "violations_by_action" not in esc
        assert [c["rank"] for c in esc["candidates"]] == [0, 1, 2, 3, 4]
        assert esc["candidates"][0]["action"] == esc["action"]
        ws.send_json(
            {
                "type": "resolve",
                "escalation_id": esc["id"],
                "decision": "override",
                "action": "BRAKE",
            }
        )
        assert "override needs one of" in recv_until(ws, "error")["message"]
        chosen = esc["candidates"][2]["action"]
        ws.send_json(
            {
                "type": "resolve",
                "escalation_id": esc["id"],
                "decision": "override",
                "action": chosen,
            }
        )
        step = recv_until(ws, "step")["record"]
        assert step["executed"] == chosen and step["escalation_reason"] == "no_compliant_action"
        assert step["human"]["decision"] == "override" and step["human"]["action"] == chosen
        assert step["fallback"]["kind"] == "least_bad"
        assert recv_until(ws, "metrics")["conflicts"] == 1


def test_shield_toggle_thresholds_speed_and_reset(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        drain_greeting(ws)
        ws.send_json({"type": "set_shield", "on": False})
        assert recv_until(ws, "state")["shield_on"] is False
        ws.send_json({"type": "set_thresholds", "t_allow": 0.25, "t_block": 0.75})
        assert recv_until(ws, "state")["thresholds"] == {"t_allow": 0.25, "t_block": 0.75}
        ws.send_json({"type": "set_thresholds", "t_allow": 0.9, "t_block": 0.1})
        assert "set_thresholds" in recv_until(ws, "error")["message"]
        ws.send_json({"type": "set_speed", "steps_per_sec": 4})
        assert recv_until(ws, "state")["speed"] == 4
        ws.send_json({"type": "step"})
        recv_until(ws, "step")
        ws.send_json({"type": "reset", "seed": 7})
        hello = recv_until(ws, "hello")
        assert hello["type"] == "hello"
        state = recv_until(ws, "state")
        assert state["seed"] == 7 and state["step"] == 0 and state["done"] is False


def test_reset_while_an_escalation_is_open_cancels_it(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        drain_greeting(ws)
        ws.send_json({"type": "add_constraint", "text": "Speed limit 25 m/s"})
        recv_until(ws, "constraints")
        ws.send_json({"type": "step"})
        esc_id = recv_until(ws, "escalation")["escalation"]["id"]
        recv_until(ws, "state", paused_on_escalation_id=esc_id)
        ws.send_json({"type": "reset", "seed": 1})
        recv_until(ws, "hello")
        state = recv_until(ws, "state")
        assert (
            state["paused_on_escalation_id"] is None and state["step"] == 0 and state["seed"] == 1
        )


def test_play_runs_the_loop_and_pause_stops_it(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        drain_greeting(ws)
        ws.send_json({"type": "set_speed", "steps_per_sec": 10})
        recv_until(ws, "state")
        ws.send_json({"type": "play"})
        assert recv_until(ws, "state")["playing"] is True
        first = recv_until(ws, "step")["record"]["step"]
        second = recv_until(ws, "step")["record"]["step"]
        assert second == first + 1
        ws.send_json({"type": "pause"})
        assert recv_until(ws, "state", playing=False)["playing"] is False


def test_replay_streams_a_logged_run(client: TestClient, tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    runs.mkdir(exist_ok=True)
    with client.websocket_connect("/ws") as ws:
        drain_greeting(ws)
        ws.send_json({"type": "add_constraint", "text": "Speed limit 25 m/s"})
        recv_until(ws, "constraints")
        run_id = ""
        for _ in range(2):
            ws.send_json({"type": "step"})
            esc = recv_until(ws, "escalation")["escalation"]
            ws.send_json({"type": "resolve", "escalation_id": esc["id"], "decision": "deny"})
            run_id = recv_until(ws, "step")["record"]["run_id"]
            recv_until(ws, "metrics")
    log_path = runs / f"{run_id}.jsonl"
    assert log_path.exists() and len(log_path.read_text().splitlines()) == 2

    with client.websocket_connect("/ws") as ws:
        hello = drain_greeting(ws)
        assert run_id in hello["runs"]
        ws.send_json({"type": "load_replay", "run_id": run_id})
        state = recv_until(ws, "state")
        assert state["source"] == "replay" and state["total_steps"] == 2 and state["step"] == 0
        ws.send_json({"type": "step"})
        step = recv_until(ws, "step")["record"]
        assert (
            step["run_id"] == run_id and step["step"] == 0 and step["human"]["decision"] == "deny"
        )
        assert recv_until(ws, "metrics")["steps"] == 1
        ws.send_json({"type": "step"})
        recv_until(ws, "step")
        assert recv_until(ws, "state")["done"] is True
        ws.send_json({"type": "load_live"})
        assert recv_until(ws, "state")["source"] == "live"


def test_late_joiner_receives_the_episode_history(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        drain_greeting(ws)
        for _ in range(3):
            ws.send_json({"type": "step"})
            recv_until(ws, "metrics")
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "hello"
        assert recv_until(ws, "state")["step"] == 3
        history = ws.receive_json()
        assert history["type"] == "history" and [r["step"] for r in history["records"]] == [0, 1, 2]


def test_eval_latest_reports_absence_and_presence(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(server_module, "EVAL_REPORT", tmp_path / "none.json")
    assert client.get("/eval/latest").json()["available"] is False
    present = tmp_path / "latest.json"
    present.write_text(json.dumps({"sweep": [], "calibration": {"overall": {"n": 0}}}))
    monkeypatch.setattr(server_module, "EVAL_REPORT", present)
    body = client.get("/eval/latest").json()
    assert body["available"] is True and body["sweep"] == []


def test_console_origins_enable_cors_for_listed_origins_only(
    policy: Policy, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("backend.logger.LOGS_DIR", tmp_path)
    monkeypatch.setenv("CONSOLE_ORIGINS", "https://console.example, https://preview.example")
    assert server_module.console_origins_from_env() == [
        "https://console.example",
        "https://preview.example",
    ]
    session = Session(policy, JevClient(live=None, cache=JevCache(None)), escalation_timeout_s=None)
    with TestClient(create_app(session)) as c:
        listed = c.get("/health", headers={"Origin": "https://console.example"})
        assert listed.headers["access-control-allow-origin"] == "https://console.example"
        other = c.get("/health", headers={"Origin": "https://elsewhere.example"})
        assert "access-control-allow-origin" not in other.headers


def test_no_console_origins_keeps_same_origin_only(client: TestClient) -> None:
    response = client.get("/health", headers={"Origin": "https://console.example"})
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_reset_sends_the_twin_of_the_new_seed(client: TestClient, tmp_path: Path) -> None:
    from tests.test_twin import record, write

    write(tmp_path / "runs" / "2026-10-18T01-00-00_seed7_off.jsonl", [record(0, 7, False, True)])
    with client.websocket_connect("/ws") as ws:
        drain_greeting(ws)
        ws.send_json({"type": "reset", "seed": 7})
        twin = recv_until(ws, "twin")
        assert twin["seed"] == 7 and twin["run_id"] == "r7" and len(twin["steps"]) == 1
        assert twin["violations_total"] == 1 and twin["crashed_at"] is None
        ws.send_json({"type": "reset", "seed": 8})
        assert recv_until(ws, "twin")["steps"] == []
