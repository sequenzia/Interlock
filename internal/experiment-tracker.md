# Experiment tracker: Weights & Biases

Written Oct 19, 2026. An assessment of adding a hosted experiment tracker,
Weights & Biases, to Interlock, and a plan for doing it. The decision on
Oct 19 was to defer until after the Oct 23 talk. This note holds the
reasoning and the plan so the work can be picked up without re-deriving it.
Nothing here is implemented.

## Verdict

Worth doing after the talk, not before it. The eval harness is where a tracker
pays off; the training loop is where W&B is usually plugged in but matters
little for Interlock. The effort is one focused agent session behind an opt-in
flag. Nothing architectural changes.

## What the project tracks today

Interlock already has a hand-rolled tracker, and it is showing strain.

- `newest_runs` in `backend/evaluate.py` recomputes a config label from each
  run's `metrics.json` and keeps the newest directory per label. Older runs
  under the same label are silently superseded.
- `build_report` aggregates those newest runs into `internal/eval/latest.json`
  and the four PNGs under `internal/plots/`. The console's Metrics tab and the
  slides read from there.
- Comparisons across days live as hand-pasted tables in plan section 10, four
  of them as of Oct 18 (Oct 16, Oct 17, Oct 17 second run, Oct 17 third run,
  plus the Oct 18 baseline block).
- Training writes a `.eval.json` sidecar beside each checkpoint and a plain
  text log under `backend/logs/`. No callbacks, no curves.

| What exists | Count on Oct 19 |
| --- | --- |
| Eval run directories under `backend/logs/eval/` since Oct 16 | 31 |
| Training runs ever | 2 |
| Hand-maintained results tables in the plan | 4 |

## Where a tracker helps

The experiment axis in Interlock is the judge's inputs and the shield's
policy, not the agent. Between runs the agent is frozen and the things that
change are thresholds, the physics floor, the fact schema, rule text and the
state of the Jev cache. A tracker's config filtering and run grouping answer
"which runs used the old fact schema" directly. Today that is a timestamp
lookup against the plan's tables.

Concretely, W&B would give:

- One run per `run_config` call with its config and aggregate metrics, so the
  threshold sweep is a scatter in the UI instead of a regenerated PNG.
- Config diffs between any two runs, including runs the "newest wins" rule
  dropped from `latest.json`.
- Per-seed episode tables and the calibration numbers next to the run that
  produced them.
- A durable home for the logs and plots, beyond the gitignored `backend/logs/`.

## Where it does not help

- Training. The plan says no retraining (section 16.6), there are two
  checkpoints ever, and the 20k against 100k comparison is already a table in
  section 12. The SB3 `WandbCallback` is the textbook integration and the
  least useful one here. Add it only if retraining or agent comparison comes
  back on the table.
- The demo. The console reads `latest.json`; nothing on stage would change.

## Constraints to respect

These come from `CLAUDE.md` and the plan and shape the implementation.

- The headless CLI, the tests, mock mode and the Fly image must keep working
  offline. Tracking is strictly opt-in behind a flag, and the package is
  imported only when the flag is set.
- `latest.json` and the JSONL record stay the contract for console, plots and
  eval. W&B is a second sink, never a replacement, and never feeds a decision.
- `WANDB_API_KEY` joins the other keys in `backend/.env`. Never committed,
  never logged.
- The Dockerfile installs with `uv sync --frozen --no-dev`, which installs only
  the default groups. A separate `track` dependency group keeps W&B and its
  dependency tail (protobuf, sentry-sdk, GitPython, psutil, and more) out of
  the container and the docs runner.
- Ground-truth checkers and hand labels score only. Logging them to W&B is
  fine; nothing read back from W&B may touch the shield.

## Plan

Phases run in order. Each ends with the tests green and the docs page updated
for anything it changed. No day estimates.

| Phase | Work | Done when |
| --- | --- | --- |
| 1 | `interlock eval --list`: walk every `backend/logs/eval/*/metrics.json` and print one row per run with stamp, label, `shield_on`, `t_allow`, `t_block`, `floor_s`, `zone_at_step`, `jev_mode`, seed count, violations per episode, escalation rate, crash rate, mean return, cost per episode and wall seconds. Reuse `config_label`. | Every run directory appears once; the newest row per label matches `latest.json`. No new dependency. |
| 2 | Plumbing: `track = ["wandb", "tensorboard"]` dependency group; `backend/tracking.py` with a lazy import and a no-op path when tracking is off; `--track` flag on `evaluate.command` and `train.command`; `WANDB_API_KEY` read from `backend/.env`; project name `interlock`. | `uv sync --all-groups` installs wandb and `uv sync --no-dev` does not. `uv run pytest` passes with wandb uninstalled. `WANDB_MODE=offline uv run interlock eval --seeds 0-1 --mode on --jev mock --track` writes a run under `wandb/` and the eval output is byte-identical to a run without the flag. |
| 3 | Eval hook. In `run_config`: one W&B run per config, `name` the run directory name, `job_type` `eval`, `config` the report header (`shield_on`, thresholds, `floor_s`, `zone_at_step`, rules, `jev_mode`, model, seeds, concurrency, `max_steps`, git commit, sorted fact field names from the first record as a schema marker), `summary` the flattened aggregate, a `wandb.Table` of per-seed episodes, and `metrics.json` plus the seed JSONL files as an artifact. In `build_report`: a `report` run logging the four PNGs as images and `latest.json` as an artifact. | A scatter of `escalation_rate` against `violations_per_episode` grouped by `floor_s` in the W&B UI reproduces `tradeoff.png`. The three Oct 16 to 18 sweeps are distinguishable by the schema marker. |
| 4 | Training hook, only if retraining is back on the table. `tensorboard_log` in `build_model` when tracking, `wandb.init(sync_tensorboard=True)`, `WandbCallback` from `wandb.integration.sb3` in `model.learn`, the `.eval.json` summary logged and the checkpoint uploaded as an artifact. | A 2k-step smoke run shows `rollout/ep_rew_mean` and `train/loss` curves and the checkpoint lands as an artifact. |
| 5 | Docs: the flag on `docs/user-guide/cli.md` and `docs/user-guide/evaluation.md`, the env key on `docs/reference/configuration.md`, the module on `docs/reference/modules.md`, the commands block in `CLAUDE.md`, a short note in plan section 10. | `uv run mkdocs build --strict` passes. |

Gotchas, both minor. Seeds run concurrently inside one config but one W&B run
per config is right, so no `reinit`. `eval --all` runs configs sequentially in
one process, so `init` and `finish` pairs work as is. Tests run with the flag
off so the package is never imported.

## Lighter alternatives

- Phase 1 alone. The `--list` table gets most of the "what did I run and what
  changed" value with no dependency, no account and no network. It is worth
  doing even if W&B never lands.
- MLflow with a local file store, if a browsable UI without a hosted account
  is wanted. Same hook points as phases 2 and 3; `mlflow ui` over the store
  directory replaces the hosted dashboard. Heavier server, less polished for
  sweeps.

## Decision log

- Oct 19: assessed, deferred to after the talk. Phase 6 of the upgrade plan
  (section 16.6) is a code freeze and the tracker would not appear on stage.
  Pick up with phase 1 when the freeze lifts.
