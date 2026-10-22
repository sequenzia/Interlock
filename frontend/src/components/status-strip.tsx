import { useEffect, useState } from "react";
import { DECISION_CLASS, DECISION_LABEL, fmtMs, fmtUsd } from "../format";
import { KeyboardIcon, PauseIcon, PlayIcon, ResetIcon, StepIcon } from "../icons";
import { selectLatestStep, useStore } from "../store";
import { send } from "../ws-client";

const SPEEDS = [0.5, 1, 2, 4];
const NO_RUNS: string[] = [];

/** A readout: the label over a mono value, left-aligned so the label reads as a column head whatever the value's width. */
function Stat({ label, value, className }: { label: string; value: string; className?: string }) {
  return (
    <div className={`flex flex-col leading-tight ${className ?? ""}`}>
      <span className="stat-label">{label}</span>
      <span className="num text-xs text-zinc-100">{value}</span>
    </div>
  );
}

/** One slot, one badge: the most urgent state wins, so the header never grows. */
function StatusSlot() {
  const session = useStore((s) => s.session);
  const inspecting = useStore((s) => s.selectedStep);
  const latest = useStore(selectLatestStep);
  const paused = session?.paused_on_escalation_id != null;
  const done = session?.done ?? false;
  let badge: React.ReactNode = null;
  if (paused) {
    badge = (
      <span className="badge min-w-0 border-escalate/60 bg-escalate/15 text-escalate">
        <span className="truncate">waiting on operator</span>
      </span>
    );
  } else if (inspecting !== null) {
    badge = (
      <span className="badge min-w-0 border-zinc-500 bg-zinc-800 text-zinc-100" title="arrow keys move, esc follows live">
        <span className="truncate">inspecting {inspecting}</span>
      </span>
    );
  } else if (done) {
    badge = (
      <span className="badge min-w-0 border-zinc-600 text-zinc-300">
        <span className="truncate">episode over</span>
      </span>
    );
  } else if (latest) {
    badge = (
      <span className={`badge min-w-0 ${DECISION_CLASS[latest.decision]}`}>
        <span className="truncate">
          {DECISION_LABEL[latest.decision]}
          {latest.executed !== latest.candidates[0]?.action && <span className="font-mono"> → {latest.executed}</span>}
        </span>
      </span>
    );
  }
  return <div className="flex min-w-0 flex-1 items-center overflow-hidden">{badge}</div>;
}

function Transport() {
  const connected = useStore((s) => s.connected);
  const session = useStore((s) => s.session);
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
  const shieldOn = session?.shield_on ?? true;

  return (
    <>
      <div className="flex items-center gap-1 rounded-md border border-zinc-800 bg-zinc-900/60 p-1">
        <button
          className="btn btn-flat h-7"
          disabled={!ready}
          onClick={() => send({ type: "reset", seed })}
          aria-label="reset"
          title="reset the episode on this seed"
        >
          <ResetIcon />
          <span className="talk-hide max-2xl:hidden">reset</span>
        </button>
        <label className="flex h-7 items-center gap-1.5 pr-1 text-2xs text-zinc-400">
          <span className="max-2xl:hidden">seed</span>
          <input
            type="number"
            min={0}
            aria-label="seed"
            className="num h-6 w-11 rounded border border-zinc-700 bg-zinc-950 px-1.5 text-xs text-zinc-100 focus:border-accent focus-visible:outline-none"
            value={seed}
            onChange={(e) => setSeed(Number(e.target.value))}
          />
        </label>
        <span className="h-4 w-px bg-zinc-700/70" />
        <button
          className="btn btn-flat h-7"
          disabled={!ready || playing || paused || done}
          onClick={() => send({ type: "step" })}
          aria-label="step"
          title="one step (n)"
        >
          <StepIcon />
          <span className="max-2xl:hidden">step</span>
        </button>
        <button
          className={`btn h-7 ${playing ? "" : "btn-primary"}`}
          disabled={!ready || done}
          onClick={() => send({ type: playing ? "pause" : "play" })}
          aria-label={playing ? "pause" : "play"}
          title="play or pause (space)"
        >
          {playing ? <PauseIcon /> : <PlayIcon />}
          <span className="max-2xl:hidden">{playing ? "pause" : "play"}</span>
        </button>
        <select
          aria-label="speed in steps per second"
          title="steps per second"
          className="btn btn-flat num h-7 pr-1 pl-2"
          value={session?.speed ?? 2}
          disabled={!ready}
          onChange={(e) => send({ type: "set_speed", steps_per_sec: Number(e.target.value) })}
        >
          {SPEEDS.map((v) => (
            <option key={v} value={v}>
              {v}/s
            </option>
          ))}
        </select>
      </div>

      <button
        type="button"
        role="switch"
        aria-checked={shieldOn}
        disabled={!ready || replay}
        onClick={() => send({ type: "set_shield", on: !shieldOn })}
        className="flex shrink-0 items-center gap-1.5 text-xs text-zinc-200 disabled:cursor-not-allowed disabled:opacity-40"
        aria-label="shield"
        title="Toggle the shield on the same seed"
      >
        <span className="switch" data-on={shieldOn} aria-hidden="true">
          <span className="switch-knob" />
        </span>
        <span className="max-2xl:hidden">shield</span>
        <span className={`num ${shieldOn ? "text-accent" : "text-zinc-400"}`}>{shieldOn ? "on" : "off"}</span>
      </button>

      <StatusSlot />
    </>
  );
}

