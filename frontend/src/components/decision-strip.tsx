import { useMemo, useState } from "react";
import { DECISION_COLOR, DECISION_LABEL, violatedRules } from "../format";
import { useStore } from "../store";
import type { LogRecord } from "../types";

function summary(r: LogRecord): string {
  const top = r.candidates[0]?.action;
  const parts = [`step ${r.step}`, `${DECISION_LABEL[r.decision]} → ${r.executed}`];
  if (top !== undefined && top !== r.executed) {
    parts.push((r.floor?.removed ?? []).includes(top) ? `${top} under the floor` : `${top} blocked`);
  }
  if (r.human) parts.push(`operator ${r.human.decision}${r.human.action ? ` ${r.human.action}` : ""}`);
  const violated = violatedRules(r);
  if (violated.length > 0) parts.push(`violated ${violated.join(", ")}`);
  if (r.crashed) parts.push("crash");
  return parts.join(" · ");
}

/** Rose, darker the more rules broke at the step; one scale for the live row and the twin's. */
const violationFill = (count: number): string => `rgba(251,113,133,${Math.min(0.9, 0.3 + count * 0.2)})`;

function Swatch({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className="h-2 w-3.5 rounded-sm" style={{ background: color }} />
      {label}
    </span>
  );
}

export function DecisionStrip() {
  const steps = useStore((s) => s.steps);
  const selected = useStore((s) => s.selectedStep);
  const selectStep = useStore((s) => s.selectStep);
  const duration = useStore((s) => s.hello?.config.duration ?? 60);
  const twin = useStore((s) => s.twin);
  const seed = useStore((s) => s.session?.seed ?? null);
  const [hover, setHover] = useState<number | null>(null);
  const violations = useMemo(() => steps.map((r) => violatedRules(r).length), [steps]);
  const total = Math.max(duration, steps.length);
  const twinSteps = twin && twin.seed === seed && twin.steps.length > 0 ? twin.steps : null;
  const hovered = hover !== null ? (steps[hover] ?? null) : null;
  const latest = steps.length - 1;
  const pct = (i: number): string => `${((i + 0.5) / total) * 100}%`;
  const ticksEvery = total > 120 ? 20 : 10;

  return (
    <section className="panel shrink-0">
      <div className="panel-title">
        <span className="flex items-center gap-2">
          Decisions
          <span className="panel-subtitle">
            {steps.length} steps · {selected === null ? "click a tick to inspect" : "arrow keys move · esc follows live"}
          </span>
        </span>
        <span className="panel-subtitle flex min-w-0 items-center gap-3 overflow-hidden">
          <Swatch color={DECISION_COLOR.allow} label="allowed" />
          <Swatch color={DECISION_COLOR.fallback} label="fallback" />
          <Swatch color={DECISION_COLOR.escalate} label="escalated" />
          <Swatch color={DECISION_COLOR.all_blocked} label="all blocked" />
          <span className="flex items-center gap-1.5 max-[1440px]:hidden">
            <span className="h-1.5 w-1.5 rounded-full bg-white" />
            operator answered
          </span>
          <span
            className="max-[1440px]:hidden"
            title={twinSteps ? "the rows under the ticks: the live run's violations, then the twin's" : "the row under the ticks: steps where the action that ran broke a rule"}
          >
            <Swatch color={violationFill(1)} label="violation" />
          </span>
        </span>
      </div>
      <div className="relative px-2 pt-1.5 pb-1">
        {hovered && hover !== null && (
          <div
            className="pointer-events-none absolute bottom-full z-10 mb-1 max-w-xs rounded-md border border-zinc-700 bg-zinc-950/95 px-2 py-1 text-2xs whitespace-nowrap text-zinc-200 shadow-lg"
            style={{
              left: pct(hover),
              transform: hover / total < 0.08 ? "translateX(0)" : hover / total > 0.92 ? "translateX(-100%)" : "translateX(-50%)",
            }}
          >
            <span className="font-mono">{summary(hovered)}</span>
          </div>
        )}
        <div className="flex h-7 items-end gap-px" onMouseLeave={() => setHover(null)}>
          {Array.from({ length: total }, (_, i) => {
            const r = steps[i];
            const isSelected = selected === i;
            return (
              <button
                key={i}
                type="button"
                disabled={!r}
                onClick={() => selectStep(isSelected ? null : i)}
                onMouseEnter={() => setHover(r ? i : null)}
                className={`relative flex-1 rounded-sm transition-[height] ${r ? "cursor-pointer hover:brightness-125" : ""} ${
                  isSelected ? "ring-1 ring-white" : ""
                }`}
                style={{
                  height: r ? (isSelected ? "100%" : "78%") : "28%",
                  background: r ? DECISION_COLOR[r.decision] : "#27272a",
                  opacity: r?.escalated ? 1 : r ? 0.85 : 0.6,
                }}
                aria-label={r ? `inspect step ${r.step}` : undefined}
                aria-pressed={r ? isSelected : undefined}
              >
                {r?.human && <span className="absolute bottom-0.5 left-1/2 h-1 w-1 -translate-x-1/2 rounded-full bg-white" />}
              </button>
            );
          })}
        </div>
        <div className="mt-px flex h-1.5 gap-px" title="the live run's violations per step: the action that ran broke a rule, by the checkers">
          {Array.from({ length: total }, (_, i) => {
            const v = violations[i] ?? 0;
            return <span key={i} className="flex-1 rounded-sm" style={{ background: v > 0 ? violationFill(v) : "transparent" }} />;
          })}
        </div>
        {twinSteps && (
          <div className="mt-px flex h-1.5 gap-px" title="the unshielded twin's violations per step">
            {Array.from({ length: total }, (_, i) => {
              // The twin log is complete from the start; reveal it in step with the live run.
              const t = i <= latest ? twinSteps[i] : undefined;
              const crashed = i <= latest && twin?.crashed_at === i;
              const v = t?.violations ?? 0;
              return (
                <span
                  key={i}
                  className="flex-1 rounded-sm"
                  style={{
                    background: crashed ? DECISION_COLOR.all_blocked : v > 0 ? violationFill(v) : "transparent",
                  }}
                />
              );
            })}
          </div>
        )}
        <div className="relative mt-0.5 h-3.5 text-[0.625rem] text-zinc-500">
          {Array.from({ length: Math.floor((total - 1) / ticksEvery) + 1 }, (_, k) => k * ticksEvery).map((i) => (
            <span key={i} className="num absolute -translate-x-1/2" style={{ left: pct(i) }}>
              {i}
            </span>
          ))}
          {latest >= 0 && (
            <span
              className="absolute -top-0.5 h-0 w-0 -translate-x-1/2 border-x-[4px] border-b-[5px] border-x-transparent border-b-zinc-200"
              style={{ left: pct(latest) }}
              title="now"
            />
          )}
          {selected !== null && (
            <span
              className="absolute -top-0.5 h-0 w-0 -translate-x-1/2 border-x-[4px] border-b-[5px] border-x-transparent border-b-white"
              style={{ left: pct(selected) }}
              title="inspecting"
            />
          )}
        </div>
      </div>
    </section>
  );
}
