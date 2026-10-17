import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  LabelList,
} from "recharts";
import { httpUrl } from "../backend-url";
import { fmtUsd } from "../format";
import type { EvalReport, Reliability } from "../types";

// Dark-surface steps of the reference palette: slot 1 blue for shield on,
// slot 2 orange for shield off, slot 3 aqua for the third checker.
const ON = "#3987e5";
const OFF = "#d95926";
const AQUA = "#199e70";
const CHECKER_COLOR: Record<string, string> = { speed_limit: ON, lane_change_gap: OFF, left_lane_passing: AQUA };
const CHECKER_LABEL: Record<string, string> = {
  speed_limit: "speed limit",
  lane_change_gap: "lane change gap",
  left_lane_passing: "left lane passing",
  lane_closed: "lane closed",
};
const GRID = "#383835";
const INK = "#c3c2b7";
const TOOLTIP = { backgroundColor: "#1a1a19", border: "1px solid #383835", color: "#f0efec", fontSize: 11 };

function Tile({ label, off, on, fmt }: { label: string; off: number | undefined; on: number | undefined; fmt: (v: number) => string }) {
  return (
    <div className="rounded border border-zinc-800 bg-zinc-900/60 px-3 py-2">
      <div className="text-[10px] tracking-[0.18em] text-zinc-500 uppercase">{label}</div>
      <div className="mt-1 flex items-baseline gap-3 tabular-nums">
        <span className="text-zinc-500">
          off <span className="text-lg" style={{ color: OFF }}>{off === undefined ? "-" : fmt(off)}</span>
        </span>
        <span className="text-zinc-500">
          on <span className="text-lg" style={{ color: ON }}>{on === undefined ? "-" : fmt(on)}</span>
        </span>
      </div>
    </div>
  );
}

function Panel({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <section className="panel flex min-h-[300px] flex-col">
      <div className="panel-title">
        <span>{title}</span>
        {subtitle && <span className="font-normal tracking-normal text-zinc-500 normal-case">{subtitle}</span>}
      </div>
      <div className="min-h-0 flex-1 p-2">{children}</div>
    </section>
  );
}

function reliabilitySeries(rel: Reliability) {
  return rel.bins.filter((b) => b.count > 0 && b.mean_p !== null).map((b) => ({ p: b.mean_p, observed: b.observed, count: b.count }));
}

