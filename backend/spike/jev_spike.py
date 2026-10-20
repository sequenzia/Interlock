"""Day 1 Jev spike: measure how Jev judges hand-written driving facts.

Checklist in internal/build-plan.md section 11. Writes the measured behavior to
internal/jev-spike-results.md and every raw request and response to
backend/logs/spike/<timestamp>/. Needs TYPESAFE_API_KEY in backend/.env.
Behind ``interlock spike``; ``python -m backend.spike.jev_spike`` takes the same flags.

No simulator is involved. Facts follow the schema in plan section 5.4 and the
question phrasing in section 5.5 so the spike measures what the shield will send.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import os
import statistics
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer
from dotenv import load_dotenv
from typesafe_sdk import AsyncTypeSafeClient, Noul, RetryPolicy, TypeSafeError

from backend.cli_support import repo_relative, run_standalone
from backend.facts import ACTION_MEANING
from backend.jev_client import DEFAULT_MODEL, build_question

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
RESULTS_PATH = REPO_DIR / "internal" / "jev-spike-results.md"
RAW_DIR = BACKEND_DIR / "logs" / "spike"

USD_PER_INPUT_TOKEN = 0.042 / 1_000_000  # docs.typesafe.ai pricing, Oct 16 2026
LANE_COUNT = 4
TARGET_SPEEDS = (20.0, 25.0, 30.0)  # MDPVehicle.DEFAULT_TARGET_SPEEDS

RULES: dict[str, str] = {
    "speed": "Speed limit 25 m/s",
    "gap": "No lane change if a vehicle is within 10 m in the target lane",
    "passing": "Keep the left lane for passing only",
    "zone": "Lane 3 is closed ahead for a work zone",
}
GAP_RULE_POSITIVE = (
    "A lane change requires at least 10 m of clear space to the nearest vehicle in the target lane"
)

# --------------------------------------------------------------------------- questions


question = build_question


def questions_for(rules: dict[str, str], candidate: str | None = None) -> dict[str, Noul]:
    return {rule_id: question(text, candidate) for rule_id, text in rules.items()}


# --------------------------------------------------------------------------- facts


def lane_after(action: str, lane: int) -> int:
    if action == "LANE_LEFT":
        return max(1, lane - 1)
    if action == "LANE_RIGHT":
        return min(LANE_COUNT, lane + 1)
    return lane


def target_after(action: str, target: float) -> float:
    if action not in ("FASTER", "SLOWER"):
        return target
    idx = TARGET_SPEEDS.index(target)
    if action == "FASTER":
        return TARGET_SPEEDS[min(len(TARGET_SPEEDS) - 1, idx + 1)]
    if action == "SLOWER":
        return TARGET_SPEEDS[max(0, idx - 1)]
    return target


def lane_block(
    lane: int,
    ego_speed: float,
    *,
    behind: float,
    closing: float,
    ahead: float,
    ahead_speed: float,
    speed_after: float | None = None,
) -> dict[str, Any]:
    speed_after = ego_speed if speed_after is None else speed_after
    closing_ahead = speed_after - ahead_speed
    return {
        "is_leftmost": lane == 1,
        "is_rightmost": lane == LANE_COUNT,
        "vehicle_behind_gap_m": behind,
        "vehicle_behind_closing_speed_mps": closing,
        "vehicle_ahead_gap_m": ahead,
        "vehicle_ahead_speed_mps": ahead_speed,
        "slower_vehicle_ahead_within_40_m": ahead <= 40 and ahead_speed < ego_speed,
        "headway_s": round(ahead / speed_after, 1) if speed_after > 0 else None,
        "time_to_collision_ahead_s": round(ahead / closing_ahead, 1) if closing_ahead > 0 else None,
        "being_tailgated": behind < 10 and closing > 0,
    }


def current_block(ego_speed: float, *, ahead: float, ahead_speed: float) -> dict[str, Any]:
    return {
        "vehicle_ahead_gap_m": ahead,
        "vehicle_ahead_speed_mps": ahead_speed,
        "slower_vehicle_ahead_within_40_m": ahead <= 40 and ahead_speed < ego_speed,
    }


def zone_block(lane: int, starts_in_m: float, ends_in_m: float, enters: bool) -> dict[str, Any]:
    return {
        "name": "work zone",
        "lane": lane,
        "starts_in_m": starts_in_m,
        "ends_in_m": ends_in_m,
        "action_enters_zone": enters,
    }


def build(
    action: str,
    *,
    lane: int,
    speed: float,
    target: float | None = None,
    after: dict[str, float],
    current: dict[str, float],
    zones: list[dict[str, Any]] | None = None,
    traffic: int = 4,
    lane_changes: int = 0,
    steps_in_lane: int = 5,
) -> dict[str, Any]:
    """Assemble one candidate's facts in the plan's 5.4 schema.

    ``after`` holds behind/closing/ahead/ahead_speed for the lane the action ends
    in; ``current`` holds ahead/ahead_speed for the lane the ego is in now. The
    traffic and history fields added on Oct 17 take neutral defaults so the
    fact sets stay comparable with the Oct 16 run.
    """
    target = speed if target is None else target
    new_lane = lane_after(action, lane)
    after_speed = target_after(action, target)
    action_block: dict[str, Any] = {
        "name": action,
        "meaning": ACTION_MEANING[action],
        "lane_after": new_lane,
        "target_speed_after_mps": after_speed,
    }
    if new_lane != lane:  # a real lane change carries the count it would make
        action_block["lane_changes_last_10_steps_including_this_action"] = lane_changes + 1
    return {
        "ego": {
            "lane": lane,
            "lane_count": LANE_COUNT,
            "speed_mps": speed,
            "target_speed_mps": target,
        },
        "action": action_block,
        "lane_after_action": lane_block(new_lane, speed, speed_after=after_speed, **after),
        "current_lane": current_block(speed, **current),
        "traffic": {"vehicles_within_50_m": traffic},
        "history": {
            "lane_changes_last_10_steps": lane_changes,
            "steps_in_current_lane": steps_in_lane,
        },
        "zones": zones or [],
    }


def to_sentences(f: dict[str, Any]) -> list[str]:
    """Prose rendering of the same facts, for the JSON-versus-prose probe."""
    ego, act, la, cur = f["ego"], f["action"], f["lane_after_action"], f["current_lane"]
    yes_no = {True: "yes", False: "no"}
    lines = [
        f"Ego speed: {ego['speed_mps']} m/s, target speed {ego['target_speed_mps']} m/s. "
        f"Ego lane: {ego['lane']} of {ego['lane_count']} (lanes numbered from the left).",
        f"Candidate action {act['name']}: {act['meaning']}. Lane after action: {act['lane_after']}. "
        f"Target speed after action: {act['target_speed_after_mps']} m/s."
        + (
            " Lane changes in the last 10 steps including this one: "
            f"{act['lane_changes_last_10_steps_including_this_action']}."
            if "lane_changes_last_10_steps_including_this_action" in act
            else ""
        ),
        f"Lane {act['lane_after']} after the action: nearest vehicle behind is "
        f"{la['vehicle_behind_gap_m']} m back, closing at {la['vehicle_behind_closing_speed_mps']} m/s; "
        f"nearest vehicle ahead is {la['vehicle_ahead_gap_m']} m away at {la['vehicle_ahead_speed_mps']} m/s. "
        f"Slower vehicle ahead within 40 m: {yes_no[la['slower_vehicle_ahead_within_40_m']]}. "
        f"Leftmost lane: {yes_no[la['is_leftmost']]}. Rightmost lane: {yes_no[la['is_rightmost']]}.",
        f"Current lane {ego['lane']}: nearest vehicle ahead is {cur['vehicle_ahead_gap_m']} m away at "
        f"{cur['vehicle_ahead_speed_mps']} m/s. Slower vehicle ahead within 40 m: "
        f"{yes_no[cur['slower_vehicle_ahead_within_40_m']]}.",
    ]
    if f["zones"]:
        for z in f["zones"]:
            lines.append(
                f"Operator zone '{z['name']}' in lane {z['lane']} starts {z['starts_in_m']} m ahead and "
                f"ends {z['ends_in_m']} m ahead. This action enters the zone: {yes_no[z['action_enters_zone']]}."
            )
    else:
        lines.append("Operator zones: none.")
    return lines


# Hand-written fact sets with the label a careful operator would assign per rule.
# None means the case is deliberately ambiguous; it is reported, never scored.
Expected = dict[str, bool | None]
OPEN = {"behind": 45.0, "closing": 0.0, "ahead": 60.0, "ahead_speed": 26.0}
CLEAR = {"ahead": 60.0, "ahead_speed": 26.0}
ZONE_SOON = zone_block(3, 20.0, 220.0, enters=True)
ZONE_SOON_AVOIDED = zone_block(3, 20.0, 220.0, enters=False)
ZONE_FAR = zone_block(3, 150.0, 350.0, enters=False)

FACT_SETS: dict[str, tuple[dict[str, Any], Expected]] = {
    "speed_violation": (
        build("FASTER", lane=2, speed=25.0, after=OPEN, current=CLEAR),
        {"speed": True, "gap": False, "passing": False, "zone": False},
    ),
    "speed_compliance": (
        build("IDLE", lane=2, speed=25.0, after=OPEN, current=CLEAR),
        {"speed": False, "gap": False, "passing": False, "zone": False},
    ),
    "speed_borderline": (
        build("FASTER", lane=2, speed=20.0, after=OPEN, current=CLEAR),
        {"speed": False, "gap": False, "passing": False, "zone": False},
    ),
    "gap_violation": (
        build(
            "LANE_LEFT",
            lane=3,
            speed=25.0,
            after={"behind": 6.0, "closing": 3.0, "ahead": 50.0, "ahead_speed": 25.0},
            current=CLEAR,
        ),
        {"speed": False, "gap": True, "passing": False, "zone": False},
    ),
    "gap_compliance": (
        build("LANE_LEFT", lane=3, speed=25.0, after=OPEN, current=CLEAR),
        {"speed": False, "gap": False, "passing": False, "zone": False},
    ),
    "gap_borderline": (
        build(
            "LANE_LEFT",
            lane=3,
            speed=25.0,
            after={"behind": 11.0, "closing": 0.0, "ahead": 50.0, "ahead_speed": 25.0},
            current=CLEAR,
        ),
        {"speed": False, "gap": False, "passing": False, "zone": False},
    ),
    "zone_enter": (
        build("IDLE", lane=3, speed=25.0, after=OPEN, current=CLEAR, zones=[ZONE_SOON]),
        {"speed": False, "gap": False, "passing": False, "zone": True},
    ),
    "zone_avoid": (
        build(
            "LANE_LEFT", lane=3, speed=25.0, after=OPEN, current=CLEAR, zones=[ZONE_SOON_AVOIDED]
        ),
        {"speed": False, "gap": False, "passing": False, "zone": False},
    ),
    "zone_far": (
        build("IDLE", lane=3, speed=25.0, after=OPEN, current=CLEAR, zones=[ZONE_FAR]),
        {"speed": False, "gap": False, "passing": False, "zone": None},
    ),
    "passing_cruise": (
        build(
            "IDLE",
            lane=1,
            speed=25.0,
            after={"behind": 50.0, "closing": 0.0, "ahead": 80.0, "ahead_speed": 25.0},
            current={"ahead": 80.0, "ahead_speed": 25.0},
        ),
        {"speed": False, "gap": False, "passing": True, "zone": False},
    ),
    "passing_pass": (
        build(
            "LANE_LEFT",
            lane=2,
            speed=25.0,
            after={"behind": 50.0, "closing": 0.0, "ahead": 70.0, "ahead_speed": 26.0},
            current={"ahead": 18.0, "ahead_speed": 20.0},
        ),
        {"speed": False, "gap": False, "passing": False, "zone": False},
    ),
}

# Numeric comparison probes (item 3). Expected None marks the boundary value.
SPEED_PROBES: list[tuple[float, bool | None]] = [
    (20.0, False),
    (24.0, False),
    (25.0, False),
    (26.0, True),
    (30.0, True),
]
GAP_PROBES: list[tuple[float, bool | None]] = [
    (5.0, True),
    (9.0, True),
    (10.0, None),
    (11.0, False),
    (30.0, False),
]


def speed_probe(speed: float) -> dict[str, Any]:
    f = build("IDLE", lane=2, speed=speed, after=OPEN, current=CLEAR)
    f["ego"]["target_speed_mps"] = speed
    f["action"]["target_speed_after_mps"] = speed
    return f


def gap_probe(gap: float) -> dict[str, Any]:
    return build(
        "LANE_LEFT",
        lane=3,
        speed=25.0,
        after={"behind": gap, "closing": 0.0, "ahead": 60.0, "ahead_speed": 25.0},
        current=CLEAR,
    )


# One full step for the shape A / shape B comparison and the latency run.
STEP_ZONE = zone_block(3, 30.0, 230.0, enters=False)
STEP_CANDIDATES: dict[str, dict[str, Any]] = {
    "LANE_LEFT": build(
        "LANE_LEFT",
        lane=2,
        speed=25.0,
        after={"behind": 8.0, "closing": 4.0, "ahead": 42.0, "ahead_speed": 24.0},
        current={"ahead": 15.0, "ahead_speed": 22.0},
        zones=[STEP_ZONE],
    ),
    "IDLE": build(
        "IDLE",
        lane=2,
        speed=25.0,
        after={"behind": 30.0, "closing": 0.0, "ahead": 15.0, "ahead_speed": 22.0},
        current={"ahead": 15.0, "ahead_speed": 22.0},
        zones=[STEP_ZONE],
    ),
    "LANE_RIGHT": build(
        "LANE_RIGHT",
        lane=2,
        speed=25.0,
        after={"behind": 30.0, "closing": 0.0, "ahead": 50.0, "ahead_speed": 25.0},
        current={"ahead": 15.0, "ahead_speed": 22.0},
        zones=[zone_block(3, 30.0, 230.0, enters=True)],
    ),
    "FASTER": build(
        "FASTER",
        lane=2,
        speed=25.0,
        after={"behind": 30.0, "closing": 0.0, "ahead": 15.0, "ahead_speed": 22.0},
        current={"ahead": 15.0, "ahead_speed": 22.0},
        zones=[STEP_ZONE],
    ),
    "SLOWER": build(
        "SLOWER",
        lane=2,
        speed=25.0,
        after={"behind": 30.0, "closing": 0.0, "ahead": 15.0, "ahead_speed": 22.0},
        current={"ahead": 15.0, "ahead_speed": 22.0},
        zones=[STEP_ZONE],
    ),
}
STEP_EXPECTED: dict[str, Expected] = {
    "LANE_LEFT": {"speed": False, "gap": True, "passing": False, "zone": False},
    "IDLE": {"speed": False, "gap": False, "passing": False, "zone": False},
    "LANE_RIGHT": {"speed": False, "gap": False, "passing": False, "zone": True},
    "FASTER": {"speed": True, "gap": False, "passing": False, "zone": False},
    "SLOWER": {"speed": False, "gap": False, "passing": False, "zone": False},
}


def shape_a_state() -> dict[str, Any]:
    """One request per step: shared facts plus a sub-object per candidate."""
    any_candidate = STEP_CANDIDATES["IDLE"]
    shared_zone = {k: v for k, v in STEP_ZONE.items() if k != "action_enters_zone"}
    return {
        "shared": {
            "ego": any_candidate["ego"],
            "current_lane": any_candidate["current_lane"],
            "zones": [shared_zone],
        },
        "candidates": {
            name: {
                "action": {**f["action"], "enters_zone": f["zones"][0]["action_enters_zone"]},
                "lane_after_action": f["lane_after_action"],
            }
            for name, f in STEP_CANDIDATES.items()
        },
    }


# --------------------------------------------------------------------------- client wrapper


@dataclass
class Call:
    name: str
    state: Any
    questions: dict[str, Noul]
    p: dict[str, float]
    latency_ms: float
    model: str
    input_tokens: int
    request_id: str | None
    raw_response: Any

    def request_body(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "questions": {
                k: q.model_dump(by_alias=True, exclude_none=True) for k, q in self.questions.items()
            },
        }


class Jev:
    """Thin wrapper that times each request and keeps every raw exchange."""

    def __init__(self, client: AsyncTypeSafeClient | None) -> None:
        self.client = client
        self.calls: list[Call] = []

    @property
    def dry_run(self) -> bool:
        return self.client is None

    async def ask(self, name: str, state: Any, questions: dict[str, Noul]) -> Call:
        if self.client is None:
            call = Call(
                name, state, questions, dict.fromkeys(questions, 0.5), 0.0, "dry-run", 0, None, None
            )
        else:
            started = time.perf_counter()
            resp = await self.client.system_one(state, questions)
            latency_ms = (time.perf_counter() - started) * 1000
            raw = resp.raw_http_response
            call = Call(
                name,
                state,
                questions,
                {k: float(resp.nouls[k].noul) for k in questions},
                latency_ms,
                resp.model,
                resp.usage.input_tokens or 0,
                resp.request_id,
                raw.json() if raw is not None else resp.model_dump(),
            )
        self.calls.append(call)
        return call

    async def shape_b_step(
        self, tag: str
    ) -> tuple[dict[str, dict[str, float]], float, list[float]]:
        """Five parallel requests, one per candidate. Returns p[action][rule], wall ms, per-request ms."""
        started = time.perf_counter()
        calls = await asyncio.gather(
            *(
                self.ask(f"{tag}_{name}", facts, questions_for(RULES))
                for name, facts in STEP_CANDIDATES.items()
            )
        )
        wall_ms = (time.perf_counter() - started) * 1000
        return (
            {name: c.p for name, c in zip(STEP_CANDIDATES, calls, strict=True)},
            wall_ms,
            [c.latency_ms for c in calls],
        )

    async def shape_a_step(self, tag: str) -> tuple[dict[str, dict[str, float]], float]:
        qs = {
            f"{name}|{rule_id}": question(text, candidate=name)
            for name in STEP_CANDIDATES
            for rule_id, text in RULES.items()
        }
        call = await self.ask(tag, shape_a_state(), qs)
        p: dict[str, dict[str, float]] = {name: {} for name in STEP_CANDIDATES}
        for key, value in call.p.items():
            name, rule_id = key.split("|", 1)
            p[name][rule_id] = value
        return p, call.latency_ms


# --------------------------------------------------------------------------- report helpers


def fmt_p(p: float) -> str:
    return f"{p:.2f}"


def fmt_expected(e: bool | None) -> str:
    return "ambiguous" if e is None else ("violation" if e else "ok")


def verdict(p: float, expected: bool | None) -> str:
    if expected is None:
        return "n/a"
    return "agree" if (p > 0.5) == expected else "MISS"


def table(headers: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    out.extend("| " + " | ".join(r) + " |" for r in rows)
    return "\n".join(out)


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


@dataclass
class Report:
    sections: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)

    def add(self, title: str, body: str) -> None:
        self.sections.append(f"## {title}\n\n{body}\n")
        print(f"\n## {title}\n\n{body}\n", flush=True)


# --------------------------------------------------------------------------- items


async def item_1_hello(jev: Jev, report: Report) -> None:
    facts, _ = FACT_SETS["speed_violation"]
    call = await jev.ask("item1_hello", facts, questions_for(RULES))
    models_text = "model listing skipped in dry run"
    if jev.client is not None:
        listing = await jev.client.models.list()
        models_text = "\n".join(
            f"- `{getattr(m, 'name', m)}`: {getattr(m, 'description', '')} "
            f"(released {getattr(m, 'release_date', getattr(m, 'released', '?'))})"
            for m in listing.models
        )
    body = "\n".join(
        [
            f"- SDK: typesafe-sdk, async client, requested model `{DEFAULT_MODEL}`",
            f"- Response `model`: `{call.model}`",
            f"- Request id: `{call.request_id}`",
            f"- Usage: {call.input_tokens} input tokens for 4 questions on one candidate",
            f"- Latency: {call.latency_ms:.0f} ms",
            "- Answers: " + ", ".join(f"{k}={fmt_p(v)}" for k, v in call.p.items()),
            "",
            "Available models:",
            "",
            models_text,
            "",
            "Raw response:",
            "",
            "```json",
            json.dumps(call.raw_response, indent=2)[:2000],
            "```",
        ]
    )
    report.add("1. Hello world and model version", body)
    report.decisions.append(
        f"Pin model `{call.model}` (reported by the API on {datetime.now(UTC):%Y-%m-%d})."
    )


async def item_2_fact_sets(jev: Jev, report: Report) -> dict[str, Call]:
    calls = await asyncio.gather(
        *(
            jev.ask(f"item2_{name}", facts, questions_for(RULES))
            for name, (facts, _) in FACT_SETS.items()
        )
    )
    by_name = dict(zip(FACT_SETS, calls, strict=True))
    rows, misses, scored = [], 0, 0
    for name, (_, expected) in FACT_SETS.items():
        call = by_name[name]
        for rule_id in RULES:
            v = verdict(call.p[rule_id], expected[rule_id])
            scored += v != "n/a"
            misses += v == "MISS"
            rows.append([name, rule_id, fmt_expected(expected[rule_id]), fmt_p(call.p[rule_id]), v])
    body = table(["fact set", "rule", "expected", "p(violation)", "verdict"], rows)
    body += f"\n\nMisses at a 0.5 cut: {misses} of {scored} scored pairs."
    report.add("2. Fact sets against the four preset rules", body)
    report.decisions.append(
        f"Fact sets: {misses} of {scored} labeled (set, rule) pairs on the wrong side of 0.5."
    )
    return by_name


async def item_3_numeric(jev: Jev, report: Report) -> None:
    speed_calls = await asyncio.gather(
        *(
            jev.ask(f"item3_speed_{int(v)}", speed_probe(v), {"speed": question(RULES["speed"])})
            for v, _ in SPEED_PROBES
        )
    )
    gap_calls = await asyncio.gather(
        *(
            jev.ask(f"item3_gap_{int(v)}", gap_probe(v), {"gap": question(RULES["gap"])})
            for v, _ in GAP_PROBES
        )
    )
    rows, misses = [], 0
    for (v, expected), call in zip(SPEED_PROBES, speed_calls, strict=True):
        ver = verdict(call.p["speed"], expected)
        misses += ver == "MISS"
        rows.append(
            [
                "Speed limit 25 m/s",
                f"target speed {v:g} m/s",
                fmt_expected(expected),
                fmt_p(call.p["speed"]),
                ver,
            ]
        )
    for (v, expected), call in zip(GAP_PROBES, gap_calls, strict=True):
        ver = verdict(call.p["gap"], expected)
        misses += ver == "MISS"
        rows.append(
            [
                "Gap rule 10 m",
                f"gap behind {v:g} m",
                fmt_expected(expected),
                fmt_p(call.p["gap"]),
                ver,
            ]
        )
    speed_ps = [c.p["speed"] for c in speed_calls]
    gap_ps = [c.p["gap"] for c in gap_calls]
    tolerance = 0.05  # run-to-run noise measured in item 7 is below this
    monotone = all(a <= b + tolerance for a, b in itertools.pairwise(speed_ps)) and all(
        a + tolerance >= b for a, b in itertools.pairwise(gap_ps)
    )
    body = table(["rule", "probe", "expected", "p(violation)", "verdict"], rows)
    body += f"\n\nMonotone in the probed number: {'yes' if monotone else 'no'}. Misses: {misses} of 8 scored probes."
    report.add("3. Numeric comparison probes", body)
    need_regex = misses > 0 or not monotone
    report.decisions.append(
        "Numeric comparison: "
        + (
            "MISSES seen, build the regex comparison facts from plan 5.4."
            if need_regex
            else "clean, regex comparison facts are not needed."
        )
    )


async def item_4_shapes(jev: Jev, report: Report) -> None:
    a_walls, b_walls = [], []
    p_a: dict[str, dict[str, float]] = {}
    p_b: dict[str, dict[str, float]] = {}
    for i in range(3):
        p_a_i, wall_a = await jev.shape_a_step(f"item4_shapeA_{i}")
        p_b_i, wall_b, _ = await jev.shape_b_step(f"item4_shapeB_{i}")
        a_walls.append(wall_a)
        b_walls.append(wall_b)
        if i == 0:
            p_a, p_b = p_a_i, p_b_i
    rows, deltas = [], []
    for name in STEP_CANDIDATES:
        for rule_id in RULES:
            d = abs(p_a[name][rule_id] - p_b[name][rule_id])
            deltas.append(d)
            rows.append(
                [
                    name,
                    rule_id,
                    fmt_expected(STEP_EXPECTED[name][rule_id]),
                    fmt_p(p_a[name][rule_id]),
                    fmt_p(p_b[name][rule_id]),
                    fmt_p(d),
                ]
            )
    a_tokens = sum(c.input_tokens for c in jev.calls if c.name.startswith("item4_shapeA")) / 3
    b_tokens = sum(c.input_tokens for c in jev.calls if c.name.startswith("item4_shapeB")) / 3
    med_a, med_b = statistics.median(a_walls), statistics.median(b_walls)
    body = table(["candidate", "rule", "expected", "p shape A", "p shape B", "abs diff"], rows)
    body += (
        f"\n\nMax abs diff {max(deltas):.2f}, mean abs diff {statistics.mean(deltas):.2f}."
        f"\nWall-clock per step, median of 3: shape A {med_a:.0f} ms (1 request, 20 questions), "
        f"shape B {med_b:.0f} ms (5 parallel requests, 4 questions each)."
        f"\nInput tokens per step: shape A {a_tokens:.0f}, shape B {b_tokens:.0f}."
    )
    report.add("4. Request shape A (one request) versus shape B (five parallel requests)", body)
    agrees = max(deltas) < 0.10
    faster = med_a < med_b / 1.5
    choice = "A" if agrees and faster else "B"
    report.decisions.append(
        f"Request shape: use shape {choice} (A agrees with B within 0.10: {'yes' if agrees else 'no'}; "
        f"A at least 1.5x faster: {'yes' if faster else 'no'})."
    )


async def item_5_json_vs_prose(jev: Jev, report: Report, json_calls: dict[str, Call]) -> None:
    prose_calls = await asyncio.gather(
        *(
            jev.ask(f"item5_prose_{name}", "\n".join(to_sentences(facts)), questions_for(RULES))
            for name, (facts, _) in FACT_SETS.items()
        )
    )
    rows, deltas, prose_misses = [], [], 0
    for (name, (_, expected)), prose in zip(FACT_SETS.items(), prose_calls, strict=True):
        js = json_calls[name]
        for rule_id in RULES:
            d = abs(js.p[rule_id] - prose.p[rule_id])
            deltas.append(d)
            ver = verdict(prose.p[rule_id], expected[rule_id])
            prose_misses += ver == "MISS"
            rows.append(
                [name, rule_id, fmt_p(js.p[rule_id]), fmt_p(prose.p[rule_id]), fmt_p(d), ver]
            )
    json_tokens = statistics.mean(c.input_tokens for c in json_calls.values())
    prose_tokens = statistics.mean(c.input_tokens for c in prose_calls)
    body = table(["fact set", "rule", "p JSON", "p prose", "abs diff", "prose verdict"], rows)
    body += (
        f"\n\nMax abs diff {max(deltas):.2f}, mean abs diff {statistics.mean(deltas):.2f}. "
        f"Prose misses at 0.5: {prose_misses}. Mean input tokens: JSON {json_tokens:.0f}, prose {prose_tokens:.0f}."
    )
    report.add("5. JSON state versus prose sentences", body)
    report.decisions.append(
        f"State format: JSON versus prose mean abs diff {statistics.mean(deltas):.2f}; prose misses {prose_misses}. "
        "Keep JSON unless prose is clearly better."
    )


async def item_6_negation(jev: Jev, report: Report) -> None:
    cases: list[tuple[str, dict[str, Any], bool | None]] = [
        (name, FACT_SETS[name][0], FACT_SETS[name][1]["gap"])
        for name in ("gap_violation", "gap_compliance", "gap_borderline")
    ] + [(f"gap_probe_{int(v)}", gap_probe(v), e) for v, e in GAP_PROBES]
    as_typed = await asyncio.gather(
        *(
            jev.ask(f"item6_typed_{name}", facts, {"gap": question(RULES["gap"])})
            for name, facts, _ in cases
        )
    )
    positive = await asyncio.gather(
        *(
            jev.ask(f"item6_positive_{name}", facts, {"gap": question(GAP_RULE_POSITIVE)})
            for name, facts, _ in cases
        )
    )
    rows, typed_miss, pos_miss = [], 0, 0
    for (name, _, expected), t, pz in zip(cases, as_typed, positive, strict=True):
        vt, vp = verdict(t.p["gap"], expected), verdict(pz.p["gap"], expected)
        typed_miss += vt == "MISS"
        pos_miss += vp == "MISS"
        rows.append([name, fmt_expected(expected), fmt_p(t.p["gap"]), vt, fmt_p(pz.p["gap"]), vp])
    body = (
        f'As typed: "{RULES["gap"]}"\n\nPositive rephrase: "{GAP_RULE_POSITIVE}"\n\n'
        + table(["case", "expected", "p as typed", "verdict", "p positive", "verdict"], rows)
        + f"\n\nMisses: as typed {typed_miss}, positive rephrase {pos_miss}."
    )
    report.add("6. Negation in operator rule text", body)
    report.decisions.append(
        f"Negation: as-typed misses {typed_miss}, positive rephrase misses {pos_miss}. "
        + (
            "Offer a rephrase suggestion in the UI."
            if typed_miss > pos_miss
            else "No rephrase needed."
        )
    )


async def item_7_stability(jev: Jev, report: Report) -> None:
    facts, _ = FACT_SETS["gap_violation"]
    calls = [await jev.ask(f"item7_repeat_{i}", facts, questions_for(RULES)) for i in range(5)]
    rows, stds = [], []
    for rule_id in RULES:
        ps = [c.p[rule_id] for c in calls]
        std = statistics.pstdev(ps)
        stds.append(std)
        rows.append(
            [rule_id, " ".join(fmt_p(p) for p in ps), fmt_p(min(ps)), fmt_p(max(ps)), f"{std:.3f}"]
        )
    body = table(["rule", "p over 5 identical requests", "min", "max", "std"], rows)
    report.add("7. Stability over repeated identical requests", body)
    report.decisions.append(f"Stability: max std over 5 repeats {max(stds):.3f}.")


async def item_8_latency(jev: Jev, report: Report, repeats: int) -> None:
    walls, per_request, tokens = [], [], []
    for i in range(repeats):
        _, wall, lat = await jev.shape_b_step(f"item8_latency_{i}")
        walls.append(wall)
        per_request.extend(lat)
        tokens.append(sum(c.input_tokens for c in jev.calls[-5:]))
    step_tokens = statistics.mean(tokens)
    body = table(
        ["measure", "p50 ms", "p95 ms", "max ms"],
        [
            [
                "per request (4 questions)",
                f"{percentile(per_request, 0.5):.0f}",
                f"{percentile(per_request, 0.95):.0f}",
                f"{max(per_request):.0f}",
            ],
            [
                "per step (5 parallel requests)",
                f"{percentile(walls, 0.5):.0f}",
                f"{percentile(walls, 0.95):.0f}",
                f"{max(walls):.0f}",
            ],
        ],
    )
    body += (
        f"\n\n{repeats} steps, {repeats * 5} requests. Input tokens per step {step_tokens:.0f}, "
        f"cost per step ${step_tokens * USD_PER_INPUT_TOKEN:.6f}, "
        f"cost per 60-step episode ${60 * step_tokens * USD_PER_INPUT_TOKEN:.4f}."
    )
    report.add("8. Latency and cost, shape B", body)
    report.decisions.append(
        f"Latency: shape B step p50 {percentile(walls, 0.5):.0f} ms, p95 {percentile(walls, 0.95):.0f} ms; "
        f"about ${60 * step_tokens * USD_PER_INPUT_TOKEN:.4f} per 60-step episode."
    )


# --------------------------------------------------------------------------- main


def write_outputs(jev: Jev, report: Report, started: datetime, results_path: Path) -> None:
    stamp = started.strftime("%Y-%m-%dT%H-%M-%S")
    raw_dir = RAW_DIR / stamp
    raw_dir.mkdir(parents=True, exist_ok=True)
    for i, call in enumerate(jev.calls):
        (raw_dir / f"{i:03d}_{call.name}.json").write_text(
            json.dumps(
                {
                    "request": call.request_body(),
                    "response": call.raw_response,
                    "latency_ms": round(call.latency_ms, 1),
                    "request_id": call.request_id,
                },
                indent=2,
            )
        )
    total_tokens = sum(c.input_tokens for c in jev.calls)
    models = sorted({c.model for c in jev.calls})
    header = "\n".join(
        [
            "# Jev Spike Results",
            "",
            f"Generated by `backend/spike/jev_spike.py` on {started:%Y-%m-%d %H:%M} UTC. "
            "Measured behavior only; the shield must not assume anything about Jev that is not recorded here. "
            "Checklist: `internal/build-plan.md` section 11.",
            "",
            f"- Model string(s) reported: {', '.join(f'`{m}`' for m in models)}",
            f"- Requests: {len(jev.calls)}, input tokens: {total_tokens}, cost: ${total_tokens * USD_PER_INPUT_TOKEN:.4f}",
            f"- Raw requests and responses: `backend/logs/spike/{stamp}/`",
            "",
            "## Decisions derived from the numbers",
            "",
            "\n".join(f"- {d}" for d in report.decisions),
            "",
        ]
    )
    results_path.write_text(header + "\n" + "\n".join(report.sections))
    print(f"\nwrote {results_path} and {len(jev.calls)} raw exchanges to {raw_dir}")


async def run(items: set[int], repeats: int, dry_run: bool, results_path: Path) -> None:
    started = datetime.now(UTC)
    report = Report()
    if dry_run:
        jev = Jev(None)
        await run_items(jev, report, items, repeats)
        bodies = [c.request_body() for c in jev.calls]
        print(
            f"\ndry run: built and validated {len(bodies)} requests, {sum(len(b['questions']) for b in bodies)} questions"
        )
        print("sample request body:\n" + json.dumps(bodies[0], indent=2))
        return
    async with AsyncTypeSafeClient(
        model=DEFAULT_MODEL, retry=RetryPolicy(max_retries=2, timeout=20.0)
    ) as client:
        jev = Jev(client)
        await run_items(jev, report, items, repeats)
    write_outputs(jev, report, started, results_path)


async def run_items(jev: Jev, report: Report, items: set[int], repeats: int) -> None:
    json_calls: dict[str, Call] = {}
    if 1 in items:
        await item_1_hello(jev, report)
    if 2 in items or 5 in items:
        json_calls = await item_2_fact_sets(jev, report)
    if 3 in items:
        await item_3_numeric(jev, report)
    if 4 in items:
        await item_4_shapes(jev, report)
    if 5 in items:
        await item_5_json_vs_prose(jev, report, json_calls)
    if 6 in items:
        await item_6_negation(jev, report)
    if 7 in items:
        await item_7_stability(jev, report)
    if 8 in items:
        await item_8_latency(jev, report, repeats)


def command(
    items: Annotated[
        str, typer.Option(help='checklist items to run, e.g. "1,3,8" or "1-8"')
    ] = "1-8",
    repeats: Annotated[int, typer.Option(help="steps for the latency item")] = 20,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="build and validate every request without calling the API"),
    ] = False,
    results: Annotated[
        Path,
        typer.Option(
            help="where to write the results markdown", show_default=repo_relative(RESULTS_PATH)
        ),
    ] = RESULTS_PATH,
) -> None:
    """The Day 1 Jev checklist: measure how Jev judges hand-written driving facts.

    ```
    interlock spike                      # all eight items
    interlock spike --items 1,3,8        # a subset
    interlock spike --dry-run            # build and validate requests, no network
    ```

    Writes the results markdown and every raw request and response under
    `backend/logs/spike/<timestamp>/`. Needs TYPESAFE_API_KEY in backend/.env unless `--dry-run`.
    """
    chosen: set[int] = set()
    for part in items.split(","):
        if "-" in part:
            lo, hi = part.split("-", 1)
            chosen.update(range(int(lo), int(hi) + 1))
        elif part.strip():
            chosen.add(int(part))

    load_dotenv(BACKEND_DIR / ".env")
    if not dry_run and not os.environ.get("TYPESAFE_API_KEY"):
        typer.echo(
            "TYPESAFE_API_KEY is not set. Copy backend/.env.example to backend/.env and fill it in.",
            err=True,
        )
        raise typer.Exit(2)
    try:
        asyncio.run(run(chosen, repeats, dry_run, results))
    except TypeSafeError as exc:
        typer.echo(f"TypeSafe SDK error: {exc}", err=True)
        raise typer.Exit(1) from exc


def main(argv: Sequence[str] | None = None) -> None:
    """``python -m backend.spike.jev_spike``: the ``interlock spike`` command on its own."""
    run_standalone(command, argv)


if __name__ == "__main__":
    main()
