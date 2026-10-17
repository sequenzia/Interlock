"""FastAPI WebSocket server over EpisodeRunner. Plan section 8.

One session per process; it is a demo. The live source advances the simulator
at ``steps_per_sec`` while playing and pauses on an escalation until the
operator resolves it or the timeout denies it. The replay source streams a
JSONL run from backend/logs/runs/ through the same messages.

    uv run uvicorn backend.server:app --reload
    JEV_MODE=mock uv run uvicorn backend.server:app          # offline
    ESCALATION_TIMEOUT_S=0 uv run uvicorn backend.server:app # wait forever
    CONSOLE_ORIGINS=https://interlock-console-pied.vercel.app uv run uvicorn backend.server:app  # console on another origin
    uv run interlock console --jev mock --escalation-timeout 0  # both, plus the Vite console
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import time
from collections.abc import AsyncIterator
from dataclasses import asdict
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from backend.constraints import (
    DEFAULT_ZONE_AHEAD_M,
    DEFAULT_ZONE_LANE,
    DEFAULT_ZONE_LENGTH_M,
    DEFAULT_ZONE_NAME,
    PRESETS,
    ConstraintStore,
)
from backend.env import ACTION_NAMES, DEFAULT_CONFIG
from backend.episode import EpisodeRunner, Escalation, OperatorAnswer
from backend.jev_client import DEFAULT_CACHE_PATH, JevClient, make_client
from backend.logger import JsonlLogger, default_log_path, read_log
from backend.paths import DEFAULT_MODEL_PATH, ENV_FILE, INTERNAL_DIR, LOGS_DIR
from backend.policy import Policy
from backend.shield import Thresholds

log = logging.getLogger("shield.server")
RUNS_DIR = LOGS_DIR / "runs"
EVAL_REPORT = INTERNAL_DIR / "eval" / "latest.json"
DEFAULT_STEPS_PER_SEC = 2.0
DEFAULT_ESCALATION_TIMEOUT_S = 20.0


def list_runs() -> list[str]:
    if not RUNS_DIR.exists():
        return []
    return sorted((p.stem for p in RUNS_DIR.glob("*.jsonl")), reverse=True)


def replay_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Running counters recomputed from records, so replay needs nothing but the log."""
    decisions: dict[str, int] = {}
    violations: dict[str, int] = {}
    human: dict[str, int] = {}
    total_reward = 0.0
    crashed = False
    for r in records:
        decisions[r["decision"]] = decisions.get(r["decision"], 0) + 1
        total_reward += r["reward"]
        crashed = crashed or r["crashed"]
        if r["human"]:
            human[r["human"]["decision"]] = human.get(r["human"]["decision"], 0) + 1
        executed = next((c for c in r["candidates"] if c["action"] == r["executed"]), None)
        for check in executed["checks"] if executed else []:
            if check["ground_truth"]:
                violations[check["constraint_id"]] = violations.get(check["constraint_id"], 0) + 1
    return {
        "run_id": records[0]["run_id"] if records else "",
        "seed": records[0]["seed"] if records else 0,
        "shield_on": records[0]["shield_on"] if records else True,
        "steps": len(records),
        "return": round(total_reward, 3),
        "crashed": crashed,
        "decisions": decisions,
        "violations": violations,
        "violations_total": sum(violations.values()),
        "human": human,
        "cost_usd": round(sum(r["judge"]["cost_usd"] for r in records), 6),
    }


