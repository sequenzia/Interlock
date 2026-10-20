import { useEffect, useState } from "react";
import type { Thresholds } from "../types";
import { send } from "../ws-client";

interface Props {
  current: Thresholds;
  floorS: number;
  disabled: boolean;
  marker: number | null; // the open escalation's p, drawn on the band
}

/** One track, three bands, two handles: the whole decision rule in one control. */
export function ThresholdBand({ current, floorS, disabled, marker }: Props) {
  const [local, setLocal] = useState(current);
  useEffect(() => setLocal(current), [current]);
  const commit = (): void => {
    if (local.t_allow !== current.t_allow || local.t_block !== current.t_block) {
      send({ type: "set_thresholds", t_allow: local.t_allow, t_block: local.t_block });
    }
  };
  const setAllow = (v: number): void => setLocal((l) => ({ t_allow: Math.min(v, l.t_block), t_block: l.t_block }));
  const setBlock = (v: number): void => setLocal((l) => ({ t_allow: l.t_allow, t_block: Math.max(v, l.t_allow) }));
  const a = local.t_allow;
  const b = local.t_block;

  return (
    <div className="flex flex-col gap-1.5 border-t border-zinc-800 pt-2.5">
      <div className="flex items-center justify-between">
        <span className="stat-label">Thresholds</span>
        <span className="num text-2xs text-zinc-400">
          allow &lt; {a.toFixed(2)} · escalate · block &gt; {b.toFixed(2)}
        </span>
      </div>
      <div className="relative h-6">
        <div className="absolute inset-x-0 top-1/2 h-2 -translate-y-1/2 overflow-hidden rounded-full bg-zinc-800">
          <div className="absolute inset-y-0 left-0 bg-allow/70" style={{ width: `${a * 100}%` }} />
          <div className="absolute inset-y-0 bg-escalate/70" style={{ left: `${a * 100}%`, width: `${(b - a) * 100}%` }} />
          <div className="absolute inset-y-0 right-0 bg-blocked/70" style={{ width: `${(1 - b) * 100}%` }} />
        </div>
        {marker !== null && (
          <div
            className="absolute top-0.5 bottom-0.5 w-0.5 -translate-x-1/2 bg-white"
            style={{ left: `${marker * 100}%` }}
            title={`the open escalation: p = ${marker.toFixed(2)}`}
          />
        )}
        <input
          type="range"
          className="band-range"
          min={0}
          max={1}
          step={0.05}
          value={a}
          disabled={disabled}
          aria-label="t_allow"
          onChange={(e) => setAllow(Number(e.target.value))}
          onPointerUp={commit}
          onKeyUp={commit}
        />
        <input
          type="range"
          className="band-range"
          min={0}
          max={1}
          step={0.05}
          value={b}
          disabled={disabled}
          aria-label="t_block"
          onChange={(e) => setBlock(Number(e.target.value))}
          onPointerUp={commit}
          onKeyUp={commit}
        />
      </div>
      <div className="flex justify-between text-2xs text-zinc-400">
        <span className="text-allow">runs on its own</span>
        <span className="text-escalate">asks a person</span>
        <span className="text-blocked">falls back</span>
      </div>
      <div className="text-2xs text-zinc-400">
        <span
          className="cursor-help underline decoration-dotted underline-offset-2"
          title={
            floorS > 0
              ? `A candidate closing on the vehicle ahead in under ${floorS.toFixed(1)} s never runs, whatever Jev says. Set at launch with --floor-s, not here.`
              : "Every candidate is eligible, whatever its time to collision. Set at launch with --floor-s, not here."
          }
        >
          physics floor {floorS > 0 ? `${floorS.toFixed(1)} s` : "off"}
        </span>
      </div>
    </div>
  );
}
