# Components

Nine components and three helpers live in `frontend/src/components/`, plus the icon set in `src/icons.tsx`. Each reads the store with narrow selectors, sends commands through `send()`, and keeps local state only for things the server does not own. Shared formatters and the decision palette come from `format.ts`: `DECISION_LABEL` (allowed, fallback, escalated, all blocked), `DECISION_CLASS` (Tailwind classes on the outcome tokens for badges and cells), `DECISION_COLOR` (hex for the canvas and the timeline), `HAZARD_COLOR` and `ACCENT_COLOR`, `isLaneNoop()` (a lane change at the road edge changes nothing) and `uiScale()` (the root font size over 16 px, so canvas text follows the density toggle).

## status-strip

The header on both views, one row in every state. A three-column grid: brand, tabs and source on the left; the transport in a flexible middle cell; the density and shortcut buttons and the stats on the right.

- `SourceMenu` is one native `<select>` styled as a badge. It reads `live` or, amber, the replaying run; its options are `live` plus every logged run from `hello.runs`, newest first, shown as `replay 10-17 01:27 seed0_on` by `runLabel()`. Picking `live` sends `load_live`, anything else `load_replay`. Before the first `state` it is an `offline` badge.
- `Transport` holds reset (icon, with the seed input beside it), step, play or pause and the speed select in one bordered group, then the shield as a `role="switch"` button, then `StatusSlot`. The seed input is local state mirrored from `session.seed` in an effect, so a reset from another browser updates it but typing does not round-trip until reset is clicked. Enabled state follows the session: step is disabled while playing, while an escalation is open and when the episode is done; play only when the episode is done; the shield in replay. Speed options are 0.5, 1, 2 and 4 steps per second, labeled `2/s`, sent as `set_speed`.
- `StatusSlot` shows exactly one badge, the most urgent state first: "waiting on operator" while `paused_on_escalation_id` is set, "inspecting N · esc follows live" while a tick is selected, "episode over" when done, otherwise `DECISION_LABEL` for the latest record with `→ <executed>` when the executed action differs from the top candidate. The slot is `flex-1` with `overflow-hidden`, so it absorbs slack and clips rather than wraps.
- On the metrics tab the middle cell renders `ReportMeta` from `store.report` (generated time, seed count, thresholds, judge mode) and the live stats hide.
- The right cell has the "Aa" density toggle (`aria-pressed`, calls `setDensity`), the keyboard button (`setShortcutsOpen(true)`), and `LiveStats`: step (with total from `total_steps` in replay or `config.duration` live), Jev source and latency, cost so far, violations so far. Jev and cost carry `max-xl:hidden talk-hide`, so they drop below 1280 px and at talk density; the reset label drops at talk density too.

## road-view

A Canvas 2D view with its own animation loop and a DOM overlay for the HUD and the legend.

| Constant | Value | Meaning |
| --- | --- | --- |
| `VIEW_M` | 160 | Metres of road across the canvas, right of the gutter |
| `EGO_OFFSET_M` | 50 | Ego sits 50 m from the gutter, so 110 m is visible ahead |
| `GUTTER_PX` | 44 | Lane labels live here, outside the road surface; scaled by `uiScale()` |
| `HUD_PX` | 40 | The band the DOM overlay occupies; the road starts below it |
| `MIN_LANE_H`, `MAX_LANE_H` | 40, 120 px | Lane height clamps; lanes grow to fill the canvas |
| `LANE_WIDTH_M`, `CAR_L_M`, `CAR_W_M` | 4, 5, 2.2 | Scale for cars |

The component keeps a `Frame` ref (`prev`, `cur`, `t0`, `intervalMs`) rather than redrawing on React renders. One `requestAnimationFrame` loop calls `render()` every frame; an effect replaces the frame whenever the view step, the previous step or the speed changes, with `intervalMs = 1000 / speed`. `render()` computes `alpha` as the elapsed fraction of the interval and linearly interpolates ego position, ego lane and every other vehicle (matched by `id` between `prev` and `cur`), so cars glide between steps instead of jumping. While inspecting, `t0` is set to 0 so `alpha` is 1 and the frame is drawn at rest.

