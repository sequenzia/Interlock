# Facts

`backend/facts.py` turns the simulator state plus one candidate action into
the JSON that Jev judges and the sentences the console shows. Everything that
involves a number, a comparison or a lane index is computed here, so the judge
only has to read. This page documents the schema, the geometry rules behind
each field and the two render helpers.

## Why geometry stays in code

Jev's documented weak spots are arithmetic, counting, numeric comparison,
literal reading of negation and multi-hop reasoning, and irrelevant state
lowers its accuracy. So the extractor sends a small, flat object per candidate
with units in the field names, booleans for the comparisons a rule is likely
to need, and nothing else. Facts come from the simulator's vehicle objects,
never from the normalized observation the policy sees.

## The schema

One object per candidate action. Here is a real one from a logged step, the
ego in the rightmost lane and the candidate `LANE_LEFT`, with the fields added
on Oct 17 (`headway_s`, `time_to_collision_ahead_s`, `being_tailgated`,
`traffic`, `history`) filled in with illustrative values.

```json
{
  "ego": {"lane": 4, "lane_count": 4, "speed_mps": 24.4, "target_speed_mps": 25.0},
  "action": {
    "name": "LANE_LEFT",
    "meaning": "move one lane to the left",
    "lane_after": 3,
    "target_speed_after_mps": 25.0
  },
  "lane_after_action": {
    "is_leftmost": false,
    "is_rightmost": false,
    "vehicle_behind_gap_m": 1.5,
    "vehicle_behind_closing_speed_mps": -3.9,
    "vehicle_ahead_gap_m": 56.3,
    "vehicle_ahead_speed_mps": 20.4,
    "slower_vehicle_ahead_within_40_m": false,
    "headway_s": 2.3,
    "time_to_collision_ahead_s": 12.2,
    "being_tailgated": false
  },
  "current_lane": {
    "vehicle_ahead_gap_m": 7.2,
    "vehicle_ahead_speed_mps": 21.1,
    "slower_vehicle_ahead_within_40_m": true
  },
  "traffic": {"vehicles_within_50_m": 5},
  "history": {"lane_changes_last_10_steps": 1, "steps_in_current_lane": 4},
  "zones": []
}
```

Two blocks are conditional. `lane_right_of_lane_after` appears only when the
lane after the action is lane 1; `zones` holds one entry per zone not yet
passed and is an empty list otherwise.

### `ego`

| Field | Meaning |
| --- | --- |
| `lane` | Current lane, numbered from the left starting at 1. |
| `lane_count` | Lanes on the road, 4 in the demo configuration. |
| `speed_mps` | Current speed. |
| `target_speed_mps` | The speed the vehicle controller is holding. |

### `action`

| Field | Meaning |
| --- | --- |
| `name` | One of `LANE_LEFT`, `IDLE`, `LANE_RIGHT`, `FASTER`, `SLOWER`. |
| `meaning` | Plain words. A lane change at the road edge says it changes nothing: "keep lane 1, already the leftmost lane, so this action changes nothing". Without that, the judge scored a no-op lane change as a gap violation. |
| `lane_after` | Lane after the action, clamped to the road. |
| `target_speed_after_mps` | The controller's target after the action, from the vehicle's discrete speed grid: `FASTER` and `SLOWER` move `speed_index` one notch and clamp to the ends of `target_speeds`. |

### `lane_after_action`

Describes the lane the ego will be in after the action, which is the current
lane for `IDLE`, `FASTER` and `SLOWER`.