/** "2026-10-20T02-14-00_seed0_on" reads as "10-20 02:14 seed0_on" in the menu. */
function runLabel(runId: string): string {
  return runId.replace(/^\d{4}-(\d\d-\d\d)T(\d\d)-(\d\d)-\d\d_/, "$1 $2:$3 ");
}

/** One menu for the source: live, or any logged run to replay. */
function SourceMenu() {
  const connected = useStore((s) => s.connected);
  const session = useStore((s) => s.session);
  const runs = useStore((s) => s.hello?.runs) ?? NO_RUNS;
  if (!session) return <span className="badge border-zinc-700 text-zinc-400">offline</span>;
  const replay = session.source === "replay";
  return (
    <select
      aria-label="source: live or a logged run"
      title={replay ? `replaying ${session.run_id}. Pick live to go back.` : "Replay a logged run"}
      className={`badge cursor-pointer bg-transparent ${replay ? "w-[12rem] border-fallback/50 text-fallback" : "w-[4.75rem] border-zinc-700 text-zinc-300"}`}
      value={replay ? session.run_id : "live"}
      disabled={!connected}
      onChange={(e) => {
        if (e.target.value === "live") send({ type: "load_live" });
        else send({ type: "load_replay", run_id: e.target.value });
      }}
    >
      <option value="live">live</option>
      {replay && !runs.includes(session.run_id) && <option value={session.run_id}>replay {runLabel(session.run_id)}</option>}
      {runs.map((r) => (
        <option key={r} value={r}>
          replay {runLabel(r)}
        </option>
      ))}
    </select>
  );
}

function ReportMeta() {
  const report = useStore((s) => s.report);
  if (!report?.available || !report.before_after) {
    return <span className="text-xs text-zinc-400">Evaluation report</span>;
  }
  const on = report.before_after.on ?? report.before_after.off;
  const t = report.thresholds_default;
  const generated = report.generated_at ? report.generated_at.slice(0, 16).replace("T", " ") : "?";
  return (
    <div className="flex min-w-0 items-center gap-4 overflow-hidden text-xs whitespace-nowrap text-zinc-400">
      <span className="font-medium text-zinc-200">Evaluation report</span>
      <span>
        generated <span className="num text-zinc-200">{generated}</span>
      </span>
      <span>
        seeds <span className="num text-zinc-200">{on?.seeds.length ?? 0}</span>
      </span>
      {t && (
        <span>
          thresholds{" "}
          <span className="num text-zinc-200">
            {t.t_allow} / {t.t_block}
          </span>
        </span>
      )}
      {on && (
        <span>
          jev <span className="num text-zinc-200">{on.jev_mode}</span>
        </span>
      )}
    </div>
  );
}

