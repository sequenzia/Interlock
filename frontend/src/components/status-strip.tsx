import { useEffect, useState } from "react";
import { DECISION_CLASS, DECISION_LABEL, fmtMs, fmtUsd } from "../format";
import { selectLatestStep, useStore } from "../store";
import { send } from "../ws-client";

const SPEEDS = [0.5, 1, 2, 4];
const NO_RUNS: string[] = [];

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col items-end leading-tight">
      <span className="text-[10px] tracking-[0.18em] text-zinc-500 uppercase">{label}</span>
      <span className="text-[12px] text-zinc-200 tabular-nums">{value}</span>
    </div>
  );
}

export function StatusStrip() {
  const connected = useStore((s) => s.connected);
  const session = useStore((s) => s.session);
  const hello = useStore((s) => s.hello);
  const metrics = useStore((s) => s.metrics);
  const latest = useStore(selectLatestStep);
  const runs = useStore((s) => s.hello?.runs) ?? NO_RUNS;
  const view = useStore((s) => s.view);
  const setView = useStore((s) => s.setView);
  const inspecting = useStore((s) => s.selectedStep);
  const [seed, setSeed] = useState(0);
  const sessionSeed = session?.seed;
  useEffect(() => {
    if (sessionSeed !== undefined) setSeed(sessionSeed);
  }, [sessionSeed]);

  const ready = connected && session !== null;
  const playing = session?.playing ?? false;
  const paused = session?.paused_on_escalation_id != null;
  const done = session?.done ?? false;
  const replay = session?.source === "replay";
  const total = replay ? session?.total_steps : hello?.config.duration;

  return (
    <header className="panel flex flex-wrap items-center gap-x-3 gap-y-1.5 px-3 py-1.5">
      <div className="flex shrink-0 items-center gap-2">
        <span className={`h-2 w-2 rounded-full ${connected ? "bg-emerald-400" : "bg-rose-500"}`} />
        <span className="text-[12px] font-semibold tracking-[0.22em] text-zinc-200">INTERLOCK</span>
      </div>
      <div className="flex shrink-0 overflow-hidden rounded border border-zinc-700 text-[11px]">
        {(["console", "metrics"] as const).map((v) => (
          <button
            key={v}
            type="button"
            onClick={() => setView(v)}
            className={`px-2 py-0.5 ${view === v ? "bg-zinc-700 text-zinc-100" : "bg-zinc-900 text-zinc-400 hover:text-zinc-200"}`}
          >
            {v}
          </button>
        ))}
      </div>
      <span className={`badge ${replay ? "border-amber-500/50 text-amber-300" : "border-zinc-700 text-zinc-300"}`}>
        {session?.source ?? "offline"}
      </span>
      <span className={`badge ${session?.judge_mode === "live" ? "border-cyan-500/40 text-cyan-300" : "border-zinc-700 text-zinc-400"}`}>
        jev {session?.judge_mode ?? "?"}
      </span>

      <div className="mx-1 h-5 w-px bg-zinc-800" />

      <label className="flex items-center gap-1 text-[11px] text-zinc-400">
        seed
        <input
          type="number"
          min={0}
          className="w-14 rounded border border-zinc-700 bg-zinc-900 px-1.5 py-0.5 text-zinc-200"
          value={seed}
          onChange={(e) => setSeed(Number(e.target.value))}
        />
      </label>
      <button className="btn" disabled={!ready} onClick={() => send({ type: "reset", seed })}>
        reset
      </button>
      <button className="btn" disabled={!ready || playing || paused || done} onClick={() => send({ type: "step" })}>
        step
      </button>
      <button
        className={`btn ${playing ? "" : "btn-primary"}`}
        disabled={!ready || done}
        onClick={() => send({ type: playing ? "pause" : "play" })}
      >
        {playing ? "pause" : "play"}
      </button>
      <select
        className="rounded border border-zinc-700 bg-zinc-900 px-1.5 py-1 text-[11px] text-zinc-300"
        value={session?.speed ?? 2}
        disabled={!ready}
        onChange={(e) => send({ type: "set_speed", steps_per_sec: Number(e.target.value) })}
      >
        {SPEEDS.map((v) => (
          <option key={v} value={v}>
            {v} steps/s
          </option>
        ))}
      </select>

      <div className="mx-1 h-5 w-px bg-zinc-800" />

      <button
        disabled={!ready || replay}
        onClick={() => send({ type: "set_shield", on: !(session?.shield_on ?? true) })}
        className={`badge transition-colors ${
          session?.shield_on
            ? "border-cyan-500/60 bg-cyan-500/20 text-cyan-100"
            : "border-zinc-700 bg-zinc-800 text-zinc-400"
        }`}
        title="Toggle the shield on the same seed"
      >
        shield {session?.shield_on ? "on" : "off"}
      </button>
      {paused && <span className="badge border-violet-500/60 bg-violet-500/20 text-violet-200">waiting on operator</span>}
      {done && <span className="badge border-zinc-600 text-zinc-300">episode over</span>}

      <div className="mx-1 h-5 w-px bg-zinc-800" />

      <select
        className="max-w-[210px] rounded border border-zinc-700 bg-zinc-900 px-1.5 py-1 text-[11px] text-zinc-300"
        value=""
        disabled={!ready || runs.length === 0}
        onChange={(e) => {
          if (e.target.value) send({ type: "load_replay", run_id: e.target.value });
        }}
        title="Replay a logged run"
      >
        <option value="">{runs.length ? `replay a run (${runs.length})` : "no logged runs yet"}</option>
        {runs.map((r) => (
          <option key={r} value={r}>
            {r}
          </option>
        ))}
      </select>
      {replay && (
        <button className="btn" onClick={() => send({ type: "load_live" })}>
          back to live
        </button>
      )}
      {inspecting !== null && (
        <span className="badge border-violet-500/40 text-violet-200">inspecting {inspecting}</span>
      )}

      <div className="flex-1" />

      {latest && (
        <span className={`badge ${DECISION_CLASS[latest.decision]}`}>
          {DECISION_LABEL[latest.decision]}
          {latest.executed !== latest.candidates[0]?.action && ` -> ${latest.executed}`}
        </span>
      )}
      <Stat label="step" value={session ? `${session.step}${total ? ` / ${total}` : ""}` : "-"} />
      <Stat label="jev" value={latest ? `${latest.judge.source} ${fmtMs(latest.judge.latency_ms)}` : "-"} />
      <Stat label="cost" value={metrics ? fmtUsd(metrics.cost_usd) : "-"} />
      <Stat label="violations" value={metrics ? String(metrics.violations_total) : "-"} />
    </header>
  );
}
