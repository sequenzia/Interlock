import { useEffect, useMemo, useState } from "react";
import { DECISION_CLASS, DECISION_LABEL, FALLBACK_LABEL, REASON_LABEL, fmtMs, fmtP, fmtUsd } from "../format";
import { ChevronLeftIcon, ChevronRightIcon, CloseIcon } from "../icons";
import { selectInspected, useStore } from "../store";
import type { ActionName, Candidate, LogRecord } from "../types";
import { send } from "../ws-client";

function pClass(p: number, tAllow: number, tBlock: number): string {
  if (p < tAllow) return "bg-allow/15 text-allow";
  if (p > tBlock) return "bg-blocked/20 text-blocked";
  return "bg-escalate/20 text-escalate";
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

const JSON_CLASS = "min-h-0 overflow-auto rounded-md bg-zinc-950/70 p-2 font-mono text-2xs leading-snug text-zinc-400";

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
  const floored = new Set<string>(record.floor?.removed ?? []);
  const raw = candidateExchange(record, chosen);
  const fired = record.fired_constraint;

  return (
    <section className="panel enter flex h-[min(22rem,42vh)] shrink-0 flex-col">
      <div className="panel-title">
        {/* Priority left to right: step, outcome, the operator's answer, why it escalated, the fired rule. The last truncates first. */}
        <span className="flex min-w-0 flex-1 items-center gap-2 overflow-hidden">
          <span className="whitespace-nowrap text-zinc-100">Inspector · step {record.step}</span>
          <span className={`badge shrink-0 ${DECISION_CLASS[record.decision]}`}>
            {DECISION_LABEL[record.decision]}
            {record.executed !== record.candidates[0]?.action && <span className="font-mono"> → {record.executed}</span>}
          </span>
          {record.human && (
            <span className="badge shrink-0 border-escalate/40 text-escalate">
              operator {record.human.decision}
              {record.human.action && <span className="font-mono"> {record.human.action}</span>}
              <span className="font-normal normal-case"> in {fmtMs(record.human.latency_ms)}</span>
            </span>
          )}
          {record.escalated && (
            <span
              className="badge shrink-0 border-zinc-600 text-zinc-300"
              title={record.fallback ? `deny would have run ${record.fallback.action} (${FALLBACK_LABEL[record.fallback.kind]} fallback)` : undefined}
            >
              {record.escalation_reason ? REASON_LABEL[record.escalation_reason] : "escalated"}
            </span>
          )}
          {fired && record.decision !== "allow" && (
            <span className="panel-subtitle min-w-0 truncate" title={`fired ${fired}: ${textOf(fired)}`}>
              fired <span className="font-mono text-zinc-300">{fired}</span> "{textOf(fired)}"
            </span>
          )}
        </span>
        <span className="flex shrink-0 items-center gap-1">
          <button className="btn btn-icon" onClick={() => selectStep(Math.max(0, selected - 1))} disabled={selected === 0} aria-label="previous step" title="previous step (←)">
            <ChevronLeftIcon />
          </button>
          <button
            className="btn btn-icon"
            onClick={() => selectStep(Math.min(stepCount - 1, selected + 1))}
            disabled={selected >= stepCount - 1}
            aria-label="next step"
            title="next step (→)"
          >
            <ChevronRightIcon />
          </button>
          <button className="btn btn-icon" onClick={() => selectStep(null)} aria-label="follow live" title="follow live (esc)">
            <CloseIcon />
          </button>
        </span>
      </div>
      <div className="grid min-h-0 flex-1 grid-cols-[minmax(24rem,1fr)_minmax(0,1.2fr)] gap-2 p-2">
        <div className="min-h-0 overflow-auto">
          <table className="w-full border-separate border-spacing-y-0.5 text-xs">
            <thead className="text-left text-2xs text-zinc-400">
              <tr>
                <th className="px-1 font-normal">#</th>
                <th className="px-1 font-normal">candidate</th>
                <th className="px-1 font-normal">Q</th>
                {columns.map((cid) => (
                  <th key={cid} className="num px-1 text-center font-normal" title={textOf(cid)}>
                    {cid}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {record.candidates.map((c) => {
                const isChosen = c.action === chosen.action;
                const isExecuted = c.action === record.executed;
                const isFloored = floored.has(c.action);
                const width = qMax === qMin ? 100 : ((c.q - qMin) / (qMax - qMin)) * 100;
                return (
                  <tr
                    key={c.action}
                    onClick={() => setAction(c.action)}
                    className={`cursor-pointer ${isChosen ? "bg-zinc-800" : "hover:bg-zinc-800/50"} ${isFloored ? "opacity-50" : ""}`}
                  >
                    <td className="num px-1 text-zinc-500">{c.rank + 1}</td>
                    <td className="px-1 whitespace-nowrap">
                      <span className={`font-mono ${isExecuted ? "font-semibold text-zinc-50" : "text-zinc-300"}`}>{c.action}</span>
                      {isExecuted && <span className="ml-1.5 text-[0.625rem] text-allow uppercase">ran</span>}
                      {c.rank === 0 && !isExecuted && <span className="ml-1.5 text-[0.625rem] text-blocked uppercase">blocked</span>}
                      {isFloored && <span className="ml-1.5 text-[0.625rem] text-fallback uppercase">floor</span>}
                    </td>
                    <td className="px-1">
                      <div className="flex items-center gap-1.5">
                        <div className="h-1.5 w-14 rounded bg-zinc-800">
                          <div className="h-full rounded bg-zinc-400" style={{ width: `${Math.max(4, width)}%` }} />
                        </div>
                        <span className="num text-zinc-400">{c.q.toFixed(2)}</span>
                      </div>
                    </td>
                    {columns.map((cid) => {
                      const check = c.checks.find((k) => k.constraint_id === cid);
                      if (!check) {
                        return (
                          <td key={cid} className="px-1 text-center text-zinc-600">
                            -
                          </td>
                        );
                      }
                      return (
                        <td
                          key={cid}
                          className={`num rounded px-1.5 text-center ${pClass(check.p_violation, t_allow, t_block)}`}
                          title={`${textOf(cid)}\np(violation) ${fmtP(check.p_violation)}\nground truth: ${
                            check.ground_truth === null ? "no checker" : check.ground_truth ? "violation" : "ok"
                          }`}
                        >
                          {fmtP(check.p_violation)}
                          <span className="text-[0.625rem] opacity-80">{truthMark(check.ground_truth)}</span>
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="mt-1 px-1 text-2xs leading-snug text-zinc-400">
            cells colored by thresholds <span className="num">{t_allow.toFixed(2)}</span> / <span className="num">{t_block.toFixed(2)}</span> · ● checker
            says violation · ○ checker says ok
            {record.floor?.applied && floored.size > 0 && <> · faded rows are under the physics floor and could not run</>}
          </div>
          <div className="num mt-0.5 px-1 text-2xs text-zinc-400">
            jev {record.judge.source} · {fmtMs(record.judge.latency_ms)} · {record.judge.model} · {fmtUsd(record.judge.cost_usd)} · reward {record.reward.toFixed(2)}
          </div>
        </div>
        <div className="flex min-h-0 flex-col">
          <div className="mb-1 flex items-center gap-1.5 text-xs">
            <span className="mr-1 font-mono text-zinc-300">{chosen.action}</span>
            <button className={`chip ${tab === "facts" ? "chip-on" : ""}`} onClick={() => setTab("facts")}>
              facts
            </button>
            <button className={`chip ${tab === "raw" ? "chip-on" : ""}`} onClick={() => setTab("raw")}>
              raw request and response
            </button>
            {raw ? (
              <span className="num ml-auto truncate text-2xs text-zinc-400">
                {raw.exchange.source} · {fmtMs(raw.exchange.latency_ms)} · asked {raw.exchange.asked.join(", ")}
                {raw.exchange.request_id && ` · ${raw.exchange.request_id}`}
              </span>
            ) : (
              <span className="ml-auto text-2xs text-zinc-400">
                {record.judge.exchanges ? "no request sent: every answer came from the cache" : "no exchange in this log"}
              </span>
            )}
          </div>
          {tab === "facts" ? (
            <div className="grid min-h-0 flex-1 grid-cols-2 gap-2">
              <ul className="min-h-0 list-disc overflow-auto pl-4 text-xs leading-snug text-zinc-200">
                {chosen.sentences.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
              <pre className={JSON_CLASS}>{JSON.stringify(chosen.facts, null, 1)}</pre>
            </div>
          ) : (
            <div className="grid min-h-0 flex-1 grid-cols-2 gap-2">
              <pre className={JSON_CLASS}>{raw ? JSON.stringify(raw.request, null, 1) : "no request"}</pre>
              <pre className={JSON_CLASS}>{raw ? JSON.stringify(raw.exchange.response, null, 1) : "no response"}</pre>
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
