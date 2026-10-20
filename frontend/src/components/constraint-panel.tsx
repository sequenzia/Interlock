import { useMemo, useState } from "react";
import { ChevronDownIcon, CloseIcon } from "../icons";
import { useStore } from "../store";
import type { Preset } from "../types";
import { send } from "../ws-client";
import { ThresholdBand } from "./threshold-band";

const NO_PRESETS: Preset[] = [];
const GAP_POSITIVE = "A lane change requires at least 10 m of clear space to the nearest vehicle in the target lane";

export function ConstraintPanel() {
  const constraints = useStore((s) => s.constraints);
  const zones = useStore((s) => s.zones);
  const zoneNote = useStore((s) => s.zoneNote);
  const clearZoneNote = useStore((s) => s.clearZoneNote);
  const presets = useStore((s) => s.hello?.presets) ?? NO_PRESETS;
  const session = useStore((s) => s.session);
  const steps = useStore((s) => s.steps);
  const escalationP = useStore((s) => s.escalation?.p ?? null);
  const [text, setText] = useState("");
  const [presetsOpen, setPresetsOpen] = useState(true);
  const replay = session?.source === "replay";
  const disabled = session === null || replay;
  const active = constraints.filter((c) => c.enabled).length;
  const showRephrase = /^no\s/i.test(text.trim()) && /lane change/i.test(text);
  const available = presets.filter((p) => !constraints.some((c) => c.text === p.text));

  // How often each rule has been the one that fired, from the records already in the store.
  const fired = useMemo(() => {
    const counts = new Map<string, number>();
    for (const r of steps) if (r.fired_constraint) counts.set(r.fired_constraint, (counts.get(r.fired_constraint) ?? 0) + 1);
    return counts;
  }, [steps]);

  const add = (): void => {
    const trimmed = text.trim();
    if (!trimmed) return;
    send({ type: "add_constraint", text: trimmed });
    setText("");
  };

  return (
    <section className="panel">
      <div className="panel-title">
        <span>Operator rules</span>
        <span className="panel-subtitle">
          {active} active{replay && " · replay, read only"}
        </span>
      </div>
      <div className="flex flex-col gap-2.5 p-3">
        <form
          className="flex gap-1.5"
          onSubmit={(e) => {
            e.preventDefault();
            add();
          }}
        >
          <input
            className="min-w-0 flex-1 rounded-md border border-zinc-700 bg-zinc-950 px-2.5 py-1.5 text-sm text-zinc-100 placeholder:text-zinc-500"
            placeholder="Type a rule in plain English"
            aria-label="new rule"
            value={text}
            disabled={disabled}
            onChange={(e) => setText(e.target.value)}
          />
          <button className="btn btn-primary" type="submit" disabled={disabled || text.trim() === ""}>
            add
          </button>
        </form>
        {showRephrase && (
          <div className="enter flex flex-col gap-1.5 rounded-md border border-escalate/30 bg-escalate/10 p-2 text-xs text-zinc-200">
            <span>Jev scores positive phrasing more crisply than "No ... if ...". Your text is kept either way.</span>
            <button className="chip max-w-full self-start" type="button" onClick={() => setText(GAP_POSITIVE)}>
              <span className="truncate">use: {GAP_POSITIVE}</span>
            </button>
          </div>
        )}

        <ul className="flex flex-col gap-1.5">
          {constraints.map((c) => {
            const n = fired.get(c.id) ?? 0;
            return (
              <li
                key={c.id}
                className={`flex items-start gap-2.5 rounded-md border px-2.5 py-2 transition-colors ${
                  c.enabled ? "border-zinc-700 bg-zinc-800/50" : "border-zinc-800 bg-zinc-900/30 text-zinc-500"
                }`}
              >
                <button
                  type="button"
                  role="switch"
                  aria-checked={c.enabled}
                  data-on={c.enabled}
                  aria-label={`enable ${c.id}`}
                  className="switch mt-0.5"
                  disabled={disabled}
                  onClick={() => send({ type: "toggle_constraint", id: c.id, enabled: !c.enabled })}
                >
                  <span className="switch-knob" />
                </button>
                <div className="min-w-0 flex-1">
                  <div className="text-sm leading-snug">{c.text}</div>
                  <div className="mt-0.5 flex items-center gap-2 text-2xs text-zinc-400">
                    <span className="font-mono">{c.id}</span>
                    {c.checker ? (
                      <span className="badge border-zinc-700 text-zinc-400" title={`checker ${c.checker}`}>
                        scored
                      </span>
                    ) : (
                      <span className="badge border-zinc-800 text-zinc-500" title="no checker: the evaluation cannot score this rule">
                        not scored
                      </span>
                    )}
                    {n > 0 && (
                      <span className="num" title="steps where this rule decided the outcome">
                        fired {n}×
                      </span>
                    )}
                  </div>
                </div>
                <button
                  type="button"
                  className="btn btn-icon border-transparent bg-transparent text-zinc-500 hover:text-blocked"
                  aria-label={`remove ${c.id}`}
                  disabled={disabled}
                  onClick={() => send({ type: "remove_constraint", id: c.id })}
                >
                  <CloseIcon />
                </button>
              </li>
            );
          })}
          {constraints.length === 0 && <li className="text-xs text-zinc-400">No rules yet. The agent drives on task reward alone.</li>}
        </ul>

        {available.length > 0 && (
          <div className="flex flex-col gap-1.5 border-t border-zinc-800 pt-2.5">
            <button
              type="button"
              className="flex w-full items-center justify-between"
              aria-expanded={presetsOpen}
              onClick={() => setPresetsOpen((v) => !v)}
            >
              <span className="stat-label">Presets</span>
              <span className="flex items-center gap-1 text-2xs text-zinc-400">
                {available.length} to add
                <ChevronDownIcon className={`h-3 w-3 transition-transform ${presetsOpen ? "" : "-rotate-90"}`} />
              </span>
            </button>
            {presetsOpen && (
              <div className="flex flex-wrap gap-1">
                {available.map((p) => (
                  <button
                    key={p.id}
                    className="chip max-w-full"
                    type="button"
                    disabled={disabled}
                    title={p.text}
                    onClick={() => send({ type: "add_constraint", text: p.text, checker: p.checker ?? undefined })}
                  >
                    <span className="truncate">+ {p.text}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="flex items-center justify-between border-t border-zinc-800 pt-2.5">
          <span className="stat-label">Zones</span>
          <button className="btn" type="button" disabled={disabled} onClick={() => send({ type: "drop_zone" })}>
            drop work zone ahead
          </button>
        </div>
        {zones.map((z, i) => (
          <div key={i} className="enter flex items-center gap-2 rounded-md border border-hazard/40 bg-hazard/10 px-2.5 py-1.5 text-xs text-orange-100">
            <span className="h-2 w-3.5 rounded-sm border border-hazard/80 bg-[repeating-linear-gradient(135deg,rgba(251,146,60,0.6)_0_2px,transparent_2px_5px)]" />
            <span>
              {z.name} · lane {z.lane} · <span className="num">{Math.round(z.start_m)}</span> to <span className="num">{Math.round(z.end_m)}</span> m
            </span>
          </div>
        ))}
        {zoneNote && (
          <div className="enter flex items-center justify-between rounded-md border border-hazard/40 bg-hazard/10 px-2.5 py-1.5 text-xs text-orange-100">
            <span>{zoneNote}</span>
            <button type="button" className="chip" onClick={clearZoneNote}>
              ok
            </button>
          </div>
        )}
        {session && <ThresholdBand current={session.thresholds} floorS={session.floor_s ?? 0} disabled={disabled} marker={escalationP} />}
      </div>
    </section>
  );
}
