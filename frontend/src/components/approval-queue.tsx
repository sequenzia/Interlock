import { useEffect, useState } from "react";
import { fmtP } from "../format";
import { useStore } from "../store";
import type { OperatorAnswer } from "../types";
import { send } from "../ws-client";

const EMPTY_COUNTS: Record<string, number> = {};

export function ApprovalQueue() {
  const escalation = useStore((s) => s.escalation);
  const shieldOn = useStore((s) => s.session?.shield_on ?? true);
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
    return (
      <section className="panel">
        <div className="panel-title">
          <span>Approval queue</span>
          <span className="font-normal tracking-normal text-zinc-500 normal-case">
            {approved + denied > 0 ? `${approved} approved · ${denied} denied` : "empty"}
          </span>
        </div>
        <div className="p-3 text-zinc-500">
          {shieldOn ? "Nothing waiting. The shield is deciding on its own." : "Shield is off. Nothing escalates."}
        </div>
      </section>
    );
  }

  const remaining = expiresAt === null ? null : Math.max(0, expiresAt * 1000 - now) / 1000;
  const resolve = (decision: OperatorAnswer): void =>
    send({ type: "resolve", escalation_id: escalation.id, decision });

  return (
    <section className="panel border-violet-500/60 shadow-[0_0_24px_rgba(167,139,250,0.15)]">
      <div className="panel-title text-violet-300">
        <span>Approval queue</span>
        <span className="font-normal tracking-normal normal-case">step {escalation.step}</span>
      </div>
      <div className="flex flex-col gap-2.5 p-3">
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
            <div className="h-full rounded bg-violet-400" style={{ width: `${escalation.p * 100}%` }} />
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
        <div className="text-[11px] text-zinc-500">
          Deny executes {escalation.fallback}.
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
