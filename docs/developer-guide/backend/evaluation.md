# Evaluation internals

Three modules turn JSONL run logs into numbers and figures:

| Module | Role |
| --- | --- |
| `backend/evaluate.py` | Runs seeded episodes under one or more configurations, writes per-run directories, aggregates the newest run per label into a report |
| `backend/metrics.py` | Pure functions over records: per-episode counters, aggregates over seeds, calibration |
| `backend/plots.py` | Matplotlib PNGs from the report |

The design rule is that everything is computed from records only. The console's replay (see [Server and session](server.md)) recomputes the same counters from the same records, so the metrics tab, the headless summary and the report agree by construction. How to run the eval and read the results is in [Evaluation and results](../../user-guide/evaluation.md); the JSON shapes are in [Evaluation report](../contracts/eval-report.md).

## `backend/evaluate.py`

### `run_config(policy, judge, seeds, *, shield_on, thresholds, out_dir, zone_at_step=None, rules=None, concurrency=3, max_steps=None, quiet=False)`

Runs every seed under one configuration and returns the per-configuration report.

- `out_dir` is created. An `asyncio.Semaphore(concurrency)` bounds how many episodes are in flight, which keeps the Jev request rate under the API limit.
- Each seed gets its own `ConstraintStore` seeded with `STANDING_RULES` (the three presets other than `lane_closed`, or the `rules` list), its own `JsonlLogger` at `out_dir/seed<N>.jsonl`, and its own `EpisodeRunner` with `simulated_operator`. `judge` and `policy` are shared across seeds.
- After `runner.run(seed, max_steps, zone_at_step)` the JSONL is read back and `episode_metrics` is computed from it, not from the runner's in-memory totals. A one-line progress row prints unless `quiet`.
- `asyncio.gather` collects `(metrics, records)` per seed. The report holds `label`, `shield_on`, `thresholds`, `zone_at_step`, `seeds`, `jev_mode`, `model` (`DEFAULT_MODEL`), `created`, `wall_seconds`, `episodes`, `aggregate(episodes)` and `calibration(all_records)`, and is written to `out_dir/metrics.json`.

### Labels and directories

`config_label(shield_on, thresholds, zone_at_step)` produces `on_ta0.30_tb0.70`, `off`, or with a zone `on_ta0.30_tb0.70_zone10`; a shield-off label carries no thresholds because they change nothing there. `new_run_dir(root, label)` prefixes a UTC stamp: `backend/logs/eval/2026-10-18T02-06-19_on_ta0.30_tb0.70/`. `newest_runs(root)` globs `*/metrics.json` in sorted order, recomputes each run's label from its `shield_on`, `thresholds` and `zone_at_step` fields rather than reading the stored one, and keeps the last directory per label, so the stamp decides which run is current and an old `off_ta0.20_tb0.80` run counts as `off`.

### `build_report(root, report_path, plots_dir, thresholds)`

Aggregates the newest run per label into `internal/eval/latest.json` and the three plots.

1. Load every newest `metrics.json`.
2. `before_after.on` is the shield-on run without a zone whose label matches the default thresholds, `before_after.off` is the run labeled `off`. Missing ones are `null`.
3. `sweep` is every run with `shield_on` and no zone, reduced to the threshold pair and its aggregate rates, sorted by `t_allow`.
4. `calibration` pools every record of every newest run (all labels, including shield off) through `calibration()`.
5. Plots: `before_after.png` when both default runs exist, `tradeoff.png` when the sweep is non-empty, `calibration.png` when there is at least one labeled check. The `backend.plots` import sits inside this function so matplotlib never loads on the hot path.
6. The report is written with `indent=1` and returned.

### CLI logic

`add_arguments` defines `--seeds` (default `0-19`), `--mode off|on|shadow`, `--t-allow`, `--t-block`, `--sweep`, `--all`, `--report`, `--zone-at-step`, `--jev`, `--concurrency` (3), `--max-steps`, `--model-path`, `--out` (default `backend/logs/eval`).

`run_cli` maps `shadow` to `off` (the judge and checkers run either way, so shadow is only a name) and exits 2 with a hint when none of `--mode`, `--sweep`, `--all` or `--report` is set. `main_async` then:

- With `--report` alone: `build_report(args.out)`, print the run and plot paths, return.
- Otherwise resolve `--jev auto` to live when the key is present, parse seeds with `parse_seed_range` from `backend/train.py`, load the policy once and make one client.
- `--all` queues shield off at the default thresholds followed by the five `SWEEP` pairs `(0.1, 0.9), (0.2, 0.8), (0.3, 0.7), (0.4, 0.6), (0.5, 0.5)`. Without `--all`, `--mode` adds one configuration and `--sweep` adds the five pairs.
- Each configuration runs through `run_config` into a fresh stamped directory and prints `print_summary`.
- `--report` or `--all` finishes with `build_report`.

