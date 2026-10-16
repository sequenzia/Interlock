// Mirrors the JSONL log record (plan section 7) and the WebSocket protocol
// (plan section 8). Change the plan first, then backend/logger.py, then this.

export type ActionName = "LANE_LEFT" | "IDLE" | "LANE_RIGHT" | "FASTER" | "SLOWER";
export type DecisionKind = "allow" | "fallback" | "escalate" | "all_blocked";
export type JudgeSource = "live" | "cache" | "unavailable";
export type OperatorAnswer = "approve" | "deny";

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
  latency_ms: number;
  operator: string;
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
  judge: Judge;
  reward: number;
  crashed: boolean;
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
  judge_unavailable: boolean;
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
  cost_usd: number;
  judge_sources?: Record<string, number>;
  latency_ms_p50?: number;
  latency_ms_p95?: number;
  input_tokens?: number;
}

export interface Preset {
  checker: string;
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

export type ServerMessage =
  | ({ type: "hello" } & Hello)
  | ({ type: "state" } & SessionState)
  | { type: "history"; records: LogRecord[] }
  | { type: "step"; record: LogRecord }
  | { type: "escalation"; escalation: Escalation }
  | { type: "constraints"; constraints: Constraint[]; zones: Zone[] }
  | ({ type: "metrics" } & Metrics)
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
  | { type: "resolve"; escalation_id: string; decision: OperatorAnswer }
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
  crash_rate: number;
  mean_return: number;
  cost_per_episode_usd: number;
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
}

export interface EvalReport {
  available: boolean;
  message?: string;
  generated_at?: string;
  thresholds_default?: Thresholds;
  before_after?: { off: RunReport | null; on: RunReport | null };
  sweep?: SweepPoint[];
  calibration?: { overall: Reliability; by_checker: Record<string, Reliability> };
}