class Session:
    """Everything one operator console talks to: runner, transport, queue and clients."""

    def __init__(
        self,
        policy: Policy,
        judge: JevClient,
        *,
        seed: int = 0,
        steps_per_sec: float = DEFAULT_STEPS_PER_SEC,
        escalation_timeout_s: float | None = DEFAULT_ESCALATION_TIMEOUT_S,
    ) -> None:
        self.judge = judge
        self.store = ConstraintStore()
        self.runner = EpisodeRunner(
            policy=policy,
            judge=judge,
            store=self.store,
            operator=self._operator,
            operator_name="ui",
            source=judge.mode,
        )
        self.clients: set[WebSocket] = set()
        self.playing = False
        self.done = False
        self.speed = steps_per_sec
        self.timeout_s = escalation_timeout_s or None
        self.source = "live"
        self.pending: Escalation | None = None
        self.pending_future: asyncio.Future[OperatorAnswer] | None = None
        self.pending_expires_at: float | None = None
        self.logger: JsonlLogger | None = None
        self.replay: list[dict[str, Any]] = []
        self.replay_index = 0
        self.records: list[dict[str, Any]] = []  # this live episode, for late joiners
        self._task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self._reset_runner(seed)

    # ------------------------------------------------------------------ messages

    def hello(self) -> dict[str, Any]:
        return {
            "type": "hello",
            "config": {
                **DEFAULT_CONFIG,
                "action_names": list(ACTION_NAMES),
                "steps_per_sec": self.speed,
                "escalation_timeout_s": self.timeout_s,
            },
            "presets": [{"checker": checker, "text": text} for checker, text in PRESETS.items()],
            "zone_defaults": {
                "lane": DEFAULT_ZONE_LANE,
                "ahead_m": DEFAULT_ZONE_AHEAD_M,
                "length_m": DEFAULT_ZONE_LENGTH_M,
                "name": DEFAULT_ZONE_NAME,
            },
            "runs": list_runs(),
            **self.store.snapshot(),
        }

    def state(self) -> dict[str, Any]:
        th = self.runner.thresholds
        return {
            "type": "state",
            "playing": self.playing,
            "paused_on_escalation_id": self.pending.id if self.pending else None,
            "shield_on": self.runner.shield_on,
            "source": self.source,
            "judge_mode": self.judge.mode,
            "episode": self.runner.episode,
            "seed": self.runner.seed if self.source == "live" else self.replay[0]["seed"],
            "run_id": self.runner.run_id if self.source == "live" else self.replay[0]["run_id"],
            "speed": self.speed,
            "step": self.runner.step_index if self.source == "live" else self.replay_index,
            "total_steps": None if self.source == "live" else len(self.replay),
            "done": self.done,
            "thresholds": {"t_allow": th.t_allow, "t_block": th.t_block},
        }

    def constraints_msg(self) -> dict[str, Any]:
        return {"type": "constraints", **self.store.snapshot()}

    def history_msg(self) -> dict[str, Any]:
        records = self.replay[: self.replay_index] if self.source == "replay" else self.records
        return {"type": "history", "records": records}

    def metrics_msg(self) -> dict[str, Any]:
        if self.source == "replay":
            return {"type": "metrics", **replay_metrics(self.replay[: self.replay_index])}
        return {"type": "metrics", **self.runner.summary()}

    def escalation_msg(self, esc: Escalation) -> dict[str, Any]:
        payload = {k: v for k, v in asdict(esc).items() if k != "ground_truth"}
        payload["expires_at"] = self.pending_expires_at
        payload["timeout_s"] = self.timeout_s
        return {"type": "escalation", "escalation": payload}

    async def send(self, ws: WebSocket, msg: dict[str, Any]) -> None:
        try:
            await ws.send_json(msg)
        except Exception:
            self.clients.discard(ws)

    async def broadcast(self, msg: dict[str, Any]) -> None:
        for ws in list(self.clients):
            await self.send(ws, msg)

    # ------------------------------------------------------------------ connections

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.clients.add(ws)
        await self.send(ws, self.hello())
        await self.send(ws, self.state())
        await self.send(ws, self.history_msg())
        await self.send(ws, self.metrics_msg())
        if self.pending is not None:
            await self.send(ws, self.escalation_msg(self.pending))

    def disconnect(self, ws: WebSocket) -> None:
        self.clients.discard(ws)

    # ------------------------------------------------------------------ commands

    async def handle(self, ws: WebSocket, msg: dict[str, Any]) -> None:
        kind = msg.get("type")
        try:
            match kind:
                case "play":
                    await self.play()
                case "pause":
                    await self.pause()
                case "step":
                    await self.step_once()
                case "reset":
                    await self.reset(int(msg.get("seed", self.runner.seed)))
                case "set_speed":
                    self.speed = max(0.1, min(10.0, float(msg["steps_per_sec"])))
                    await self.broadcast(self.state())
                case "set_shield":
                    self.runner.shield_on = bool(msg["on"])
                    await self.broadcast(self.state())
                case "set_thresholds":
                    self.runner.thresholds = Thresholds(
                        float(msg["t_allow"]), float(msg["t_block"])
                    )
                    await self.broadcast(self.state())
                case "add_constraint":
                    self.store.add(str(msg["text"]), msg.get("checker"))
                    await self.broadcast(self.constraints_msg())
                case "toggle_constraint":
                    self.store.toggle(str(msg["id"]), bool(msg["enabled"]))
                    await self.broadcast(self.constraints_msg())
                case "remove_constraint":
                    self.store.remove(str(msg["id"]))
                    await self.broadcast(self.constraints_msg())
                case "drop_zone":
                    self.store.drop_zone(
                        self.runner.ego_x_m,
                        lane=int(msg.get("lane", DEFAULT_ZONE_LANE)),
                        ahead_m=float(msg.get("ahead_m", DEFAULT_ZONE_AHEAD_M)),
                        length_m=float(msg.get("length_m", DEFAULT_ZONE_LENGTH_M)),
                        name=str(msg.get("name", DEFAULT_ZONE_NAME)),
                    )
                    await self.broadcast(self.constraints_msg())
                case "resolve":
                    await self.resolve(str(msg["escalation_id"]), msg["decision"])
                case "load_replay":
                    await self.load_replay(str(msg["run_id"]))
                case "load_live":
                    await self.reset(self.runner.seed)
                case _:
                    await self.send(
                        ws, {"type": "error", "message": f"unknown message type {kind!r}"}
                    )
        except (KeyError, ValueError, TypeError) as exc:
            await self.send(ws, {"type": "error", "message": f"{kind}: {exc}"})

    @property
    def busy(self) -> bool:
        return self._task is not None and not self._task.done()

    async def play(self) -> None:
        if self.done or self.playing:
            return
        self.playing = True
        if not self.busy:
            self._task = asyncio.create_task(self._loop())
        await self.broadcast(self.state())

    async def pause(self) -> None:
        self.playing = False
        await self.broadcast(self.state())

    async def step_once(self) -> None:
        if self.done or self.busy:
            return
        self._task = asyncio.create_task(self._advance())

    async def _loop(self) -> None:
        while self.playing and not self.done:
            started = time.perf_counter()
            await self._advance()
            await asyncio.sleep(max(0.0, 1.0 / self.speed - (time.perf_counter() - started)))

    async def _advance(self) -> None:
        async with self._lock:
            if self.source == "replay":
                await self._advance_replay()
            else:
                await self._advance_live()

    async def _advance_live(self) -> None:
        before = self.store.snapshot()
        result = await self.runner.step()
        self.records.append(result.record)
        await self.broadcast({"type": "step", "record": result.record})
        if self.store.snapshot() != before:
            await self.broadcast(self.constraints_msg())
        await self.broadcast(self.metrics_msg())
        if result.done:
            self.done = True
            self.playing = False
        await self.broadcast(self.state())

    async def _advance_replay(self) -> None:
        if self.replay_index >= len(self.replay):
            self.done = True
            self.playing = False
            await self.broadcast(self.state())
            return
        record = self.replay[self.replay_index]
        self.replay_index += 1
        await self.broadcast({"type": "step", "record": record})
        await self.broadcast(
            {"type": "constraints", "constraints": record["constraints"], "zones": record["zones"]}
        )
        await self.broadcast(self.metrics_msg())
        if self.replay_index >= len(self.replay):
            self.done = True
            self.playing = False
        await self.broadcast(self.state())

    async def _operator(self, escalation: Escalation) -> OperatorAnswer:
        loop = asyncio.get_running_loop()
        self.pending = escalation
        self.pending_future = loop.create_future()
        self.pending_expires_at = time.time() + self.timeout_s if self.timeout_s else None
        await self.broadcast(self.escalation_msg(escalation))
        await self.broadcast(self.state())
        try:
            answer: OperatorAnswer = await asyncio.wait_for(
                asyncio.shield(self.pending_future), timeout=self.timeout_s
            )
        except TimeoutError:
            answer = "deny"
        finally:
            self.pending = None
            self.pending_future = None
            self.pending_expires_at = None
        await self.broadcast(self.state())
        return answer

    async def resolve(self, escalation_id: str, decision: str) -> None:
        if decision not in ("approve", "deny"):
            raise ValueError(f"decision must be approve or deny, got {decision!r}")
        if self.pending is None or self.pending.id != escalation_id:
            raise ValueError(f"no open escalation {escalation_id}")
        if self.pending_future is not None and not self.pending_future.done():
            self.pending_future.set_result(decision)  # type: ignore[arg-type]

    async def _cancel_inflight(self) -> None:
        self.playing = False
        if self._task is not None and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        self._task = None
        self.pending = None
        self.pending_future = None
        self.pending_expires_at = None

    def _reset_runner(self, seed: int) -> None:
        if self.logger is not None:
            self.logger.close()
        self.runner.reset(seed)
        self.logger = JsonlLogger(default_log_path(self.runner.run_id))
        self.runner.logger = self.logger
        self.done = False
        self.source = "live"
        self.replay = []
        self.replay_index = 0
        self.records = []

    async def reset(self, seed: int) -> None:
        await self._cancel_inflight()
        self._reset_runner(seed)
        await self.broadcast(self.hello())
        await self.broadcast(self.state())
        await self.broadcast(self.metrics_msg())

    async def load_replay(self, run_id: str) -> None:
        path = RUNS_DIR / f"{Path(run_id).name}.jsonl"
        if not path.exists():
            raise ValueError(f"no run named {run_id}")
        records = read_log(path)
        if not records:
            raise ValueError(f"run {run_id} is empty")
        await self._cancel_inflight()
        self.source = "replay"
        self.replay = records
        self.replay_index = 0
        self.done = False
        await self.broadcast(self.state())
        await self.broadcast(
            {
                "type": "constraints",
                "constraints": records[0]["constraints"],
                "zones": records[0]["zones"],
            }
        )
        await self.broadcast(self.metrics_msg())

    async def close(self) -> None:
        await self._cancel_inflight()
        if self.logger is not None:
            self.logger.close()
        self.runner.close()
        await self.judge.close()


