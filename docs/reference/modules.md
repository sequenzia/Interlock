# Module reference

A hand-written index of every source file: what it is for, the public names it exports with their signatures as written, and any side effects (files written, network calls). Behaviour is explained on the linked developer pages; this page is for finding the name.

Shared type aliases: `Facts = dict[str, Any]` in `backend/facts.py`, `backend/checkers.py` and `backend/jev_client.py`; `PGrid = dict[str, dict[str, float]]` (action to constraint id to p) in `backend/shield.py`; `Source = Literal["live", "cache", "unavailable"]` in `backend/jev_client.py`; `OperatorAnswer = Literal["approve", "deny"]` in `backend/episode.py`.

## Backend

### `backend/env.py`

highway-fast-v0 with the demo configuration. See [Training and policy](../developer-guide/backend/training.md).

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
| `add_arguments` | `(parser: argparse.ArgumentParser) -> None` |
| `run_cli` | `(args: argparse.Namespace) -> int` |
| `main` | `(argv: Sequence[str] \| None = None) -> None` |

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
| `CHECKER_SPEED_LIMIT`, `CHECKER_LANE_CHANGE_GAP`, `CHECKER_LEFT_LANE_PASSING`, `CHECKER_LANE_CLOSED` | `"speed_limit"`, `"lane_change_gap"`, `"left_lane_passing"`, `"lane_closed"` |
| `PRESETS` | `dict[str, str]`, checker id to rule text, in chip order |
| `DEFAULT_ZONE_LANE`, `DEFAULT_ZONE_AHEAD_M`, `DEFAULT_ZONE_LENGTH_M`, `DEFAULT_ZONE_NAME` | `3`, `120.0`, `200.0`, `"work zone"` |
| `Constraint` | dataclass: `id: str`, `text: str`, `enabled: bool = True`, `checker: str \| None = None`; `to_dict() -> dict[str, Any]` |
| `Zone` | dataclass: `name: str`, `lane: int`, `start_m: float`, `end_m: float`; `to_dict() -> dict[str, Any]` |
| `infer_checker` | `(text: str) -> str \| None` |
| `ConstraintStore.constraints` | property `-> list[Constraint]` (copy) |
| `ConstraintStore.zones` | property `-> list[Zone]` (copy) |
| `ConstraintStore.enabled` | `() -> list[Constraint]` |
| `ConstraintStore.add` | `(text: str, checker: str \| None = None) -> Constraint` |
| `ConstraintStore.add_presets` | `(checker_ids: Iterable[str] \| None = None) -> list[Constraint]` |
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

### `backend/shield.py`

Pure decision functions. See [Shield algorithm](../developer-guide/backend/shield.md).

| Name | Signature |
| --- | --- |
| `DecisionKind` | `Literal["allow", "fallback", "escalate", "all_blocked"]`; `all_blocked` is only read from logs written before Oct 17 |
| `FallbackKind` | `Literal["safe", "least_bad", "last_resort"]` |
| `EscalationReason` | `Literal["uncertain", "no_compliant_action"]` |
| `OperatorDecision` | `Literal["approve", "deny", "override"]` |
| `Thresholds` | frozen dataclass: `t_allow: float = 0.2`, `t_block: float = 0.8`; validates in `__post_init__` |
| `Fallback` | frozen dataclass: `action: str`, `kind: FallbackKind` |
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
| `check_speed_limit`, `check_lane_change_gap`, `check_left_lane_passing`, `check_lane_closed` | each `(facts: Facts, constraint: Constraint) -> bool` |
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
| `OPERATORS` | `{"simulated", "approve", "deny"}` to the three above |
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
| `main_async` | `async (args: argparse.Namespace) -> int` |
| `add_arguments`, `run_cli`, `main` | the module CLI triple |

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

### `backend/metrics.py`

Pure functions over records. See [Evaluation internals](../developer-guide/backend/evaluation.md).

| Name | Signature |
| --- | --- |
| `executed_candidate` | `(record: Record) -> Record \| None` |
| `episode_metrics` | `(records: list[Record]) -> dict[str, Any]` |
| `aggregate` | `(episodes: list[dict[str, Any]]) -> dict[str, Any]` |
| `collect_checks` | `(records: Iterable[Record]) -> list[tuple[float, bool, str]]` |
| `reliability` | `(checks: list[tuple[float, bool, str]], bins: int = 10) -> dict[str, Any]` |
| `calibration` | `(records: Iterable[Record], bins: int = 10) -> dict[str, Any]` |

