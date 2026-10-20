# Evaluation report

The eval harness writes three kinds of JSON. All of them are plain outputs of `backend/evaluate.py`, `backend/metrics.py` and `backend/train.py`, and all of them are computed from the JSONL [log record](log-record.md) alone. The computation is described in [Evaluation internals](../backend/evaluation.md).

| File | Written by | Read by |
| --- | --- | --- |
| `backend/logs/eval/<stamp>_<label>/metrics.json` | `run_config` | `build_report` |
| `internal/eval/latest.json` | `build_report` | `GET /eval/latest`, the metrics tab |
| `models/<checkpoint>.eval.json` | `train.run_cli` | People choosing a checkpoint |

## Per-configuration `metrics.json`

One per run directory. The label encodes the configuration: `on_ta0.30_tb0.70`, `off`, `on_ta0.30_tb0.70_nofloor` when the physics floor was off, `on_ta0.30_tb0.70_floor1` for a non-default floor, or `on_ta0.30_tb0.70_zone10` with a zone drop. `metrics.json` carries `floor_s`; a run without that field predates the floor and is read as `_nofloor`. A shield-off label carries no thresholds because they change nothing with the shield off; runs written before Oct 17 stored `off_ta0.20_tb0.80`, which the report reads as `off`.

| Field | Type | Meaning |
| --- | --- | --- |
| `label` | string | `config_label` output |
| `shield_on` | bool | |
| `thresholds` | `{t_allow, t_block}` | |
| `zone_at_step` | int or null | |
| `seeds` | int[] | Seeds in the run |
| `jev_mode` | `"live"` or `"mock"` | |
| `model` | string | The pinned Jev model id |
| `created` | ISO 8601 UTC | |
| `wall_seconds` | number | Wall-clock for the whole configuration |
| `episodes` | object[] | One `episode_metrics` per seed |
| `aggregate` | object | `aggregate(episodes)` |
| `calibration` | object | `calibration(all records of this run)` |

### `episodes[]` entry

| Field | Type | Meaning |
| --- | --- | --- |
| `run_id` | string | `<stamp>_seed<N>_on|off` |
| `seed` | int | |
| `shield_on` | bool | |
| `thresholds` | object | |
| `steps` | int | Records in the episode |
| `return` | number | Sum of per-step reward, 3 decimals |
| `crashed` | bool | |
| `violations` | `{constraint_id: int}` | Executed-action violations per rule |
| `violations_total` | int | |
| `decisions` | `{kind: int}` | Counts of `allow`, `fallback`, `escalate`; `all_blocked` appears only for logs written before Oct 17 |
| `escalations` | int | |
| `escalation_rate` | number | `escalations / steps` |
| `all_blocked` | int | Records whose `all_blocked` flag is set: an executed last resort after a deny or a timeout |
| `conflicts` | int | Records with `escalation_reason == "no_compliant_action"`; 0 for logs written before Oct 17, which have no reason field |
| `conflict_rate` | number | `conflicts / steps` |
| `human` | `{approve: int, deny: int, override: int}` | Simulated operator answers; only keys that occurred are present per episode |
| `judge_sources` | `{live, cache, unavailable: int}` | Step-level judge source counts |
| `live_steps` | int | Steps with `judge.source == "live"` |
| `latency_ms_p50`, `latency_ms_p95` | number | Over live steps only |
| `input_tokens` | int | |
| `cost_usd` | number | 6 decimals |

Example (seed 0, shield on, default thresholds):

```json
{
  "run_id": "2026-10-16T23-15-42_seed0_on", "seed": 0, "shield_on": true,
  "thresholds": {"t_allow": 0.2, "t_block": 0.8},
  "steps": 60, "return": 48.376, "crashed": false,
  "violations": {}, "violations_total": 0,
  "decisions": {"fallback": 23, "allow": 28, "escalate": 9},
  "escalations": 9, "escalation_rate": 0.15, "all_blocked": 0,
  "human": {"deny": 7, "approve": 2},
  "judge_sources": {"cache": 11, "live": 49}, "live_steps": 49,
  "latency_ms_p50": 148.0, "latency_ms_p95": 233.8,
  "input_tokens": 113142, "cost_usd": 0.004752
}
```

### `aggregate`

| Field | Meaning |
| --- | --- |
| `episodes`, `steps` | Counts |
| `violations_per_episode`, `violations_per_episode_std` | Mean and population std over seeds |
| `violations_per_step` | Pooled |
| `violations_by_constraint` | `{constraint_id: int}` summed over seeds |
| `mean_return`, `mean_return_std` | |
| `crash_rate` | Share of episodes that crashed |
| `mean_steps` | |
| `escalation_rate`, `all_blocked_rate`, `conflict_rate` | Pooled over steps |
| `human` | `{approve, deny, override}` summed |
| `live_steps` | |
| `latency_ms_p50` | Median of per-episode p50s over episodes with live steps |
| `latency_ms_p95` | Max of per-episode p95s |
| `cost_usd`, `cost_per_episode_usd` | |

### `calibration`

```json
{
  "overall": {"n": 169500, "positives": 28040, "bins": [...], "ece": 0.0839, "brier": 0.0281, "accuracy_at_0_5": 0.9735},
  "by_checker": {"lane_change_gap": {...}, "left_lane_passing": {...}, "speed_limit": {...}}
}
```