def session_from_env() -> Session:
    load_dotenv(ENV_FILE)
    mode = os.environ.get("JEV_MODE", "auto")
    if mode == "auto":
        mode = "live" if os.environ.get("TYPESAFE_API_KEY") else "mock"
    timeout = float(os.environ.get("ESCALATION_TIMEOUT_S", DEFAULT_ESCALATION_TIMEOUT_S))
    model_path = Path(os.environ.get("MODEL_PATH", DEFAULT_MODEL_PATH))
    cache_path = (
        Path(os.environ["JEV_CACHE_PATH"])
        if os.environ.get("JEV_CACHE_PATH")
        else DEFAULT_CACHE_PATH
    )
    log.info(
        "session: jev %s, model %s, escalation timeout %s s",
        mode,
        model_path.name,
        timeout or "none",
    )
    return Session(
        Policy.load(model_path),
        make_client(mode, cache_path=cache_path),  # type: ignore[arg-type]
        seed=int(os.environ.get("SEED", "0")),
        escalation_timeout_s=timeout,
    )


def console_origins_from_env() -> list[str]:
    """Origins allowed to call /health and /eval cross-origin: the deployed console."""
    return [o.strip() for o in os.environ.get("CONSOLE_ORIGINS", "").split(",") if o.strip()]


