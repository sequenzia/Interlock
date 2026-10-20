# Interlock: Summary Report

Oct 17, 2026. The full story lives next to this file in `project-brief.md`,
`build-plan.md`, `jev-spike-results.md` and `eval/latest.json`.

## What it is

Interlock is a runtime safety shield for a reinforcement learning agent, with a
human on the loop. A Stable-Baselines3 DQN drives in highway-env and was trained
on task reward alone: speed, no collisions, a small bonus for keeping right. It
has never seen a rule. At every step, Jev, TypeSafe's decision model, judges
each of the agent's candidate actions against rules an operator types in plain
English, such as "Speed limit 25 m/s" or "Lane 3 is closed ahead for a work
zone", and returns a probability of violation. Code then allows the action,
falls back to the agent's next-best safe action, or pauses and asks a person.

The one-line pitch: the policy was trained once; the rules changed live, in
plain English.

It is an independent personal project, built in October 2026 as the demo for a
short talk on runtime safety for learned policies. The name is the
safety-engineering term for a mechanism that permits an action only when a
condition holds, with a supervised override.

## What it does

Each simulation step runs one loop, whether driven headlessly from the
`interlock` command or streamed to the console over a WebSocket:

1. The DQN ranks all five actions (LANE_LEFT, IDLE, LANE_RIGHT, FASTER, SLOWER)
   by Q-value.
2. Code computes what each candidate would do and packages it as JSON facts
   with units: ego speed and lane, the lane and target speed after the action,
   gaps and closing speeds in the target lane, and whether the action enters a
   closed zone. Jev never sees the raw action or the simulator.
3. One Jev request per candidate, five in parallel, carries one yes/no question
   per enabled rule with the rule text quoted verbatim. Each answer is a
   probability from 0 to 1. Five actions and seven standing rules make
   thirty-five questions and a five-by-seven grid.
4. Code removes any candidate that would close on the vehicle ahead in under
   2 seconds: the physics floor, set at launch, which no rule can type away.
   The shield then takes the top remaining action's highest probability
   across rules and applies two thresholds, by default 0.3 and 0.7. Every
   candidate was judged, so a fallback costs no extra round trip, and the
   console can always say which rule fired.
5. Ground-truth checkers label every candidate for scoring only. One JSONL
   record per step holds the facts, every probability, the decision, the
   human's answer and the raw Jev exchange. The console, replay and
   evaluation all read that one record.

A question, as sent:

```
Executing the candidate action described in state would violate this operator rule: "Speed limit 25 m/s"
```

One rule per question is deliberate: asking whether an action breaks any rule
would be a multi-hop question, which Jev's docs list as a weakness. Answers are
cached by a hash of the facts and the question, so a repeated situation never
calls Jev again.

### Shield on versus off

Shield off is not "skip the shield". Both modes run the same pipeline through
a computed decision. The only difference is one override in the step loop that
executes the policy's top action regardless, so before and after numbers come
from one code path.

| Stage | Shield on | Shield off |
| --- | --- | --- |
| Rank, facts, Jev requests, checker labels, decision | Same | Same, at the same cost and latency |
| What executes | The physics floor drops candidates under 2 s to collision; allow runs the top remaining action; fallback runs the next confidently safe one; anything else pauses and asks, with every candidate on offer when none is confidently safe | Always the top action, floor not applied; the decision is overwritten to "allow" |
| Operator | Pauses on an escalation until an answer or the timeout | Never consulted, never pauses |
| Log record | Full | Same probabilities, labels and fired rule; only the kind, executed action and human fields differ |
| Violations counted | On the executed action | On the top action |

Rules and zones stay active with the shield off and are still scored. The
console toggle flips the flag for the next step without a reset; reset on the
same seed for a clean comparison. On can override the policy's own crash
avoidance in the name of a rule; the floor is the one layer that reads
physics, and it reads time to collision ahead only, not a vehicle alongside
during a lane change.

The console adds a road view, a rules panel with presets, free text and a
one-click work zone, an approval queue, a timeline with a per-step inspector
showing the exact Jev exchange, replay and a metrics tab. A mock mode replays
cached answers offline; anything not cached escalates flagged "judge
unavailable" rather than inventing a number.

