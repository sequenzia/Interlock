"""Jev clients: live, cached and mock behind one interface. Plan section 5.7.

Shape B by default: one request per candidate action with one noul question
per enabled constraint. Every (facts, question) pair is cached by content hash.
A cache miss with no live judge, or a live failure after the SDK's retries,
yields p = 0.5 flagged "unavailable" so the shield escalates to the human
instead of trusting a made-up judgment.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from typesafe_sdk import (
    AsyncTypeSafeClient,
    Noul,
    RetryPolicy,
    TypeSafeAPIConnectionError,
    TypeSafeAPIError,
    TypeSafeAPITimeoutError,
)

from backend.constraints import Constraint
from backend.paths import LOGS_DIR

USD_PER_INPUT_TOKEN = 0.042 / 1_000_000  # docs.typesafe.ai pricing, Oct 16 2026
DEFAULT_MODEL = "jev-1.13.0"  # pinned Oct 16 2026 from the spike; jev-latest resolved to this
UNAVAILABLE_P = 0.5
DEFAULT_CACHE_PATH = LOGS_DIR / "jev_cache.jsonl"

Source = Literal["live", "cache", "unavailable"]
Facts = dict[str, Any]


def build_question(rule_text: str, candidate: str | None = None) -> Noul:
    """One noul question per (action, rule) pair. Positive assertion, rule text verbatim."""
    if candidate is None:
        subject = "Executing the candidate action described in state"
    else:
        subject = (
            f'Executing candidate action "{candidate}", described in state.candidates.{candidate},'
        )
    return Noul(
        instructions=f'{subject} would violate this operator rule: "{rule_text}"',
        criteria={
            "true": (
                "The action, once executed, breaks the rule or puts the ego vehicle "
                "in a state the rule forbids."
            ),
            "false": "The action complies with the rule, or the rule does not apply to this situation.",
        },
    )


def question_dict(question: Noul) -> dict[str, Any]:
    return question.model_dump(by_alias=True, exclude_none=True)


def cache_key(model: str, state: Any, question: Noul) -> str:
    q = question_dict(question)
    payload = {
        "model": model,
        "state": state,
        "instructions": q["instructions"],
        "criteria": q.get("criteria"),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class JevCache:
    """Append-only JSONL cache keyed by content hash, loaded into memory at start."""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self._entries: dict[str, tuple[float, str]] = {}
        if path is not None and path.exists():
            with path.open() as fh:
                for line in fh:
                    if line.strip():
                        row = json.loads(line)
                        self._entries[row["key"]] = (float(row["p"]), str(row["model"]))

    def __len__(self) -> int:
        return len(self._entries)

    def get(self, key: str) -> tuple[float, str] | None:
        return self._entries.get(key)

    def put(self, key: str, p: float, model: str) -> None:
        self._entries[key] = (p, model)
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a") as fh:
                fh.write(json.dumps({"key": key, "p": p, "model": model, "ts": time.time()}) + "\n")


@dataclass
class LiveAnswer:
    p: dict[str, float]
    model: str
    input_tokens: int
    raw_response: Any
    latency_ms: float


class LiveJudge:
    """The real API through the SDK. Returns None when the network gives up after retries."""

    def __init__(self, model: str = DEFAULT_MODEL, timeout_s: float = 10.0) -> None:
        self.model = model
        self._client = AsyncTypeSafeClient(
            model=model, retry=RetryPolicy(max_retries=2, timeout=timeout_s)
        )

    async def ask(self, state: Any, questions: dict[str, Noul]) -> LiveAnswer | None:
        started = time.perf_counter()
        try:
            resp = await self._client.system_one(state, questions)
        except (TypeSafeAPIError, TypeSafeAPIConnectionError, TypeSafeAPITimeoutError):
            return None
        latency_ms = (time.perf_counter() - started) * 1000
        raw = resp.raw_http_response
        return LiveAnswer(
            p={k: float(resp.nouls[k].noul) for k in questions},
            model=resp.model,
            input_tokens=resp.usage.input_tokens or 0,
            raw_response=raw.json() if raw is not None else resp.model_dump(),
            latency_ms=latency_ms,
        )

    async def close(self) -> None:
        await self._client.aclose()


@dataclass
class Exchange:
    """One raw request and response, kept for the decision inspector."""

    action: str
    request: dict[str, Any]
    response: Any
    latency_ms: float
    source: Source


@dataclass
class CheckResult:
    p: dict[str, dict[str, float]]  # action -> constraint id -> p(violation)
    sources: dict[str, dict[str, Source]]
    model: str
    source: Source  # step summary
    latency_ms: float  # wall-clock for the whole step
    input_tokens: int
    cost_usd: float
    exchanges: list[Exchange] = field(default_factory=list)

    @property
    def judge_unavailable(self) -> bool:
        return self.source == "unavailable"

    def judge_record(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "source": self.source,
            "latency_ms": round(self.latency_ms, 1),
            "input_tokens": self.input_tokens,
            "cost_usd": round(self.cost_usd, 8),
        }


class JevClient:
    """Shape B checks with a content cache. ``live=None`` is mock mode."""

    def __init__(self, live: LiveJudge | None, cache: JevCache, model: str = DEFAULT_MODEL) -> None:
        self.live = live
        self.cache = cache
        self.model = model

    @property
    def mode(self) -> str:
        return "mock" if self.live is None else "live"

    async def check(
        self, candidates: dict[str, Facts], constraints: list[Constraint]
    ) -> CheckResult:
        started = time.perf_counter()
        per_action = await asyncio.gather(
            *(
                self._check_candidate(action, facts, constraints)
                for action, facts in candidates.items()
            )
        )
        p: dict[str, dict[str, float]] = {}
        sources: dict[str, dict[str, Source]] = {}
        exchanges: list[Exchange] = []
        tokens = 0
        model = self.model
        for action, (p_a, s_a, tokens_a, model_a, exchange) in zip(
            candidates, per_action, strict=True
        ):
            p[action], sources[action] = p_a, s_a
            tokens += tokens_a
            if model_a:
                model = model_a
            if exchange is not None:
                exchanges.append(exchange)
        flat = [s for by_c in sources.values() for s in by_c.values()]
        summary: Source = (
            "unavailable" if "unavailable" in flat else ("live" if "live" in flat else "cache")
        )
        return CheckResult(
            p=p,
            sources=sources,
            model=model,
            source=summary,
            latency_ms=(time.perf_counter() - started) * 1000,
            input_tokens=tokens,
            cost_usd=tokens * USD_PER_INPUT_TOKEN,
            exchanges=exchanges,
        )

    async def _check_candidate(
        self, action: str, facts: Facts, constraints: list[Constraint]
    ) -> tuple[dict[str, float], dict[str, Source], int, str | None, Exchange | None]:
        p: dict[str, float] = {}
        sources: dict[str, Source] = {}
        missing: dict[str, tuple[Noul, str]] = {}
        for c in constraints:
            q = build_question(c.text)
            key = cache_key(self.model, facts, q)
            hit = self.cache.get(key)
            if hit is None:
                missing[c.id] = (q, key)
            else:
                p[c.id], sources[c.id] = hit[0], "cache"
        if not missing:
            return p, sources, 0, None, None

        questions = {cid: q for cid, (q, _) in missing.items()}
        request = {
            "model": self.model,
            "state": facts,
            "questions": {cid: question_dict(q) for cid, q in questions.items()},
        }
        answer = None if self.live is None else await self.live.ask(facts, questions)
        if answer is None:
            for cid in missing:
                p[cid], sources[cid] = UNAVAILABLE_P, "unavailable"
            return p, sources, 0, None, Exchange(action, request, None, 0.0, "unavailable")
        for cid, (_, key) in missing.items():
            p[cid], sources[cid] = answer.p[cid], "live"
            self.cache.put(key, answer.p[cid], answer.model)
        exchange = Exchange(action, request, answer.raw_response, answer.latency_ms, "live")
        return p, sources, answer.input_tokens, answer.model, exchange

    async def close(self) -> None:
        if self.live is not None:
            await self.live.close()


def make_client(
    mode: Literal["live", "mock"],
    cache_path: Path | None = DEFAULT_CACHE_PATH,
    model: str = DEFAULT_MODEL,
) -> JevClient:
    live = LiveJudge(model=model) if mode == "live" else None
    return JevClient(live=live, cache=JevCache(cache_path), model=model)
