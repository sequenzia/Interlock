import { useEffect, useState } from "react";
import { FALLBACK_LABEL, REASON_LABEL, fmtP } from "../format";
import { useStore } from "../store";
import type { Escalation, EscalationCandidate, OperatorAnswer } from "../types";
import { send } from "../ws-client";

const EMPTY_COUNTS: Record<string, number> = {};

function answerWith(escalation: Escalation, candidate: EscalationCandidate): void {
  // Picking the proposal means approve; any other candidate is an override.
  if (candidate.rank === 0) {
    send({ type: "resolve", escalation_id: escalation.id, decision: "approve" });
  } else {
    send({ type: "resolve", escalation_id: escalation.id, decision: "override", action: candidate.action });
  }
}

/** Keyboard digits 1 to 5 answer with the candidate of that rank. */
export function resolveWithRank(escalation: Escalation, index: number): void {
  const candidate = escalation.candidates[index];
  if (candidate) answerWith(escalation, candidate);
}

export function ApprovalQueue() {
  const escalation = useStore((s) => s.escalation);
  const shieldOn = useStore((s) => s.session?.shield_on ?? true);
  const constraints = useStore((s) => s.constraints);
  const human = useStore((s) => s.metrics?.human) ?? EMPTY_COUNTS;
  const [now, setNow] = useState(() => Date.now());
  const expiresAt = escalation?.expires_at ?? null;

  useEffect(() => {
    if (expiresAt === null) return;
    const id = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(id);
  }, [expiresAt]);

  if (!escalation) {
    const approved = human["approve"] ?? 0;
    const denied = human["deny"] ?? 0;
    const overridden = human["override"] ?? 0;
    const counts = [
      approved > 0 && `${approved} approved`,
      denied > 0 && `${denied} denied`,
      overridden > 0 && `${overridden} overridden`,
    ].filter((s): s is string => typeof s === "string");
    return (
      <section className="panel">
        <div className="panel-title">
          <span>Approval queue</span>
          <span className="font-normal tracking-normal text-zinc-500 normal-case">
            {counts.length > 0 ? counts.join(" · ") : "empty"}
          </span>
        </div>
        <div className="p-3 text-zinc-500">
          {shieldOn ? "Nothing waiting. The shield is deciding on its own." : "Shield is off. Nothing escalates."}
        </div>
      </section>
    );
  }

  const conflict = escalation.reason === "no_compliant_action";
  const remaining = expiresAt === null ? null : Math.max(0, expiresAt * 1000 - now) / 1000;
  const resolve = (decision: OperatorAnswer): void =>
    send({ type: "resolve", escalation_id: escalation.id, decision });
  const ruleText = (cid: string | null): string =>
    cid === null ? "" : (constraints.find((c) => c.id === cid)?.text ?? cid);

  return (
    <section
      className={`panel ${
        conflict
          ? "border-amber-500/60 shadow-[0_0_24px_rgba(251,191,36,0.15)]"
          : "border-violet-500/60 shadow-[0_0_24px_rgba(167,139,250,0.15)]"
      }`}
    >
      <div className={`panel-title ${conflict ? "text-amber-300" : "text-violet-300"}`}>
        <span>Approval queue</span>
        <span className="font-normal tracking-normal normal-case">step {escalation.step}</span>
      </div>
      <div className="flex flex-col gap-2.5 p-3">
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={`badge w-fit ${
              conflict
                ? "border-amber-500/50 bg-amber-500/15 text-amber-200"
                : "border-violet-500/40 bg-violet-500/15 text-violet-200"
            }`}
          >
            {REASON_LABEL[escalation.reason]}
          </span>
          <span className="text-[11px] text-zinc-400">
            {conflict
              ? "No candidate is confidently safe. Pick one below, or deny to run the fallback."
              : "The proposal sits inside the uncertain band."}
          </span>
        </div>
        <div className="flex items-baseline gap-2">
          <span className="text-xl font-semibold text-zinc-50">{escalation.action}</span>
          <span className="text-zinc-400">proposed by the policy, rank {escalation.q_rank + 1}</span>
        </div>
        <div>
          <div className="flex justify-between text-[11px] text-zinc-400">
            <span>p(violation)</span>
            <span className="tabular-nums">{fmtP(escalation.p)}</span>
          </div>
          <div className="h-1.5 rounded bg-zinc-800">
            <div
              className={`h-full rounded ${conflict ? "bg-amber-400" : "bg-violet-400"}`}
              style={{ width: `${escalation.p * 100}%` }}
            />
          </div>
        </div>
        {escalation.constraint_text && (
          <div className="rounded border border-zinc-700 bg-zinc-800/60 p-2 text-zinc-100">
            "{escalation.constraint_text}"
          </div>
        )}
        {escalation.judge_unavailable && (
          <div className="badge w-fit border-rose-500/50 bg-rose-500/15 text-rose-300">
            judge unavailable, p is a placeholder
          </div>
        )}
        <ul className="list-disc pl-4 text-[12px] leading-snug text-zinc-300">
          {escalation.sentences.map((s, i) => (
            <li key={i}>{s}</li>
          ))}
        </ul>
        <div>
          <div className="mb-1 text-[11px] text-zinc-400">
            {conflict ? "Every candidate, best Q first. Click one to run it, or press its number." : "Or run another candidate (press its number):"}
          </div>
          <ol className={conflict ? "flex flex-col gap-1" : "flex flex-wrap gap-1"}>
            {escalation.candidates.map((c, i) => (
              <li key={c.action} className={conflict ? "" : "contents"}>
                <button
                  type="button"
                  aria-label={`${c.action}: ${c.rank === 0 ? "approve the proposal" : "override"}`}
                  title={c.constraint_id ? `${c.constraint_id} "${ruleText(c.constraint_id)}"` : "no rule fired"}
                  onClick={() => answerWith(escalation, c)}
                  className={
                    conflict
                      ? "flex w-full items-center gap-2 rounded border border-zinc-700 bg-zinc-800/60 px-2 py-1 text-left hover:border-amber-400 hover:bg-zinc-800"
                      : "chip flex items-center gap-1.5"
                  }
                >
                  <span className="text-[10px] tabular-nums text-zinc-500">{i + 1}</span>
                  <span className={c.rank === 0 ? "font-semibold text-zinc-50" : "text-zinc-200"}>{c.action}</span>
                  <span className="tabular-nums text-zinc-400">{fmtP(c.p)}</span>
                  {conflict && c.constraint_id && (
                    <span className="min-w-0 flex-1 truncate text-[11px] text-zinc-500">
                      {c.constraint_id} "{ruleText(c.constraint_id)}"
                    </span>
                  )}
                  {c.rank === 0 && <span className="text-[9px] text-violet-300 uppercase">proposal</span>}
                  {c.noop && <span className="text-[9px] text-zinc-500 uppercase">no-op</span>}
                </button>
              </li>
            ))}
          </ol>
        </div>
        <div className="text-[11px] text-zinc-500">
          Deny executes {escalation.fallback} ({FALLBACK_LABEL[escalation.fallback_kind]} fallback).
          {remaining !== null && ` Auto-deny in ${remaining.toFixed(0)} s.`}
        </div>
        <div className="flex gap-2">
          <button className="btn btn-primary flex-1 py-2" onClick={() => resolve("approve")}>
            approve <span className="text-cyan-300/70">(a)</span>
          </button>
          <button
            className="btn flex-1 border-rose-500/50 bg-rose-500/20 py-2 text-rose-100 hover:bg-rose-500/40"
            onClick={() => resolve("deny")}
          >
            deny <span className="text-rose-300/70">(d)</span>
          </button>
        </div>
      </div>
    </section>
  );
}
