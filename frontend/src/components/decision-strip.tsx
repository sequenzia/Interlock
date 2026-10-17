import { DECISION_COLOR } from "../format";
import { useStore } from "../store";

export function DecisionStrip() {
  const steps = useStore((s) => s.steps);
  const selected = useStore((s) => s.selectedStep);
  const selectStep = useStore((s) => s.selectStep);
  const duration = useStore((s) => s.hello?.config.duration ?? 60);
  const total = Math.max(duration, steps.length);
  return (
    <section className="panel shrink-0">
      <div className="panel-title">
        <span>Decisions</span>
        <span className="font-normal tracking-normal text-zinc-500 normal-case">
          {steps.length} steps · click a tick to inspect · green allowed · amber fallback · violet escalated · rose all blocked
        </span>
      </div>
      <div className="flex h-8 items-end gap-px px-2 pt-1 pb-1.5">
        {Array.from({ length: total }, (_, i) => {
          const r = steps[i];
          const isSelected = selected === i;
          return (
            <button
              key={i}
              type="button"
              disabled={!r}
              onClick={() => selectStep(isSelected ? null : i)}
              className={`flex-1 rounded-sm transition-[height] ${r ? "cursor-pointer hover:brightness-125" : ""} ${
                isSelected ? "ring-2 ring-white" : ""
              }`}
              style={{
                height: r ? (isSelected ? "100%" : "80%") : "30%",
                background: r ? DECISION_COLOR[r.decision] : "#27272a",
                opacity: r?.escalated ? 1 : r ? 0.85 : 0.6,
              }}
              title={r ? `step ${r.step}: ${r.decision} -> ${r.executed}${r.human ? ` (${r.human.decision}${r.human.action ? ` ${r.human.action}` : ""})` : ""}` : undefined}
              aria-label={r ? `inspect step ${r.step}` : undefined}
            />
          );
        })}
      </div>
    </section>
  );
}