Drawing order: shoulders and surface, lane lines (the dashes are world-fixed, so `lineDashOffset` scrolls them with the ego's x), lane labels in the gutter, then everything on the road inside a clip rectangle so nothing bleeds into the gutter: zones, traffic, the ego, the arrows, the chip. `carSize()` gives a car its true length along x and caps its height at `length / 1.6`, so a car reads as a car rather than a tile whatever the lane height; `drawCar()` adds a darker cabin, headlights at the front (the right end), taillights at the rear, and for the ego a white outline and a glow in `ACCENT_COLOR`. Zones come from the live store normally and from the inspected record's `zones` while scrubbing; a closed stretch is filled with a cached hatch pattern in `HAZARD_COLOR`, and its label is clamped inside the visible part of the zone on a dark pill. Arrows start at the car's edge: the executed action is solid in `DECISION_COLOR[cur.decision]` over a dark halo; when the top candidate differs from what ran it is drawn first as a dashed ghost, rose when a rule blocked it and amber when `cur.floor.removed` names it. IDLE, or a lane change `isLaneNoop()` rejects, is a hold mark (two short bars) under the car by `drawHold()`, on the far side from any ghost arrow. A chip above and to the right of the ego reads `FASTER ✓` or `FASTER ✕ → IDLE` in the outcome color, clamped inside the canvas. `CRASH` appears beside the ego when the record says so. The canvas is resized to `devicePixelRatio` on every frame and the context transform set to match, so text stays crisp on retina displays. The helpers (`drawCar`, `carSize`, `drawArrow`, `drawHold`, `arrowFor`, `lerp`) and the constants are exported for the twin strip.

The overlay is pointer-transparent. Left: the "Road view" label and, once there is a record, a HUD with step, lane, speed, the outcome badge (with `· FASTER blocked` or `· FASTER under the floor` when the top candidate did not run) and the operator's answer. Bottom right, hidden while a step is selected: the legend, with swatches for the ego and the closed lane, tiny arrow glyphs for ran, blocked and floored, and the two-bar hold mark. The section is borderless on a darker surface, the one hero panel on the page.

## twin-strip

The unshielded twin under the road view, titled "Without the shield". Reads `twin` from the store (set by the `twin` message), the view step from `selectViewStep`, `selectedStep`, the session speed and seed. It renders nothing unless the twin's `steps` are non-empty and its seed matches the session's, and `app.tsx` swaps it for the inspector while a step is selected. The twin step index is the view step's `step`, clamped to the twin's last step, so playback and scrubbing share one clock; past the twin's end the strip holds its last frame and prints `CRASHED`. It keeps its own `TwinFrame` ref and `requestAnimationFrame` loop and interpolates like the road view, but draws at 65 percent alpha with grey traffic, a lighter ego, lane numbers in the gutter, scrolling dashes, no zones and a neutral arrow or hold mark, in lanes 12 to 24 px high. The title line carries the current step, the twin's violations so far as a rose headline over its total, and the crash step; the subtitle's tooltip names the run and how many rules it was scored against.

## decision-strip

The timeline. Reads `steps`, `selectedStep`, `config.duration`, `twin` and the session seed, and keeps a hovered index in local state. It renders `max(duration, steps.length)` tick buttons so the bar is full width from step 0; ticks without a record are disabled and dim. Height encodes state (selected 100 percent, present 78, empty 28), color is `DECISION_COLOR[r.decision]`, escalated steps are fully opaque, and a record with `human` gets a white dot. The hover card above the bar is `summary()`: `step N · outcome → executed`, the blocked or floored top candidate, the operator's answer and `crash`; it slides to stay inside the strip near either edge. Under the ticks, when the seed has a twin, a thin row shows `twin.steps[i].violations` as rose cells, darker the more rules broke, solid at `crashed_at`, revealed only up to the latest live step so the two timelines fill together. Under that, an axis with a label every ten steps (twenty past 120), a light caret at the latest step and a white caret at the selected one. The title holds the legend as swatches. Clicking a tick toggles `selectStep`; the button carries `aria-label="inspect step N"` and `aria-pressed`.

## inspector-drawer

![The inspector open on one step](../../assets/screenshots/inspector.png)

Renders only when `selectInspected` returns a record, in the twin's slot, capped at `min(22rem, 42vh)`. Local state holds the chosen candidate (reset whenever the step changes) and the `facts` or `raw` tab.

- The left table lists the five candidates by rank with a grey Q bar scaled between the step's min and max Q, a `ran` tag on the executed action, a `blocked` tag on a top action that did not run, and a `floor` tag with the row faded on a candidate the physics floor removed (`record.floor.removed`). One column per enabled constraint shows `p_violation`, coloured by `pClass` against the record's own thresholds (allow below `t_allow`, blocked above `t_block`, escalate between). A filled dot marks a checker label of violation, a hollow dot a label of ok, nothing when the rule has no checker.
- The right side shows the chosen candidate's sentences and facts JSON, or the raw exchange. `candidateExchange()` finds the `judge.exchanges` entry for that action and rebuilds the request as `{ model, state: candidate.facts, questions }` from `judge.questions`, because the log stores the state once per candidate and the question once per constraint. A step answered entirely from the cache has no exchange, and the drawer says so.
- The header carries, in priority order so the last truncates first: "Inspector · step N", the decision badge with `→ <executed>` when the executed action differs from the proposal, the operator's answer and latency when there was one (an override also names the action), a badge on escalated steps with `REASON_LABEL[escalation_reason]` whose tooltip names the `fallback` action deny would have run and its `FALLBACK_LABEL[kind]`, and the fired constraint's id and text. Icon buttons move between steps and close the drawer. The judge source, latency, model, cost and reward sit under the candidates table. Action names, ids and numbers are mono; sentences are sans.

## approval-queue

Reads `escalation`, `session.shield_on`, `session.thresholds`, `constraints` (for the rule text behind each candidate) and `metrics.human`. With nothing open it is a single title row: "empty, the shield is deciding on its own", "empty, no rules yet" or "shield off, nothing escalates", followed by the running approve, deny and override counts. With an escalation it expands in place, violet for `uncertain` and rose for `no_compliant_action`, in this order: the reason badge in the title; the proposed action and its rank; `PBar`, the probability as a white marker over the three bands of the current thresholds; approve and deny, with the deny button filling as `remaining / timeout_s` counts down and reading "auto in N s"; one line of context with what deny would execute and `FALLBACK_LABEL[fallback_kind]`; the "judge unavailable" badge when the backend had no answer; the fired rule's text as a quote; the first three sentences with an "all N facts" chip; and the candidates as rows with their number key, action, worst p coloured by the thresholds, the rule behind it, and `proposal` or `no-op` tags. A candidate button sends `resolve` with `override` and its action, except the proposal, which sends `approve`; the exported `resolveWithRank()` does the same for the digit keys in `app.tsx`. When `expires_at` is set, a 250 ms interval updates a local clock; with a timeout of 0 the server sends `expires_at: null` and no clock runs. The facts toggle resets when the escalation id changes.

## constraint-panel

Reads `constraints`, `zones`, `zoneNote`, `hello.presets`, `session`, `steps` and the open escalation's `p`. Everything is disabled in replay or before the first `state`, and the title says "replay, read only".

- The text box sends `add_constraint` with the trimmed text; the server infers a checker. A hint appears when the text starts with "No" and mentions a lane change (`/^no\s/i` and `/lane change/i`), offering the positive rephrase of the gap rule; the operator's own wording is always kept.
- The rule list comes first. Each row has a `role="switch"` button (`toggle_constraint`), the text, a meta line with the id in mono, a `scored` tag whose tooltip names the checker (or `not scored`), and `fired N×` from a `useMemo` over `steps` counting records whose `fired_constraint` is this rule, and an icon button to remove it (`remove_constraint`).
- Presets follow under a collapsible heading that counts how many are left to add. Only presets whose text is not already in the list are shown; a chip sends `add_constraint` with the preset's `checker`. The chip text truncates with the full text in its tooltip.
- The zones block has the `drop_zone` button, one hazard-coloured row per zone with its lane and absolute start and end, and the retirement note from the store.
- `ThresholdBand` (in `threshold-band.tsx`) keeps a local copy of the thresholds, re-synced from `session.thresholds` by an effect. Two range inputs overlay one track drawn as three bands (allow, escalate, block); they step by 0.05 and clamp against each other so `t_allow` never exceeds `t_block`. `set_thresholds` is sent on pointer up or key up, and only if a value changed, so dragging does not flood the socket. A white marker shows the open escalation's probability. The physics floor from `session.floor_s` is one line with the explanation in its tooltip; there is no control for it.

## metrics-view

Fetches `httpUrl("/eval/latest")` once, stores the result with `setReport` so the status strip can show its metadata, and renders the report, an error (as a report with `available: false`), or the server's instruction to run the evaluation. Five tiles lead with the delta (`30× fewer`, `-9.4% return`, `40% → 0%`, `16.5% of steps`, `$0.0005 / episode`) with shield off and on under it. Four chart panels follow, each `shrink-0` so a tall table never bleeds into the next panel:

| Panel | Chart | Beside it |
| --- | --- | --- |
| Violations per seed | `BarChart`, two series from `episodes[].violations_total` | |
| Task return per seed | `BarChart`, two series from `episodes[].return` | |
| Choosing the thresholds | `ScatterChart` with a connecting line over `sweep[]` | a table of pairs with escalated, violations and return, the default pair marked |
| Is p(violation) calibrated? | `LineChart` with a diagonal `ReferenceLine`: `calibration.overall` dashed plus one line per checker in `CHECKER_COLOR` | a table with ECE, checks and label source per rule, in place of a legend |

Then the physics floor table, banded by threshold pair with the default pair and floor marked and numbers right-aligned, and, when a baseline exists, the chat-model reliability chart with a table of ECE, Brier, accuracy, median latency and cost per judge. Colors are blue for shield on, orange for off and aqua for the third checker; checkers without an entry in `CHECKER_COLOR` are not drawn. A footer line gives the report timestamp, p50 and p95 latency and the simulated operator's answer counts. The report shape is documented in [Evaluation report](../contracts/eval-report.md).

## toasts and shortcuts-overlay

`Toasts` renders `errors` fixed at the top center under the strip, with an icon button to dismiss, and clears them six seconds after the last push. `ShortcutsOverlay` renders a `role="dialog"` list of the keyboard shortcuts while `shortcutsOpen` is set; a click outside, its close button, ++esc++ or ++question++ closes it. Both use the `enter` animation.

## icons

`icons.tsx` holds the eleven inline SVG icons the components use (play, pause, step, reset, close, chevrons, keyboard, arrow), 16 px stroke icons with `aria-hidden`, so a button's accessible name is its text or its `aria-label` alone.