## What the numbers say

Twenty seeded episodes of 60 steps, seven standing rules, live `jev-1.13.0`,
and a simulated operator answering from the checkers, measured Oct 17.

| Configuration | Violations per episode | Task return | Crash rate | Steps escalated |
| --- | --- | --- | --- | --- |
| Shield off | 105.45 | 50.7 | 40% | 0.0% |
| Shield on, 0.2 / 0.8 | 3.45 | 45.7 | 0% | 48.2% |
| Shield on, 0.3 / 0.7 (default) | 3.55 | 46.0 | 0% | 16.5% |

By rule, off to on at the default: speed limit 1030 to 0, lane-change gap 124
to 1, left lane for passing 8 to 0, headway 647 to 65, lane-change rate 300
to 5. The passing leak from the first run is gone: states where no action
satisfied every rule now reach the operator instead of looping on a no-op
last resort. The headway rule took the crash rate to 5% and a 2 second
time-to-collision floor in code, which no rule can type away, took it to 0;
the floor costs 22 headway violations because the car follows slow traffic
instead of changing lanes into closing gaps. Calibration over 174,625 labeled checks on the five crisp rules gives an
expected calibration error of 0.095 and 98.7% accuracy at a 0.5 cut. The two
fuzzy rules, labeled Oct 19 against one fixed standard over every pooled
state, come in at 0.110 for driving conservatively in dense traffic and 0.221
for leaving room when moving in ahead of a faster vehicle, the one rule whose
probability does not track the facts that decide it. A full
step answers in about 158 ms at the median from a cold cache, and an
episode costs under a cent.

The same questions put to chat models, 2,000 checks balanced over rule and
label, Oct 18: Claude Sonnet 5.5 is better calibrated than Jev on that sample,
ECE 0.060 against 0.139, and slightly more accurate, yet at the default
0.3 / 0.7 band it would have allowed 3 violations and blocked 5 compliant
actions where Jev allowed and blocked none, because Jev's error is
underconfidence and the band turns it into a question. Jev asks on 20.6% of
those checks against 3.1%, answers a full step of 35 checks in 158 ms against
about a second per check, and an episode costs about $0.005 against about
$4.40 with Sonnet and $0.33 with Haiku.

## Why it is interesting

- **Rules live outside the policy.** The agent is never retrained. Behaviour
  changes the moment an operator types a sentence, and the mid-episode work
  zone makes that visible on screen.
- **The boundary between code and model is a design choice.** Jev's docs list
  arithmetic, numeric comparison, multi-hop reasoning and negation as
  weaknesses, and the Day 1 spike confirmed the misses. So code computes every
  number and Jev only judges. A rule typed with negation gets a suggested
  rephrase, never an edit.
- **A calibrated probability is a control signal.** Two thresholds turn one
  number into three outcomes, and the sweep shows the dial: 0.1 / 0.9 asks a
  person on 89% of steps, 0.3 / 0.7 on 14%, for the same violations and crash
  rate. The band sets operator load. Calibration is measured, not assumed.
- **Human on the loop, not in the loop.** The system asks only when it is
  unsure. The passing rule sits near 0.5 for Jev regardless of phrasing; that
  is treated as the human moment, not a bug to prompt away. Every approve or
  deny is logged as a labeled example.
- **Three layers.** Physical limits in code, rules in the model, judgment
  calls to the human. The floor removed the last shielded crash at a cost of
  22 headway violations; the console draws the unshielded twin under the
  live run so the comparison is on screen, not only in a table.
- **Honest by construction.** Checkers score and never decide. A lost network
  escalates at p = 0.5 with a flag; the shield never fakes a judgment. The eval
  notes that a perfect simulated operator flatters the high-escalation settings.
- **Decision model versus chat LLM.** Typed probabilities instead of text to
  parse, a step in about 160 ms, an episode for pennies. Prior work in the same
  environment used GPT-3.5 as a planner.

## Limits and next steps

It is cars, not aircraft, because highway-env was the fastest route to a
reward-only policy that misbehaves in readable ways. Twenty seeds is a
demo-sized evaluation. Next steps named in the brief: a UAV environment such as
PyFlyt, click-to-place zones, and a measured comparison against a chat-LLM
shield.
