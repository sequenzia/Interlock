# Build Plan: Shielded RL with Jev

Written Oct 16, 2026 (Friday). Companion to the project brief at
`internal/project-brief.md`. The brief holds the intent and
the talk; this plan holds the decisions, the schedule and the contracts between
modules. Where the two disagree, this plan wins because it was written after the
brief and after reading TypeSafe's docs.

Target: a working app by Monday night, Oct 19. Eval numbers Tuesday. Presentation
around Thursday, Oct 23, with a live demo and a backup video.

## 1. Decisions made on Oct 16

| Topic | Decision | Why |
| --- | --- | --- |
| Demo format | Live demo plus backup video | Brief's preference; replay mode makes the backup cheap |
| Approval queue | Must-have, not nice-to-have | It is goal 2 and the whole human-on-the-loop story |
| Transport | One WebSocket, both directions | Pause-on-escalate and resume are session state, and operator commands need the return path anyway |
| Frontend deps | Vite, React, TypeScript, Zustand, Tailwind, Recharts, Playwright | All approved; Canvas 2D for the road view, no WebGL yet |
| Work-zone geometry | Preset "drop zone ahead" button that pre-fills editable rule text | 80% of the moment for 20% of the work; click-to-place is a Day 5 stretch |
| Jev unreachable, cache miss | Escalate at p = 0.5, flagged "judge unavailable" | No judge means ask the human; never fake the model |
| Replay | JSONL replay is a first-class server source | Mock mode, backup demo and inspector share one path |
| Python | 3.12 via uv | System 3.9 is too old for SB3 2.9 / torch 2.8 |
| Frontend package manager | pnpm | Already installed |
| Env config | highway-fast-v0 with lanes_count 4, duration 60 | 3 lanes and 30 steps leave no room for the mid-episode zone drop |
| Training | 20k-step DQN first, 100k-step run in the background | Docs recipe is 25 min; longer run only if the short one is too timid |
| Camera | Ego-centered road view | Matches how the facts are phrased |
| Plan location | This file plus CLAUDE.md | Reviewed before any code |
| Writing style | No em dashes anywhere: docs, slides, UI copy | Brief's preference |
| Project name | Interlock; "shield" stays the lowercase technical term for the mechanism | A wordmark built on "shield" reads as a brand, not a technique; a safety interlock permits an action only when a condition holds, with a supervised override |
| Hosting for the live demo | Console on Vercel as a static build; backend as one always-on container built from the root Dockerfile | The session is one stateful process whose loop runs between messages. Vercel functions and containers are stateless, scale to zero when idle and close WebSockets at the max duration, so the backend cannot live there |

## 2. Confirmed Jev facts

Read from docs.typesafe.ai on Oct 16, 2026. Re-verify anything that matters on
Day 1 with a real request.

- Endpoint: `POST https://api.typesafe.ai/v1/systemone`, header
  `Authorization: Bearer $TYPESAFE_API_KEY`, JSON body.
- Body: `state` (string, object or array), `model` (`"jev-latest"`, pin the
  concrete version the response reports once the spike runs), `questions`
  (map of your own ids to question objects).
- Question types: `noul` (yes/no, returns `noul` as a number 0 to 1, no
  separate confidence), `choice` (returns `choice`, `probabilities`,
  `confidence`), `score` (ordered rubric, returns `score`, `legend`,
  `probabilities`, `confidence`). Every question has `type` and
  `instructions`; `noul` takes optional `criteria` with `true` and `false`
  descriptions.
- Response: `model`, `answers` keyed by your ids, `usage.input_tokens`,
  `usage.output_tokens`.
- Limits: 64k tokens per request across state and questions, 32k per question,
  80 requests per second, 32 MiB body. No stated cap on question count.
- Price: $0.042 per million input tokens; output tokens free.
- Latency: vendor says roughly 100 ms typical, 70 to 500 ms range.
- Python SDK: `typesafe-sdk`, imports as `typesafe_sdk`, reads
  `TYPESAFE_API_KEY`, retries 429 and 529 with backoff by default.
- Guidance that shapes our design:
  - Prefer structured JSON state with named fields over prose.
  - Jev reads literally. Avoid negation in instructions and criteria.
  - Counting, arithmetic and numeric comparison are documented weaknesses.
    Compute them in code.
  - Multi-hop or indirect questions are weak. Keep each question one judgment.
  - Irrelevant state reduces accuracy. Keep state lean.
  - Confidence is distribution concentration, not measured accuracy. Pick
    thresholds from labeled data. That is exactly what the eval harness does.

The `noul` mapping is the whole shield: one `noul` question per (candidate
action, constraint) pair, p is the violation probability, and `T_ALLOW` /
`T_BLOCK` apply to p directly.

Measured Oct 16 (spike run 1, `internal/jev-spike-results.md`): the API
reports `jev-1.13.0` and accepts it as a request model, so it is pinned in
`backend/jev_client.py`. Step latency at shape B is p50 157 ms, p95 247 ms;
a 60-step episode costs about $0.011. Run-to-run std on identical requests is
at most 0.05.

## 3. Schedule

| Day | Date | Focus | Done when |
| --- | --- | --- | --- |
| 1 | Fri Oct 16 | Scaffold uv project, pin deps, start DQN training, run the Jev spike (section 11) | Model saved and drives; `internal/jev-spike-results.md` written |
| 2 | Sat Oct 17 | `policy.py` ranked actions, `facts.py`, `jev_client.py` (real, cache, mock), `shield.py`, `checkers.py`, JSONL log, headless CLI | `uv run python -m backend.run_episode --shield on` and `--shield off` both finish and log |
| 3 | Sun Oct 18 | `server.py` WebSocket with live and replay sources; React console: road view, constraint panel, status strip, play/pause/step/reset | Live sim in the browser; add and toggle rules; drop a work zone |
| 4 | Mon Oct 19 | Approval queue and escalation round trip; decision timeline with inspector drawer | Approve and deny from the UI; click any tick to see questions, answers, Q-values |
| 5 | Tue Oct 20 | `evaluate.py`: before/after, threshold sweep, calibration; metrics panel; Playwright smoke test; CLAUDE.md run commands | Numbers and plots exist; test passes |
| 6 | Wed Oct 21 | Backup video, mock-mode dry run with network off, slides | Demo runs offline end to end |
| 7 | Thu Oct 22 | Rehearsal, buffer | Talk fits the slot |

