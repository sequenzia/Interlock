import type { ActionName, DecisionKind, EscalationReason, FallbackKind, LogRecord } from "./types";

export const fmtP = (p: number): string => p.toFixed(2);
export const fmtMs = (ms: number): string => `${Math.round(ms)} ms`;
export const fmtUsd = (usd: number): string => (usd < 0.01 ? `$${usd.toFixed(4)}` : `$${usd.toFixed(3)}`);
export const fmtSpeed = (mps: number): string => `${mps.toFixed(1)} m/s`;
export const fmtPct = (v: number, digits = 0): string => `${(v * 100).toFixed(digits)}%`;

export const DECISION_LABEL: Record<DecisionKind, string> = {
  allow: "allowed",
  fallback: "fallback",
  escalate: "escalated",
  all_blocked: "all blocked",
};

// Tailwind classes per outcome; the same hues drive the canvas and the timeline.
export const DECISION_CLASS: Record<DecisionKind, string> = {
  allow: "bg-allow/15 text-allow border-allow/40",
  fallback: "bg-fallback/15 text-fallback border-fallback/40",
  escalate: "bg-escalate/15 text-escalate border-escalate/40",
  all_blocked: "bg-blocked/15 text-blocked border-blocked/40",
};

// Hex twins of the @theme tokens in styles.css, for Canvas 2D and inline styles.
export const DECISION_COLOR: Record<DecisionKind, string> = {
  allow: "#34d399",
  fallback: "#fbbf24",
  escalate: "#a78bfa",
  all_blocked: "#fb7185",
};
export const HAZARD_COLOR = "#fb923c";
export const ACCENT_COLOR = "#22d3ee";

export const REASON_LABEL: Record<EscalationReason, string> = {
  uncertain: "uncertain",
  no_compliant_action: "no compliant action",
};

export const FALLBACK_LABEL: Record<FallbackKind, string> = {
  safe: "safe",
  least_bad: "least bad",
  last_resort: "last resort",
};

/** A lane change at the edge of the road changes nothing. */
export function isLaneNoop(action: ActionName, lane: number, laneCount: number): boolean {
  return (action === "LANE_LEFT" && lane <= 1) || (action === "LANE_RIGHT" && lane >= laneCount);
}

/**
 * Ids of the rules the executed action broke by the ground-truth checkers, in column order.
 * Scoring after the fact: the shield never reads these, and a rule without a checker never appears.
 */
export function violatedRules(r: LogRecord): string[] {
  const executed = r.candidates.find((c) => c.action === r.executed);
  return executed ? executed.checks.filter((c) => c.ground_truth === true).map((c) => c.constraint_id) : [];
}

/** The root font size as a multiple of 16px, so canvas text follows the density toggle. */
export function uiScale(): number {
  const px = parseFloat(getComputedStyle(document.documentElement).fontSize);
  return Number.isFinite(px) && px > 0 ? px / 16 : 1;
}
