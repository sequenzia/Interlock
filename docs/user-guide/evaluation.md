# Evaluation and results

The evaluation answers one question with numbers: what does the shield cost and what does it buy, over the same seeded episodes with the shield off and on. It also measures whether Jev's probabilities deserve to be thresholded.

## Running it

```bash
uv run interlock eval --seeds 0-19 --mode off                 # baseline
uv run interlock eval --seeds 0-19 --mode on                  # default thresholds 0.3 / 0.7
uv run interlock eval --seeds 0-19 --sweep                    # five threshold pairs, shield on
uv run interlock eval --seeds 0-19 --all --concurrency 2      # off, the sweep, then the report
uv run interlock eval --report                                # rebuild the report from the newest runs
```

Every configuration runs each seed as a 60-step episode with the seven standing rules: every preset except the lane-closed one, which only arrives with a zone. Since Oct 17 that is the speed limit, the lane change gap, the left lane for passing, the 2 second headway, one lane change per 10 seconds, and the two fuzzy presets about moving in ahead of a faster vehicle and driving conservatively in dense traffic. Escalations are answered by the **simulated operator**, which approves when the ground-truth checkers say the proposed action is fine and denies otherwise. Unknown labels are denied. When no candidate is confidently safe, it overrides with the candidate that breaks the fewest rules, ties going to the policy's ranking. Flags are listed on [Command line](cli.md).

The full `--all` run against live Jev takes about eight minutes at concurrency 2 and costs under a dollar.

### What it writes

| Path | Contents |
| --- | --- |
| `backend/logs/eval/<stamp>_<label>/seedN.jsonl` | one log per seed, same record as the console |
| `backend/logs/eval/<stamp>_<label>/metrics.json` | per-episode metrics, aggregates and calibration for that configuration |
| `internal/eval/latest.json` | the report: newest run per label, before/after, sweep, calibration |
| `internal/plots/before_after.png`, `tradeoff.png`, `calibration.png` | the three plots |

The label encodes the configuration, for example `on_ta0.30_tb0.70` or `off`; the shield-off label carries no thresholds because they change nothing when the shield is off. The report picks the newest folder per label, so rerunning one configuration replaces only that row. The before and after pair is the shield-on run at the default thresholds against the newest shield-off run. The console's [Metrics tab](console/metrics-tab.md) reads the same report. The file format is on the [Evaluation report](../developer-guide/contracts/eval-report.md) page.

### Hand labels for the fuzzy rules

The two fuzzy presets have no checker, so nothing in code can say whether Jev was right about them. `interlock label` fills that gap with your judgment:

```bash
uv run interlock label --run backend/logs/eval/<stamp>_on_ta0.30_tb0.70 --rule dense_traffic --sample 100
uv run interlock label --run backend/logs/eval/<stamp>_on_ta0.30_tb0.70 --rule cut_in --sample 100
uv run interlock eval --report
```

Each card shows a step's candidate action and the facts as sentences, with Jev's probability hidden, and takes `y`, `n`, `s` or `q`. The sampler spreads the cards across the range of Jev's probability so the reliability line gets points in every bin. Labels accumulate under `backend/logs/labels/`, keyed by the facts and the rule text, and `eval --report` folds them into the calibration with no Jev cost: the fuzzy rules then appear in the reliability diagram and the metrics tab marked with their labeler, "labels: human". A few hundred labels per rule is enough for a readable line. Flags are on [Command line](cli.md#interlock-label).

The labels behind the results below were not collected by hand. On Oct 19 Claude (Fable 5.1) pinned the guide's standard into [`interlock autolabel`](cli.md#interlock-autolabel) and ran it over every distinct state in the calibration pool instead of a sample: 19,067 states per rule, with 24 per rule skipped where a value sat within 1 m or 0.5 s of a threshold. Dense means four or more vehicles within 50 m. When it is dense, FASTER breaks the rule; a lane change breaks it when either gap in the new lane is under 15 m or it leaves under 2 s of headway or under 5 s to collision; IDLE breaks it when it leaves under 2 s of headway or under 5 s to collision while SLOWER was available; SLOWER complies. A cut-in violation is a real lane change with a faster vehicle behind in the new lane under 15 m away, or while tailgated. Every row under `backend/logs/labels/` carries `labeler: autolabel`, the files are committed so the numbers below are reproducible, and the plot and the Metrics tab show that labeler as the rule's label source.

## Chat-LLM baseline