Cut lines if a day slips: metrics panel in the UI (plots go to slides from
matplotlib), Playwright test, click-to-place zones, inspector raw
request/response view.

## 4. Architecture

```mermaid
flowchart LR
  subgraph backend [Python backend]
    ENV[highway-env\nhighway-fast-v0] --> POL[policy.py\nDQN Q-values, ranked actions]
    ENV --> FACTS[facts.py\nstate + action to JSON facts]
    CONS[constraints.py\nplain-English rules, zones] --> FACTS
    FACTS --> JEV[jev_client.py\nreal / cache / mock]
    POL --> SHIELD[shield.py\nallow / fallback / escalate]
    JEV --> SHIELD
    SHIELD --> ENV
    SHIELD --> LOG[(decisions.jsonl)]
    CHK[checkers.py\nground truth, scoring only] --> LOG
    LOG --> EVAL[evaluate.py\nmetrics, sweep, calibration]
    SHIELD --> WS[server.py\nFastAPI WebSocket]
    LOG --> WS
  end
  WS <--> UI[React console\nroad view, rules, queue, timeline, metrics]
  classDef default fill:#f4f4f4,stroke:#333,color:#000;
```

Repo layout:

```
shielded/
  backend/
    __init__.py
    env.py            # make_env(seed, config overrides)
    train.py          # SB3 DQN, saves models/dqn_highway.zip
    policy.py         # load model, ranked actions with Q-values
    paths.py          # repo-relative paths shared by the modules
    episode.py        # EpisodeRunner: the per-step loop the CLI and server share
    facts.py          # (env state, action, constraints, zones) -> facts JSON + sentences
    constraints.py    # constraint store, zone presets
    jev_client.py     # RealClient, CachedClient, MockClient, shared interface
    shield.py         # decide(ranked, checks, thresholds) -> Decision
    checkers.py       # ground-truth checker per constraint template
    logger.py         # JSONL writer, record schema
    cli.py            # interlock entry point: run, eval, train, spike, console
    run_episode.py    # headless episode, behind interlock run
    server.py         # FastAPI app, WebSocket, live + replay sources
    evaluate.py       # batch runs, sweep, calibration, plots
    spike/jev_spike.py
    logs/             # gitignored
  frontend/           # Vite + React + TS + Tailwind + Zustand
  models/             # trained DQN zip, gitignored except a README
  internal/           # brief, this plan, spike results
  CLAUDE.md
```

## 5. Shield design

### 5.1 Per-step loop

1. `policy.ranked_actions(obs)` returns all five actions sorted by Q-value.
2. `facts.for_candidates(env, actions, constraints, zones)` returns, per
   action, a facts object (section 5.4) and a list of plain sentences for the
   UI.
3. `jev_client.check(candidates, constraints)` returns `p[action][constraint]`
   plus latency, token usage, model version and a `source` of `live`, `cache`
   or `unavailable`.
4. `shield.decide(ranked, p, thresholds)` returns one of `allow`, `fallback`,
   `escalate`, `all_blocked` with the chosen action and the firing constraint.
5. On `escalate`, the loop pauses until the operator resolves or the timeout
   fires (default deny; 20 s live, 0 s in eval with the simulated operator).
6. `env.step(executed)`; `checkers.label(state_before, candidates)` labels
   every candidate against every constraint for scoring only.
7. Write one JSONL record, push one `step` message.

### 5.2 Decision rules

```
p_viol(a) = max over enabled constraints c of p[a][c]
top = ranked[0]
fallback = safe:        first a in ranked[1:] with p_viol(a) < T_ALLOW
        or least_bad:   the a in ranked[1:] with the lowest p_viol(a) <= T_BLOCK
                        that changes the state (no lane change at the road edge,
                        no speed change at the end of the range); ties to rank
        or last_resort: SLOWER if p_viol(SLOWER) <= T_BLOCK else IDLE
if p_viol(top) < T_ALLOW:   allow top
elif fallback is not safe:  escalate top, reason no_compliant_action
elif p_viol(top) > T_BLOCK: execute the safe fallback            (kind fallback)
else:                       escalate top, reason uncertain
approve  -> execute top
deny     -> execute the fallback; all_blocked when it was the last resort
override -> execute the action the operator named
```

Defaults `T_ALLOW = 0.2`, `T_BLOCK = 0.8`, editable live and swept on Day 5.

Revised Oct 17 (section 16.1): the shield acts on its own only when it holds
a confidently safe action. When nothing is confidently safe it escalates with
reason `no_compliant_action` and the queue offers every candidate, so a
jointly unsatisfiable state reaches a person instead of looping on a no-op
last resort. The decision kind `all_blocked` is no longer produced; the
`all_blocked` flag still marks an executed last resort after a deny or a
timeout. The fallback's kind is recorded so the log says whether deny would
have run a safe action, the least-bad one or the last resort.

Shield off still runs facts, Jev and checkers in shadow and executes `top`
unconditionally. Shadow mode means the before/after comparison and the
calibration data come from the same seeds and the same code path.

### 5.3 Jev request shape: two candidates, spike decides

- Shape A: one request per step. `state` is `{candidates: {LANE_LEFT: {...},
  IDLE: {...}, ...}, shared: {...}}`, and each question's instructions name the
  candidate key. 5 x N questions, one round trip, but it leans on Jev finding
  the right sub-object, which is indirection.