def create_app(
    session: Session | None = None, *, console_origins: list[str] | None = None
) -> FastAPI:
    """``console_origins`` None reads CONSOLE_ORIGINS; an empty list keeps same-origin only."""

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.session = session or session_from_env()
        yield
        await app.state.session.close()

    app = FastAPI(title="Interlock: shielded RL with Jev", lifespan=lifespan)
    origins = console_origins_from_env() if console_origins is None else console_origins
    if origins:
        # Browsers apply CORS to the fetches only; the WebSocket upgrade is exempt,
        # so this covers /health and /eval/latest for a console on another origin.
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET"])

    @app.get("/health")
    async def health() -> dict[str, Any]:
        s: Session = app.state.session
        return {
            "ok": True,
            "judge_mode": s.judge.mode,
            "source": s.source,
            "step": s.runner.step_index,
        }

    @app.get("/eval/latest")
    async def eval_latest() -> dict[str, Any]:
        """The newest evaluation report written by backend.evaluate, for the metrics tab."""
        if not EVAL_REPORT.exists():
            return {
                "available": False,
                "message": "run: uv run python -m backend.evaluate --seeds 0-19 --all",
            }
        return {"available": True, **json.loads(EVAL_REPORT.read_text())}

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        s: Session = app.state.session
        await s.connect(ws)
        try:
            while True:
                msg = await ws.receive_json()
                await s.handle(ws, msg)
        except WebSocketDisconnect:
            s.disconnect(ws)

    return app


app = create_app()
