# Evaluation and results

The evaluation answers one question with numbers: what does the shield cost and what does it buy, over the same seeded episodes with the shield off and on. It also measures whether Jev's probabilities deserve to be thresholded.

## Running it

```bash
uv run interlock eval --seeds 0-19 --mode off                 # baseline
uv run interlock eval --seeds 0-19 --mode on                  # default thresholds 0.2 / 0.8
uv run interlock eval --seeds 0-19 --sweep                    # five threshold pairs, shield on
uv run interlock eval --seeds 0-19 --all --concurrency 2      # off, the sweep, then the report
uv run interlock eval --report                                # rebuild the report from the newest runs
```

Every configuration runs each seed as a 60-step episode with the three standing rules (speed limit, lane change gap, left lane for passing). Escalations are answered by the **simulated operator**, which approves when the ground-truth checkers say the proposed action is fine and denies otherwise. Unknown labels are denied. When no candidate is confidently safe, it overrides with the candidate that breaks the fewest rules, ties going to the policy's ranking. Flags are listed on [Command line](cli.md).

The full `--all` run against live Jev takes about eight minutes at concurrency 2 and costs under a dollar.

### What it writes

| Path | Contents |
| --- | --- |
| `backend/logs/eval/<stamp>_<label>/seedN.jsonl` | one log per seed, same record as the console |
| `backend/logs/eval/<stamp>_<label>/metrics.json` | per-episode metrics, aggregates and calibration for that configuration |
| `internal/eval/latest.json` | the report: newest run per label, before/after, sweep, calibration |
| `internal/plots/before_after.png`, `tradeoff.png`, `calibration.png` | the three plots |

The label encodes the configuration, for example `on_ta0.20_tb0.80` or `off_ta0.20_tb0.80`. The report picks the newest folder per label, so rerunning one configuration replaces only that row. The console's [Metrics tab](console/metrics-tab.md) reads the same report. The file format is on the [Evaluation report](../developer-guide/contracts/eval-report.md) page.

## Results

20 seeds, 60 steps, three standing rules, live Jev 1.13.0, simulated operator. Measured on Oct 16 with the shield as it was before the Oct 17 conflict policy, which escalates instead of executing a last resort when no candidate is confidently safe. The all-blocked column was recomputed from the records on Oct 17, when the metric was found to count only the decision kind and miss denied escalations that ended in the last resort.

### Before and after

| Configuration | Violations per episode | Task return | Crash rate | Steps escalated |
| --- | --- | --- | --- | --- |
| Shield off | 58.1 | 50.7 | 40% | 0% |
| Shield on, 0.2 / 0.8 | 2.65 | 41.4 | 25% | 23.9% |
| Shield on, 0.4 / 0.6 | 1.25 | 42.0 | 40% | 6.6% |

![Rule violations and task return per seed, shield off versus on](../assets/plots/before_after.png)

### By rule

Totals over the 20 episodes, shield off to shield on at the default thresholds:

| Rule | Off | On |
| --- | --- | --- |
| Speed limit 25 m/s | 1030 | 0 |
| No lane change if a vehicle is within 10 m in the target lane | 124 | 1 |
| Keep the left lane for passing only | 8 | 52 |

### The threshold sweep

| t_allow / t_block | Violations per episode | Return | Crash rate | Escalated | All blocked |
| --- | --- | --- | --- | --- | --- |
| 0.1 / 0.9 | 2.85 | 45.1 | 10% | 49.9% | 28.7% |
| 0.2 / 0.8 | 2.65 | 41.4 | 25% | 23.9% | 5.2% |
| 0.3 / 0.7 | 2.65 | 41.6 | 30% | 18.5% | 5.0% |
| 0.4 / 0.6 | 1.25 | 42.0 | 40% | 6.6% | 1.3% |
| 0.5 / 0.5 | 1.85 | 41.7 | 30% | 0.2% | 0.6% |

![Violations per episode against escalation rate for each threshold pair](../assets/plots/tradeoff.png)

### Calibration

Every candidate action is labeled against every rule on every step, and the report pools the records of every configuration it contains, so the six runs of 20 episodes (shield off plus the five sweep points) yield 93,285 labeled checks, 31,095 per rule.

| Rule | ECE | Accuracy at a 0.5 cut |
| --- | --- | --- |
| All rules | 0.093 | 97.5% |
| Speed limit | 0.059 | 100% |
| Lane change gap | 0.081 | 96.5% |
| Left lane for passing | 0.179 | 95.9% |

Brier score over all checks: 0.032.

![Reliability diagram per rule](../assets/plots/calibration.png)

### Latency and cost

| Measure | Value |
| --- | --- |
| Jev latency per shielded step, p50 | 160 ms |
| Jev latency per shielded step, p95 | 304 ms |
| Cost per episode, shield on | $0.0067 |
| Cost per episode, shield off | $0.0080 |

The shielded run is cheaper because it hit the cache more often.

## How to read the numbers

- **The crisp rules are solved.** The speed limit goes from 1030 violations to 0 and the gap rule from 124 to 1. Jev's probabilities on those rules are bimodal, far below 0.2 or far above 0.8, so the shield rarely has to ask.
- **The fuzzy rule leaks, but not where it looks.** "Keep the left lane for passing only" is the one rule where violations go up, from 8 to 52. The records show that every one of the 52 was an escalation at p 0.54 to 0.80, denied by the simulated operator, in a state where no action satisfied every rule: the car sat in lane 1 with nobody to pass and a vehicle alongside in lane 2, so the only compliant action, LANE_RIGHT, broke the gap rule. The SLOWER last resort changed nothing at the lowest target speed, and the step repeated, 37 times in a row on one seed. Jev's answers had the right sign throughout; the gap was in the shield, which had no policy for a conflict between rules. The Oct 17 conflict policy escalates such steps with every candidate on offer. The passing rule's reliability line is still the weakest of the three, and it is where most escalations come from: a fuzzy rule being the human-on-the-loop moment is the intended design.
- **The knee is 0.4 / 0.6.** It reaches 1.25 violations per episode while escalating only 6.6% of steps. The default 0.2 / 0.8 asks four times as often for a slightly worse violation count, and 5.2% of its steps ended in the last resort, nearly all of them the lane 1 conflict above.
- **The simulated operator is perfect.** It answers from the checkers, so settings that escalate a lot (0.1 / 0.9 at 49.9%) are flattered. A human answering 30 cards a minute will not match it.
- **Crash rate is not a rule.** The shield enforces operator rules, not collision safety. 0.1 / 0.9 has the lowest crash rate because 28.7% of its steps are all-blocked and the car simply drives slower; 0.4 / 0.6 matches the unshielded crash rate. If collisions matter, put a following-distance rule in the set.
- **Return drops by about nine points.** That is the speed reward the speed limit removes. It is the cost of safety and it is visible per seed in the first plot.

## Reproducing

The eval is deterministic in the simulator (seeded) but not in Jev, whose answers vary by a few hundredths between identical requests. Rerunning against the warm cache reproduces the numbers exactly; rerunning with a cleared cache reproduces them closely. Internals are on [Evaluation internals](../developer-guide/backend/evaluation.md).