### `backend/evaluate.py`

Batch evaluation and report. Writes `backend/logs/eval/<stamp>_<label>/`, `internal/eval/latest.json` and `internal/plots/*.png`; calls Jev in live mode.

| Name | Signature or value |
| --- | --- |
| `EVAL_DIR`, `REPORT_PATH`, `PLOTS_DIR`, `SWEEP`, `DEFAULT_THRESHOLDS`, `STANDING_RULES` | see [Configuration](configuration.md) |
| `config_label` | `(shield_on: bool, thresholds: Thresholds, zone_at_step: int \| None) -> str` |
| `run_config` | `async (policy: Policy, judge: JevClient, seeds: list[int], *, shield_on: bool, thresholds: Thresholds, out_dir: Path, zone_at_step: int \| None = None, rules: list[str] \| None = None, concurrency: int = 3, max_steps: int \| None = None, quiet: bool = False) -> dict[str, Any]` |
| `new_run_dir` | `(root: Path, label: str) -> Path` |
| `newest_runs` | `(root: Path) -> dict[str, Path]` |
| `build_report` | `(root: Path = EVAL_DIR, report_path: Path = REPORT_PATH, plots_dir: Path = PLOTS_DIR, thresholds: Thresholds = DEFAULT_THRESHOLDS) -> dict[str, Any]` |
| `print_summary` | `(report: dict[str, Any]) -> None` |
| `main_async`, `add_arguments`, `run_cli`, `main` | the module CLI |

### `backend/plots.py`

Matplotlib figures, `Agg` backend. Each returns the path it wrote.

| Name | Signature |
| --- | --- |
| `plot_before_after` | `(before: dict[str, Any], after: dict[str, Any], path: Path) -> Path` |
| `plot_tradeoff` | `(sweep: list[dict[str, Any]], path: Path) -> Path` |
| `plot_calibration` | `(cal: dict[str, Any], path: Path) -> Path` |

### `backend/cli.py`

The `interlock` command. See [CLI internals](../developer-guide/backend/cli.md). `run_console` starts child processes.

| Name | Signature or value |
| --- | --- |
| `FRONTEND_DIR`, `VITE_BIN`, `DEFAULT_SERVER_PORT`, `DEFAULT_UI_PORT`, `STOP_GRACE_S`, `POLL_S` | `frontend/`, `frontend/node_modules/.bin/vite`, `8000`, `5173`, `10.0`, `0.25` |
| `add_console_arguments` | `(parser: argparse.ArgumentParser) -> None` |
| `server_command`, `ui_command` | `(args: argparse.Namespace) -> list[str]` |
| `server_env`, `ui_env` | `(args: argparse.Namespace) -> dict[str, str]` |
| `terminate` | `(procs: Iterable[subprocess.Popen[bytes]]) -> None` |
| `wait_all` | `(procs: Sequence[subprocess.Popen[bytes]], timeout_s: float) -> bool` |
| `reap` | `(procs: Iterable[subprocess.Popen[bytes]], grace_s: float) -> None` |
| `run_console` | `(args: argparse.Namespace) -> int` |
| `build_parser` | `() -> argparse.ArgumentParser` |
| `main` | `(argv: Sequence[str] \| None = None) -> None` |

### `backend/spike/jev_spike.py`

The Jev checklist against hand-written facts. Calls the API unless `--dry-run`; writes a markdown results file and raw JSON under `backend/logs/spike/<stamp>/`.

| Name | Meaning |
| --- | --- |
| `RULES` | `dict[str, str]`: `speed`, `gap`, `passing`, `zone` to the four preset texts |
| `GAP_RULE_POSITIVE` | The positive rephrase of the gap rule offered by the console |
| `item_1_hello` ... `item_8_latency` | The eight checklist items: hello world and model version, fact sets, numeric probes, request shapes, JSON versus prose, negation, stability, latency |
| `add_arguments`, `run_cli`, `main` | the module CLI (`--items`, `--repeats`, `--dry-run`) |

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
| `components/road-view.tsx` | `RoadView()` |
| `components/constraint-panel.tsx` | `ConstraintPanel()` |
| `components/approval-queue.tsx` | `ApprovalQueue()` |
| `components/decision-strip.tsx` | `DecisionStrip()` |
| `components/inspector-drawer.tsx` | `InspectorDrawer()` |
| `components/metrics-view.tsx` | `MetricsView()` |

Component behaviour is described in [Components](../developer-guide/frontend/components.md).