`interlock baseline` asks ordinary chat models the judge's own questions, so the report can show whether a decision model earns its place. It samples labeled checks from the newest eval runs, spread evenly over rule and label, sends each model the identical facts JSON and question text and asks for one probability as a structured JSON object, with thinking left at the model's default, and scores every judge with the same reliability code. Jev's answers for the same checks come from the logs, so including it costs nothing.

```bash
uv run interlock baseline --dry-run                                    # sample, print one request, send nothing
uv run interlock baseline --checks 2000 --models claude-haiku-5-5,claude-sonnet-5-5
uv run interlock baseline --prices other.json                          # prices from another file
uv run interlock eval --report                                         # fold baseline.json into the report
```

The key is `ANTHROPIC_API_KEY` in `backend/.env`, gitignored and never logged; a key that is not scoped to a workspace also needs `ANTHROPIC_WORKSPACE_ID` there, which goes out as the `anthropic-workspace-id` header. A bad key, a missing workspace or an unknown model id stops the run on the first call; transient failures are counted and the run goes on, as is a reply cut off at the token cap or stopped by a refusal, whose tokens still count toward cost. Prices are never hardcoded: copy `backend/prices.example.json` to `backend/prices.json`, gitignored, and fill in the USD per million tokens from the pricing page; the command reads it when it exists, or another file through `--prices`. Without one the report shows tokens and no cost, and a blank entry is an error rather than a free run. Replies are cached under `backend/logs/baseline_cache.jsonl`, so a re-run with the same sample is free. The block lands in `internal/eval/baseline.json`; the report reads it into `baseline`, draws `baseline.png`, and the [Metrics tab](console/metrics-tab.md) shows Jev's reliability line next to one per model. Flags are on [Command line](cli.md#interlock-baseline).

## Results

20 seeds, 60 steps, the seven standing rules, live Jev 1.13.0, simulated operator. Measured on Oct 17 with the conflict policy, the operator override, the wider fact schema, the lane-change count fact and the 2 second physics floor in place. This third Oct 17 sweep took about two minutes and cost under two cents: almost every state had been judged in the earlier sweeps, so the answers came from the cache. The Oct 16 results with three rules are kept in the plan for comparison.

### Before and after

| Configuration | Violations per episode | Task return | Crash rate | Steps escalated |
| --- | --- | --- | --- | --- |
| Shield off | 105.45 | 50.7 | 40% | 0.0% |
| Shield on, 0.2 / 0.8 | 3.45 | 45.7 | 0% | 48.2% |
| Shield on, 0.3 / 0.7 (default) | 3.55 | 46.0 | 0% | 16.5% |

![Rule violations and task return per seed, shield off versus on](../assets/plots/before_after.png)

### By rule

Totals over the 20 episodes, shield off to shield on at the default thresholds, 0.3 / 0.7:

| Rule | Off | On |
| --- | --- | --- |
| Speed limit 25 m/s | 1030 | 0 |
| No lane change if a vehicle is within 10 m in the target lane | 124 | 1 |
| Keep the left lane for passing only | 8 | 0 |
| Keep at least 2 seconds of headway to the vehicle ahead | 647 | 65 |
| At most 1 lane change in any 10 seconds | 300 | 5 |