function LiveStats() {
  const session = useStore((s) => s.session);
  const hello = useStore((s) => s.hello);
  const metrics = useStore((s) => s.metrics);
  const latest = useStore(selectLatestStep);
  const replay = session?.source === "replay";
  const total = replay ? session?.total_steps : hello?.config.duration;
  // The same box as the transport group, at the same height. Hairlines between the cells, and
  // each cell at least as wide as its widest usual value (padding included), so the row holds
  // still while the numbers change under it.
  return (
    <div className="flex divide-x divide-zinc-700/70 rounded-md border border-zinc-800 bg-zinc-900/60 py-0.5">
      <Stat label="step" value={session ? `${session.step}${total ? ` / ${total}` : ""}` : "-"} className="min-w-[4.75rem] px-3" />
      <Stat label="jev" value={latest ? `${latest.judge.source} ${fmtMs(latest.judge.latency_ms)}` : "-"} className="talk-hide min-w-[7rem] px-3 max-[1440px]:hidden" />
      <Stat label="cost" value={metrics ? fmtUsd(metrics.cost_usd) : "-"} className="talk-hide min-w-[4.75rem] px-3 max-[1440px]:hidden" />
      <Stat label="violations" value={metrics ? String(metrics.violations_total) : "-"} className="px-3" />
    </div>
  );
}

export function StatusStrip() {
  const connected = useStore((s) => s.connected);
  const session = useStore((s) => s.session);
  const view = useStore((s) => s.view);
  const setView = useStore((s) => s.setView);
  const density = useStore((s) => s.density);
  const setDensity = useStore((s) => s.setDensity);
  const setShortcutsOpen = useStore((s) => s.setShortcutsOpen);
  const talk = density === "talk";

  return (
    <header className="panel grid shrink-0 grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 px-3 py-1.5">
      <div className="flex shrink-0 items-center gap-3">
        <div className="flex items-center gap-2">
          <span
            className={`h-2 w-2 rounded-full ${connected ? "bg-allow" : "pulse bg-blocked"}`}
            title={connected ? "connected" : "reconnecting"}
          />
          <span className="text-xs font-semibold tracking-[0.18em] text-zinc-100">INTERLOCK</span>
        </div>
        <div role="tablist" className="flex overflow-hidden rounded-md border border-zinc-700 text-xs">
          {(["console", "metrics"] as const).map((v) => (
            <button
              key={v}
              type="button"
              role="tab"
              aria-selected={view === v}
              onClick={() => setView(v)}
              className={`px-2.5 py-0.5 transition-colors ${view === v ? "bg-zinc-700 text-zinc-50" : "bg-zinc-900 text-zinc-400 hover:text-zinc-100"}`}
            >
              {v}
            </button>
          ))}
        </div>
        {view === "console" && <SourceMenu />}
        {session?.judge_mode === "mock" && <span className="badge border-fallback/50 text-fallback">jev mock</span>}
        {!connected && <span className="text-2xs text-blocked">reconnecting</span>}
      </div>

      <div className="flex min-w-0 items-center gap-2.5 overflow-hidden">{view === "console" ? <Transport /> : <ReportMeta />}</div>

      {/* Readouts, then the two app-level utilities in the corner, clear of the session controls. */}
      <div className="flex shrink-0 items-center gap-6">
        {view === "console" && <LiveStats />}
        <div className="flex items-center gap-1">
          <button
            type="button"
            aria-pressed={talk}
            className={`btn btn-icon ${talk ? "border-accent/60 bg-accent/20 text-cyan-50" : ""}`}
            title="Talk density: larger type for a projector"
            onClick={() => setDensity(talk ? "normal" : "talk")}
          >
            Aa
          </button>
          <button
            type="button"
            className="btn btn-icon"
            aria-label="keyboard shortcuts"
            title="Keyboard shortcuts (?)"
            onClick={() => setShortcutsOpen(true)}
          >
            <KeyboardIcon />
          </button>
        </div>
      </div>
    </header>
  );
}
