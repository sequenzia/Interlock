import { useEffect, useState } from "react";
import { useStore } from "../store";
import type { Preset, Thresholds } from "../types";
import { send } from "../ws-client";

const NO_PRESETS: Preset[] = [];
const GAP_POSITIVE =
  "A lane change requires at least 10 m of clear space to the nearest vehicle in the target lane";

function ThresholdControls({ current, disabled }: { current: Thresholds; disabled: boolean }) {
  const [local, setLocal] = useState(current);
  useEffect(() => setLocal(current), [current]);
  const commit = (): void => {
    if (local.t_allow !== current.t_allow || local.t_block !== current.t_block) {
      send({ type: "set_thresholds", t_allow: local.t_allow, t_block: local.t_block });
    }
  };
  const setAllow = (v: number): void => setLocal((l) => ({ t_allow: Math.min(v, l.t_block), t_block: l.t_block }));
  const setBlock = (v: number): void => setLocal((l) => ({ t_allow: l.t_allow, t_block: Math.max(v, l.t_allow) }));
  return (
    <div className="flex flex-col gap-1 border-t border-zinc-800 pt-2">
      <div className="flex items-center justify-between">
        <span className="text-[11px] tracking-[0.18em] text-zinc-400 uppercase">Thresholds</span>
        <span className="text-[11px] text-zinc-500 tabular-nums">
          allow &lt; {local.t_allow.toFixed(2)} · escalate · block &gt; {local.t_block.toFixed(2)}
        </span>
      </div>
      {(["t_allow", "t_block"] as const).map((key) => (
        <label key={key} className="flex items-center gap-2 text-[11px] text-zinc-400">
          <span className="w-14">{key}</span>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={local[key]}
            disabled={disabled}
            className="flex-1 accent-cyan-400"
            onChange={(e) => (key === "t_allow" ? setAllow : setBlock)(Number(e.target.value))}
            onPointerUp={commit}
            onKeyUp={commit}
          />
          <span className="w-8 text-right tabular-nums">{local[key].toFixed(2)}</span>
        </label>
      ))}
    </div>
  );
}

export function ConstraintPanel() {
  const constraints = useStore((s) => s.constraints);
  const zones = useStore((s) => s.zones);
  const zoneNote = useStore((s) => s.zoneNote);
  const clearZoneNote = useStore((s) => s.clearZoneNote);
  const presets = useStore((s) => s.hello?.presets) ?? NO_PRESETS;
  const session = useStore((s) => s.session);
  const [text, setText] = useState("");
  const replay = session?.source === "replay";
  const disabled = session === null || replay;
  const active = constraints.filter((c) => c.enabled).length;
  const showRephrase = /^no\s/i.test(text.trim()) && /lane change/i.test(text);

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
        <span className="font-normal tracking-normal text-zinc-500 normal-case">{active} active</span>
      </div>
      <div className="flex flex-col gap-2 p-3">
        <form
          className="flex gap-1.5"
          onSubmit={(e) => {
            e.preventDefault();
            add();
          }}
        >
          <input
            className="min-w-0 flex-1 rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-zinc-100 placeholder:text-zinc-600"
            placeholder="Type a rule in plain English"
            value={text}
            disabled={disabled}
            onChange={(e) => setText(e.target.value)}
          />
          <button className="btn btn-primary" type="submit" disabled={disabled || text.trim() === ""}>
            add
          </button>
        </form>
        {showRephrase && (
          <div className="flex flex-col gap-1 rounded border border-violet-500/30 bg-violet-500/10 p-2 text-[11px] text-violet-200">
            <span>Jev scores positive phrasing more crisply than "No ... if ...". Your text is kept either way.</span>
            <button className="chip self-start" type="button" onClick={() => setText(GAP_POSITIVE)}>
              use: {GAP_POSITIVE}
            </button>
          </div>
        )}
        <div className="flex flex-wrap gap-1">
          {presets.map((p) => {
            const present = constraints.some((c) => c.text === p.text);
            return (
              <button
                key={p.id}
                className="chip"
                type="button"
                disabled={disabled || present}
                title={present ? "already in the list" : "add this preset rule"}
                onClick={() => send({ type: "add_constraint", text: p.text, checker: p.checker ?? undefined })}
              >
                + {p.text}
              </button>
            );
          })}
        </div>
        <ul className="flex flex-col gap-1">
          {constraints.map((c) => (
            <li
              key={c.id}
              className={`flex items-start gap-2 rounded border px-2 py-1.5 ${
                c.enabled ? "border-zinc-700 bg-zinc-800/50" : "border-zinc-800 bg-zinc-900/30 text-zinc-500"
              }`}
            >
              <input
                type="checkbox"
                className="mt-0.5 accent-cyan-400"
                checked={c.enabled}
                disabled={disabled}
                onChange={(e) => send({ type: "toggle_constraint", id: c.id, enabled: e.target.checked })}
              />
              <div className="min-w-0 flex-1">
                <div className="leading-snug">{c.text}</div>
                <div className="text-[10px] text-zinc-500">
                  {c.id} · {c.checker ? `checker ${c.checker}` : "no checker, not scored"}
                </div>
              </div>
              <button
                type="button"
                className="px-1 text-zinc-500 hover:text-rose-300 disabled:opacity-40"
                aria-label={`remove ${c.id}`}
                disabled={disabled}
                onClick={() => send({ type: "remove_constraint", id: c.id })}
              >
                ×
              </button>
            </li>
          ))}
          {constraints.length === 0 && (
            <li className="text-zinc-500">No rules yet. The agent drives on task reward alone.</li>
          )}
        </ul>

        <div className="flex items-center justify-between border-t border-zinc-800 pt-2">
          <span className="text-[11px] tracking-[0.18em] text-zinc-400 uppercase">Zones</span>
          <button className="btn" type="button" disabled={disabled} onClick={() => send({ type: "drop_zone" })}>
            drop work zone ahead
          </button>
        </div>
        {zones.map((z, i) => (
          <div key={i} className="flex items-center gap-2 rounded border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-amber-200">
            <span className="h-2 w-2 rounded-sm bg-amber-400" />
            <span>
              {z.name} · lane {z.lane} · {Math.round(z.start_m)} to {Math.round(z.end_m)} m
            </span>
          </div>
        ))}
        {zoneNote && (
          <div className="flex items-center justify-between rounded border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-amber-200">
            <span>{zoneNote}</span>
            <button type="button" className="chip" onClick={clearZoneNote}>
              ok
            </button>
          </div>
        )}
        {session && <ThresholdControls current={session.thresholds} disabled={disabled} />}
      </div>
    </section>
  );
}