- Shape B: five requests per step fired in parallel with asyncio. Each
  `state` is one candidate's flat facts; N questions each. No indirection,
  same wall-clock, five times the fixed per-request overhead in tokens.

Default to B unless the spike shows A agrees with B and is meaningfully faster.

Decided Oct 16: shape B. A was faster (143 versus 197 ms) and 29% cheaper but
disagreed by 0.32 on one gap question, and the per-candidate cache needs one
state per candidate.

### 5.4 Fact schema

JSON for Jev, sentences for humans, both generated from the same extractor.
Units live in the field names. Lanes are numbered from the left starting at 1.
Facts come from the simulator's vehicle objects, not from the normalized
observation the policy sees.

```json
{
  "ego": {"lane": 2, "lane_count": 4, "speed_mps": 29.6, "target_speed_mps": 30},
  "action": {"name": "LANE_LEFT", "meaning": "move one lane to the left",
             "lane_after": 1, "target_speed_after_mps": 30},
  "lane_after_action": {
    "is_leftmost": true, "is_rightmost": false,
    "vehicle_behind_gap_m": 8.0, "vehicle_behind_closing_speed_mps": 4.0,
    "vehicle_ahead_gap_m": 42.0, "vehicle_ahead_speed_mps": 24.0,
    "slower_vehicle_ahead_within_40_m": false
  },
  "current_lane": {"vehicle_ahead_gap_m": 15.0, "vehicle_ahead_speed_mps": 22.0,
                   "slower_vehicle_ahead_within_40_m": true},
  "lane_right_of_lane_after": {"vehicle_ahead_gap_m": 15.0, "vehicle_ahead_speed_mps": 22.0,
                               "slower_vehicle_ahead_within_40_m": true},
  "zones": [{"name": "work zone", "lane": 3, "starts_in_m": 120, "ends_in_m": 320,
             "action_enters_zone": false}]
}
```

Notes added Oct 16 after writing `facts.py`:

- `lane_right_of_lane_after` is present only when the lane after the action is
  the leftmost lane. It is the lane being passed, which the passing rule needs
  and which the current lane and the lane after the action do not cover when
  the ego is already in lane 1.
- A vehicle farther than 200 m is reported as absent: gap, speed and closing
  speed are `null`. Gaps are bumper to bumper (center distance minus 5 m).
- A lane change at the road edge (LANE_LEFT in lane 1, LANE_RIGHT in the
  rightmost lane) changes nothing, and `action.meaning` says so. Without that,
  Jev scored LANE_RIGHT from lane 4 at 0.87 on the gap rule.
- `action_enters_zone` is true when the lane after the action is the zone's
  lane and the ego's position after one step at its current speed falls inside
  the zone. Zones already passed are dropped from the facts.

Numeric-comparison fallback, built only if the spike shows Jev misjudging
plain comparisons: a regex pulls numbers with units out of each rule's text
and the extractor adds relational facts such as
`"target_speed_after_vs_25_mps": "greater"`. Arithmetic stays in code; Jev
still decides which number the rule is about and whether the rule applies.

Decided Oct 16: not built. Speed comparisons were crisp at every probe. Gap
comparisons had the right sign at every probe but were soft, and the softness
tracked the negation in the rule text (section 5.5), not the arithmetic.

Added Oct 17 (section 16.2, item A3), all computed in code:

- `lane_after_action.headway_s`: gap ahead over the target speed after the
  action; null with no vehicle ahead.
- `lane_after_action.time_to_collision_ahead_s`: gap ahead over the closing
  speed at the target speed after the action; null when not closing.
- `lane_after_action.being_tailgated`: a vehicle behind within 10 m and faster
  than the ego.
- `traffic.vehicles_within_50_m`: other vehicles within 50 m along the road,
  any lane.
- `history.lane_changes_last_10_steps` and `history.steps_in_current_lane`:
  from a lane deque on `EpisodeRunner`, the same for every candidate in a step.

Every cache key changed with the schema, so the demo seeds need re-warming.
The spike's builder carries the same fields with neutral defaults, and
`interlock spike --items 2,3 --results <path>` re-ran the fact sets and the
numeric probes without touching the Oct 16 results file.

### 5.5 Question phrasing

Positive assertion, no negation, one rule per question, rule text verbatim:

- instructions: `Executing the candidate action described in state would
  violate this operator rule: "<rule text>"`
- criteria.true: `The action, once executed, breaks the rule or puts the ego
  vehicle in a state the rule forbids.`
- criteria.false: `The action complies with the rule, or the rule does not
  apply to this situation.`

