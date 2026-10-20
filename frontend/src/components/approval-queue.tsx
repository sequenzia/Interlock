import { useEffect, useState } from "react";
import { FALLBACK_LABEL, REASON_LABEL, fmtP } from "../format";
import { useStore } from "../store";
import type { Escalation, EscalationCandidate, OperatorAnswer, Thresholds } from "../types";
import { send } from "../ws-client";

const EMPTY_COUNTS: Record<string, number> = {};
const DEFAULT_THRESHOLDS: Thresholds = { t_allow: 0.3, t_block: 0.7 };
const FACTS_SHOWN = 3;

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

function pTone(p: number, t: Thresholds): string {
  if (p < t.t_allow) return "text-allow";
  if (p > t.t_block) return "text-blocked";
  return "text-escalate";
}

/** The probability against the three bands, so the number has a place to sit. */
function PBar({ p, t }: { p: number; t: Thresholds }) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-baseline justify-between text-2xs text-zinc-400">
        <span>p(violation)</span>
        <span className={`num text-sm font-semibold ${pTone(p, t)}`}>{fmtP(p)}</span>
      </div>
      <div className="relative h-2 overflow-hidden rounded-full bg-zinc-800">
        <div className="absolute inset-y-0 left-0 bg-allow/35" style={{ width: `${t.t_allow * 100}%` }} />
        <div className="absolute inset-y-0 bg-escalate/35" style={{ left: `${t.t_allow * 100}%`, width: `${(t.t_block - t.t_allow) * 100}%` }} />
        <div className="absolute inset-y-0 right-0 bg-blocked/35" style={{ width: `${(1 - t.t_block) * 100}%` }} />
        <div className="absolute inset-y-0 w-0.5 -translate-x-1/2 bg-white" style={{ left: `${p * 100}%` }} />
      </div>
    </div>
  );
}

