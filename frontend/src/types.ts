// Mirrors the JSONL log record (plan section 7) and the WebSocket protocol
// (plan section 8). Change the plan first, then backend/logger.py, then this.

export type ActionName = "LANE_LEFT" | "IDLE" | "LANE_RIGHT" | "FASTER" | "SLOWER";
export type DecisionKind = "allow" | "fallback" | "escalate" | "all_blocked";
export type JudgeSource = "live" | "cache" | "unavailable";
export type OperatorAnswer = "approve" | "deny" | "override";
export type EscalationReason = "uncertain" | "no_compliant_action";
export type FallbackKind = "safe" | "least_bad" | "last_resort";

export interface Thresholds {
  t_allow: number;
  t_block: number;
}

export interface Constraint {
  id: string;
  text: string;
  enabled: boolean;
  checker: string | null;
}

export interface Zone {
  name: string;
  lane: number;
  start_m: number;
  end_m: number;
}

export interface Check {
  constraint_id: string;
  p_violation: number;
  ground_truth: boolean | null;
}

export interface Candidate {
  action: ActionName;
  rank: number;
  q: number;
  facts: Record<string, unknown>;
  sentences: string[];
  checks: Check[];
}

export interface Human {
  decision: OperatorAnswer;
  action: ActionName | null; // set only for an override
  latency_ms: number;
  operator: string;
}

export interface FallbackChoice {
  action: ActionName;
  kind: FallbackKind;
}

export interface JevQuestion {
  type: "noul";
  instructions: string;
  criteria?: { true: string; false: string };
}

export interface Exchange {
  action: ActionName;
  source: JudgeSource;
  latency_ms: number;
  asked: string[];
  request_id: string | null;
  response: unknown;
}

export interface Judge {
  model: string;
  source: JudgeSource;
  latency_ms: number;
  input_tokens: number;
  cost_usd: number;
  questions?: Record<string, JevQuestion>;
  exchanges?: Exchange[];
}

export interface Ego {
  lane: number;
  speed_mps: number;
  x_m: number;
}

export interface VehicleSnapshot {
  id: number;
  lane: number;
  x_m: number;
  speed_mps: number;
}

export interface FloorRecord {
  applied: boolean; // shield on and a floor above 0: the executable set was filtered
  removed: ActionName[]; // candidates under the time-to-collision floor, in rank order
}

export interface LogRecord {
  run_id: string;
  episode: number;
  step: number;
  seed: number;
  source: string;
  shield_on: boolean;
  thresholds: Thresholds;
  ego: Ego;
  vehicles: VehicleSnapshot[];
  zones: Zone[];
  constraints: Constraint[];
  candidates: Candidate[];
  decision: DecisionKind;
  executed: ActionName;
  fired_constraint: string | null;
  escalated: boolean;
  human: Human | null;
  all_blocked: boolean;
  escalation_reason: EscalationReason | null;
  fallback: FallbackChoice;
  floor?: FloorRecord; // absent in logs written before Oct 17
  judge: Judge;
  reward: number;
  crashed: boolean;
}

export interface EscalationCandidate {
  action: ActionName;
  rank: number;
  p: number; // worst p(violation) across enabled rules
  constraint_id: string | null; // the rule behind that p
  noop: boolean; // the action would not change lane or target speed
}

export interface Escalation {
  id: string;
  step: number;
  action: ActionName;
  sentences: string[];
  constraint_id: string | null;
  constraint_text: string | null;
  p: number;
  q_rank: number;
  fallback: ActionName;
  fallback_kind: FallbackKind;
  judge_unavailable: boolean;
  reason: EscalationReason;
  candidates: EscalationCandidate[]; // every ranked action, rank 0 is the proposal
  expires_at: number | null;
  timeout_s: number | null;
}

export interface SessionState {
  playing: boolean;
  paused_on_escalation_id: string | null;
  shield_on: boolean;
  source: "live" | "replay";
  judge_mode: "live" | "mock";
  episode: number;
  seed: number;
  run_id: string;
  speed: number;
  step: number;
  total_steps: number | null;
  done: boolean;
  thresholds: Thresholds;
  floor_s: number; // time-to-collision floor in seconds, 0 when off; set at launch
}

export interface Metrics {
  run_id?: string;
  steps: number;
  return: number;
  crashed: boolean;
  decisions: Record<string, number>;
  violations: Record<string, number>;
  violations_total: number;
  human: Record<string, number>;
  conflicts?: number; // escalations with no compliant action
  cost_usd: number;
  judge_sources?: Record<string, number>;
  latency_ms_p50?: number;
  latency_ms_p95?: number;
  input_tokens?: number;
}

export interface Preset {
  id: string;
  checker: string | null;
  text: string;
}

export interface ZoneDefaults {
  lane: number;
  ahead_m: number;
  length_m: number;
  name: string;
}

export interface Hello {
  config: {
    lanes_count: number;
    duration: number;
    vehicles_count: number;
    policy_frequency: number;
    action_names: ActionName[];
    steps_per_sec: number;
    escalation_timeout_s: number | null;
  };
  presets: Preset[];
  zone_defaults: ZoneDefaults;
  runs: string[];
  constraints: Constraint[];
  zones: Zone[];
}

