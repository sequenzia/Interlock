# Store and selectors

`frontend/src/store.ts` is the only client-side state. It is one Zustand store assembled from five slices, each a `StateCreator<Store, [], [], Slice>` spread into `create<Store>()`. Components subscribe with narrow selectors and never copy server state into their own `useState`.

## Slices

| Slice | Fields | Actions |
| --- | --- | --- |
| Connection | `view`, `density`, `shortcutsOpen`, `connected`, `hello`, `session`, `errors` | `setView`, `setDensity`, `setShortcutsOpen`, `setConnected`, `setHello`, `setSession`, `pushError`, `dismissErrors` |
| Steps | `steps`, `selectedStep`, `twin` | `pushStep`, `replaceSteps`, `resetSteps`, `selectStep`, `setTwin` |
| Constraints | `constraints`, `zones`, `zoneNote` | `setConstraints`, `clearZoneNote` |
| Queue | `escalation` | `setEscalation` |
| Metrics | `metrics`, `report` | `setMetrics`, `setReport` |

`density` is `normal` or `talk`; it starts from `?density=talk` in the URL, else the value remembered in `localStorage`, and `setDensity` writes it back. `App` mirrors it onto `<html data-density>`. `report` holds the evaluation report once the metrics view has fetched `/eval/latest`, so the status strip can show its metadata and the fetch happens once per page load.

`hello` is the server's `hello` message (config, presets, zone defaults, logged runs, initial constraints). `session` is the latest `state` message. `steps` is this episode's log records in order. `metrics` is the running counters the server sends after every step. The message shapes are in [WebSocket protocol](../contracts/websocket-protocol.md) and the record in [Log record](../contracts/log-record.md).

## Run changes are detected, not announced

The server has no "new episode" message. `setSession` infers one from the `state` message:

```typescript
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
```

Two consequences:

- A reset, a replay load or a return to live changes `run_id` (or rewinds `step`), so the timeline clears before the first new `step` message arrives.
- The queue clears itself. When the server resolves an escalation it re-sends `state` with `paused_on_escalation_id: null`, and that alone empties `escalation`. There is no "escalation closed" message to handle.

## Steps

`pushStep` appends a record and keeps at most `MAX_STEPS = 2000`, dropping the oldest when full. Episodes are 60 steps, so the cap only matters for very long replays. `replaceSteps` loads the `history` message on connect and clears the selection, which is how a browser refresh mid-episode keeps the timeline. `selectStep(null)` means "follow live".

## Zone note

`setConstraints` receives the full constraint list and zone list every time either changes. It compares with the previous state to produce the one piece of derived UI state in the store:

- `retired`: there were zones, now there are none, and the `lane_closed` rule flipped from enabled to disabled. The note "Zone passed. The lane-closed rule was retired." appears in the rules panel until dismissed.
- `dropped`: no zones before, zones now. Any stale note is cleared.

The retirement itself happens on the server (`ConstraintStore.retire_passed_zones` at the top of each step). The store only recognises it. See [Constraints and checkers](../backend/constraints-and-checkers.md).

## Selectors

Five selectors at the bottom of the file encode the live-versus-inspecting rule:

| Selector | Returns |
| --- | --- |
| `selectLatestStep` | The last record, or null |
| `selectPreviousStep` | The record before it, for interpolation |
| `selectInspected` | The selected record, or null when following live |
| `selectViewStep` | The record the road view should draw: selected if any, else latest |
| `selectViewPrevStep` | The record before the view step, selected or latest |

The road view and the inspector read these rather than indexing `steps` themselves, so scrubbing with the arrow keys moves the canvas and the drawer together while the sim keeps running underneath.

## The stable-reference rule

Zustand compares each selector's result with `Object.is` and re-renders the component when it changes. A selector that builds a new value on every call therefore never compares equal, and the component re-renders on every store update, including updates to unrelated slices. With React 19's `useSyncExternalStore` underneath, an always-changing snapshot can also trip the "getSnapshot should be cached" guard and loop. The project rule is: never `?? []` or `?? {}` inside a selector.

The pattern used instead hoists the fallback to a module-level constant and applies it outside the selector:

```typescript
const NO_RUNS: string[] = [];
const runs = useStore((s) => s.hello?.runs) ?? NO_RUNS;
```

The selector returns the same array reference from the store (or `undefined`), so it is stable. The fallback is also one shared reference, so hooks that depend on `runs` do not re-fire. The same constants exist as `NO_PRESETS` in `constraint-panel.tsx` and `EMPTY_COUNTS` in `approval-queue.tsx`. Anything derived from several fields (counts, filters, maps) is computed in the component body after narrow selections, or in `useMemo`, never inside the selector.

## Reading the store

Components take one field per `useStore` call:

```typescript
const connected = useStore((s) => s.connected);
const session = useStore((s) => s.session);
const latest = useStore(selectLatestStep);
```

Event handlers that need several fields at once, such as the keyboard handler in `app.tsx`, call `useStore.getState()` inside the handler instead of subscribing. The socket client does the same in `apply()`, which keeps `ws-client.ts` free of React.