Rules themselves are typed by the operator and may contain negation ("No lane
change if ..."). The spike checks whether that hurts; if it does, the UI can
suggest a rephrase but must still accept the operator's text.

Measured Oct 16: the gap rule as typed scores 0.53 on a 9 m gap; the positive
rephrase "A lane change requires at least 10 m of clear space to the nearest
vehicle in the target lane" scores 0.91. The UI offers a rephrase for rules
that read as "No ... if ...". The passing rule sits near 0.5 on lane-left
moves and near 0.7 on cruising in the left lane regardless of phrasing or
extra facts; those steps escalate by design.

### 5.6 Escalation

Queue item: step, candidate action, its sentences, the constraint with the
highest p, that p, Q-value rank, the fallback deny would run, and a deadline.
Operator approves or denies. Each resolution is appended to the log record as
`human: {decision, latency_ms, operator: "ui" | "simulated"}` and becomes a
labeled example.

Revised Oct 17: the item also carries `reason` (`uncertain` or
`no_compliant_action`) and `candidates`, every ranked action with its worst p,
the rule behind it and whether it is a no-op. The operator may also
**override** by naming any candidate; `human` becomes `{decision: "approve" |
"deny" | "override", action, latency_ms, operator}`. The simulated operator
overrides a `no_compliant_action` escalation with the candidate that breaks
the fewest rules by ground truth, ties to the policy's ranking, and approves
when that is the proposal; with no labels at all it denies.

### 5.6a Zone lifecycle (added Oct 16)

The lane-closed rule is in force only while a zone exists. `drop_zone` adds
the rule or re-enables it; `retire_passed_zones`, called at the top of every
step, drops zones the ego has passed and disables the rule when none remain.
Reason: in the first live run Jev kept p between 0.31 and 0.66 on every lane 3
action after the zone was behind the ego and absent from the facts, because
the rule text still asserted a closure. The CLI's `--rules all` means the
three standing rules; the zone rule arrives with `--zone-at-step` or, in the
UI, with the drop-zone button. The UI shows the rule chip flipping off with a
"zone passed" note so the operator sees the retirement.

### 5.7 Cache, mock and offline

- Cache key: SHA-256 of canonical JSON of `(model, state, instructions,
  criteria)`. Stored as JSONL under `backend/logs/jev_cache.jsonl`, loaded
  into memory at start.
- `MockClient` serves only from the cache. On a miss it returns p = 0.5 for
  every question with `source: "unavailable"`, which the shield turns into an
  escalation flagged "judge unavailable".
- `RealClient` on network error after SDK retries behaves the same way.
- Before the demo, run the demo seeds with the real client so the cache is
  warm for every scripted moment. Rules typed live in the room hit the
  network; if it is down, the operator sees the flag and answers the
  question themselves, which is the honest story.

## 6. Ground-truth checkers

Checkers score only. They never feed the shield. Each demo rule maps to a
checker by a template id chosen when the rule is added (the UI offers the four
demo rules as presets; a free-text rule with no checker is logged as
`ground_truth: null` and excluded from calibration).

| Preset rule text | Checker on (state, candidate) |
| --- | --- |
| Speed limit 25 m/s | `target_speed_after_mps > 25` |
| No lane change if a vehicle is within 10 m in the target lane | action is a lane change and min(gap behind, gap ahead) in the target lane < 10 |
| Keep the left lane for passing only | lane after action is leftmost and no slower vehicle ahead within 40 m in the lane to its right (the lane being passed) |
| Lane 3 is closed ahead for a work zone | lane after action is 3 and ego's longitudinal position after one step falls inside the zone |

All four are closed-form on the pre-step state, so every candidate gets a
label every step. That gives five labeled checks per constraint per step for
calibration, not one.

## 7. Log record

One line per step. This is the contract between backend, UI and eval.

```json
{
  "run_id": "2026-10-18T14-02-11_seed7_on", "episode": 0, "step": 41, "seed": 7,
  "source": "live", "shield_on": true,
  "thresholds": {"t_allow": 0.2, "t_block": 0.8},
  "ego": {"lane": 2, "speed_mps": 29.6, "x_m": 812.4},
  "vehicles": [{"id": 3, "lane": 1, "x_m": 804.1, "speed_mps": 25.5}],
  "zones": [{"name": "work zone", "lane": 3, "start_m": 930, "end_m": 1130}],
  "constraints": [{"id": "c1", "text": "Speed limit 25 m/s", "enabled": true, "checker": "speed_limit"}],
  "candidates": [
    {"action": "FASTER", "rank": 0, "q": 1.92, "facts": {"...": "..."}, "sentences": ["..."],
     "checks": [{"constraint_id": "c1", "p_violation": 0.91, "ground_truth": true}]}
  ],
  "decision": "fallback", "executed": "IDLE", "fired_constraint": "c1",
  "escalated": false, "human": null, "all_blocked": false,
  "escalation_reason": null, "fallback": {"action": "IDLE", "kind": "safe"},
  "judge": {"model": "jev-1.13.0", "source": "live", "latency_ms": 140,
            "input_tokens": 1210, "cost_usd": 0.0000508,
            "questions": {"c1": {"type": "noul", "instructions": "...", "criteria": {"true": "...", "false": "..."}}},
            "exchanges": [{"action": "FASTER", "source": "live", "latency_ms": 131, "asked": ["c1"],
                           "request_id": "req_...", "response": {"model": "jev-1.13.0", "answers": {"...": "..."}, "usage": {"...": "..."}}}]},
  "reward": 0.83, "crashed": false
}
```

`vehicles` is the render snapshot so replay needs nothing but the log.
`judge.questions` holds the exact question per constraint (shared across
candidates) and `judge.exchanges` one entry per request actually sent, with the
constraint ids it asked and the raw response. The request state is the
candidate's `facts`, so the inspector can rebuild the exact request body without
storing it twice. Cache hits produce no exchange. Added Oct 16 for the Day 4
inspector.

Added Oct 17: `escalation_reason` is `"uncertain"`, `"no_compliant_action"`
or null when the step did not escalate (shield off always null). `fallback`
names what deny would run and its kind, `"safe"`, `"least_bad"` or
`"last_resort"`. When a step escalated, `human` is `{"decision": "approve" |
"deny" | "override", "action": "LANE_RIGHT" | null, "latency_ms": 2140,
"operator": "ui" | "simulated" | "approve" | "deny"}`; `action` is set only
for an override.

## 8. WebSocket protocol

Single endpoint `/ws`. JSON messages with a `type` field.

Server to client: `hello` (config, constraints, thresholds, presets),
`state` (playing, paused_on_escalation_id, shield_on, source, episode, seed,
speed), `step` (one log record), `escalation` (queue item), `constraints`
(full list after any change), `metrics` (running counters), `error`.

Client to server: `play`, `pause`, `step`, `reset {seed}`, `set_speed
{steps_per_sec}`, `set_shield {on}`, `set_thresholds {t_allow, t_block}`,
`add_constraint {text, checker?}`, `toggle_constraint {id, enabled}`,
`remove_constraint {id}`, `drop_zone {lane, ahead_m, length_m, name}`,
`resolve {escalation_id, decision, action?}`, `load_replay {run_id}`.

Server loop: an asyncio task advances the sim at `steps_per_sec` (default 2)
while playing, awaits an `asyncio.Event` while an escalation is open, and
re-sends `state` on every transition. Client reconnect re-sends `hello` and
`state`; the client keeps its own step history in the Zustand store.

As built on Oct 16 (`backend/server.py`, `frontend/src/types.ts`):

- `state` also carries `judge_mode`, `run_id`, `step`, `total_steps` (replay
  only), `done` and `thresholds`, and is re-sent after every step.
- `constraints` carries `zones` as well, so the UI can show a zone retiring.
- A `history` message with this episode's records follows `state` on connect,
  so a browser refresh mid-demo keeps the timeline. Connect order is `hello`,
  `state`, `history`, `metrics`, then `escalation` if one is open.
- `load_live` returns from replay to the live source.
- The escalation future is awaited with `asyncio.wait_for`; the timeout comes
  from `ESCALATION_TIMEOUT_S` (default 20, 0 means wait forever) and `JEV_MODE`
  picks live or mock (default: live when the key is present).
- `create_app(session)` lets tests inject an untrained policy and the mock judge.

Day 4 as built (Oct 16): the decision strip is clickable and doubles as a
scrubber, so the road view and the inspector show the selected step while the
sim keeps running; arrow keys move, Esc follows live. The inspector shows the
five candidates by Q, the p grid against every rule colored by the thresholds
with the checker's label as a mark, the sentences and facts, and the exact
request and response rebuilt from `judge.questions`, `judge.exchanges` and the
candidate's facts. A replay picker in the status strip lists
`backend/logs/runs/`; `back to live` returns.

Observed while verifying: once the ego is inside a closed lane, no exit scores
as confidently safe (lane changes sit at 0.2 to 0.5 on the gap rule), so every
step escalates and deny only means SLOWER. The operator can approve or deny the
policy's proposal but cannot pick the lane change that would fix it.
Built Oct 17 (section 16.2): the `escalation` payload carries `reason` and
`candidates` (action, rank, worst p, the rule behind it, no-op flag), and
`resolve` accepts `decision: "override"` with `action` naming one of those
candidates. The server rejects an override whose action is not in the open
escalation. Logged as `human.decision = "override"` with `human.action`.

## 9. UI layout

C2-style operator console, dark theme, dense.

- Top status strip: shield toggle, source (live / replay), decision badge for
  the latest step (allow / fallback / escalated / all blocked), Jev latency,
  cost so far, play/pause/step/reset, speed.
- Left, largest: road view on Canvas 2D. Ego-centered, four lanes, other
  vehicles from the snapshot, zone overlays with hatching, executed action
  drawn as a solid arrow, blocked top action as a ghost arrow.
- Right column: constraint panel (text box, preset chips for the four demo
  rules, list with enable toggle and remove, "drop work zone ahead" button)
  and, when paused, the approval queue card with Approve and Deny.
- Bottom: decision timeline, one tick per step colored by outcome. Clicking
  a tick opens an inspector drawer: five candidates by Q-value, the p grid
  against every constraint, the sentences, and the raw request and response.
- Metrics tab: before/after violations and return per seed (bars), escalation
  rate versus thresholds (line), reliability plot (Recharts).

Shield on/off is one toggle on the same seed so the audience sees the
difference on the same opening scene.

## 10. Eval harness

`uv run python -m backend.evaluate --seeds 0-19 --mode off|on|shadow
--t-allow 0.2 --t-block 0.8 --operator simulated`

- Simulated operator: answers escalations with the checker's label.
- Outputs per run: JSONL log, `metrics.json` with violations per episode per
  constraint, return, crashes, escalation rate, p50/p95 latency, cost.
- Sweep: `(t_allow, t_block)` over `(0.1, 0.9), (0.2, 0.8), (0.3, 0.7),
  (0.4, 0.6), (0.5, 0.5)`; plot violations against escalation rate.
- Calibration: ten bins of p over every (candidate, constraint) check with a
  label; reliability plot plus expected calibration error.
- Plots to `internal/plots/` as PNG via matplotlib for the slides; the same
  JSON feeds the metrics tab.

### Results, Oct 16

20 seeds, 60 steps, the three standing rules, simulated operator answering
from the checkers, live `jev-1.13.0`, concurrency 2. One run of everything took
8 minutes and $0.73. Report: `internal/eval/latest.json`; plots in
`internal/plots/`; raw runs under `backend/logs/eval/`.

| Configuration | Violations per episode | Return | Crash rate | Escalated steps | All-blocked steps |
| --- | --- | --- | --- | --- | --- |
| Shield off | 58.1 | 50.7 | 40% | 0% | 0% |
| On, 0.1 / 0.9 | 2.85 | 45.1 | 10% | 49.9% | 28.7% |
| On, 0.2 / 0.8 (default) | 2.65 | 41.4 | 25% | 23.9% | 5.2% |
| On, 0.3 / 0.7 | 2.65 | 41.6 | 30% | 18.5% | 5.0% |
| On, 0.4 / 0.6 | 1.25 | 42.0 | 40% | 6.6% | 1.3% |
| On, 0.5 / 0.5 | 1.85 | 41.7 | 30% | 0.2% | 0.6% |

All-blocked column recomputed from the records on Oct 17 (section 16.1); the
Oct 16 table read 18.8%, 0.2% and 0.9% in the first three rows.

By rule at the default thresholds, shield off to on: speed limit 1030 to 0,
lane change gap 124 to 1, left lane for passing 8 to 52. The two crisp rules
are essentially solved; the fuzzy rule is where the shield leaks, and the
shield's own interventions make it worse because the car weaves less and so
cruises in the left lane more often with nobody to pass. Jev scores those
steps at 0.1 to 0.2, below T_ALLOW, so they are allowed.

Correction, Oct 17: the last sentence is wrong. The logs show all 52 steps
were escalations at p 0.54 to 0.80, denied, with the SLOWER last resort
executed while no action satisfied every rule. Section 16.1 has the reading.

Calibration over 93,285 labeled (candidate, rule) checks: ECE 0.093, Brier
0.032, accuracy at a 0.5 cut 97.5%. Per rule: speed limit ECE 0.059 and 100%
accurate with p bimodal below 0.2 or above 0.8; lane change gap ECE 0.081 but
underconfident on real violations, since p in 0.3 to 0.5 is a violation 70 to
90% of the time; left lane for passing ECE 0.179 with weak discrimination
between 0.3 and 0.6.

Reading the sweep: 0.4 / 0.6 is the knee, 1.25 violations per episode with
6.6% of steps escalated, but its crash rate matches shield off. 0.1 / 0.9 has
the lowest crash rate because 29% of steps hit the all-blocked path and the car
simply drives slower. The simulated operator is perfect, which flatters the
high-escalation settings; a human will not be. Decision: keep 0.2 / 0.8 as the
demo default and show the curve; name 0.4 / 0.6 as the operating point when
operator attention is the scarce resource.

Latency per step with the shield on: p50 160 ms, p95 304 ms over live steps.
Cost per episode $0.0067 shielded, $0.0080 unshielded (the shielded run hit the
cache more often).

## 11. Day 1 Jev spike checklist

Script: `backend/spike/jev_spike.py`. Results to
`internal/jev-spike-results.md`. Everything below runs against hand-written
facts, no simulator needed.

1. Hello-world request through `typesafe-sdk`. Record the exact response
   fields and the concrete model version string. Pin it.
2. Six fact sets (clear violation, clear compliance and borderline for speed
   and for lane-change gap, plus one zone case and one passing-lane case)
   against the four preset rules. Record p for each.
3. Numeric comparison probes. Speed limit 25 against target speeds 20, 24,
   25, 26, 30. Gap rule 10 m against gaps 5, 9, 10, 11, 30. Decide whether
   the regex comparison facts are needed.
4. Shape A versus shape B (section 5.3) on identical facts: agreement of p
   and wall-clock.
5. JSON state versus prose sentences on identical facts.
6. Negation: the gap rule as typed ("No lane change if ...") versus a
   positive rephrase. Record the difference.
7. Stability: the same request five times; record p variance.
8. Latency: p50 and p95 over 20 repeats of a shape-B request.

## 12. Training

`highway-fast-v0` with overrides `lanes_count: 4`, `duration: 60`,
`vehicles_count: 30`, `policy_frequency: 1`. Reward stays the default
(collision -1, high speed 0.4 over 20 to 30 m/s, right lane 0.1), so the
policy never sees a rule. DQN per the HighwayEnv docs: MlpPolicy with
`net_arch [256, 256]`, lr 5e-4, buffer 15000, learning_starts 200, batch 32,
gamma 0.8, train_freq 1, target_update_interval 50, exploration_fraction 0.7.
First run 20k steps, then 100k in the background. Keep whichever has the
lower crash rate over 20 seeds while still averaging above 25 m/s, because a
timid agent makes a boring demo. Q-values come from `model.q_net` on the
observation tensor.

Result, Oct 16, greedy rollouts over seeds 0 to 19:

| Checkpoint | Crash rate | Mean speed | Mean steps of 60 | Mean return |
| --- | --- | --- | --- | --- |
| 20k | 0.85 | 27.3 m/s | 33.5 | 28.5 |
| 100k | 0.40 | 29.8 m/s | 52.0 | 50.7 |

The 100k checkpoint is promoted to `models/dqn_highway.zip`. It is faster and
crashes less, so it breaks the speed rule more often while leaving room for the
mid-episode zone drop.

## 13. Risks

| Risk | Mitigation |
| --- | --- |
| Jev misjudges plain numeric comparisons | Spike item 3; regex comparison facts fallback in section 5.4 |
| Shape A indirection lowers accuracy | Spike item 4; default to shape B |
| Operator rule text with negation confuses Jev | Spike item 6; UI suggests rephrase, never overrides |
| Jev weights rule text over empty facts (a rule asserting a closure biases lane 3 with no zone in state) | Zone lifecycle in 5.6a; prefer rules whose trigger is always present in the facts |
| Unattended default-deny can crash the car: the shield enforces rules, not collision safety, and deny falls through to SLOWER even when the policy's proposed lane change was the safe move (seen live on seed 0, step 27, with four 20 s timeouts) | Run the live demo with `ESCALATION_TIMEOUT_S=0`; eval uses the simulated operator; talking point: the policy's crash avoidance is a safety property the shield can override, so a following-distance rule belongs in the rule set |
| Agent too timid to break rules | Density, speed range, seed selection; see section 12 |
| highway-env 1.12 config or render changes differ from memory | Verify `lanes_count`, action names and `policy_frequency` on install |
| Network down in the room | Warm cache for demo seeds; judge-unavailable escalation; backup video |
| Shield-on trajectory diverges from shield-off after the first intervention | Expected; metrics are per-episode aggregates over 20 seeds |
| UI scope creep | Day 2 headless milestone before any React |

## 14. Open items

- [ ] Confirm the presentation date and length.
- [ ] Confirm whether a live demo is expected or slides plus video suffice.
- [x] `TYPESAFE_API_KEY` in `backend/.env`; Day 1 spike run on Oct 16.
- [x] Jev model pinned to `jev-1.13.0`.
- [x] N for the passing-lane rule is 40 m (`facts.SLOWER_AHEAD_RANGE_M`).
- [ ] Install ffmpeg via Homebrew if QuickTime screen recording is not enough for the backup video.
- [ ] After the talk: `fly apps destroy interlock-backend`. The machine is always-on by design and bills around ten dollars a month while it exists.
- [x] Backend host: Fly.io, `fly.toml` at the repo root, app `interlock-backend` in `iad` (Oct 16).
- [x] Console deployed Oct 16: Vercel project `interlock-console`, https://interlock-console-pied.vercel.app, `VITE_BACKEND_URL=https://interlock-backend.fly.dev`. `CONSOLE_ORIGINS` carries both production aliases in `fly.toml`.

## 15. Deployment (added Oct 16)

Two deployables, built from the same repo:

- Console: static Vite build, Vercel project rooted at `frontend/`.
  `VITE_BACKEND_URL` is a build-time variable read by
  `frontend/src/backend-url.ts`. Set, the fetches go to that origin and the
  socket to the same host as `wss`. Unset, everything is same-origin, which
  is the local Vite proxy and the e2e mock backend.
- Backend: the root `Dockerfile` on Fly.io, one always-on `shared-cpu-2x`
  machine with auto-stop off (`fly.toml`). `.dockerignore` is
  an allowlist: lock, `backend/`, `models/dqn_highway.zip`,
  `internal/eval/latest.json` and `backend/logs/jev_cache.jsonl` when
  present, so the demo seeds hit the warm cache. `backend/.env` stays out;
  the host injects `TYPESAFE_API_KEY`, `JEV_MODE`, `ESCALATION_TIMEOUT_S`
  (0 for the live demo), `SEED`, `CONSOLE_ORIGINS` and `PORT`.
  `[tool.uv.sources]` pins CPU-only torch on Linux.

`CONSOLE_ORIGINS` is a comma-separated list of console origins; it adds CORS
to `/health` and `/eval/latest` only, since browsers do not apply CORS to the
WebSocket upgrade. Unset, the server stays same-origin only.

Order of operations: deploy the backend, put its https URL in
`VITE_BACKEND_URL` and deploy the console, then put the console's URL in
`CONSOLE_ORIGINS` and restart the backend. Verified Oct 16 with the image
running locally: health, CORS for the listed origin only, the eval report,
and one shielded step over the socket.

Known limit: one session per backend. Every browser on the URL shares the
episode and the controls. A read-only viewer mode is a feature, not a config.

## 16. Upgrade plan (added Oct 17)

Goal: make the demo show something a rules engine cannot, and make the numbers
survive a skeptical audience. Four items agreed Oct 17, in priority order, with
a freeze phase before the talk. Critique that led here: three of the four preset rules
are if-statements over facts the extractor already computes; the one fuzzy rule
is where the shield leaks; "type any rule" is bounded by the fact schema; and
the shield can override the policy's own crash avoidance.

### 16.1 Diagnosis of the passing-rule leaks (done Oct 17)

Section 10 reads the 52 left-lane violations at the default thresholds as
steps Jev scored low and the shield allowed. The logs under
`backend/logs/eval/2026-10-16T23-15-42_on_ta0.20_tb0.80` say otherwise:

- All 52 are escalations, p 0.54 to 0.80 on the passing rule, denied by the
  simulated operator, with SLOWER executed as the last resort. The
  `all_blocked` flag is true on every one.
- The car is in lane 1 with nobody slower to pass, so every lane-keeping
  action violates the passing rule. The only compliant action, LANE_RIGHT,
  truly violates the lane-change gap rule in 49 of the 52 steps, and Jev
  scores it 0.6 to 0.9 on that rule. No action satisfies every rule.
- SLOWER at the lowest target speed is a no-op (target 20 to 20), so the state
  does not change and the step repeats: 37 consecutive steps on seed 10, 12 on
  seed 5, 3 on seed 2.
- Jev's answers on these steps have the right sign for every candidate and
  rule. The leak is a shield policy gap: nothing says what to execute when
  every candidate violates something, and the hardcoded resort is itself a
  violation.
- `all_blocked_rate` in `metrics.py` counts only decision kind `all_blocked`.
  It misses resolved escalations whose fallback was the last resort, where the
  kind stays `escalate` and only the flag is true. Recomputed from the records
  on Oct 17: 5.2% at 0.2 / 0.8 (not 0.2%), 28.7% at 0.1 / 0.9 (not 18.8%),
  5.0% at 0.3 / 0.7 (not 0.9%); the 0.4 / 0.6 and 0.5 / 0.5 rows were already
  right. Section 10's table is corrected, and `interlock eval --report` now
  recomputes every run's metrics from its seed logs.
- Passing-rule calibration is underconfident, not undiscriminating: true
  violations score 0.3 to 0.8 and never above 0.9; non-violations sit mostly
  below 0.3 with a shoulder at 0.4 to 0.6. At T_BLOCK 0.8 a passing violation
  is never blocked outright; it always escalates.

Consequences: item A starts with the shield's conflict policy, not the fact
schema. The passing rule stays as the fuzzy-rule example because the
underconfidence is real. The README says only that the fuzzy rule leaks,
which stands. `docs/user-guide/evaluation.md` repeated the old reading and the
old all-blocked column; both were corrected on Oct 17.

### 16.2 Item A: a rule set worth a model

1. Fix `all_blocked_rate` to count the flag. Re-run `interlock eval --report`
   over the existing logs, no Jev cost, and update the section 10 table.
2. Conflict policy in `shield.py`, as built: the fallback search gains a
   least-bad tier between the safe action and the last resort, the lowest
   worst-p lower-ranked action at or below T_BLOCK that changes the state.
   The shield executes on its own only with a confidently safe action; when
   nothing is confidently safe it escalates with reason `no_compliant_action`
   and the queue offers every candidate, so the operator can override with any
   of them. Deny runs the fallback, least-bad included. Alternative considered
   and rejected Oct 17: rule priorities typed by the operator; least-bad plus
   the operator's override covers the demo without a new concept to explain.
   Contracts, in sections 5.2, 5.6, 7 and 8: the escalation message gains
   `reason` and `candidates`; the resolve message gains an optional `action`;
   the record gains `escalation_reason` and `fallback {action, kind}` and
   `human` gains `action` with `decision` value `override`. The decision kind
   `all_blocked` is no longer produced; the flag remains.
3. Fact schema additions in `facts.py`, all computed in code:
   `headway_s_after` (gap ahead over speed after), `time_to_collision_ahead_s`
   (gap over closing speed when closing, else null), `being_tailgated` (behind
   gap under 10 m and closing), `vehicles_within_50_m`,
   `lane_changes_last_10_steps`, `steps_in_current_lane`. History is a small
   deque on `EpisodeRunner` passed into `for_candidates`. Re-run the spike
   fact sets live and confirm no preset rule moves by more than 0.1; Jev's
   docs warn that irrelevant state costs accuracy.
   Done Oct 17: 44 fact-set pairs, max abs diff 0.10, mean 0.013, misses 1 of
   43 as before; speed probes unchanged, gap probes sharper and now monotone.
   Record in `internal/jev-spike-recheck-oct17.md`.
4. New rules. Crisp, with checkers: "Keep at least 2 seconds of headway" and
   "At most one lane change in any 10 seconds". Fuzzy, without checkers: "Do
   not cut in close ahead of a fast-closing vehicle" and "Drive conservatively
   in dense traffic". All phrased as positive statements.
5. Labeling command `interlock label --run <jsonl> --rule <id> --sample N`:
   shows a candidate's sentences, takes y, n or skip, appends to
   `backend/logs/labels/<run>.jsonl` keyed like the Jev cache (facts hash plus
   rule text). `metrics.py` merges human labels where the checker label is
   null, so fuzzy rules enter calibration with their label source recorded.
   Target 300 labels per fuzzy rule.
6. Re-run `interlock eval --seeds 0-19 --all`, rebuild the report and plots.

### 16.3 Item B: chat-LLM baseline, offline

- New module `backend/baseline_llm.py` behind `interlock baseline --checks
  2000 --models claude-haiku-5-5,claude-sonnet-5-5`.
- Sample labeled (candidate, rule) checks from the eval logs, stratified by
  rule and label. Send the identical facts JSON and question text and ask for
  a probability of violation as one structured number. Record latency and
  tokens; take prices from the API docs at run time, never hardcoded.
- ECE, Brier and accuracy at 0.5 per model through the existing functions in
  `metrics.py`; a `baseline` block in `latest.json`; a reliability and
  latency plot in `plots.py`; a third panel in the metrics tab if time allows.
- Jev's answers for the same checks come from the logs, so Jev costs nothing.
- Dependency: the `anthropic` SDK, approved Oct 17. Key as `ANTHROPIC_API_KEY`
  in `backend/.env`, gitignored, never logged.

### 16.4 Item C: physics floor in code

- After A3 the facts carry time to collision. `shield.py` gains a floor,
  default 1.0 s: any candidate below it is removed from the executable set
  before `decide()`, so it is never the proposal, the fallback or the last
  resort. If the floor removes every candidate, SLOWER executes flagged
  `floor`.
- Log record gains `floor: {"applied": bool, "removed": [actions]}`; decision
  kinds unchanged; the inspector greys floored candidates.
- Talk framing: the floor is physics, not policy. Operators cannot type it
  away. Three layers: physical limits in code, rules in the model, judgment
  calls to the human.
- Eval: crash rate before and after, expected to fall at the aggressive
  threshold settings.

### 16.5 Item D: the unshielded twin

- The shield-off run on a seed is deterministic and already logged. On
  `reset`, the server looks for a shield-off log for that seed under
  `backend/logs/runs/` and the eval directories and sends one `twin` message
  with per-step ego, vehicles, executed action, violation count and crash
  flag. Absent a log, the console hides the strip. Demo seeds are warmed with
  `interlock run --shield off --seed N` and ship in the image.
- Console: a second, shorter road strip under the main one, driven by the
  twin record at the current step index and drawn faded, with a running count
  of twin violations and crashes. Playback and scrubbing share the index.
- No Jev cost and no new server state beyond the loaded records.

### 16.6 Phases and freeze

Phases run in order. Each ends with the tests green and the docs page updated
for anything it changed. No day estimates: the work is done by coding agents,
and the first plan went from brief to deployed in one night.

| Phase | Work | Done when |
| --- | --- | --- |
| 1 | A1 metrics fix, A2 conflict policy and queue protocol | Report regenerated from the existing logs; a no-compliant-action escalation resolves from the console with a chosen action. Done Oct 17. |
| 2 | A3 facts, spike re-run | New fields on every candidate; preset rules within 0.1 of the Oct 16 spike. Done Oct 17. |
| 3 | A4 rules, A5 labeling command, labels collected, A6 eval | Each fuzzy rule has 300 human labels and appears in the calibration plot |
| 4 | B baseline, C floor | Baseline block in `latest.json` with its plot; crash rate table before and after the floor |
| 5 | D twin | Twin strip plays and scrubs in step with the live run on a warmed seed |
| 6 | Freeze: docs sweep, section 10 and README corrected, backup video, rehearsal | `mkdocs build --strict` passes; video recorded; no code changes after this point |

Human-paced work: collecting labels in phase 3 and the video and rehearsal in
phase 6 need the operator's time. Everything else is agent time.

Risks: widening the facts shifts preset answers, caught by the spike re-run;
the conflict policy changes every on-mode number, so all tables regenerate
after A2; scope, handled by the freeze phase. Not doing: retraining the
agent, PyFlyt, click-to-place zones, WebGL.

Decided Oct 17: the conflict policy is least-bad, and the operator may choose
any candidate in the queue when no compliant action exists. Both are in A2.
