# Approval queue

The approval queue is the human-on-the-loop half of Interlock. It is empty most of the time. When the shield cannot act on its own, it fills with one card and the simulation waits.

![The approval queue during an escalation](../../assets/screenshots/approval-queue.png)

## When an escalation happens

The shield executes on its own only when it holds a confidently safe action: the proposal below the allow threshold, or a lower-ranked action below it when the proposal is a confident violation. Everything else pauses the loop before the action executes, the status strip shows "waiting on operator", and the card appears. The card names one of two reasons:

| Reason | Meaning | Card color |
| --- | --- | --- |
| uncertain | The proposal's worst p(violation) sits inside the band between the two thresholds, 0.2 to 0.8 by default, and a confidently safe fallback exists. | violet |
| no compliant action | No candidate at all scores below the allow threshold. Every action breaks some rule as far as the judge can tell, or the judge had no answer. | amber |

Three situations produce most escalations:

- A rule that is genuinely fuzzy for the judge. "Keep the left lane for passing only" sits near 0.5 for many lane-left moves.
- Rules that cannot all be satisfied at once. Cruising in lane 1 with nobody to pass breaks the passing rule, and the only way out, a lane change to the right, breaks the gap rule while a car sits alongside. Nothing is compliant, so the card says so and offers every candidate.
- No answer at all. In mock mode with a cold cache, or in live mode when the network is down, every unanswered question is p = 0.5. Nothing is confidently safe, so these also arrive as no compliant action.

## What the card shows

| Element | Meaning |
| --- | --- |
| Reason badge | "uncertain" or "no compliant action", with one line saying what that means for you |
| Action name | the policy's proposed action, always its rank 1 choice |
| p(violation) bar | the worst probability across enabled rules for that action |
| Rule in quotes | the rule that produced that probability |
| "judge unavailable, p is a placeholder" | at least one question in this step had no answer; the 0.5 is not a judgment |
| Facts as sentences | the same facts Jev saw, rendered in plain words: ego speed and lane, what the action does, gaps in the target lane, the current lane, the lane to the right when relevant, zones |
| Candidate list | every action in the policy's ranking with its number key, its worst p, and for a no-compliant-action card the rule behind that p. "proposal" marks rank 1, "no-op" marks an action that would change neither lane nor target speed |
| "Deny executes X (safe / least bad / last resort fallback)" | what deny would run and how the shield found it |
| "Auto-deny in N s" | the countdown, only when a timeout is configured |
| "approve" and "deny" | the two one-key answers |

## Approve, deny or override

- **Approve** (++a++) executes the proposed action.
- **Deny** (++d++) executes the fallback named on the card. The fallback is **safe** when a lower-ranked action is confidently below the allow threshold, **least bad** when none is and the shield picks the lower-ranked action with the lowest probability that is not a confident violation and is not a no-op, or the **last resort**, SLOWER or IDLE, when nothing else qualifies. A last resort is recorded as all blocked.
- **Override** (++1++ to ++5++, or click a candidate) executes the candidate of that rank whatever the judge said about it. Picking rank 1 is the same as approve. On an uncertain card the candidates are a compact row under the facts; on a no-compliant-action card they are the main event, one row each with the rule that scored them.

Any connected console can answer; the first answer wins and the card disappears everywhere. The server rejects an override whose action is not one of the five candidates.

!!! tip "Getting out of a box"
    When no action is compliant the shield cannot resolve the conflict by itself, and a deny only runs the least-bad action, which often keeps the car where it is. Read the candidates: the way out is usually an action that breaks a rule once in order to stop breaking another one on every following step, for example FASTER to pull ahead of the car alongside so that the next lane change is clear.

## The timeout

`ESCALATION_TIMEOUT_S`, or `--escalation-timeout` on `interlock console`, sets how long the server waits. The default is 20 seconds, after which the escalation is denied automatically. A value of 0 waits forever. The hosted demo runs with 0 so a missed card never silently slows the car.

!!! warning "Unattended default-deny can crash the car"
    Deny means the fallback, and the fallback is a different action from the one the policy chose for a reason. If the proposal was a lane change away from a slow vehicle, a run of auto-denies can put the car into it. Use a timeout of 0 whenever a person is actually watching.

## Judge unavailable

The badge "judge unavailable, p is a placeholder" means the shield has no opinion and is asking you to supply one. Read the facts and the rule, then answer as the judge would have. The record keeps `source: "unavailable"` on the judge, so these steps stand out in the log and the inspector.

## When the queue is idle

With no open escalation the panel title shows the running counts, for example "3 approved · 1 denied · 2 overridden", or "empty". The body says "Nothing waiting. The shield is deciding on its own." With the shield off it says "Shield is off. Nothing escalates."

## Where the answer goes

Each answer is written into the step's log record as `human`: the decision, the chosen action for an override and null otherwise, how long the operator took in milliseconds, and `operator: "ui"`. The record also keeps `escalation_reason` and the `fallback` the shield had ready. The inspector shows the answer as a badge ("operator override LANE_RIGHT in 2140 ms") next to the reason, the decisions strip tooltip appends it in parentheses, and the metrics message counts it. These records are the labeled examples that a later threshold tuning would use. See [Timeline and inspector](timeline-and-inspector.md) and the [Log record](../../developer-guide/contracts/log-record.md).

## On the command line

Headless runs have no queue. `interlock run --operator simulated` answers from the ground-truth checkers: it denies a true violation on an uncertain card, and on a no-compliant-action card it overrides with the candidate that breaks the fewest rules, ties going to the policy's ranking. `--operator approve` and `--operator deny` always give that answer. See [Command line](../cli.md).