export function MetricsView() {
  const [report, setReport] = useState<EvalReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(httpUrl("/eval/latest"))
      .then((r) => r.json() as Promise<EvalReport>)
      .then((r) => {
        if (!cancelled) setReport(r);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) return <div className="panel p-4 text-rose-300">Could not load the evaluation report: {error}</div>;
  if (!report) return <div className="panel p-4 text-zinc-500">Loading the evaluation report</div>;
  if (!report.available || !report.before_after) {
    return (
      <div className="panel p-4 text-zinc-400">
        No evaluation yet. {report.message}
      </div>
    );
  }

  const off = report.before_after.off;
  const on = report.before_after.on;
  const seeds = off?.episodes.map((e) => e.seed) ?? on?.episodes.map((e) => e.seed) ?? [];
  const perSeed = seeds.map((seed) => {
    const o = off?.episodes.find((e) => e.seed === seed);
    const n = on?.episodes.find((e) => e.seed === seed);
    return { seed, violations_off: o?.violations_total ?? 0, violations_on: n?.violations_total ?? 0, return_off: o?.return ?? 0, return_on: n?.return ?? 0 };
  });
  const sweep = (report.sweep ?? []).map((p) => ({ ...p, label: `${p.t_allow.toFixed(1)}/${p.t_block.toFixed(1)}` }));
  const cal = report.calibration;
  const checkers = cal ? Object.keys(cal.by_checker).filter((k) => k in CHECKER_COLOR) : [];

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-auto">
      <div className="grid grid-cols-5 gap-2">
        <Tile label="violations per episode" off={off?.aggregate.violations_per_episode} on={on?.aggregate.violations_per_episode} fmt={(v) => v.toFixed(1)} />
        <Tile label="task return" off={off?.aggregate.mean_return} on={on?.aggregate.mean_return} fmt={(v) => v.toFixed(1)} />
        <Tile label="crash rate" off={off?.aggregate.crash_rate} on={on?.aggregate.crash_rate} fmt={(v) => `${Math.round(v * 100)}%`} />
        <Tile label="escalation rate" off={off?.aggregate.escalation_rate} on={on?.aggregate.escalation_rate} fmt={(v) => `${(v * 100).toFixed(1)}%`} />
        <Tile label="cost per episode" off={off?.aggregate.cost_per_episode_usd} on={on?.aggregate.cost_per_episode_usd} fmt={fmtUsd} />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <Panel title="Violations per seed" subtitle={`${seeds.length} seeds · thresholds ${report.thresholds_default?.t_allow} / ${report.thresholds_default?.t_block}`}>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={perSeed} barGap={2} barCategoryGap="30%">
              <CartesianGrid stroke={GRID} vertical={false} />
              <XAxis dataKey="seed" tick={{ fill: INK, fontSize: 10 }} axisLine={{ stroke: GRID }} tickLine={false} />
              <YAxis tick={{ fill: INK, fontSize: 10 }} axisLine={false} tickLine={false} width={28} />
              <Tooltip contentStyle={TOOLTIP} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
              <Legend wrapperStyle={{ fontSize: 11, color: INK }} />
              <Bar dataKey="violations_off" name="shield off" fill={OFF} radius={[2, 2, 0, 0]} />
              <Bar dataKey="violations_on" name="shield on" fill={ON} radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Panel>
        <Panel title="Task return per seed" subtitle="the cost of safety">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={perSeed} barGap={2} barCategoryGap="30%">
              <CartesianGrid stroke={GRID} vertical={false} />
              <XAxis dataKey="seed" tick={{ fill: INK, fontSize: 10 }} axisLine={{ stroke: GRID }} tickLine={false} />
              <YAxis tick={{ fill: INK, fontSize: 10 }} axisLine={false} tickLine={false} width={28} />
              <Tooltip contentStyle={TOOLTIP} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
              <Legend wrapperStyle={{ fontSize: 11, color: INK }} />
              <Bar dataKey="return_off" name="shield off" fill={OFF} radius={[2, 2, 0, 0]} />
              <Bar dataKey="return_on" name="shield on" fill={ON} radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Panel>
        <Panel title="Choosing the thresholds" subtitle="violations per episode against the share of steps escalated">
          <ResponsiveContainer width="100%" height={260}>
            <ScatterChart margin={{ top: 16, right: 40, bottom: 8, left: 0 }}>
              <CartesianGrid stroke={GRID} />
              <XAxis
                type="number"
                dataKey="escalation_rate"
                name="escalation rate"
                tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
                tick={{ fill: INK, fontSize: 10 }}
                axisLine={{ stroke: GRID }}
                tickLine={false}
                domain={[0, "auto"]}
              />
              <YAxis type="number" dataKey="violations_per_episode" name="violations per episode" tick={{ fill: INK, fontSize: 10 }} axisLine={false} tickLine={false} width={36} domain={[0, "auto"]} />
              <Tooltip contentStyle={TOOLTIP} cursor={{ stroke: GRID }} formatter={(v, name) => (String(name) === "escalation rate" ? `${(Number(v) * 100).toFixed(1)}%` : String(v ?? ""))} />
              <Scatter data={sweep} fill={ON} line={{ stroke: ON, strokeWidth: 2 }} name="t_allow / t_block">
                <LabelList dataKey="label" position="top" fill={INK} fontSize={10} />
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
        </Panel>
        <Panel title="Is p(violation) calibrated?" subtitle={cal ? `${cal.overall.n} labeled checks · ECE ${cal.overall.ece.toFixed(3)} · Brier ${cal.overall.brier.toFixed(3)}` : ""}>
          {cal && (
            <ResponsiveContainer width="100%" height={260}>
              <LineChart margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                <CartesianGrid stroke={GRID} />
                <XAxis type="number" dataKey="p" domain={[0, 1]} tick={{ fill: INK, fontSize: 10 }} axisLine={{ stroke: GRID }} tickLine={false} label={{ value: "Jev p(violation)", fill: INK, fontSize: 10, position: "insideBottom", dy: 8 }} />
                <YAxis type="number" domain={[0, 1]} tick={{ fill: INK, fontSize: 10 }} axisLine={false} tickLine={false} width={36} />
                <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]} stroke={GRID} strokeWidth={1} />
                <Tooltip contentStyle={TOOLTIP} />
                <Legend wrapperStyle={{ fontSize: 11, color: INK }} />
                <Line data={reliabilitySeries(cal.overall)} dataKey="observed" name={`all rules, ECE ${cal.overall.ece.toFixed(3)}`} stroke={INK} strokeDasharray="4 3" strokeWidth={2} dot={false} isAnimationActive={false} />
                {checkers.map((name) => {
                  const rel = cal.by_checker[name];
                  if (!rel) return null;
                  return (
                    <Line key={name} data={reliabilitySeries(rel)} dataKey="observed" name={`${CHECKER_LABEL[name] ?? name}, ECE ${rel.ece.toFixed(3)}`} stroke={CHECKER_COLOR[name]} strokeWidth={2} dot={{ r: 3, strokeWidth: 0 }} isAnimationActive={false} />
                  );
                })}
              </LineChart>
            </ResponsiveContainer>
          )}
        </Panel>
      </div>
      <div className="text-[11px] text-zinc-500">
        generated {report.generated_at} · {on?.aggregate.latency_ms_p50 ?? "-"} ms p50 / {on?.aggregate.latency_ms_p95 ?? "-"} ms p95 per step live ·{" "}
        operator {on?.aggregate.human.approve ?? 0} approved, {on?.aggregate.human.deny ?? 0} denied (simulated by the checkers)
      </div>
    </div>
  );
}