The two fuzzy presets have no checker and therefore no violation count. Their calibration comes from the labels described above and is read under [Calibration](#calibration). Headway was 43 before the physics floor: the floor keeps the car out of lane changes into closing gaps, so it follows slow traffic more often. The floor section below has the comparison.

### The threshold sweep

| t_allow / t_block | Violations per episode | Return | Crash rate | Escalated | Conflicts | Overrides | Steps floored |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0.1 / 0.9 | 3.55 | 46.0 | 0% | 89.3% | 63.7% | 627 | 12.9% |
| 0.2 / 0.8 | 3.45 | 45.7 | 0% | 48.2% | 6.2% | 46 | 10.8% |
| 0.3 / 0.7 (default) | 3.55 | 46.0 | 0% | 16.5% | 6.2% | 44 | 11.6% |
| 0.4 / 0.6 | 3.55 | 45.8 | 0% | 11.6% | 6.0% | 42 | 11.7% |
| 0.5 / 0.5 | 3.55 | 43.6 | 5% | 6.5% | 5.9% | 40 | 11.0% |

"Conflicts" is the share of steps escalated because no candidate was confidently safe, "overrides" counts the simulated operator choosing a candidate other than the proposal on those steps, and "steps floored" is the share of steps on which the physics floor removed at least one candidate. No step in any configuration ended in the SLOWER last resort, and the floor never removed every candidate.

![Violations per episode against escalation rate for each threshold pair](../assets/plots/tradeoff.png)

### The physics floor

The floor removes any candidate whose time to collision ahead after the action is under the floor before the rules are judged. Every pair was run without it, at 1 s and at 2 s; the default pair and 0.5 / 0.5 also at 3 s.

| t_allow / t_block | Floor | Crash rate | Violations per episode | Return | Escalated | Steps floored |
| --- | --- | --- | --- | --- | --- | --- |
| 0.1 / 0.9 | off | 5% | 2.40 | 44.4 | 89.0% | 0% |
| 0.1 / 0.9 | 1 s | 5% | 2.40 | 44.4 | 89.0% | 6.6% |
| 0.1 / 0.9 | 2 s | 0% | 3.55 | 46.0 | 89.3% | 12.9% |
| 0.2 / 0.8 | off | 5% | 2.30 | 44.1 | 46.8% | 0% |
| 0.2 / 0.8 | 1 s | 5% | 2.30 | 44.1 | 46.8% | 5.8% |
| 0.2 / 0.8 | 2 s | 0% | 3.45 | 45.7 | 48.2% | 10.8% |
| 0.3 / 0.7 | off | 5% | 2.40 | 44.4 | 14.1% | 0% |
| 0.3 / 0.7 | 1 s | 5% | 2.40 | 44.4 | 14.1% | 6.0% |
| 0.3 / 0.7 | 2 s | 0% | 3.55 | 46.0 | 16.5% | 11.6% |
| 0.3 / 0.7 | 3 s | 0% | 2.75 | 46.0 | 14.9% | 15.0% |
| 0.4 / 0.6 | off | 5% | 2.40 | 44.2 | 9.8% | 0% |
| 0.4 / 0.6 | 1 s | 5% | 2.40 | 44.2 | 9.8% | 5.7% |
| 0.4 / 0.6 | 2 s | 0% | 3.55 | 45.8 | 11.6% | 11.7% |
| 0.5 / 0.5 | off | 10% | 2.40 | 42.1 | 4.7% | 0% |
| 0.5 / 0.5 | 1 s | 10% | 2.40 | 42.1 | 4.7% | 5.9% |
| 0.5 / 0.5 | 2 s | 5% | 3.55 | 43.6 | 6.5% | 11.0% |
| 0.5 / 0.5 | 3 s | 10% | 2.65 | 42.3 | 5.1% | 14.0% |

At 1 s the floor removed a candidate on 6% of steps and changed nothing: never the one that would have run. A step is one second, so a 1 s floor fires on the last step, when only SLOWER is left and it cannot shed enough speed in time. The one shielded crash on 20 seeds was exactly that: the gap ahead closed 14, 10, 6, 1 metres over four steps while IDLE ran twice at 2.3 s and 1.3 s to collision, and the operator's rule-driven override had no reason to prefer SLOWER. At 2 s the floor fires one step earlier and that crash is gone at every pair. The crash left at 0.5 / 0.5 is a lane change into a vehicle alongside, with 0 m behind in the target lane and 22 s to collision ahead; a floor that reads time to collision ahead cannot see it, and at 0.5 / 0.5 the gap rule's probability fell on the wrong side of the single cut. 3 s floors 15% of steps for no further gain and crashed on the same seed at 0.5 / 0.5 by a different path. The floor costs rule compliance: headway violations rise from 43 to 65 per 20 episodes because the car follows slow traffic instead of changing lanes into closing gaps. Return rises because no episode ends early.

### Calibration

Every candidate action is labeled against every rule on every step, by a checker for the five crisp rules and by the labels above for the two fuzzy ones, and the report pools the records of the shield-off run and the five sweep runs at the default floor: 244,393 labeled checks, 34,925 per crisp rule and 34,885 and 34,883 for the two fuzzy rules after the skips. Runs at other floors are left out because they repeat the same states with the same cached answers.

| Rule | ECE | Accuracy at a 0.5 cut |
| --- | --- | --- |
| All rules | 0.101 | 94.6% |
| Speed limit | 0.056 | 100.0% |
| One lane change per 10 s | 0.084 | 100.0% |
| Lane change gap | 0.064 | 97.9% |
| Headway 2 s | 0.110 | 98.8% |
| Left lane for passing | 0.174 | 96.9% |
| Conservative in dense traffic | 0.110 | 79.1% |
| Room when moving in | 0.221 | 89.4% |

Brier score over all checks: 0.049; over the five crisp rules alone it stays at 0.024, ECE 0.095 and accuracy 98.7%, unchanged from Oct 17.

The two fuzzy rules read differently from the rest. Dense traffic is monotone up to about 0.8 and then falls back to 0.63 in the top bin. The 754 compliant checks that Jev scores at 0.8 or above all have exactly three vehicles within 50 m, one short of the labeling standard's four, so Jev's idea of dense is a little wider than the labeler's; at a three-vehicle cut those bins would read 0.91 to 0.96. Cut-in never rises above an observed 6% in any bin while Jev spreads its probability up to 0.8. Its mean probability on a lane change is about the same whether the vehicle behind is faster or slower and whether the gap is under 14 m or over 16 m, and only 6% of the 487 labeled violations score above 0.5, so the number does not track the two facts that decide the rule. A judge that always answered no would score 98.6% on that rule at the 0.5 cut. The shield-off car never meets the rule's precondition, because at 30 m/s it is the fastest vehicle on the road; every cut-in violation comes from a shielded run, where the speed limit puts faster traffic behind the car.

![Reliability diagram per rule](../assets/plots/calibration.png)

### Latency and cost

| Measure | Value |
| --- | --- |
| Jev latency per shielded step, p50 | 158 ms |
| Jev latency per shielded step, p95 | 293 ms |
| Cost per episode, shield on | $0.0051 |
| Cost per episode, shield off | $0.0132 |

These are the cold-cache figures from the first Oct 17 sweep. The later sweeps hit the cache on nearly every step, so their latency and cost say more about the cache than about Jev; the floor sweep had 42 live steps out of 1,200 at the default pair. The shielded run is cheaper on a cold cache because it visits fewer distinct states.

### Jev against chat models

`interlock baseline` put 2,000 of the logged checks, 200 violations and 200 compliant checks per scored rule, to Claude Haiku 5.5 and Claude Sonnet 5.5 with the judge's own question text and facts JSON, one check per call, thinking left at each model's default. Jev's answers for the same checks come from the logs. Measured on Oct 18; no call failed.

| Judge | ECE | Brier | Accuracy at a 0.5 cut |
| --- | --- | --- | --- |
| Jev, from the logs | 0.139 | 0.046 | 97.9% |
| Claude Haiku 5.5 | 0.080 | 0.029 | 96.8% |
| Claude Sonnet 5.5 | 0.060 | 0.015 | 98.8% |

Both chat models are better calibrated than Jev on this sample, and Sonnet is more accurate. The sample is half violations, which weighs the side where Jev is underconfident: its checks near p 0.56 to 0.64 are violations 91% to 99% of the time, where a calibrated judge would say 0.9. On the pooled calibration above, where most checks are compliant, Jev's ECE is 0.095.

What the default 0.3 / 0.7 band would have done with the same 2,000 checks:

| Judge | Violations allowed | Compliant checks blocked | Checks escalated |
| --- | --- | --- | --- |
| Jev | 0 | 0 | 412 (20.6%) |
| Claude Haiku 5.5 | 24 | 2 | 86 (4.3%) |
| Claude Sonnet 5.5 | 3 | 5 | 63 (3.1%) |

Jev's underconfidence lands inside the band, so it turns into a question for the operator rather than an allowed action. The chat models' errors land outside it: Haiku would have allowed 16 passing-rule and 6 gap-rule violations, Sonnet 3, and both would have blocked a few compliant actions. Per rule, Jev escalated 236 of the 400 passing-rule checks, the rule the spike found it least sure about.

Latency and cost are the other half. One chat-model check took about 1.1 s at the median and 2.5 to 2.7 s at p95, against 158 ms for Jev's full step of five requests covering 35 checks. Even with every check of a step in flight at once, a chat-model shield would wait on its slowest call. Haiku's 2,000 checks cost $0.31 with about 124 output tokens of thinking per check; Sonnet's cost $4.19 with about 24. At those rates a 60-step episode of 2,100 checks, one call each, would cost about $0.33 with Haiku and $4.40 with Sonnet, against $0.0051 for Jev from a cold cache.

![Reliability diagram, Jev against chat models on the same checks](../assets/plots/baseline.png)

## How to read the numbers

- **Five of five scored rules are enforced.** The speed limit goes from 1030 violations to 0, the gap rule from 124 to 1, the lane-change rate from 300 to 5, and the headway rule from 647 to 65. Headway is the one that still leaks, because traffic can close a 2 second gap faster than one action can reopen it, and the physics floor adds to it by keeping the car behind slow traffic.
- **The passing-rule leak is gone.** On Oct 16 the shield turned 8 violations into 52 by looping on a no-op last resort in states where no action satisfied every rule. With the conflict policy those states escalate, the operator picks a way out, and the count is 0.
- **The crash rate fell from 40% to 0%.** The headway rule took it to 5% on its own: a following-distance rule is what the Oct 16 reading said was missing, and the least-bad fallback no longer slams the car into SLOWER when the policy wanted a lane change. The 2 s physics floor removed the last crash, a rear-end that the rule-driven operator approved into. The rules still enforce rules; the floor is the only part of the shield that reads physics, and it reads one dimension of it.
- **The thresholds now trade operator load, not violations.** From 7% of steps escalated at 0.5 / 0.5 to 89% at 0.1 / 0.9 the violations stay between 3.45 and 3.55 per episode. Every uncertain or conflicting step reaches a decision maker at any pair; the pair only decides whether that is the judge alone or the operator. 0.5 / 0.5 has no band at all and the one crash the floor cannot see.
- **The default moved from 0.2 / 0.8 to 0.3 / 0.7.** Escalation at 0.2 / 0.8 doubled from the three-rule run, because seven rules put more steps inside the band and because conflicts escalate instead of running a silent last resort. The narrower band asks on 16.5% of steps instead of 48.2% for the same violations and crash rate, so it is the default since Oct 17. At 0.1 / 0.9 almost every step is a conflict, which is the simulated operator doing the driving.
- **One fact fixed the lane-change rate rule.** In the first Oct 17 sweep the facts gave the count so far and the judge had to add this action and compare, which is the counting its documentation warns about: p 0.2 to 0.3 was a violation 95% of the time and accuracy at a 0.5 cut was 94.0%. With `lane_changes_last_10_steps_including_this_action` on every real lane-change candidate the judge reads one number against the rule's. Now every check below 0.3 is a compliance, every check above 0.5 a violation, nothing lands between, and accuracy is 100%. It is still underconfident in size, p 0.6 to 0.9 where the observed rate is 1.0, which is what keeps that rule's ECE at 0.083 and nudged the pooled ECE up from 0.084 while the Brier score and accuracy improved. In the second sweep the same change moved the 0.5 / 0.5 point: it used to wave those second lane changes through at p 0.2 and then blocked them, so its rate violations fell from 9 to 4 and its headway violations rose from 21 to 42, because the car stays behind slow traffic. The headway rule shows the old shape more mildly.
- **The physics floor is a one-dimensional safety net and that is the point.** It reads one fact, time to collision ahead, it is set at launch, and no rule can type it away. At 2 s it removed the only rear-end on 20 seeds and cost 22 headway violations and a little operator load. It does not see a vehicle alongside during a lane change; that is the gap rule's job, and at 0.5 / 0.5 the judge got one such call wrong.
- **The simulated operator is perfect.** It answers from the checkers, so the high-escalation settings are flattered, and its 627 overrides at 0.1 / 0.9 are not something a person would match.
- **A chat model can be better calibrated and still a worse shield.** On 2,000 balanced checks Sonnet 5.5 beat Jev on ECE, Brier and accuracy, yet at the default band it would have allowed 3 violations and blocked 5 compliant actions where Jev allowed and blocked none, because Jev's errors are underconfidence and the band catches them. Jev pays with operator load, 20.6% of checks escalated against 3.1%. The chat model pays with about a second per check against 158 ms per step, and an episode would cost about 65 times as much with Haiku and 860 times with Sonnet.
- **The fuzzy rules are where the judge is weakest, in two different ways.** Dense traffic calibrates about as well as the headway rule up to 0.8, and its top-bin miss is a one-vehicle disagreement about what dense means. Cut-in is the rule Jev cannot score on this road: a lane change with a faster vehicle 5 m behind gets about the same probability as one with nobody behind, and at the default band 112 of the 487 labeled violations would have run on this rule alone while 345 compliant checks sat above the block threshold. The band does not hide a judge that is uninformative, only one that is underconfident.
- **Return drops by about five points.** Less than the nine of the three-rule run, because the override keeps the car moving where SLOWER used to stall it, and less than the six before the floor, because no shielded episode ends in a crash.

## Reproducing

The eval is deterministic in the simulator (seeded) but not in Jev, whose answers vary by a few hundredths between identical requests. Rerunning against the warm cache reproduces the numbers exactly; rerunning with a cleared cache reproduces them closely. Internals are on [Evaluation internals](../developer-guide/backend/evaluation.md).
