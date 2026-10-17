# Glossary

Terms as Interlock uses them, with the page that covers each one.

**Action**
: One of the five highway-env meta-actions the policy chooses from: `LANE_LEFT`, `IDLE`, `LANE_RIGHT`, `FASTER`, `SLOWER`. Index order comes from highway-env. See [Training and policy](../developer-guide/backend/training.md).

**All blocked**
: The decision kind when the top action is a confident violation and no lower-ranked action is confidently safe. The shield executes `SLOWER` if its probability is at or below the block threshold, otherwise `IDLE`, and flags the step. See [Shield algorithm](../developer-guide/backend/shield.md).

**Allow**
: The decision kind when the top action's violation probability is below `t_allow`. The policy's choice runs unchanged.

**Brier score**
: Mean squared error between the predicted probability and the 0 or 1 label over every labeled check. Lower is better. See [Evaluation internals](../developer-guide/backend/evaluation.md).

**Calibration**
: Whether a probability means what it says: among checks scored 0.8, about 80 percent should be real violations. Measured with a reliability diagram, ECE and the Brier score. See [Metrics tab](../user-guide/console/metrics-tab.md).

**Candidate**
: One of the five actions on a given step, with its rank, Q-value, facts, sentences and per-rule checks. Every candidate is judged every step so the fallback is already in hand.

**Checker**
: A closed-form function in `backend/checkers.py` that labels a candidate against a rule as violation or ok. Checkers score only; they never influence the decision. See [Constraints and checkers](../developer-guide/backend/constraints-and-checkers.md).

**Closing speed**
: The speed of the vehicle behind in the target lane minus the ego speed, in m/s. Positive means it is catching up.

**Constraint, rule**
: A plain-English operator rule with a stable id (`c1`, `c2`, ...), an enabled flag and an optional checker id. Used interchangeably; the code says constraint, the console says rule. See [Rules and zones](../user-guide/console/rules-and-zones.md).

**Decision model**
: A model that returns typed answers with probabilities over a closed answer space instead of generating text. Jev is the one Interlock uses. See [Concepts](../user-guide/concepts.md).

**ECE, expected calibration error**
: The average absolute gap between mean predicted probability and observed violation rate across ten probability bins, weighted by how many checks fall in each bin.

**Ego**
: The vehicle the policy controls. Facts and the road view are both ego-centered.

**Episode**
: One seeded run of the simulator from reset until termination (a crash) or truncation (60 steps).

**Escalation**
: A step whose top action scored between the two thresholds. The simulator pauses and the operator approves or denies. See [Approval queue](../user-guide/console/approval-queue.md).

**Exchange**
: One request actually sent to Jev, recorded with the action, the constraint ids asked, the raw response, latency and request id. Cache hits produce no exchange. See [Log record](../developer-guide/contracts/log-record.md).

**Facts**
: The structured JSON describing the ego, one candidate action and its consequences, computed in code with units in the field names. Jev judges facts; it never computes them. See [Facts](../developer-guide/backend/facts.md).

**Fallback**
: The decision kind when the top action is a confident violation and a lower-ranked action is confidently safe. That action runs instead. Also the action a denied escalation executes.

**Fired constraint**
: The rule with the highest violation probability on the proposed action. It is the rule the approval card quotes.

**Gap**
: Bumper-to-bumper distance to a neighbouring vehicle in metres: center distance minus the 5 m vehicle length, floored at zero. Vehicles beyond 200 m are reported as absent.

**Ground truth**
: The checker's label for one candidate against one rule: `true`, `false`, or `null` for a free-text rule with no checker.

**Human on the loop**
: The design where the system acts on its own when confident and asks a person only in the uncertain band. See [Concepts](../user-guide/concepts.md).

**Jev**
: TypeSafe's decision model, pinned at `jev-1.13.0`. Interlock asks it one yes/no question per candidate and rule and reads back a probability. See [Jev integration](../developer-guide/backend/jev-integration.md).

**Judge source**
: Where a step's probabilities came from: `live` (at least one API call), `cache` (every answer replayed), or `unavailable` (at least one question could not be answered and was set to 0.5).

**Lane numbering**
: Lanes count from the left starting at 1. In the four-lane demo, lane 1 is the leftmost and lane 4 the rightmost.

**Mock mode**
: `JEV_MODE=mock`: the judge answers only from the cache and marks every miss unavailable, so the shield escalates it. No network is used. See [Troubleshooting](../user-guide/troubleshooting.md).

**Noul**
: Jev's yes/no question type. The answer is a number from 0 to 1, which the shield reads as the probability of violation.

**Operator**
: Whoever answers escalations. The console records `ui`; headless runs use `simulated` (answers from the checkers), `approve` or `deny`. See [Command line](../user-guide/cli.md).

**Policy**
: The Stable-Baselines3 DQN trained on task reward alone. It ranks the five actions by Q-value and knows nothing about rules.

**Preset**
: One of the four built-in rules with a checker: speed limit, lane change gap, left lane for passing, lane closed.

**Q-value**
: The DQN's estimate of return for taking an action in the current state. Candidates are ranked by it, best first.

**Reliability diagram**
: A plot of observed violation rate against mean predicted probability per bin. A calibrated judge sits on the diagonal.

**Replay**
: Streaming a logged JSONL run through the console instead of the live simulator. See [Replay](../user-guide/console/replay.md).

**Run id**
: `<UTC stamp>_seed<N>_on|off`, the name of a run's JSONL file and the key the replay picker shows.

**Seed**
: The integer that fixes the simulator's traffic layout, so the same episode can be driven with the shield off and on.

**Sentences**
: The plain-English rendering of a candidate's facts, generated from the same data Jev receives, shown in the approval card and the inspector.

**Session**
: The server-side object holding the runner, the open escalation, the connected browsers and the replay state. One per process. See [Server and session](../developer-guide/backend/server.md).

**Shadow mode**
: Shield off. Facts, Jev and checkers still run every step and the record is still written, but the policy's top action always executes. Before and after numbers come from the same code path.

**Shield**
: The runtime mechanism that allows, falls back or escalates each proposed action based on the judge's probabilities. Always lowercase; Interlock is the project, the shield is the technique.

**Step**
: One policy decision and one simulator advance, one second of simulated time, one record in the log.

**Task return**
: The sum of highway-env reward over an episode. The shield lowers it; that is the cost of safety.

**Thresholds**
: `t_allow` and `t_block`, defaults 0.2 and 0.8. Below `t_allow` allows, above `t_block` blocks, between them escalates. See [Rules and zones](../user-guide/console/rules-and-zones.md).

**TypeSafe**
: The vendor of Jev. The API key lives in `backend/.env` as `TYPESAFE_API_KEY`.

**Work zone, zone**
: A closed stretch of one lane in absolute road coordinates (`lane`, `start_m`, `end_m`). The default drop places one in lane 3, 120 m ahead, 200 m long.

**Zone lifecycle**
: Dropping a zone adds or re-enables the lane-closed rule; passing the last zone retires it. The rule and the zone are never in force without each other. See [Constraints and checkers](../developer-guide/backend/constraints-and-checkers.md).