## `backend/metrics.py`

### Helpers

`_percentile(values, q)` sorts and interpolates linearly between neighbours; empty input gives 0. `executed_candidate(record)` finds the candidate whose `action` equals `record["executed"]`.

### `episode_metrics(records)`

One episode's counters from its records. Raises on an empty list.

| Field | Source |
| --- | --- |
| `run_id`, `seed`, `shield_on`, `thresholds` | The first record |
| `steps` | `len(records)` |
| `return` | Sum of `reward`, rounded to 3 places |
| `crashed` | Any record with `crashed` true |
| `violations` | Per constraint id, counting only the executed candidate's `ground_truth` true checks |
| `violations_total` | Sum of the above |
| `decisions` | Count per `decision` kind |
| `escalations`, `escalation_rate` | `decisions["escalate"]` and that over `steps` |
| `all_blocked` | Records with the `all_blocked` flag set (before Oct 17 this counted the decision kind, which missed denied escalations that ended in the last resort) |
| `conflicts`, `conflict_rate` | Records with `escalation_reason == "no_compliant_action"`, and that count over steps |
| `human` | Count per operator answer where `human` is set |
| `judge_sources` | Count per `judge.source` |
| `live_steps` | Steps whose `judge.source` was `live` |
| `latency_ms_p50`, `latency_ms_p95` | Percentiles over the latencies of live steps only, so cache hits do not drag the numbers down |
| `input_tokens`, `cost_usd` | Sums over `judge` |

Violations are counted on the executed action, never on blocked candidates. A fallback that avoided a violation therefore counts as zero.

### `aggregate(episodes)`

Means and pooled rates over seeds, read by the before/after table and the sweep:

- `violations_per_episode` and `mean_return` with population standard deviations; `violations_per_step` pooled over all steps.
- `violations_by_constraint` summed per id.
- `crash_rate` is the share of episodes that crashed; `mean_steps` the pooled step count per episode.
- `escalation_rate` and `all_blocked_rate` are pooled over steps, not averaged per episode.
- `human` sums approvals and denials.
- `latency_ms_p50` is the median of the per-episode p50s over episodes that had live steps; `latency_ms_p95` is the maximum of the per-episode p95s. Episodes with no live step are excluded from both.
- `cost_usd` and `cost_per_episode_usd`.

### Calibration

`collect_checks(records)` yields `(p, label, checker)` for every candidate and every check with a non-null `ground_truth`, across all five candidates per step. The checker name comes from the record's `constraints` list; a rule without a checker is tagged `free_text` but is already excluded because its label is `None`.

`reliability(checks, bins=10)`:

- Ten equal-width bins over `p`; the last bin also takes `p == 1.0`.
- Per bin: `count`, `mean_p`, `observed` (share of true labels). Empty bins keep `count: 0` with `null` values.
- `ece` is the sum over bins of `(count / n) * |observed - mean_p|`.
- `brier` is the mean squared error of `p` against the 0 or 1 label.
- `accuracy_at_0_5` counts a check as correct when `(p > 0.5) == label`.

`calibration(records, bins=10)` returns `{"overall": reliability(all), "by_checker": {name: reliability(subset)}}` with checkers sorted by name.

!!! note "Five labels per step, per rule"
    Because every candidate gets a label every step, one configuration of 20 episodes of about 52 steps with three rules produces about 15,000 labeled checks, and `build_report` pools every newest run, so the six configurations in the current report give 93,285. That is enough for a reliability diagram with populated bins at both ends.

## `backend/plots.py`

Light-surface figures for the README and the docs, written at 160 dpi with the `Agg` backend selected at import.

| Function | Input | Output |
| --- | --- | --- |
| `plot_before_after(before, after, path)` | The two default `metrics.json` reports | Two stacked bar panels per seed: violations and task return, shield off in orange, shield on in blue, with the aggregate means and crash rates as a caption |
| `plot_tradeoff(sweep, path)` | The `sweep` list | Violations per episode against escalation rate, one annotated point per threshold pair, percent axis |
| `plot_calibration(cal, path)` | The `calibration` object | Reliability diagram with the identity line, the pooled curve dashed and one line per checker labelled with its ECE, plus a histogram of checks per bin |

The palette constants (`SURFACE`, `TEXT`, `GRID`, `SERIES`, `CHECKER_SERIES`) and `CHECKER_LABEL` live at the top of the module. `_style` applies the shared axis treatment: left-aligned title, hidden top and right spines, horizontal grid only.

The three PNGs land in `internal/plots/` and are copied into these docs under `assets/plots/` for the results page.