export function ApprovalQueue() {
  const escalation = useStore((s) => s.escalation);
  const shieldOn = useStore((s) => s.session?.shield_on ?? true);
  const thresholds = useStore((s) => s.session?.thresholds) ?? DEFAULT_THRESHOLDS;
  const constraints = useStore((s) => s.constraints);
  const human = useStore((s) => s.metrics?.human) ?? EMPTY_COUNTS;
  const [now, setNow] = useState(() => Date.now());
  const [allFacts, setAllFacts] = useState(false);
  const expiresAt = escalation?.expires_at ?? null;
  const escalationId = escalation?.id;

  useEffect(() => setAllFacts(false), [escalationId]);
  useEffect(() => {
    if (expiresAt === null) return;
    const id = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(id);
  }, [expiresAt]);

  const approved = human["approve"] ?? 0;
  const denied = human["deny"] ?? 0;
  const overridden = human["override"] ?? 0;
  const counts = [
    approved > 0 && `${approved} approved`,
    denied > 0 && `${denied} denied`,
    overridden > 0 && `${overridden} overridden`,
  ].filter((s): s is string => typeof s === "string");

  if (!escalation) {
    const state = !shieldOn
      ? "shield off, nothing escalates"
      : constraints.some((c) => c.enabled)
        ? "empty, the shield is deciding on its own"
        : "empty, no rules yet";
    return (
      <section className="panel shrink-0">
        <div className="panel-title">
          <span className="whitespace-nowrap">Approval queue</span>
          <span className="panel-subtitle min-w-0 truncate">
            {state}
            {counts.length > 0 && ` · ${counts.join(" · ")}`}
          </span>
        </div>
      </section>
    );
  }

  const conflict = escalation.reason === "no_compliant_action";
  const remaining = expiresAt === null ? null : Math.max(0, expiresAt * 1000 - now) / 1000;
  const fill = remaining !== null && escalation.timeout_s ? Math.min(1, remaining / escalation.timeout_s) : 0;
  const resolve = (decision: OperatorAnswer): void => send({ type: "resolve", escalation_id: escalation.id, decision });
  const ruleText = (cid: string | null): string => (cid === null ? "" : (constraints.find((c) => c.id === cid)?.text ?? cid));
  const facts = allFacts ? escalation.sentences : escalation.sentences.slice(0, FACTS_SHOWN);
  // Written out in full so Tailwind sees both variants.
  const reasonBadge = conflict ? "border-blocked/50 bg-blocked/15 text-blocked" : "border-escalate/50 bg-escalate/15 text-escalate";
  const quoteBorder = conflict ? "border-blocked/60" : "border-escalate/60";

  return (
    <section
      className={`panel enter shrink-0 ${
        conflict ? "border-blocked/60 shadow-[0_0_24px_rgba(251,113,133,0.12)]" : "border-escalate/60 shadow-[0_0_24px_rgba(167,139,250,0.15)]"
      }`}
    >
      <div className={`panel-title ${conflict ? "text-blocked" : "text-escalate"}`}>
        <span className="flex items-center gap-2">
          Approval queue
          <span className={`badge ${reasonBadge}`}>{REASON_LABEL[escalation.reason]}</span>
        </span>
        <span className="panel-subtitle num">step {escalation.step}</span>
      </div>
      <div className="flex flex-col gap-3 p-3">
        <div className="flex items-baseline justify-between gap-2">
          <span className="font-mono text-xl font-semibold text-zinc-50">{escalation.action}</span>
          <span className="text-xs text-zinc-400">
            proposed by the policy · rank <span className="num">{escalation.q_rank + 1}</span>
          </span>
        </div>
        <PBar p={escalation.p} t={thresholds} />

        <div className="flex gap-2">
          <button className="btn btn-primary flex-1 py-2 text-sm" onClick={() => resolve("approve")}>
            approve <kbd className="kbd">a</kbd>
          </button>
          <button className="btn btn-danger relative flex-1 overflow-hidden py-2 text-sm" onClick={() => resolve("deny")}>
            {fill > 0 && (
              <span
                aria-hidden="true"
                className="absolute inset-y-0 left-0 bg-blocked/25 transition-[width] duration-200 ease-linear"
                style={{ width: `${fill * 100}%` }}
              />
            )}
            <span className="relative flex items-center gap-1.5">
              deny <kbd className="kbd">d</kbd>
              {remaining !== null && <span className="num text-rose-200/80">· auto in {remaining.toFixed(0)} s</span>}
            </span>
          </button>
        </div>
        <p className="text-xs leading-snug text-zinc-400">
          {conflict ? "No candidate is confidently safe. " : "The proposal sits inside the uncertain band. "}
          Deny executes <span className="font-mono text-zinc-200">{escalation.fallback}</span> ({FALLBACK_LABEL[escalation.fallback_kind]}{" "}
          fallback).
        </p>
        {escalation.judge_unavailable && (
          <span className="badge w-fit border-blocked/50 bg-blocked/15 text-blocked">judge unavailable, p is a placeholder</span>
        )}

        {escalation.constraint_text && (
          <blockquote className={`rounded-md border-l-2 bg-zinc-800/50 px-2.5 py-1.5 text-sm text-zinc-100 ${quoteBorder}`}>
            "{escalation.constraint_text}"
          </blockquote>
        )}

        <div>
          <div className="mb-1 flex items-center justify-between">
            <span className="stat-label">facts Jev saw</span>
            {escalation.sentences.length > FACTS_SHOWN && (
              <button type="button" className="chip" onClick={() => setAllFacts((v) => !v)}>
                {allFacts ? "fewer" : `all ${escalation.sentences.length} facts`}
              </button>
            )}
          </div>
          <ul className="list-disc pl-4 text-xs leading-snug text-zinc-200">
            {facts.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </div>

        <div>
          <div className="mb-1 flex items-center justify-between">
            <span className="stat-label">{conflict ? "every candidate, best Q first" : "or run another candidate"}</span>
            <span className="text-2xs text-zinc-400">click one, or press its number</span>
          </div>
          <ol className="flex flex-col gap-1">
            {escalation.candidates.map((c, i) => {
              const text = ruleText(c.constraint_id);
              return (
                <li key={c.action}>
                  <button
                    type="button"
                    aria-label={`${c.action}: ${c.rank === 0 ? "approve the proposal" : "override"}`}
                    title={c.constraint_id ? `${c.constraint_id} "${text}"` : "no rule fired"}
                    onClick={() => answerWith(escalation, c)}
                    className={`flex w-full items-center gap-2 rounded-md border px-2 py-1 text-left text-xs transition-colors hover:bg-zinc-800 ${
                      c.rank === 0 ? "border-zinc-600 bg-zinc-800/70" : "border-zinc-800 bg-zinc-900/40 hover:border-zinc-600"
                    }`}
                  >
                    <kbd className="kbd">{i + 1}</kbd>
                    <span className={`w-24 font-mono ${c.rank === 0 ? "font-semibold text-zinc-50" : "text-zinc-200"}`}>{c.action}</span>
                    <span className={`num w-9 text-right ${pTone(c.p, thresholds)}`}>{fmtP(c.p)}</span>
                    <span className="min-w-0 flex-1 truncate text-zinc-400">
                      {c.constraint_id ? (
                        <>
                          <span className="font-mono text-zinc-500">{c.constraint_id}</span> {text}
                        </>
                      ) : (
                        "no rule fired"
                      )}
                    </span>
                    {c.rank === 0 && <span className="text-[0.625rem] text-escalate uppercase">proposal</span>}
                    {c.noop && <span className="text-[0.625rem] text-zinc-500 uppercase">no-op</span>}
                  </button>
                </li>
              );
            })}
          </ol>
        </div>
      </div>
    </section>
  );
}
