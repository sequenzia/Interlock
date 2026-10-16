import { useEffect } from "react";
import { ApprovalQueue } from "./components/approval-queue";
import { ConstraintPanel } from "./components/constraint-panel";
import { DecisionStrip } from "./components/decision-strip";
import { RoadView } from "./components/road-view";
import { StatusStrip } from "./components/status-strip";
import { useStore } from "./store";
import { connect, send } from "./ws-client";

export function App() {
  const errors = useStore((s) => s.errors);
  const dismissErrors = useStore((s) => s.dismissErrors);

  useEffect(() => connect(), []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLSelectElement) return;
      const { session, escalation } = useStore.getState();
      if (e.code === "Space") {
        e.preventDefault();
        send({ type: session?.playing ? "pause" : "play" });
      } else if (e.key === "n") {
        send({ type: "step" });
      } else if (e.key === "a" && escalation) {
        send({ type: "resolve", escalation_id: escalation.id, decision: "approve" });
      } else if (e.key === "d" && escalation) {
        send({ type: "resolve", escalation_id: escalation.id, decision: "deny" });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="flex h-full flex-col gap-2 p-2">
      <StatusStrip />
      <div className="flex min-h-0 flex-1 gap-2">
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <RoadView />
          <DecisionStrip />
        </div>
        <aside className="flex w-[400px] shrink-0 flex-col gap-2 overflow-y-auto">
          <ApprovalQueue />
          <ConstraintPanel />
        </aside>
      </div>
      {errors.length > 0 && (
        <div className="fixed right-3 bottom-3 max-w-md rounded border border-rose-500/50 bg-rose-950/90 p-3 text-rose-100 shadow-lg">
          <div className="flex items-start justify-between gap-3">
            <ul className="flex flex-col gap-1">
              {errors.map((m, i) => (
                <li key={i}>{m}</li>
              ))}
            </ul>
            <button className="btn" onClick={dismissErrors}>
              dismiss
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
