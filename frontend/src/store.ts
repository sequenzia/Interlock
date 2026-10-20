import { create } from "zustand";
import type { StateCreator } from "zustand";
import type { Constraint, Escalation, EvalReport, Hello, LogRecord, Metrics, SessionState, Twin, Zone } from "./types";

// One store, four slices (plan: steps, constraints, queue, metrics) plus the
// connection slice that holds hello and the session state.

export type View = "console" | "metrics";
export type Density = "normal" | "talk";

const DENSITY_KEY = "interlock.density";

// ?density=talk wins, then the remembered choice, then normal.
function initialDensity(): Density {
  if (typeof window === "undefined") return "normal";
  const fromUrl = new URLSearchParams(window.location.search).get("density");
  if (fromUrl === "talk" || fromUrl === "normal") return fromUrl;
  try {
    return window.localStorage.getItem(DENSITY_KEY) === "talk" ? "talk" : "normal";
  } catch {
    return "normal";
  }
}

interface ConnectionSlice {
  view: View;
  setView: (view: View) => void;
  density: Density;
  setDensity: (density: Density) => void;
  shortcutsOpen: boolean;
  setShortcutsOpen: (open: boolean) => void;
  connected: boolean;
  hello: Hello | null;
  session: SessionState | null;
  errors: string[];
  setConnected: (connected: boolean) => void;
  setHello: (hello: Hello) => void;
  setSession: (session: SessionState) => void;
  pushError: (message: string) => void;
  dismissErrors: () => void;
}

interface StepsSlice {
  steps: LogRecord[];
  selectedStep: number | null;
  twin: Twin | null; // the shield-off run of the current seed, scrubbed with the live steps
  setTwin: (twin: Twin | null) => void;
  pushStep: (record: LogRecord) => void;
  replaceSteps: (records: LogRecord[]) => void;
  resetSteps: () => void;
  selectStep: (step: number | null) => void;
}

interface ConstraintsSlice {
  constraints: Constraint[];
  zones: Zone[];
  zoneNote: string | null;
  setConstraints: (constraints: Constraint[], zones: Zone[]) => void;
  clearZoneNote: () => void;
}

interface QueueSlice {
  escalation: Escalation | null;
  setEscalation: (escalation: Escalation | null) => void;
}

interface MetricsSlice {
  metrics: Metrics | null;
  setMetrics: (metrics: Metrics) => void;
  report: EvalReport | null; // the evaluation report once the metrics view has fetched it
  setReport: (report: EvalReport | null) => void;
}

export type Store = ConnectionSlice & StepsSlice & ConstraintsSlice & QueueSlice & MetricsSlice;

const MAX_STEPS = 2000;

const createConnectionSlice: StateCreator<Store, [], [], ConnectionSlice> = (set) => ({
  view: "console",
  setView: (view) => set({ view }),
  density: initialDensity(),
  setDensity: (density) => {
    try {
      window.localStorage.setItem(DENSITY_KEY, density);
    } catch {
      // Private mode or blocked storage: the choice lasts for the session only.
    }
    set({ density });
  },
  shortcutsOpen: false,
  setShortcutsOpen: (shortcutsOpen) => set({ shortcutsOpen }),
  connected: false,
  hello: null,
  session: null,
  errors: [],
  setConnected: (connected) => set({ connected }),
  setHello: (hello) => set({ hello }),
  setSession: (session) =>
    set((s) => {
      // A new run id or a rewind to step 0 means the step history belongs to another run.
      const newRun = s.session !== null && (s.session.run_id !== session.run_id || session.step < s.session.step);
      return {
        session,
        steps: newRun ? [] : s.steps,
        selectedStep: newRun ? null : s.selectedStep,
        escalation: session.paused_on_escalation_id === null ? null : s.escalation,
      };
    }),
  pushError: (message) => set((s) => ({ errors: [...s.errors.slice(-4), message] })),
  dismissErrors: () => set({ errors: [] }),
});

const createStepsSlice: StateCreator<Store, [], [], StepsSlice> = (set) => ({
  steps: [],
  selectedStep: null,
  twin: null,
  setTwin: (twin) => set({ twin }),
  pushStep: (record) =>
    set((s) => {
      const steps = s.steps.length >= MAX_STEPS ? s.steps.slice(-MAX_STEPS + 1) : s.steps.slice();
      steps.push(record);
      return { steps };
    }),
  replaceSteps: (records) => set({ steps: records.slice(-MAX_STEPS), selectedStep: null }),
  resetSteps: () => set({ steps: [], selectedStep: null }),
  selectStep: (selectedStep) => set({ selectedStep }),
});

const createConstraintsSlice: StateCreator<Store, [], [], ConstraintsSlice> = (set) => ({
  constraints: [],
  zones: [],
  zoneNote: null,
  setConstraints: (constraints, zones) =>
    set((s) => {
      const hadZones = s.zones.length > 0;
      const zoneRuleBefore = s.constraints.find((c) => c.checker === "lane_closed");
      const zoneRuleAfter = constraints.find((c) => c.checker === "lane_closed");
      const retired =
        hadZones && zones.length === 0 && zoneRuleBefore?.enabled === true && zoneRuleAfter?.enabled === false;
      const dropped = !hadZones && zones.length > 0;
      return {
        constraints,
        zones,
        zoneNote: retired ? "Zone passed. The lane-closed rule was retired." : dropped ? null : s.zoneNote,
      };
    }),
  clearZoneNote: () => set({ zoneNote: null }),
});

const createQueueSlice: StateCreator<Store, [], [], QueueSlice> = (set) => ({
  escalation: null,
  setEscalation: (escalation) => set({ escalation }),
});

const createMetricsSlice: StateCreator<Store, [], [], MetricsSlice> = (set) => ({
  metrics: null,
  setMetrics: (metrics) => set({ metrics }),
  report: null,
  setReport: (report) => set({ report }),
});

export const useStore = create<Store>()((...a) => ({
  ...createConnectionSlice(...a),
  ...createStepsSlice(...a),
  ...createConstraintsSlice(...a),
  ...createQueueSlice(...a),
  ...createMetricsSlice(...a),
}));

export const selectLatestStep = (s: Store): LogRecord | null => s.steps[s.steps.length - 1] ?? null;
export const selectPreviousStep = (s: Store): LogRecord | null => s.steps[s.steps.length - 2] ?? null;
export const selectInspected = (s: Store): LogRecord | null =>
  s.selectedStep === null ? null : (s.steps[s.selectedStep] ?? null);
// The road view follows the live step unless a tick is selected, then it scrubs.
export const selectViewStep = (s: Store): LogRecord | null =>
  s.selectedStep === null ? selectLatestStep(s) : (s.steps[s.selectedStep] ?? null);
export const selectViewPrevStep = (s: Store): LogRecord | null =>
  s.selectedStep === null ? selectPreviousStep(s) : (s.steps[s.selectedStep - 1] ?? null);