Each reliability object has `n`, `positives`, ten `bins`, `ece`, `brier` and `accuracy_at_0_5`, and each `by_checker` entry also has `label_source`: `"checker"` for a rule scored in code, otherwise the labeler named on the label rows, `"human"` from `interlock label` or `"autolabel"` from `interlock autolabel`, joined with a plus sign when both labeled the rule. The keys of `by_checker` are checker ids for crisp rules and preset ids (or a slug of the rule text) for rules without a checker; a rule with neither checker nor labels does not appear. A bin is `{lo, hi, count, mean_p, observed}`; an empty bin has `count: 0` and `null` for the two means. Two real bins from the pooled report:

```json
{"lo": 0.0, "hi": 0.1, "count": 9061, "mean_p": 0.0502, "observed": 0.0}
{"lo": 0.9, "hi": 1.0, "count": 945,  "mean_p": 0.9374, "observed": 1.0}
```

## `internal/eval/latest.json`

The report `build_report` writes from the newest run per label.

| Field | Type | Meaning |
| --- | --- | --- |
| `generated_at` | ISO 8601 UTC | |
| `thresholds_default` | `{t_allow, t_block}` | The pair that selects `before_after.on` |
| `runs` | `{label: directory}` | Which run directory fed each label |
| `before_after.off`, `before_after.on` | full `metrics.json` or null | `on` is the shield-on run without a zone at the default thresholds; `off` is the newest shield-off run without a zone |
| `sweep` | object[] | One point per shield-on run without a zone at the default floor, sorted by `t_allow` |
| `floor` | `{floor_s, rows}` | One row per threshold pair that was run with more than one floor: `t_allow`, `t_block` and `by_floor`, keyed by the floor in seconds as text (`"0"`, `"1"`, `"2"`), each `{label, crash_rate, violations_per_episode, mean_return, escalation_rate, floored_rate, floor_all_rate}` |
| `baseline` | object or null | The contents of `internal/eval/baseline.json` when `interlock baseline` has run: `checks`, `strata`, `jev` and `models`, each judge with `overall` and `by_group` reliability plus latency, tokens and cost for the chat models. See [Chat-LLM baseline](../../user-guide/evaluation.md#chat-llm-baseline) |
| `calibration` | object | Pooled over the records of the shield-off runs and the shield-on runs at the default floor |
| `plots` | `{before_after, tradeoff, calibration, baseline: path}` | Only the figures that could be drawn |

### `sweep[]` entry

```json
{
  "label": "on_ta0.20_tb0.80", "t_allow": 0.2, "t_block": 0.8,
  "violations_per_episode": 2.3, "escalation_rate": 0.4556, "all_blocked_rate": 0.0,
  "conflict_rate": 0.044, "floored_rate": 0.0,
  "crash_rate": 0.05, "mean_return": 44.035, "cost_per_episode_usd": 0.007255,
  "human": {"approve": 219, "deny": 268, "override": 41}
}
```

`build_report` recomputes `episodes`, `aggregate` and `calibration` from the
run's `seed*.jsonl` files and rewrites its `metrics.json` before aggregating,
so a change in `metrics.py` reaches old runs with `interlock eval --report`
and no Jev cost. The record is the source of truth; `metrics.json` is a
cache of it.

## `GET /eval/latest`

The server reads the file on every request:

```json
{"available": true, "generated_at": "...", "thresholds_default": {...}, "runs": {...}, "before_after": {...}, "sweep": [...], "calibration": {...}, "plots": {...}}
```

When the file is missing:

```json
{"available": false, "message": "run: uv run python -m backend.evaluate --seeds 0-19 --all"}
```

The console shows that message in the metrics tab. In the container the file is copied in at build time, so it reflects the last eval before the image was built.

## The TypeScript mirror

`frontend/src/types.ts` declares the subset the metrics tab needs:

| Type | Fields used |
| --- | --- |
| `EpisodeMetrics` | `seed`, `steps`, `return`, `crashed`, `violations_total`, `escalations`, `all_blocked` |
| `AggregateMetrics` | `episodes`, `steps`, `violations_per_episode` and `_std`, `violations_by_constraint`, `mean_return`, `crash_rate`, `escalation_rate`, `all_blocked_rate`, `human`, `latency_ms_p50`, `latency_ms_p95`, `cost_usd`, `cost_per_episode_usd` |
| `RunReport` | `label`, `shield_on`, `thresholds`, `seeds`, `jev_mode`, `created`, `episodes`, `aggregate` |
| `SweepPoint` | Everything in the sweep entry except `human` and `conflict_rate` |
| `ReliabilityBin`, `Reliability` | As above |
| `EvalReport` | `available`, `message?`, `generated_at?`, `thresholds_default?`, `before_after?`, `sweep?`, `calibration?` |

`MetricsView` reads: the five aggregate tiles (`violations_per_episode`, `mean_return`, `crash_rate`, `escalation_rate`, `cost_per_episode_usd`) off and on; per-seed `violations_total` and `return` for the two bar charts; the sweep for the tradeoff scatter; `calibration.overall` and the three known checkers for the reliability lines; and in the footer `latency_ms_p50`, `latency_ms_p95` and `human` from the shield-on aggregate. Fields outside this list can change without touching the frontend; fields inside it must change in `types.ts` too.

## Per-checkpoint `.eval.json`

`interlock train` writes `<checkpoint>.eval.json` beside the checkpoint:

```json
{
  "model": ".../models/dqn_highway_100k.zip",
  "episodes": 20, "mean_return": 50.732, "crash_rate": 0.4,
  "mean_speed_mps": 29.77, "mean_steps": 52.0,
  "per_episode": [{"seed": 0, "return": 59.394, "crashed": false, "mean_speed_mps": 29.99, "steps": 60}, ...]
}
```

These are greedy rollouts with no shield and no rules, so `mean_return` here matches the shield-off `mean_return` in the eval only when both use the same seeds and checkpoint. See [Training and policy](../backend/training.md).
