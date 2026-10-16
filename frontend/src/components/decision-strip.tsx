import { DECISION_COLOR } from "../format";
import { useStore } from "../store";

export function DecisionStrip() {
  const steps = useStore((s) => s.steps);
  const duration = useStore((s) => s.hello?.config.duration ?? 60);
  const total = Math.max(duration, steps.length);
  return (
    <section className="panel shrink-0">
      <div className="panel-title">
        <span>Decisions</span>
        <span className="font-normal tracking-normal text-zinc-500 normal-case">
          {steps.length} steps · green allowed · amber fallback · violet escalated · rose all blocked
        </span>
      </div>
      <div className="flex h-7 items-end gap-px px-2 pt-1 pb-1.5">
        {Array.from({ length: total }, (_, i) => {
          const r = steps[i];
          return (
            <div
              key={i}
              className="flex-1 rounded-sm"
              style={{
                height: r ? "100%" : "30%",
                background: r ? DECISION_COLOR[r.decision] : "#27272a",
                opacity: r?.escalated ? 1 : r ? 0.85 : 0.6,
              }}
              title={r ? `step ${r.step}: ${r.decision} -> ${r.executed}` : undefined}
            />
          );
        })}
      </div>
    </section>
  );
}
