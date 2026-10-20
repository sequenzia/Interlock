# Command line

`interlock` is one command with eight subcommands, built on [Typer](https://typer.tiangolo.com). `uv sync` installs it into the project environment, so it runs as `uv run interlock ...`, or as plain `interlock` once `.venv/bin` is on your `PATH`.

```bash
uv run interlock --help
uv run interlock run --help
uv run interlock run -h                  # the same
uv run interlock --install-completion    # tab completion for the current shell
```

Every subcommand except `console` is a thin wrapper over a module in `backend/`, and the module runs standalone with the same flags:

| Subcommand | Module | Equivalent |
| --- | --- | --- |
| `run` | `backend/run_episode.py` | `uv run python -m backend.run_episode` |
| `eval` | `backend/evaluate.py` | `uv run python -m backend.evaluate` |
| `train` | `backend/train.py` | `uv run python -m backend.train` |
| `spike` | `backend/spike/jev_spike.py` | `uv run python -m backend.spike.jev_spike` |
| `label` | `backend/label.py` | `uv run python -m backend.label` |
| `autolabel` | `backend/autolabel.py` | `uv run python -m backend.autolabel` |
| `baseline` | `backend/baseline_llm.py` | `uv run python -m backend.baseline_llm` |
| `console` | `backend/cli.py` | none; it starts uvicorn and Vite as children |

How the dispatcher works is on [CLI internals](../developer-guide/backend/cli.md).

## Jev mode

`run`, `eval` and `console` take `--jev auto|live|mock`. `auto`, the default, is live when `TYPESAFE_API_KEY` is set in `backend/.env` and mock otherwise. Mock mode serves the cache and escalates anything unseen; see [Concepts](concepts.md).

## interlock run

One headless episode, shield on or off, printed step by step and logged as JSONL. The [Quickstart](quickstart.md) explains the per-step line.

```bash
uv run interlock run --shield on
uv run interlock run --shield off --seed 3
uv run interlock run --jev mock --zone-at-step 10
uv run interlock run --rules speed_limit --operator approve --max-steps 20
```

| Flag | Default | Meaning |
| --- | --- | --- |
| `--shield on|off` | `on` | shield off still judges in shadow and executes the top action |
| `--seed N` | `0` | episode seed |
| `--jev auto|live|mock` | `auto` | judge mode |
| `--model ID` | `jev-1.13.0` | Jev model id |
| `--model-path PATH` | `models/dqn_highway.zip` | DQN checkpoint |
| `--rules LIST` | `all` | comma list of preset ids (`speed_limit`, `lane_change_gap`, `left_lane_passing`, `lane_closed`, `headway`, `lane_change_rate`, `cut_in`, `dense_traffic`), `all` for the standing rules (every preset but `lane_closed`), or `none` |
| `--zone-at-step N` | unset | drop the default work zone at step N, which adds the lane-closed rule |
| `--t-allow P` | `0.3` | allow threshold |
| `--t-block P` | `0.7` | block threshold |
| `--floor-s S` | `2.0` | time-to-collision floor in seconds; a candidate under it never runs; `0` disables |
| `--operator approve|deny|simulated` | `simulated` | who answers escalations; simulated answers from the ground-truth checkers |
| `--max-steps N` | unset | stop early |
| `--log PATH` | `backend/logs/runs/<run_id>.jsonl` | where the records go |
| `--quiet` | off | suppress the per-step lines, print only the summary |

Writes one JSONL file and prints a JSON summary. An unknown rule id exits with code 2.

## interlock eval

Batch evaluation over seeds with the simulated operator. Full detail on [Evaluation and results](evaluation.md).

```bash
uv run interlock eval --seeds 0-19 --mode on
uv run interlock eval --seeds 0-19 --mode off
uv run interlock eval --seeds 0-19 --sweep
uv run interlock eval --seeds 0-19 --all --concurrency 2
uv run interlock eval --report
```

| Flag | Default | Meaning |
| --- | --- | --- |
| `--seeds RANGE` | `0-19` | `0-19` or `3,7,11` |
| `--mode off|on|shadow` | unset | one configuration; `shadow` is an alias of `off` |
| `--t-allow P`, `--t-block P` | `0.3`, `0.7` | thresholds for `--mode on` |
| `--floor-s S` | `2.0` | time-to-collision floor for shield-on runs; `0` disables and adds `_nofloor` to the label, any other non-default value adds `_floor<S>` |
| `--sweep` | off | shield on over the five pairs 0.1/0.9, 0.2/0.8, 0.3/0.7, 0.4/0.6, 0.5/0.5 |
| `--all` | off | off, then the sweep, then the report |
| `--report` | off | aggregate the newest run per configuration into the report and plots |
| `--zone-at-step N` | unset | drop the zone in every episode at step N |
| `--jev auto|live|mock` | `auto` | judge mode |
| `--concurrency N` | `3` | episodes in flight; 2 is comfortable under the API rate limit for a full run |
| `--max-steps N` | unset | shorten every episode |
| `--model-path PATH` | `models/dqn_highway.zip` | DQN checkpoint |
| `--out DIR` | `backend/logs/eval` | where runs are written |

Each configuration writes `backend/logs/eval/<stamp>_<label>/` with one `seedN.jsonl` per seed and a `metrics.json`. The report rebuilds `internal/eval/latest.json` and `internal/plots/*.png`. Choosing none of `--mode`, `--sweep`, `--all`, `--report` exits with code 2.

## interlock baseline

Ask chat models the judge's own questions on labeled checks sampled from the eval logs, and score them with the same reliability code. Jev's answers come from the logs.

```bash
uv run interlock baseline --dry-run
uv run interlock baseline --checks 2000 --models claude-haiku-5-5,claude-sonnet-5-5
uv run interlock baseline --concurrency 8                  # reads backend/prices.json when it exists
```

| Flag | Default | Meaning |
| --- | --- | --- |
| `--checks N` | `2000` | checks to sample, spread evenly over (rule, label) strata and topped up from the rest |
| `--models LIST` | `claude-haiku-5-5,claude-sonnet-5-5` | comma list of model ids |
| `--runs DIR` | `backend/logs/eval` | eval runs root; the newest run per label is read |
| `--seed N` | `0` | sampling seed |
| `--concurrency N` | `4` | calls in flight per model |
| `--prices PATH` | `backend/prices.json` when it exists | JSON `{model: {"input_per_mtok": USD, "output_per_mtok": USD}}`; copy `backend/prices.example.json` and fill it from the pricing page. A blank entry is an error; a missing model gets no cost |
| `--out PATH` | `internal/eval/baseline.json` | where the block goes |
| `--cache PATH` | `backend/logs/baseline_cache.jsonl` | reply cache; a re-run with the same sample sends nothing |
| `--dry-run` | off | sample, print the strata and one full request, send nothing; needs no key |

Needs `ANTHROPIC_API_KEY` in `backend/.env` unless `--dry-run`, plus `ANTHROPIC_WORKSPACE_ID` when the key is not scoped to a workspace. Exits 2 when there are no labeled checks or no key, and stops on the first call when the API rejects the key, the workspace or the model. Then `interlock eval --report` folds the block into `latest.json` and draws `baseline.png`.

## interlock train

Train the DQN on task reward alone, then evaluate the checkpoint with greedy rollouts.

```bash
uv run interlock train
uv run interlock train --timesteps 100000 --promote
uv run interlock train --eval-only models/dqn_highway_20k.zip
```

| Flag | Default | Meaning |
| --- | --- | --- |
| `--timesteps N` | `20000` | training steps |
| `--seed N` | `0` | training seed |
| `--out PATH` | `models/dqn_highway_<N>k.zip` | checkpoint path |
| `--eval-seeds RANGE` | `0-19` | seeds for the rollout after training |
| `--eval-only PATH` | unset | skip training and evaluate this checkpoint |
| `--promote` | off | also copy the checkpoint to `models/dqn_highway.zip` |

Writes the checkpoint and a `.eval.json` next to it with return, crash rate, mean speed and steps per seed. See [Training and policy](../developer-guide/backend/training.md).

## interlock label

Hand-label candidate actions against a rule that no checker scores, so the fuzzy presets enter the calibration plot. It reads a logged run, picks pairs the checkers left unlabeled, spreads them across the range of Jev's probability, and asks you one at a time. Jev's answer is hidden unless you ask for it, so the label is your judgment.

```bash
uv run interlock label --run backend/logs/eval/<stamp>_on_ta0.30_tb0.70 --rule dense_traffic
uv run interlock label --run backend/logs/runs/<run_id>.jsonl --rule "plenty of room" --sample 100
uv run interlock eval --report                      # fold the labels into the calibration
```

Each prompt shows the seed, step and candidate, the rule, and the facts as sentences; answer `y` for a violation, `n` for none, `s` to skip, `q` to stop. Labels append to `backend/logs/labels/<preset id or slug>.jsonl`, keyed by a hash of the facts and the rule text, so they apply to any run that shows the same state. A later line for the same key wins.

| Flag | Default | Meaning |
| --- | --- | --- |
| `--run PATH` | required | a JSONL log or an eval run directory |
| `--rule TEXT` | required | a constraint id, a preset id, or a substring of the rule text |
| `--sample N` | `50` | how many pairs to label in this session |
| `--seed N` | `0` | sampling seed |
| `--labels PATH` | per rule | output file |
| `--show-p` | off | show Jev's probability on each card |
| `--include-scored` | off | also offer pairs a checker already labeled |

## interlock autolabel

Label the two fuzzy presets by one fixed standard instead of by hand, so they enter the calibration plot without a labeling session. It reads the runs the report pools for calibration, applies the standard to every distinct state the checkers left unlabeled, and appends rows through the same path as `interlock label`, marked `labeler: autolabel`. A state already labeled is skipped, so a rerun adds nothing. Dense means four or more vehicles within 50 m. In dense traffic FASTER breaks the rule; a lane change breaks it into a gap under 15 m on either side, or onto under 2 s of headway or 5 s to collision; IDLE breaks it on the same margins when SLOWER was available; SLOWER complies. A cut-in violation is a lane change with a faster vehicle under 15 m behind in the new lane, or while tailgated. A state within 1 m or 0.5 s of a threshold is skipped as unsettled. Like the checkers, these labels score only; nothing in the shield reads them.

```bash
uv run interlock autolabel --dry-run                # the split per rule, per action and per bin
uv run interlock autolabel                          # label the calibration pool, both rules
uv run interlock autolabel --run backend/logs/eval/<stamp>_off --rule dense_traffic
uv run interlock eval --report                      # fold the labels into the calibration
```

| Flag | Default | Meaning |
| --- | --- | --- |
| `--run PATH` | the calibration pool | a JSONL log or an eval run directory; repeatable |
| `--rule ID` | both | `dense_traffic` or `cut_in`; repeatable |
| `--labels-dir PATH` | `backend/logs/labels/` | where existing labels are read and new ones go |
| `--labeler NAME` | `autolabel` | the labeler recorded on each row |
| `--dry-run` | off | print the split, write nothing |

## interlock spike

The hand-written probe of Jev's behaviour on fixed fact sets. It needs the key unless `--dry-run`, which builds and validates every request without calling the API.

```bash
uv run interlock spike --dry-run
uv run interlock spike --items 1,3,8
uv run interlock spike --items 2,3 --results internal/jev-spike-recheck-oct17.md   # keep the Day 1 file
```

| Flag | Default | Meaning |
| --- | --- | --- |
| `--items LIST` | `1-8` | which checklist items to run |
| `--repeats N` | `20` | steps for the latency item |
| `--dry-run` | off | no network |
| `--results PATH` | `internal/jev-spike-results.md` | where the results markdown goes; a re-run after a schema change writes elsewhere so the Day 1 record survives |

Without the key and without `--dry-run` it exits with code 2. An SDK error exits with 1.

## interlock console

Starts the WebSocket server on port 8000 and the Vite dev server on port 5173, prints both URLs, and stops both on ++ctrl+c++. If either child exits on its own the other is stopped and its exit code is returned.

```bash
uv run interlock console
uv run interlock console --jev mock --escalation-timeout 0
uv run interlock console --jev mock --cache /tmp/empty.jsonl
uv run interlock console --reload --open
uv run interlock console --no-ui
```

| Flag | Default | Sets |
| --- | --- | --- |
| `--port N` | `8000` | server port; Vite proxies `/ws`, `/health` and `/eval` to it |
| `--ui-port N` | `5173` | Vite port |
| `--no-ui` | off | server only; run `cd frontend && pnpm dev` yourself |
| `--reload` | off | restart the server when `backend/*.py` changes |
| `--open` | off | open the browser once Vite is up |
| `--jev auto|live|mock` | from the shell | `JEV_MODE` |
| `--seed N` | from the shell | `SEED` for the first episode |
| `--escalation-timeout S` | from the shell (server default 20) | `ESCALATION_TIMEOUT_S`; 0 waits for the operator |
| `--floor-s S` | from the shell (server default 2.0) | `FLOOR_S`; the time-to-collision floor, 0 disables |
| `--model-path PATH` | from the shell | `MODEL_PATH` |
| `--cache PATH` | from the shell | `JEV_CACHE_PATH`; an empty file makes every step escalate in mock mode |

A flag that is absent leaves whatever the shell exported in place. The full variable list is on [Configuration](../reference/configuration.md). `console` exits with code 2 when `frontend/node_modules/.bin/vite` is missing, and with 130 on ++ctrl+c++.

## Running the halves by hand

```bash
uv run uvicorn backend.server:app --reload
cd frontend && pnpm dev
```

The Vite config proxies to `http://127.0.0.1:8000` unless `SHIELD_BACKEND` points elsewhere.
