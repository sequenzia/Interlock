# Module reference

A hand-written index of every source file: what it is for, the public names it exports with their signatures as written, and any side effects (files written, network calls). Behaviour is explained on the linked developer pages; this page is for finding the name.

Shared type aliases: `Facts = dict[str, Any]` in `backend/facts.py`, `backend/checkers.py` and `backend/jev_client.py`; `PGrid = dict[str, dict[str, float]]` (action to constraint id to p) in `backend/shield.py`; `Source = Literal["live", "cache", "unavailable"]` in `backend/jev_client.py`; `OperatorAnswer = Literal["approve", "deny"]` in `backend/episode.py`.

## Backend

### `backend/env.py`

highway-fast-v0 with the demo configuration. See [Training and policy](../developer-guide/backend/training.md) and [the reward function](../developer-guide/backend/training.md#the-reward-function) it leaves at the highway-env default.

| Name | Signature or value |
| --- | --- |
| `ENV_ID` | `"highway-fast-v0"` |
| `ACTION_NAMES` | `tuple[str, ...]`, `("LANE_LEFT", "IDLE", "LANE_RIGHT", "FASTER", "SLOWER")` from `DiscreteMetaAction.ACTIONS_ALL` |
| `ACTION_INDEX` | `dict[str, int]`, name to index |
| `DEFAULT_CONFIG` | `{"lanes_count": 4, "duration": 60, "vehicles_count": 30, "policy_frequency": 1}` |
| `make_env` | `(config: dict[str, Any] \| None = None, render_mode: str \| None = None) -> gym.Env` |

### `backend/train.py`

DQN training and checkpoint evaluation. Writes checkpoints and `.eval.json` files under `models/`.

| Name | Signature |
| --- | --- |
| `build_model` | `(env: Any, seed: int) -> DQN` |
| `train` | `(timesteps: int, out: Path, seed: int) -> Path` |
| `run_episode` | `(model: DQN, seed: int) -> dict[str, Any]` |
| `evaluate_checkpoint` | `(path: Path, seeds: list[int]) -> dict[str, Any]` |
| `parse_seed_range` | `(text: str) -> list[int]` |
| `command` | the `interlock train` command; its parameters are the flags |
| `main` | `(argv: Sequence[str] \| None = None) -> None`, `python -m backend.train` |

### `backend/policy.py`

Ranked actions with Q-values from a loaded DQN. No side effects.

| Name | Signature |
| --- | --- |
| `RankedAction` | frozen dataclass: `name: str`, `index: int`, `q: float`, `rank: int` |
| `Policy.__init__` | `(model: DQN) -> None` |
| `Policy.load` | classmethod `(path: Path = DEFAULT_MODEL_PATH) -> Policy` |
| `Policy.q_values` | `(obs: np.ndarray) -> np.ndarray` |
| `Policy.ranked_actions` | `(obs: np.ndarray) -> list[RankedAction]` |

### `backend/paths.py`

Repo-relative paths: `BACKEND_DIR`, `REPO_DIR`, `MODELS_DIR`, `LOGS_DIR`, `INTERNAL_DIR`, `DEFAULT_MODEL_PATH`, `ENV_FILE`. All `Path` constants.

### `backend/facts.py`

Simulator state plus one action to facts JSON and sentences. See [Facts](../developer-guide/backend/facts.md). Reads the env; no writes.

| Name | Signature or value |
| --- | --- |
| `ACTION_MEANING` | `dict[str, str]`, plain meaning per action |
| `NEIGHBOUR_RANGE_M`, `SLOWER_AHEAD_RANGE_M`, `STEP_SECONDS` | `200.0`, `40.0`, `1.0` |
| `lane_number` | `(lane_index: tuple[str, str, int]) -> int` |
| `action_meaning` | `(action: str, lane: int, lane_count: int) -> str` |
| `lane_after` | `(action: str, lane: int, lane_count: int) -> int` |
| `target_speed_after` | `(ego: Any, action: str) -> float` |
| `facts_for_action` | `(env: Any, action: str, zones: list[Zone], history: History \| None = None) -> Facts` |
| `for_candidates` | `(env: Any, actions: list[str], zones: list[Zone], history: History \| None = None) -> dict[str, Facts]` |
| `lane_history` | `(past_lanes: list[int], lane: int) -> History`, the `history` block |
| `noop_actions` | `(candidates: dict[str, Facts]) -> frozenset[str]`, lane changes at the road edge and speed changes at the end of the range |
| `snapshot` | `(env: Any) -> dict[str, Any]`, ego and vehicle positions for the log record |
| `sentences` | `(f: Facts) -> list[str]` |

### `backend/constraints.py`

Operator rules and zones. See [Constraints and checkers](../developer-guide/backend/constraints-and-checkers.md). In-memory only.

| Name | Signature or value |
| --- | --- |
| `CHECKER_SPEED_LIMIT`, `CHECKER_LANE_CHANGE_GAP`, `CHECKER_LEFT_LANE_PASSING`, `CHECKER_LANE_CLOSED`, `CHECKER_HEADWAY`, `CHECKER_LANE_CHANGE_RATE` | `"speed_limit"`, `"lane_change_gap"`, `"left_lane_passing"`, `"lane_closed"`, `"headway"`, `"lane_change_rate"` |
| `PRESET_CUT_IN`, `PRESET_DENSE_TRAFFIC` | `"cut_in"`, `"dense_traffic"`, the fuzzy presets |
| `PRESETS` | `dict[str, str]`, preset id to rule text, in chip order; eight entries |
| `FUZZY_PRESETS` | `frozenset` of the two preset ids without a checker |
| `preset_checker` | `(preset_id: str) -> str \| None` |
| `DEFAULT_ZONE_LANE`, `DEFAULT_ZONE_AHEAD_M`, `DEFAULT_ZONE_LENGTH_M`, `DEFAULT_ZONE_NAME` | `3`, `120.0`, `200.0`, `"work zone"` |
| `Constraint` | dataclass: `id: str`, `text: str`, `enabled: bool = True`, `checker: str \| None = None`; `to_dict() -> dict[str, Any]` |
| `Zone` | dataclass: `name: str`, `lane: int`, `start_m: float`, `end_m: float`; `to_dict() -> dict[str, Any]` |
| `infer_checker` | `(text: str) -> str \| None` |
| `ConstraintStore.constraints` | property `-> list[Constraint]` (copy) |
| `ConstraintStore.zones` | property `-> list[Zone]` (copy) |
| `ConstraintStore.enabled` | `() -> list[Constraint]` |
| `ConstraintStore.add` | `(text: str, checker: str \| None = None) -> Constraint` |
| `ConstraintStore.add_presets` | `(preset_ids: Iterable[str] \| None = None) -> list[Constraint]` |
| `ConstraintStore.get` | `(constraint_id: str) -> Constraint`, raises `KeyError` |
| `ConstraintStore.toggle` | `(constraint_id: str, enabled: bool) -> Constraint` |
| `ConstraintStore.remove` | `(constraint_id: str) -> None` |
| `ConstraintStore.drop_zone` | `(ego_x_m: float, lane: int = 3, ahead_m: float = 120.0, length_m: float = 200.0, name: str = "work zone") -> Zone` |
| `ConstraintStore.zone_rule` | `() -> Constraint \| None` |
| `ConstraintStore.retire_passed_zones` | `(ego_x_m: float) -> list[Zone]` |
| `ConstraintStore.clear_zones` | `() -> None` |
| `ConstraintStore.snapshot` | `() -> dict[str, list[dict[str, Any]]]` with `constraints` and `zones` |

### `backend/jev_client.py`

Live, cached and mock judging behind one interface. See [Jev integration](../developer-guide/backend/jev-integration.md). `LiveJudge` calls the TypeSafe API; `JevCache.put` appends to the cache file.

| Name | Signature or value |
| --- | --- |
| `USD_PER_INPUT_TOKEN`, `DEFAULT_MODEL`, `UNAVAILABLE_P`, `DEFAULT_CACHE_PATH` | `0.042 / 1_000_000`, `"jev-1.13.0"`, `0.5`, `backend/logs/jev_cache.jsonl` |
| `build_question` | `(rule_text: str, candidate: str \| None = None) -> Noul` |
| `question_dict` | `(question: Noul) -> dict[str, Any]` |
| `cache_key` | `(model: str, state: Any, question: Noul) -> str`, SHA-256 hex |
| `JevCache.__init__` | `(path: Path \| None) -> None`; `None` is in-memory only |
| `JevCache.get` | `(key: str) -> tuple[float, str] \| None` (p, model) |
| `JevCache.put` | `(key: str, p: float, model: str) -> None` |
| `LiveAnswer` | dataclass: `p: dict[str, float]`, `model: str`, `input_tokens: int`, `raw_response: Any`, `latency_ms: float`, `request_id: str \| None = None` |
| `LiveJudge.__init__` | `(model: str = DEFAULT_MODEL, timeout_s: float = 10.0) -> None` |
| `LiveJudge.ask` | `async (state: Any, questions: dict[str, Noul]) -> LiveAnswer \| None` |
| `LiveJudge.close` | `async () -> None` |
| `Exchange` | dataclass: `action: str`, `asked: list[str]`, `response: Any`, `latency_ms: float`, `source: Source`, `request_id: str \| None = None`; `to_dict()` |
| `CheckResult` | dataclass: `p: dict[str, dict[str, float]]`, `sources`, `model: str`, `source: Source`, `latency_ms: float`, `input_tokens: int`, `cost_usd: float`, `questions: dict[str, dict[str, Any]]`, `exchanges: list[Exchange]`; property `judge_unavailable -> bool`; `judge_record() -> dict[str, Any]` |
| `JevClient.__init__` | `(live: LiveJudge \| None, cache: JevCache, model: str = DEFAULT_MODEL) -> None` |
| `JevClient.mode` | property `-> str`, `"mock"` when `live is None` |
| `JevClient.check` | `async (candidates: dict[str, Facts], constraints: list[Constraint]) -> CheckResult` |
| `JevClient.close` | `async () -> None` |
| `make_client` | `(mode: Literal["live", "mock"], cache_path: Path \| None = DEFAULT_CACHE_PATH, model: str = DEFAULT_MODEL) -> JevClient` |
| `JevMode` | `Literal["auto", "live", "mock"]`, the `--jev` choices |
| `resolve_jev_mode` | `(mode: JevMode) -> Literal["live", "mock"]`; `auto` is live when `TYPESAFE_API_KEY` is set, mock otherwise |

### `backend/shield.py`

Pure decision functions. See [Shield algorithm](../developer-guide/backend/shield.md).

| Name | Signature |
| --- | --- |
| `DecisionKind` | `Literal["allow", "fallback", "escalate", "all_blocked"]`; `all_blocked` is only read from logs written before Oct 17 |
| `FallbackKind` | `Literal["safe", "least_bad", "last_resort"]` |
| `EscalationReason` | `Literal["uncertain", "no_compliant_action"]` |
| `OperatorDecision` | `Literal["approve", "deny", "override"]` |
| `Thresholds` | frozen dataclass: `t_allow: float = 0.3`, `t_block: float = 0.7`; validates in `__post_init__` |
| `Fallback` | frozen dataclass: `action: str`, `kind: FallbackKind` |
| `DEFAULT_FLOOR_S` | `1.0`, the time-to-collision floor |
| `Floor` | frozen dataclass: `applied: bool`, `removed: tuple[str, ...]`; `to_dict()` |
| `under_floor(candidates, floor_s)` | the candidates whose `time_to_collision_ahead_s` is under the floor, in order |
| `floor_decision(ranked, p)` | the SLOWER `fallback` when every candidate is under the floor |
| `Answer` | frozen dataclass: `decision: OperatorDecision`, `action: str \| None = None` |
| `Decision` | frozen dataclass: `kind`, `proposed: str`, `executed: str`, `fired_constraint: str \| None`, `p_proposed: float`, `p_viol: dict[str, float]`, `fallback: str`, `fallback_kind: FallbackKind`, `reason: EscalationReason \| None = None`, `all_blocked: bool = False` |
| `violation_probability` | `(p_for_action: dict[str, float]) -> tuple[float, str \| None]` |
| `fallback_action` | `(ranked: list[str], p: PGrid, thresholds: Thresholds, noop: frozenset[str] = frozenset()) -> Fallback` |
| `decide` | `(ranked: list[str], p: PGrid, thresholds: Thresholds, noop: frozenset[str] = frozenset()) -> Decision` |
| `resolve` | `(decision: Decision, answer: Answer) -> Decision`, raises `ValueError` unless `kind == "escalate"`, or for an override naming an action outside `p_viol` |

### `backend/checkers.py`

Ground-truth labels for scoring only. See [Constraints and checkers](../developer-guide/backend/constraints-and-checkers.md).

| Name | Signature |
| --- | --- |
| `LANE_CHANGE_ACTIONS` | `frozenset({"LANE_LEFT", "LANE_RIGHT"})` |
| `Checker` | `Callable[[Facts, Constraint], bool]` |
| `check_speed_limit`, `check_lane_change_gap`, `check_left_lane_passing`, `check_lane_closed`, `check_headway`, `check_lane_change_rate` | each `(facts: Facts, constraint: Constraint) -> bool` |
| `CHECKERS` | `dict[str, Checker]`, checker id to function |
| `label` | `(facts: Facts, constraint: Constraint) -> bool \| None` |
| `label_all` | `(candidates: dict[str, Facts], constraints: list[Constraint]) -> dict[str, dict[str, bool \| None]]` |

### `backend/logger.py`

The JSONL record. See [Log record](../developer-guide/contracts/log-record.md). `JsonlLogger` appends to its path.

| Name | Signature |
| --- | --- |
| `make_run_id` | `(seed: int, shield_on: bool, now: datetime \| None = None) -> str` |
| `default_log_path` | `(run_id: str) -> Path`, `backend/logs/runs/<run_id>.jsonl` |
| `build_record` | keyword-only `(run_id, episode, step, seed, source, shield_on, thresholds: Thresholds, snapshot, zones, constraints, candidates, decision: Decision, escalated, human, fallback: dict[str, str], judge, reward, crashed) -> dict[str, Any]` |
| `JsonlLogger` | `__init__(path: Path)`, `write(record: dict[str, Any]) -> None` (flushes), `close() -> None`, context manager |
| `read_log` | `(path: Path) -> list[dict[str, Any]]` |

### `backend/episode.py`

The per-step loop shared by the CLI and the server. See [Per-step loop](../developer-guide/backend/episode-loop.md). Writes a record per step through the logger when one is given.

| Name | Signature |
| --- | --- |
| `Escalation` | frozen dataclass: `id: str`, `step: int`, `action: str`, `sentences: list[str]`, `constraint_id: str \| None`, `constraint_text: str \| None`, `p: float`, `q_rank: int`, `fallback: str`, `fallback_kind: str`, `judge_unavailable: bool`, `reason: EscalationReason`, `candidates: list[dict[str, Any]]`, `ground_truth: bool \| None`, `violations_by_action: dict[str, int \| None]` |
| `Operator` | `Callable[[Escalation], Awaitable[Answer]]` |
| `simulated_operator`, `always_approve`, `always_deny` | each `async (escalation: Escalation) -> Answer` |
| `OperatorName`, `OPERATORS` | `Literal["simulated", "approve", "deny"]`, the `--operator` choices, and that name to the three above |
| `StepResult` | dataclass: `record: dict[str, Any]`, `escalation: Escalation \| None`, `terminated: bool`, `truncated: bool`; property `done` |
| `Totals` | dataclass of running counters: `steps`, `reward`, `crashed`, `decisions`, `conflicts`, `violations`, `human`, `sources`, `latencies_ms`, `input_tokens`, `cost_usd` |
| `EpisodeRunner.__init__` | keyword-only `(policy: Policy, judge: JevClient, store: ConstraintStore, thresholds: Thresholds \| None = None, shield_on: bool = True, operator: Operator \| None = None, operator_name: str = "simulated", logger: JsonlLogger \| None = None, env_config: dict[str, Any] \| None = None, source: str = "live")` |
| `EpisodeRunner.reset` | `(seed: int) -> dict[str, Any]`, returns the first snapshot |
| `EpisodeRunner.ego_x_m` | property `-> float` |
| `EpisodeRunner.step` | `async () -> StepResult` |
| `EpisodeRunner.summary` | `() -> dict[str, Any]` |
| `EpisodeRunner.run` | `async (seed: int, max_steps: int \| None = None, on_step: Callable[[StepResult], None] \| None = None, zone_at_step: int \| None = None) -> dict[str, Any]` |
| `EpisodeRunner.close` | `() -> None` |

### `backend/run_episode.py`

Headless episode behind `interlock run`. Writes the JSONL log and prints a summary.

| Name | Signature |
| --- | --- |
| `format_step` | `(result: StepResult) -> str` |
| `command`, `main` | the `interlock run` command and `python -m backend.run_episode` |

### `backend/server.py`

FastAPI WebSocket server. See [Server and session](../developer-guide/backend/server.md). Writes run logs; reads the eval report.

| Name | Signature or value |
| --- | --- |
| `RUNS_DIR`, `EVAL_REPORT`, `DEFAULT_STEPS_PER_SEC`, `DEFAULT_ESCALATION_TIMEOUT_S` | `backend/logs/runs`, `internal/eval/latest.json`, `2.0`, `20.0` |
| `list_runs` | `() -> list[str]` |
| `replay_metrics` | `(records: list[dict[str, Any]]) -> dict[str, Any]` |
| `Session.__init__` | `(policy: Policy, judge: JevClient, *, seed: int = 0, steps_per_sec: float = 2.0, escalation_timeout_s: float \| None = 20.0)` |
| `Session.hello`, `state`, `constraints_msg`, `history_msg`, `metrics_msg` | each `() -> dict[str, Any]` |
| `Session.escalation_msg` | `(esc: Escalation) -> dict[str, Any]` |
| `Session.send` | `async (ws: WebSocket, msg: dict[str, Any]) -> None` |
| `Session.broadcast` | `async (msg: dict[str, Any]) -> None` |
| `Session.connect` | `async (ws: WebSocket) -> None` |
| `Session.disconnect` | `(ws: WebSocket) -> None` |
| `Session.handle` | `async (ws: WebSocket, msg: dict[str, Any]) -> None` |
| `Session.busy` | property `-> bool` |
| `Session.play`, `pause`, `step_once` | each `async () -> None` |
| `Session.resolve` | `async (escalation_id: str, decision: str) -> None` |
| `Session.reset` | `async (seed: int) -> None` |
| `Session.load_replay` | `async (run_id: str) -> None` |
| `Session.close` | `async () -> None` |
| `session_from_env` | `() -> Session` |
| `console_origins_from_env` | `() -> list[str]` |
| `create_app` | `(session: Session \| None = None, *, console_origins: list[str] \| None = None) -> FastAPI` |
| `app` | `create_app()` |

### `backend/twin.py`

The unshielded twin. See [WebSocket protocol](../developer-guide/contracts/websocket-protocol.md).

| Name | Signature or value |
| --- | --- |
| `RUNS_DIR`, `EVAL_DIR` | `backend/logs/runs/`, `backend/logs/eval/` |
| `find_twin_log` | `(seed: int, runs_dir: Path \| None = None, eval_dir: Path \| None = None) -> Path \| None`: the newest eval off run's `seedN.jsonl`, else the newest `*_seedN_off.jsonl` |
| `twin_steps` | `(records) -> list[dict]`: `step`, `ego`, `vehicles`, `executed`, `violations`, `violations_so_far`, `crashed` per record |
| `twin_message` | `(seed: int, path: Path \| None) -> dict`: the `twin` message; empty for no log, a shielded log or another seed |
| `empty_twin` | `(seed: int) -> dict` |

### `backend/metrics.py`

Pure functions over records. See [Evaluation internals](../developer-guide/backend/evaluation.md).

| Name | Signature |
| --- | --- |
| `executed_candidate` | `(record: Record) -> Record \| None` |
| `episode_metrics` | `(records: list[Record]) -> dict[str, Any]` |
| `aggregate` | `(episodes: list[dict[str, Any]]) -> dict[str, Any]` |
| `Check` | `tuple[float, bool, str]`: p, label, calibration group |
| `collect_checks` | `(records: Iterable[Record], labels: dict[str, Label] \| None = None) -> list[Check]` |
| `reliability` | `(checks: list[Check], bins: int = 10) -> dict[str, Any]` |
| `calibration` | `(records: Iterable[Record], bins: int = 10, labels: dict[str, Label] \| None = None) -> dict[str, Any]`; each `by_checker` entry carries `label_source` |

### `backend/evaluate.py`

Batch evaluation and report. Writes `backend/logs/eval/<stamp>_<label>/`, `internal/eval/latest.json` and `internal/plots/*.png`; calls Jev in live mode.

| Name | Signature or value |
| --- | --- |
| `EVAL_DIR`, `REPORT_PATH`, `PLOTS_DIR`, `SWEEP`, `DEFAULT_THRESHOLDS`, `STANDING_RULES` | see [Configuration](configuration.md) |
| `config_label` | `(shield_on: bool, thresholds: Thresholds, zone_at_step: int \| None) -> str` |
| `run_config` | `async (policy: Policy, judge: JevClient, seeds: list[int], *, shield_on: bool, thresholds: Thresholds, out_dir: Path, zone_at_step: int \| None = None, rules: list[str] \| None = None, concurrency: int = 3, max_steps: int \| None = None, quiet: bool = False) -> dict[str, Any]` |
| `new_run_dir` | `(root: Path, label: str) -> Path` |
| `load_run` | `(path: Path, labels: dict[str, Label] \| None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]`, recomputes and rewrites `metrics.json` from the seed logs |
| `calibration_pool` | `(root: Path = EVAL_DIR) -> list[Path]`, the newest shield-off run and the newest shield-on runs at the default floor |
| `newest_runs` | `(root: Path) -> dict[str, Path]` |
| `build_report` | `(root: Path = EVAL_DIR, report_path: Path = REPORT_PATH, plots_dir: Path = PLOTS_DIR, thresholds: Thresholds = DEFAULT_THRESHOLDS) -> dict[str, Any]` |
| `print_summary` | `(report: dict[str, Any]) -> None` |
| `command`, `main` | the `interlock eval` command and `python -m backend.evaluate` |

### `backend/plots.py`

Matplotlib figures, `Agg` backend. Each returns the path it wrote.

| Name | Signature |
| --- | --- |
| `plot_before_after` | `(before: dict[str, Any], after: dict[str, Any], path: Path) -> Path` |
| `plot_tradeoff` | `(sweep: list[dict[str, Any]], path: Path) -> Path` |
| `plot_calibration` | `(cal: dict[str, Any], path: Path) -> Path` |

### `backend/label.py`

Hand labels for rules without a checker. See [Command line](../user-guide/cli.md#interlock-label).

| Name | Signature or value |
| --- | --- |
| `LABELS_DIR`, `BINS`, `ANSWERS` | `backend/logs/labels/`, `10`, `("y", "n", "s", "q")` |
| `label_key` | `(facts: dict[str, Any], rule_text: str) -> str`, sha256 of the canonical JSON of both |
| `slug`, `rule_group` | `(text: str) -> str`; the group is the preset id for a preset text, else the slug |
| `Label` | frozen dataclass: `violation: bool`, `labeler: str` |
| `load_labels` | `(directory: Path = LABELS_DIR) -> dict[str, Label]`, later lines win; a row without a labeler counts as `human` |
| `Item` | frozen dataclass: `run_id`, `seed`, `step`, `action`, `rank`, `rule_id`, `rule_text`, `facts`, `sentences`, `p`, `key` |
| `read_records` | `(run: Path) -> list[dict[str, Any]]`, a log file or an eval directory |
| `find_rule` | `(record, rule: str) -> dict \| None`, by id, preset id or text substring |
| `collect_items` | `(records, rule: str, unlabeled_only: bool = True) -> list[Item]` |
| `sample_items` | `(items: list[Item], n: int, rng: random.Random, done: set[str]) -> list[Item]`, round-robin over ten bins of p |
| `render` | `(item: Item, index: int, total: int, show_p: bool) -> str` |
| `label_session` | `(items, ask: Callable[[str], str], out_path: Path, *, show_p: bool = False, labeler: str = "human") -> int` |
| `command`, `main` | the `interlock label` command and `python -m backend.label` |

### `backend/autolabel.py`

The fixed standard for the two fuzzy presets, behind `interlock autolabel`. See [Command line](../user-guide/cli.md#interlock-autolabel).

| Name | Signature or value |
| --- | --- |
| `LABELER`, `DENSE_AT`, `HEADWAY_S`, `GAP_M`, `GAP_BAND_M`, `TTC_S`, `TTC_BAND_S`, `MIN_TARGET_MPS` | `"autolabel"`, `4`, `2.0`, `15.0`, `1.0`, `5.0`, `0.5`, `20.0` |
| `dense_traffic`, `cut_in` | `(f: Facts, gap_m: float, ttc_s: float) -> bool`, the two standards at the given thresholds |
| `STANDARDS` | preset id to standard |
| `FuzzyPreset` | `StrEnum` of the two preset ids, the `--rule` choices |
| `answer` | `(rule: str, facts: Facts) -> str`: `y`, `n`, or `s` when a 1 m or 0.5 s shift of a threshold would flip it |
| `unlabeled_items` | `(records, rule: str, done: set[str]) -> list[Item]`, one per distinct unlabeled state |
| `summary` | `(rule: str, items, answers) -> str`, counts by answer, by action and by bin of p |
| `scripted` | `(answers: Iterable[str]) -> Callable[[str], str]`, an `ask` that answers from a list |
| `command`, `main` | the `interlock autolabel` command and `python -m backend.autolabel` |

### `backend/baseline_llm.py`

Chat-LLM baseline for the judge, offline for Jev. Behind `interlock baseline`. See [Chat-LLM baseline](../user-guide/evaluation.md#chat-llm-baseline).

| Name | Signature or value |
| --- | --- |
| `DEFAULT_MODELS` | `("claude-haiku-5-5", "claude-sonnet-5-5")` |
| `BASELINE_PATH`, `CACHE_PATH` | `internal/eval/baseline.json`, `backend/logs/baseline_cache.jsonl` |
| `FORMAT`, `SYSTEM`, `MAX_TOKENS` | the structured output schema (one `probability` field), the system prompt, and the reply cap that the model's thinking also counts against |
| `Item` | frozen dataclass: `key`, `group`, `rule_text`, `action`, `facts`, `label`, `jev_p` |
| `Reply` | frozen dataclass: `p: float \| None`, `latency_ms`, `input_tokens`, `output_tokens`, `source` (`live`, `cache`, `failed`) |
| `collect_items` | `(records, labels) -> list[Item]`: one per distinct state and rule, labeled by checker or by hand |
| `stratified_sample` | `(items, n, rng) -> list[Item]`: even quota per (rule, label), topped up |
| `build_messages` | `(item) -> (system, user)`: the judge's own question text plus the facts JSON |
| `BaselineCache` | append-only JSONL keyed by model and item key |
| `parse_probability` | `(stop_reason, texts) -> float \| None`: the clamped number from a reply that ended on its own, else `None` |
| `AnthropicChat` | `ask(model, item) -> Reply` through `AsyncAnthropic` with `output_config.format`; a failed call, a cut-off reply or a refusal returns `p=None` |
| `run_models` | `(items, models, ask, concurrency) -> dict[str, list[Reply]]` |
| `judge_summary`, `summarize` | reliability overall and per rule, latency, tokens and cost per judge; Jev scored from the logged `p` |
| `load_items`, `print_summary`, `command`, `main` | CLI plumbing; `--dry-run` sends nothing |

### `backend/cli.py`

The `interlock` command, a Typer app. See [CLI internals](../developer-guide/backend/cli.md). `run_console` starts child processes.

| Name | Signature or value |
| --- | --- |
| `FRONTEND_DIR`, `VITE_BIN`, `DEFAULT_SERVER_PORT`, `DEFAULT_UI_PORT`, `STOP_GRACE_S`, `POLL_S` | `frontend/`, `frontend/node_modules/.bin/vite`, `8000`, `5173`, `10.0`, `0.25` |
| `app` | the `typer.Typer` named `interlock`, with every module's `command` registered under its subcommand name |
| `ConsoleOptions` | frozen dataclass: `port`, `ui_port`, `ui`, `reload`, `open_browser`, and the server fields `jev`, `seed`, `escalation_timeout`, `model_path`, `floor_s`, `cache`, each `None` unless its flag was given |
| `server_command`, `ui_command` | `(opts: ConsoleOptions) -> list[str]` |
| `server_env`, `ui_env` | `(opts: ConsoleOptions) -> dict[str, str]` |
| `terminate` | `(procs: Iterable[subprocess.Popen[bytes]]) -> None` |
| `wait_all` | `(procs: Sequence[subprocess.Popen[bytes]], timeout_s: float) -> bool` |
| `reap` | `(procs: Iterable[subprocess.Popen[bytes]], grace_s: float) -> None` |
| `run_console` | `(opts: ConsoleOptions) -> int`, the process exit code |
| `console` | the `interlock console` command; builds `ConsoleOptions` and exits with `run_console`'s code |
| `main` | `(argv: Sequence[str] \| None = None) -> None` |

### `backend/cli_support.py`

Typer settings shared by the `interlock` command and the modules behind it. See [CLI internals](../developer-guide/backend/cli.md).

| Name | Signature |
| --- | --- |
| `new_app` | `(*, add_completion: bool = False, **kwargs: Any) -> typer.Typer`: Markdown help, `-h`, no locals in tracebacks |
| `standalone_app` | `(command: Callable[..., None]) -> typer.Typer`, one command as an app of its own |
| `run_standalone` | `(command: Callable[..., None], argv: Sequence[str] \| None = None) -> None`, what every module's `main` calls |
| `repo_relative` | `(path: Path) -> str`, a default path as the docs write it, for `show_default` |

### `backend/spike/jev_spike.py`

The Jev checklist against hand-written facts. Calls the API unless `--dry-run`; writes a markdown results file and raw JSON under `backend/logs/spike/<stamp>/`.

| Name | Meaning |
| --- | --- |
| `RULES` | `dict[str, str]`: `speed`, `gap`, `passing`, `zone` to the four preset texts |
| `GAP_RULE_POSITIVE` | The positive rephrase of the gap rule offered by the console |
| `item_1_hello` ... `item_8_latency` | The eight checklist items: hello world and model version, fact sets, numeric probes, request shapes, JSON versus prose, negation, stability, latency |
| `command`, `main` | the `interlock spike` command (`--items`, `--repeats`, `--dry-run`, `--results`) and `python -m backend.spike.jev_spike` |

## Frontend

All files under `frontend/src/`. See [Frontend overview](../developer-guide/frontend/overview.md).

### `types.ts`

Mirrors the log record and the protocol. Exported names, grouped:

- Unions: `ActionName`, `DecisionKind`, `JudgeSource`, `OperatorAnswer`.
- Record pieces: `Thresholds`, `Constraint`, `Zone`, `Check`, `Candidate`, `Human`, `JevQuestion`, `Exchange`, `Judge`, `Ego`, `VehicleSnapshot`, `LogRecord`.
- Session: `Escalation`, `SessionState`, `Metrics`, `Preset`, `ZoneDefaults`, `Hello`.
- Protocol: `ServerMessage`, `ClientMessage`.
- Eval report: `EpisodeMetrics`, `AggregateMetrics`, `RunReport`, `SweepPoint`, `ReliabilityBin`, `Reliability`, `EvalReport`.

### `store.ts`

One Zustand store. See [Store and selectors](../developer-guide/frontend/store.md).

| Export | Meaning |
| --- | --- |
| `View` | `"console" \| "metrics"` |
| `Store` | `ConnectionSlice & StepsSlice & ConstraintsSlice & QueueSlice & MetricsSlice` |
| `useStore` | The hook |
| `selectLatestStep`, `selectPreviousStep` | Last and second-to-last record |
| `selectInspected` | The selected record or null |
| `selectViewStep`, `selectViewPrevStep` | What the road view draws: the selected step when scrubbing, otherwise live |

### `ws-client.ts`

| Export | Signature |
| --- | --- |
| `connect` | `(): () => void`, opens the socket and returns a disconnect function |
| `send` | `(msg: ClientMessage): void`, pushes an error into the store when not connected |

### `backend-url.ts`

| Export | Signature |
| --- | --- |
| `httpUrl` | `(path: string): string` |
| `wsUrl` | `(): string` |

### `format.ts`

| Export | Meaning |
| --- | --- |
| `fmtP`, `fmtMs`, `fmtUsd`, `fmtSpeed` | Formatters for probability, milliseconds, dollars, m/s |
| `DECISION_LABEL` | Kind to display label |
| `DECISION_CLASS` | Kind to Tailwind classes |
| `DECISION_COLOR` | Kind to hex colour for the canvas and timeline |

### Components and entry points

| File | Export |
| --- | --- |
| `main.tsx` | Mounts `App` under `StrictMode` |
| `app.tsx` | `App()`: layout, socket lifetime, keyboard shortcuts, error toast |
| `components/status-strip.tsx` | `StatusStrip()` |
| `components/road-view.tsx` | `RoadView()`, plus `drawCar`, `drawArrow`, `arrowFor`, `lerp` and the scale constants |
| `components/twin-strip.tsx` | `TwinStrip()` |
| `components/constraint-panel.tsx` | `ConstraintPanel()` |
| `components/approval-queue.tsx` | `ApprovalQueue()` |
| `components/decision-strip.tsx` | `DecisionStrip()` |
| `components/inspector-drawer.tsx` | `InspectorDrawer()` |
| `components/facts-table.tsx` | `FactsTable()` |
| `components/metrics-view.tsx` | `MetricsView()` |

Component behaviour is described in [Components](../developer-guide/frontend/components.md).