export interface TwinStep {
  step: number;
  ego: Ego;
  vehicles: VehicleSnapshot[];
  executed: ActionName;
  violations: number;
  violations_so_far: number;
  crashed: boolean;
}

export interface Twin {
  seed: number;
  run_id: string | null;
  rules: number; // enabled rules with a checker in the session now: what the counts are scored against
  rule_ids: string[]; // their ids, in rule order
  steps: TwinStep[]; // empty when no shield-off log exists for the seed
  violations_total: number; // over the whole twin run, against those rules
  crashed_at: number | null;
}

export type ServerMessage =
  | ({ type: "hello" } & Hello)
  | ({ type: "state" } & SessionState)
  | { type: "history"; records: LogRecord[] }
  | { type: "step"; record: LogRecord }
  | { type: "escalation"; escalation: Escalation }
  | { type: "constraints"; constraints: Constraint[]; zones: Zone[] }
  | ({ type: "metrics" } & Metrics)
  | ({ type: "twin" } & Twin)
  | { type: "error"; message: string };

export type ClientMessage =
  | { type: "play" }
  | { type: "pause" }
  | { type: "step" }
  | { type: "reset"; seed: number }
  | { type: "set_speed"; steps_per_sec: number }
  | { type: "set_shield"; on: boolean }
  | { type: "set_thresholds"; t_allow: number; t_block: number }
  | { type: "add_constraint"; text: string; checker?: string }
  | { type: "toggle_constraint"; id: string; enabled: boolean }
  | { type: "remove_constraint"; id: string }
  | { type: "drop_zone"; lane?: number; ahead_m?: number; length_m?: number; name?: string }
  | { type: "resolve"; escalation_id: string; decision: OperatorAnswer; action?: ActionName }
  | { type: "load_replay"; run_id: string }
  | { type: "load_live" };

// Evaluation report written by backend.evaluate (internal/eval/latest.json).

export interface EpisodeMetrics {
  seed: number;
  steps: number;
  return: number;
  crashed: boolean;
  violations_total: number;
  escalations: number;
  all_blocked: number;
}

export interface AggregateMetrics {
  episodes: number;
  steps: number;
  violations_per_episode: number;
  violations_per_episode_std: number;
  violations_by_constraint: Record<string, number>;
  mean_return: number;
  crash_rate: number;
  escalation_rate: number;
  all_blocked_rate: number;
  human: Record<string, number>;
  latency_ms_p50: number;
  latency_ms_p95: number;
  cost_usd: number;
  cost_per_episode_usd: number;
}

export interface RunReport {
  label: string;
  shield_on: boolean;
  thresholds: Thresholds;
  seeds: number[];
  jev_mode: string;
  created: string;
  episodes: EpisodeMetrics[];
  aggregate: AggregateMetrics;
}

export interface SweepPoint {
  label: string;
  t_allow: number;
  t_block: number;
  violations_per_episode: number;
  escalation_rate: number;
  all_blocked_rate: number;
  conflict_rate?: number;
  floored_rate?: number;
  crash_rate: number;
  mean_return: number;
  cost_per_episode_usd: number;
}

export interface FloorCells {
  label: string;
  crash_rate: number;
  violations_per_episode: number;
  mean_return: number;
  escalation_rate: number;
  floored_rate: number;
  floor_all_rate: number;
}

export interface FloorRow {
  t_allow: number;
  t_block: number;
  by_floor: Record<string, FloorCells>; // keyed by the floor in seconds as text: "0", "1", "2"
}

export interface JudgeSummary {
  overall: Reliability;
  by_group: Record<string, Reliability>;
  answered?: number;
  failed?: number;
  live?: number;
  cached?: number;
  latency_ms_p50?: number | null;
  latency_ms_p95?: number | null;
  input_tokens?: number;
  output_tokens?: number;
  cost_usd?: number | null;
}

export interface Baseline {
  generated_at: string;
  checks: number;
  strata: Record<string, { violation: number; ok: number }>;
  jev: JudgeSummary;
  models: Record<string, JudgeSummary>;
}

export interface ReliabilityBin {
  lo: number;
  hi: number;
  count: number;
  mean_p: number | null;
  observed: number | null;
}

export interface Reliability {
  n: number;
  positives: number;
  bins: ReliabilityBin[];
  ece: number;
  brier: number;
  accuracy_at_0_5: number;
  label_source?: string; // "checker", or the labeler on the rows: "human", "autolabel", or both joined with "+"
}

export interface EvalReport {
  available: boolean;
  message?: string;
  generated_at?: string;
  thresholds_default?: Thresholds;
  before_after?: { off: RunReport | null; on: RunReport | null };
  sweep?: SweepPoint[];
  floor?: { floor_s: number; rows: FloorRow[] };
  baseline?: Baseline | null;
  calibration?: { overall: Reliability; by_checker: Record<string, Reliability> };
}
