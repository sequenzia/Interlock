# Components

Seven components live in `frontend/src/components/`. Each reads the store with narrow selectors, sends commands through `send()`, and keeps local state only for things the server does not own. Shared formatters and the decision palette come from `format.ts`: `DECISION_LABEL` (allowed, fallback, escalated, all blocked), `DECISION_CLASS` (Tailwind classes for badges and cells) and `DECISION_COLOR` (hex for the canvas and the timeline).

## status-strip

The header on both views. Reads `connected`, `session`, `hello`, `metrics`, the latest step, `hello.runs`, `view` and `selectedStep`.

- The seed input is local state mirrored from `session.seed` in an effect, so a reset from another browser updates it but typing does not round-trip to the server until `reset` is clicked.
- Enabled state follows the session. `step` is disabled while playing, while an escalation is open and when the episode is done. `play` is disabled only when the episode is done. The shield toggle is disabled in replay, and the replay picker when there are no logged runs.
- Speed options are 0.5, 1, 2 and 4 steps per second, sent as `set_speed`.
- The decision badge shows `DECISION_LABEL` for the latest record and appends `-> <executed>` when the executed action differs from the top candidate.
- Right-aligned stats: step (with total from `total_steps` in replay or `config.duration` live), Jev source and latency, cost so far, violations so far.

## road-view

A Canvas 2D view with its own animation loop.

| Constant | Value | Meaning |
| --- | --- | --- |
| `VIEW_M` | 240 | Metres of road across the canvas width |
| `EGO_OFFSET_M` | 70 | Ego sits 70 m from the left edge |
| `MIN_LANE_H`, `MAX_LANE_H` | 44, 84 px | Lane height clamps |
| `LANE_WIDTH_M`, `CAR_L_M`, `CAR_W_M` | 4, 5, 2.2 | Scale for cars within a lane |

The component keeps a `Frame` ref (`prev`, `cur`, `t0`, `intervalMs`) rather than redrawing on React renders. One `requestAnimationFrame` loop calls `render()` every frame; an effect replaces the frame whenever the view step, the previous step or the speed changes, with `intervalMs = 1000 / speed`. `render()` computes `alpha` as the elapsed fraction of the interval and linearly interpolates ego position, ego lane and every other vehicle (matched by `id` between `prev` and `cur`), so cars glide between steps instead of jumping. While inspecting, `t0` is set to 0 so `alpha` is 1 and the frame is drawn at rest.

Zones come from the live store normally and from the inspected record's `zones` while scrubbing, so the overlay matches the step on screen. Closed stretches are filled with a cached diagonal hatch pattern and labelled `<NAME> lane N closed`. Arrows start at the ego: the executed action is solid in `DECISION_COLOR[cur.decision]`; when the top candidate differs from what ran, it is drawn first as a dashed ghost in rose. The canvas is resized to `devicePixelRatio` on every frame and the context transform set to match, so text stays crisp on retina displays. A `CRASH` label appears above the ego when the record says so.

## decision-strip

The timeline. Reads `steps`, `selectedStep` and `config.duration`. It renders `max(duration, steps.length)` tick buttons so the bar is full width from step 0; ticks without a record are disabled and dim. Height encodes state (selected 100 percent, present 80, empty 30), color is `DECISION_COLOR[r.decision]`, and escalated steps are fully opaque. Clicking a tick toggles `selectStep`.

## inspector-drawer

![The inspector open on one step](../../assets/screenshots/inspector.png)

Renders only when `selectInspected` returns a record. Local state holds the chosen candidate (reset whenever the step changes) and the `facts` or `raw` tab.

- The left table lists the five candidates by rank with a Q bar scaled between the step's min and max Q, a `ran` tag on the executed action and a `blocked` tag on a top action that did not run. One column per enabled constraint shows `p_violation`, coloured by `pClass` against the record's own thresholds (green below `t_allow`, rose above `t_block`, violet between). A filled dot marks a checker label of violation, a hollow dot a label of ok, nothing when the rule has no checker.
- The right side shows the chosen candidate's sentences and facts JSON, or the raw exchange. `candidateExchange()` finds the `judge.exchanges` entry for that action and rebuilds the request as `{ model, state: candidate.facts, questions }` from `judge.questions`, because the log stores the state once per candidate and the question once per constraint. A step answered entirely from the cache has no exchange, and the drawer says so.
- The header carries the decision badge, the fired constraint's text, the operator's answer and latency when there was one, and the judge source, latency, model, cost and reward. Arrow buttons move between steps and the close button returns to live.

## approval-queue

Reads `escalation`, `session.shield_on` and `metrics.human`. With nothing open it shows the running approve and deny counts and a sentence that depends on whether the shield is on. With an escalation it shows the proposed action and rank, a probability bar, the fired rule's text in quotes, a "judge unavailable" badge when the backend had no answer, the candidate's sentences, what deny would execute, and the two buttons that `send` `resolve`. When `expires_at` is set, a 250 ms interval updates a local clock and the footer counts down to auto-deny; with a timeout of 0 the server sends `expires_at: null` and no clock runs.

## constraint-panel

Reads `constraints`, `zones`, `zoneNote`, `hello.presets` and `session`. Everything is disabled in replay or before the first `state`.

- The text box sends `add_constraint` with the trimmed text; the server infers a checker. A hint appears when the text starts with "No" and mentions a lane change (`/^no\s/i` and `/lane change/i`), offering the positive rephrase of the gap rule; the operator's own wording is always kept.
- Preset chips send `add_constraint` with the preset's `checker` and are disabled once a constraint with that checker exists.
- Each rule row has an enable checkbox (`toggle_constraint`), the id and checker name, and a remove button (`remove_constraint`).
- The zones block has the `drop_zone` button, one amber row per zone with its lane and absolute start and end, and the retirement note from the store.
- `ThresholdControls` keeps a local copy of the thresholds, re-synced from `session.thresholds` by an effect. The two range inputs step by 0.05 and clamp against each other so `t_allow` never exceeds `t_block`. `set_thresholds` is sent on pointer up or key up, and only if a value changed, so dragging does not flood the socket.

## metrics-view

Fetches `httpUrl("/eval/latest")` once on mount and renders the report, an error, or the server's instruction to run the evaluation. Five tiles compare shield off and on: violations per episode, task return, crash rate, escalation rate and cost per episode. Four Recharts panels follow:

| Panel | Chart | Data |
| --- | --- | --- |
| Violations per seed | `BarChart`, two series | `episodes[].violations_total` off and on |
| Task return per seed | `BarChart`, two series | `episodes[].return` off and on |
| Choosing the thresholds | `ScatterChart` with a connecting line and `LabelList` | `sweep[]` escalation rate against violations per episode |
| Is p(violation) calibrated? | `LineChart` with a diagonal `ReferenceLine` | `calibration.overall` dashed plus one line per checker in `CHECKER_COLOR` |

Colors are blue for shield on, orange for off and aqua for the third checker; checkers without an entry in `CHECKER_COLOR` are not drawn. A footer line gives the report timestamp, p50 and p95 latency and the simulated operator's approve and deny counts. The report shape is documented in [Evaluation report](../contracts/eval-report.md).
