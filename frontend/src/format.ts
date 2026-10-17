import type { DecisionKind, EscalationReason, FallbackKind } from "./types";

export const fmtP = (p: number): string => p.toFixed(2);
export const fmtMs = (ms: number): string => `${Math.round(ms)} ms`;
export const fmtUsd = (usd: number): string => (usd < 0.01 ? `$${usd.toFixed(4)}` : `$${usd.toFixed(3)}`);
export const fmtSpeed = (mps: number): string => `${mps.toFixed(1)} m/s`;

export const DECISION_LABEL: Record<DecisionKind, string> = {
  allow: "allowed",
  fallback: "fallback",
  escalate: "escalated",
  all_blocked: "all blocked",
};

// Tailwind classes per outcome; the same hues drive the canvas and the timeline.
export const DECISION_CLASS: Record<DecisionKind, string> = {
  allow: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
  fallback: "bg-amber-500/20 text-amber-300 border-amber-500/40",
  escalate: "bg-violet-500/20 text-violet-300 border-violet-500/40",
  all_blocked: "bg-rose-500/20 text-rose-300 border-rose-500/40",
};

export const DECISION_COLOR: Record<DecisionKind, string> = {
  allow: "#34d399",
  fallback: "#fbbf24",
  escalate: "#a78bfa",
  all_blocked: "#fb7185",
};

export const REASON_LABEL: Record<EscalationReason, string> = {
  uncertain: "uncertain",
  no_compliant_action: "no compliant action",
};

export const FALLBACK_LABEL: Record<FallbackKind, string> = {
  safe: "safe",
  least_bad: "least bad",
  last_resort: "last resort",
};
