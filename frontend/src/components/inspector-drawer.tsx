import { useEffect, useMemo, useState } from "react";
import { DECISION_CLASS, DECISION_LABEL, fmtMs, fmtP, fmtUsd } from "../format";
import { selectInspected, useStore } from "../store";
import type { ActionName, Candidate, LogRecord } from "../types";
import { send } from "../ws-client";

function pClass(p: number, tAllow: number, tBlock: number): string {
  if (p < tAllow) return "bg-emerald-500/15 text-emerald-200";
  if (p > tBlock) return "bg-rose-500/20 text-rose-200";
  return "bg-violet-500/20 text-violet-200";
}

function truthMark(truth: boolean | null): string {
  if (truth === null) return "";
  return truth ? " ●" : " ○";
}

function candidateExchange(record: LogRecord, candidate: Candidate) {
  const exchange = record.judge.exchanges?.find((e) => e.action === candidate.action) ?? null;
  if (!exchange) return null;
  const questions = record.judge.questions ?? {};
  const asked = Object.fromEntries(exchange.asked.map((cid) => [cid, questions[cid]]));
  return {
    exchange,
    request: { model: record.judge.model, state: candidate.facts, questions: asked },
  };
}

export function InspectorDrawer() {
  const record = useStore(selectInspected);
  const selected = useStore((s) => s.selectedStep);
  const selectStep = useStore((s) => s.selectStep);
  const stepCount = useStore((s) => s.steps.length);
  const [action, setAction] = useState<ActionName | null>(null);
  const [tab, setTab] = useState<"facts" | "raw">("facts");
  const step = record?.step;
  useEffect(() => setAction(null), [step]);

  const chosen = useMemo(() => {
    if (!record) return null;
    return record.candidates.find((c) => c.action === action) ?? record.candidates[0] ?? null;
  }, [record, action]);

  if (!record || selected === null || !chosen) return null;

  const columns = record.candidates[0]?.checks.map((c) => c.constraint_id) ?? [];
  const textOf = (cid: string): string => record.constraints.find((c) => c.id === cid)?.text ?? cid;
  const qs = record.candidates.map((c) => c.q);
  const qMin = Math.min(...qs);
  const qMax = Math.max(...qs);
  const { t_allow, t_block } = record.thresholds;
  const raw = candidateExchange(record, chosen);
  const fired = record.fired_constraint;

  return (
    <section className="panel flex h-[340px] shrink-0 flex-col border-violet-500/40">
      <div className="panel-title">
        <span className="flex items-center gap-2">
          <span className="text-violet-300">Inspector · step {record.step}</span>
          <span className={`badge ${DECISION_CLASS[record.decision]}`}>
            {DECISION_LABEL[record.decision]}
            {record.executed !== record.candidates[0]?.action && ` -> ${record.executed}`}
          </span>
          {fired && record.decision !== "allow" && (
            <span className="font-normal tracking-normal text-zinc-400 normal-case">
              fired {fired} "{textOf(fired)}"
            </span>
          )}
          {record.human && (
            <span className="badge border-violet-500/40 text-violet-200">
              operator {record.human.decision} in {fmtMs(record.human.latency_ms)}
            </span>
          )}
        </span>
        <span className="flex items-center gap-2 font-normal tracking-normal text-zinc-400 normal-case">
          <span>
            jev {record.judge.source} · {fmtMs(record.judge.latency_ms)} · {record.judge.model} ·{" "}
            {fmtUsd(record.judge.cost_usd)} · reward {record.reward.toFixed(2)}
          </span>
          <button className="btn px-1.5 py-0" onClick={() => selectStep(Math.max(0, selected - 1))} disabled={selected === 0}>
            ←
          </button>
          <button
            className="btn px-1.5 py-0"
            onClick={() => selectStep(Math.min(stepCount - 1, selected + 1))}
            disabled={selected >= stepCount - 1}
          >
            →
          </button>
          <button className="btn px-1.5 py-0" onClick={() => selectStep(null)} title="follow live (esc)">
            ✕
          </button>
        </span>
      </div>
      <div className="grid min-h-0 flex-1 grid-cols-[minmax(380px,1fr)_minmax(0,1.2fr)] gap-2 p-2">
        <div className="min-h-0 overflow-auto">
          <table className="w-full border-separate border-spacing-y-0.5 text-[11px]">
            <thead className="text-left text-zinc-500">
              <tr>
                <th className="px-1 font-normal">#</th>
                <th className="px-1 font-normal">candidate</th>
                <th className="px-1 font-normal">Q</th>
                {columns.map((cid) => (
                  <th key={cid} className="px-1 font-normal" title={textOf(cid)}>
                    {cid}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {record.candidates.map((c) => {
                const isChosen = c.action === chosen.action;
                const isExecuted = c.action === record.executed;
                const width = qMax === qMin ? 100 : ((c.q - qMin) / (qMax - qMin)) * 100;
                return (
                  <tr
                    key={c.action}
                    onClick={() => setAction(c.action)}
                    className={`cursor-pointer ${isChosen ? "bg-zinc-800" : "hover:bg-zinc-800/50"}`}
                  >
                    <td className="px-1 text-zinc-500">{c.rank + 1}</td>
                    <td className="px-1 whitespace-nowrap">
                      <span className={isExecuted ? "font-semibold text-zinc-50" : "text-zinc-300"}>{c.action}</span>
                      {isExecuted && <span className="ml-1 text-[9px] text-emerald-300 uppercase">ran</span>}
                      {c.rank === 0 && !isExecuted && <span className="ml-1 text-[9px] text-rose-300 uppercase">blocked</span>}
                    </td>
                    <td className="px-1">
                      <div className="flex items-center gap-1">
                        <div className="h-1.5 w-14 rounded bg-zinc-800">
                          <div className="h-full rounded bg-cyan-400/80" style={{ width: `${Math.max(4, width)}%` }} />
                        </div>
                        <span className="tabular-nums text-zinc-400">{c.q.toFixed(2)}</span>
                      </div>
                    </td>
                    {columns.map((cid) => {
                      const check = c.checks.find((k) => k.constraint_id === cid);
                      if (!check) return <td key={cid} className="px-1 text-zinc-600">-</td>;
                      return (
                        <td
                          key={cid}
                          className={`rounded px-1.5 text-center tabular-nums ${pClass(check.p_violation, t_allow, t_block)}`}
                          title={`${textOf(cid)}\np(violation) ${fmtP(check.p_violation)}\nground truth: ${
                            check.ground_truth === null ? "no checker" : check.ground_truth ? "violation" : "ok"
                          }`}
                        >
                          {fmtP(check.p_violation)}
                          <span className="text-[9px] opacity-80">{truthMark(check.ground_truth)}</span>
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="mt-1 px-1 text-[10px] text-zinc-500">
            cells colored by thresholds {t_allow.toFixed(2)} / {t_block.toFixed(2)} · ● checker says violation · ○ checker says ok
          </div>
        </div>
        <div className="flex min-h-0 flex-col">
          <div className="mb-1 flex items-center gap-1 text-[11px]">
            <span className="mr-1 text-zinc-400">{chosen.action}</span>
            <button className={`chip ${tab === "facts" ? "border-zinc-400 text-zinc-100" : ""}`} onClick={() => setTab("facts")}>
              facts
            </button>
            <button className={`chip ${tab === "raw" ? "border-zinc-400 text-zinc-100" : ""}`} onClick={() => setTab("raw")}>
              raw request and response
            </button>
            {raw ? (
              <span className="ml-auto text-zinc-500">
                {raw.exchange.source} · {fmtMs(raw.exchange.latency_ms)} · asked {raw.exchange.asked.join(", ")}
                {raw.exchange.request_id && ` · ${raw.exchange.request_id}`}
              </span>
            ) : (
              <span className="ml-auto text-zinc-500">
                {record.judge.exchanges ? "no request sent: every answer came from the cache" : "no exchange in this log"}
              </span>
            )}
          </div>
          {tab === "facts" ? (
            <div className="grid min-h-0 flex-1 grid-cols-2 gap-2">
              <ul className="min-h-0 list-disc overflow-auto pl-4 text-[11px] leading-snug text-zinc-300">
                {chosen.sentences.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
              <pre className="min-h-0 overflow-auto rounded bg-zinc-950/60 p-2 text-[10px] leading-snug text-zinc-400">
                {JSON.stringify(chosen.facts, null, 1)}
              </pre>
            </div>
          ) : (
            <div className="grid min-h-0 flex-1 grid-cols-2 gap-2">
              <pre className="min-h-0 overflow-auto rounded bg-zinc-950/60 p-2 text-[10px] leading-snug text-zinc-400">
                {raw ? JSON.stringify(raw.request, null, 1) : "no request"}
              </pre>
              <pre className="min-h-0 overflow-auto rounded bg-zinc-950/60 p-2 text-[10px] leading-snug text-zinc-400">
                {raw ? JSON.stringify(raw.exchange.response, null, 1) : "no response"}
              </pre>
            </div>
          )}
          {record.escalated && record.human === null && (
            <button className="btn btn-primary mt-1 self-start" onClick={() => send({ type: "pause" })}>
              pause
            </button>
          )}
        </div>
      </div>
    </section>
  );
}