| Field | Meaning |
| --- | --- |
| `is_leftmost`, `is_rightmost` | Lane 1 and lane `lane_count`. |
| `vehicle_behind_gap_m` | Bumper to bumper gap to the nearest vehicle behind in that lane, or `null`. |
| `vehicle_behind_closing_speed_mps` | That vehicle's speed minus the ego's speed, so positive means it is catching up. `null` when absent. |
| `vehicle_ahead_gap_m` | Bumper to bumper gap to the nearest vehicle ahead, or `null`. |
| `vehicle_ahead_speed_mps` | Its speed, or `null`. |
| `slower_vehicle_ahead_within_40_m` | `true` when a vehicle ahead is within 40 m and slower than the ego. |
| `headway_s` | Gap ahead divided by the target speed after the action, or `null` with no vehicle ahead. The target speed is used rather than the current speed because it is what the action commits to; for `FASTER` that makes the headway conservative. |
| `time_to_collision_ahead_s` | Gap ahead divided by the closing speed (target speed after the action minus the vehicle ahead's speed), or `null` when not closing or with no vehicle ahead. |
| `being_tailgated` | `true` when a vehicle behind in that lane is within 10 m and faster than the ego. For a lane change this is a cut-in close ahead of a closing vehicle. |

### `traffic`

| Field | Meaning |
| --- | --- |
| `vehicles_within_50_m` | Other vehicles within 50 m of the ego longitudinally, in any lane. A density measure for rules such as "drive conservatively in dense traffic". |

### `history`

| Field | Meaning |
| --- | --- |
| `lane_changes_last_10_steps` | Lane changes over the last ten transitions, counting the one this step's state implies. |
| `steps_in_current_lane` | Consecutive previous steps spent in the current lane, 0 at the first step. |

The history comes from `EpisodeRunner`, which keeps the ego's lane at the
start of each past step and calls `lane_history` before building the facts.
It is the same for every candidate in a step: it describes the past, not the
action. A caller without a runner gets zeros.

### `current_lane` and `lane_right_of_lane_after`

Both use the smaller "ahead" block: `vehicle_ahead_gap_m`,
`vehicle_ahead_speed_mps` and `slower_vehicle_ahead_within_40_m`.
`current_lane` is the ego's lane before the action. `lane_right_of_lane_after`
is lane 2 and is present only when the action lands in lane 1 (and the road
has more than one lane). It is the lane being passed, which the passing rule
needs and which neither of the other blocks covers when the ego is already in
lane 1.

### `zones`

| Field | Meaning |
| --- | --- |
| `name`, `lane` | From the operator's zone. |
| `starts_in_m` | Distance from the ego to the zone start, floored at 0 once inside it. |
| `ends_in_m` | Distance from the ego to the zone end. |
| `action_enters_zone` | `true` when `lane_after` is the zone's lane and the ego's position after one step at its current speed falls inside the zone. |

Zones whose end is behind the ego are dropped from the facts. The store
retires them at the top of each step anyway (see
[constraints and checkers](constraints-and-checkers.md)), so the two agree.

## Geometry rules

| Rule | Where | Detail |
| --- | --- | --- |
| Lanes count from the left | `lane_number` | highway-env's lane index is zero-based; the facts add one. |
| Gaps are bumper to bumper | `_gaps` | Center distance minus the vehicle length (5 m), floored at 0. |
| Far vehicles are absent | `NEIGHBOUR_RANGE_M = 200` | Beyond 200 m a neighbour is reported as `null` rather than as a large number. |
| Slower means slower and close | `_slower_ahead`, `SLOWER_AHEAD_RANGE_M = 40` | Both conditions are required. |
| Tailgating is close and closing | `TAILGATE_RANGE_M = 10` | A vehicle behind within 10 m whose speed exceeds the ego's. |
| Density is a count | `_traffic`, `TRAFFIC_RANGE_M = 50` | Vehicles within 50 m along the road, any lane, ego excluded. |
| History is ten transitions | `lane_history`, `HISTORY_STEPS = 10` | The runner keeps twenty past lanes so `steps_in_current_lane` can exceed ten. |
| Margins use the speed after the action | `_headway_and_ttc` | Headway and time to collision divide by the target speed the action commits to. |
| One step is one second | `STEP_SECONDS = 1.0` | Matches `policy_frequency: 1`; used for zone entry. |
| Neighbours come from the road | `road.neighbour_vehicles(ego, lane_tuple)` | highway-env's own lookup on the target lane, so the facts and the simulator agree. |
| Numbers are rounded to one decimal | `_r` | Keeps the state short and the cache key stable across floating-point noise. |

## Public functions

| Function | Returns |
| --- | --- |
| `facts_for_action(env, action, zones, history=None)` | The facts object for one candidate from the live environment. |
| `for_candidates(env, actions, zones, history=None)` | `{action: facts}` for the ranking, all sharing the same history. |
| `lane_history(past_lanes, lane)` | The `history` block from the lanes of past steps and the current lane. |
| `noop_actions(candidates)` | The actions whose facts show no change in lane or target speed; the shield excludes them from the least-bad fallback. |
| `snapshot(env)` | The render snapshot for the record: ego `lane`, `speed_mps`, `x_m` and a list of other vehicles with `id`, `lane`, `x_m`, `speed_mps`. Ids are the index in `road.vehicles`, stable within an episode. |
| `sentences(facts)` | The same facts as plain sentences for the console and the approval card. |
| `lane_after`, `target_speed_after`, `action_meaning`, `lane_number` | Small helpers reused by the checkers' tests and the spike. |

### Sentences

The sentence renderer reads only the facts object, so what the operator reads
is exactly what the judge saw. For the example above:

```text
Ego speed 24.4 m/s, target 25 m/s, lane 4 of 4 (numbered from the left).
LANE_LEFT: move one lane to the left. Lane after: 3. Target speed after: 25 m/s.
Lane 3 after the action: nearest vehicle behind is 1.5 m away, closing at -3.9 m/s; nearest vehicle ahead is 56.3 m away at 20.4 m/s. Slower vehicle ahead within 40 m: no. Headway: 2.3 s. Time to collision ahead: 12.2 s. Tailgated within 10 m: no.
Current lane 4: nearest vehicle ahead is 7.2 m away at 21.1 m/s. Slower vehicle ahead within 40 m: yes.
Traffic: 5 vehicles within 50 m. Lane changes in the last 10 steps: 1. Steps in the current lane: 4.
Operator zones: none.
```

A lane-1 landing adds a sentence for the lane to its right, and each zone adds
one that ends with "This action enters it: yes" or "no".

## What is deliberately not sent

- No normalized observation vector, Q-values or reward.
- No vehicles beyond the nearest ahead and behind in the relevant lanes.
- No absolute positions: zones are expressed as distances from the ego.
- No rule text. The rule lives in the question, the state stays about the road.

## Facts and the cache

The cache key in `backend/jev_client.py` hashes the facts object together
with the model and the question. Any change to a field name, a rounding rule
or a new block therefore invalidates every cached answer. That is the right
behaviour, since a different state is a different question, but it means a
warm cache for the demo seeds has to be rebuilt after editing this module.
The Oct 17 additions did exactly that: every key changed, so the demo seeds
need `interlock run` again before a mock-mode demo. See
[Jev integration](jev-integration.md).

## Tests

`tests/test_facts.py` checks the schema against a live environment, that gaps
match the simulator's own geometry, lane clamping at the edges, the no-op
wording for edge lane changes, the lane-to-the-right block, the slower flag
needing both gap and speed, headway, time to collision, tailgating and density
against the simulator, `lane_history` over short and long sequences, the
no-op action set, zone facts relative to the ego with the entry flag, the
speed grid for `target_speed_after`, and that the sentences cover every block.
`tests/test_episode.py` checks that the history in every logged candidate
matches the lanes of the preceding records.
