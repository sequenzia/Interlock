import { useEffect } from "react";
import { ApprovalQueue, resolveWithRank } from "./components/approval-queue";
import { ConstraintPanel } from "./components/constraint-panel";
import { DecisionStrip } from "./components/decision-strip";
import { InspectorDrawer } from "./components/inspector-drawer";
import { MetricsView } from "./components/metrics-view";
import { RoadView } from "./components/road-view";
import { ShortcutsOverlay } from "./components/shortcuts-overlay";
import { StatusStrip } from "./components/status-strip";
import { Toasts } from "./components/toasts";
import { TwinStrip } from "./components/twin-strip";
import { useStore } from "./store";
import { connect, send } from "./ws-client";

export function App() {
  const view = useStore((s) => s.view);
  const density = useStore((s) => s.density);
  const inspecting = useStore((s) => s.selectedStep !== null);

  useEffect(() => connect(), []);

  useEffect(() => {
    document.documentElement.dataset.density = density;
  }, [density]);

  useEffect(() => {
    document.title = `Interlock · ${view}`;
  }, [view]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLSelectElement) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const { session, escalation, selectedStep, steps, selectStep, shortcutsOpen, setShortcutsOpen } = useStore.getState();
      if (e.key === "?") {
        setShortcutsOpen(!shortcutsOpen);
      } else if (e.key === "Escape") {
        if (shortcutsOpen) setShortcutsOpen(false);
        else selectStep(null);
      } else if (e.key === "ArrowLeft") {
        selectStep(Math.max(0, (selectedStep ?? steps.length) - 1));
      } else if (e.key === "ArrowRight" && selectedStep !== null) {
        selectStep(selectedStep >= steps.length - 1 ? null : selectedStep + 1);
      } else if (e.code === "Space") {
        e.preventDefault();
        send({ type: session?.playing ? "pause" : "play" });
      } else if (e.key === "n") {
        send({ type: "step" });
      } else if (e.key === "a" && escalation) {
        send({ type: "resolve", escalation_id: escalation.id, decision: "approve" });
      } else if (e.key === "d" && escalation) {
        send({ type: "resolve", escalation_id: escalation.id, decision: "deny" });
      } else if (escalation && /^[1-5]$/.test(e.key)) {
        resolveWithRank(escalation, Number(e.key) - 1);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="flex h-full flex-col gap-2 p-2">
      <StatusStrip />
      {view === "metrics" ? (
        <MetricsView />
      ) : (
        <div className="flex min-h-0 flex-1 gap-2">
          <div className="flex min-w-0 flex-1 flex-col gap-2">
            <RoadView />
            {/* The inspector takes the twin's slot while open, so the timeline never leaves the screen. */}
            {inspecting ? <InspectorDrawer /> : <TwinStrip />}
            <DecisionStrip />
          </div>
          <aside className="flex w-[clamp(20rem,27vw,25rem)] shrink-0 flex-col gap-2 overflow-y-auto">
            <ApprovalQueue />
            <ConstraintPanel />
          </aside>
        </div>
      )}
      <Toasts />
      <ShortcutsOverlay />
    </div>
  );
}
