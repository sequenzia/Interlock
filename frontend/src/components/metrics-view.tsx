import { useEffect } from "react";
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
} from "recharts";
import { httpUrl } from "../backend-url";
import { fmtPct, fmtUsd } from "../format";
import { useStore } from "../store";
import type { EvalReport, JudgeSummary, Reliability } from "../types";

// Dark-surface steps of the reference palette: slot 1 blue for shield on,
// slot 2 orange for shield off, slot 3 aqua for the third checker.
const ON = "#3987e5";
const OFF = "#d95926";
const AQUA = "#199e70";
const CHECKER_COLOR: Record<string, string> = {
  speed_limit: ON,
  lane_change_gap: OFF,
  left_lane_passing: AQUA,
  headway: "#a78bfa",
  lane_change_rate: "#f59e0b",
  cut_in: "#f472b6",
  dense_traffic: "#22d3ee",
};
const CHECKER_LABEL: Record<string, string> = {
  speed_limit: "speed limit",
  lane_change_gap: "lane change gap",
  left_lane_passing: "left lane passing",
  lane_closed: "lane closed",
  headway: "headway 2 s",
  lane_change_rate: "one lane change per 10 s",
  cut_in: "room when moving in",
  dense_traffic: "conservative in dense traffic",
};
const BASELINE_COLOR = [OFF, "#a78bfa", AQUA, "#f59e0b"];
const GRID = "#383835";
const INK = "#c3c2b7";
const TOOLTIP = { backgroundColor: "#1a1a19", border: "1px solid #383835", color: "#f0efec", fontSize: 11 };
const TICK = { fill: INK, fontSize: 10 };

interface TileProps {
  label: string;
  headline: string;
  tone: "allow" | "escalate" | "neutral";
  off: number | undefined;
  on: number | undefined;
  fmt: (v: number) => string;
}

/** The delta leads; off and on sit under it in the chart colors. */
function Tile({ label, headline, tone, off, on, fmt }: TileProps) {
  const toneClass = tone === "allow" ? "text-allow" : tone === "escalate" ? "text-escalate" : "text-zinc-100";
  return (
    <div className="panel px-3 py-2">
      <div className="stat-label">{label}</div>
      <div className={`num mt-0.5 text-lg font-semibold ${toneClass}`}>{headline}</div>
      <div className="num mt-0.5 flex items-baseline gap-3 text-xs text-zinc-400">
        <span>
          off <span style={{ color: OFF }}>{off === undefined ? "-" : fmt(off)}</span>
        </span>
        <span>
          on <span style={{ color: ON }}>{on === undefined ? "-" : fmt(on)}</span>
        </span>
      </div>
    </div>
  );
}

function Panel({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <section className="panel flex shrink-0 flex-col">
      <div className="panel-title">
        <span>{title}</span>
        {subtitle && <span className="panel-subtitle min-w-0 truncate">{subtitle}</span>}
      </div>
      <div className="p-2">{children}</div>
    </section>
  );
}

function reliabilitySeries(rel: Reliability) {
  return rel.bins.filter((b) => b.count > 0 && b.mean_p !== null).map((b) => ({ p: b.mean_p, observed: b.observed, count: b.count }));
}

const TH = "px-2 py-1 text-left text-2xs font-normal text-zinc-400";
const TH_NUM = "px-2 py-1 text-right text-2xs font-normal text-zinc-400";
const TD = "px-2 py-0.5";
const TD_NUM = "num px-2 py-0.5 text-right";

function violationsHeadline(off: number | undefined, on: number | undefined): string {
  if (off === undefined || on === undefined) return "-";
  if (on === 0) return off > 0 ? "none with the shield" : "none";
  const ratio = off / on;
  return ratio >= 2 ? `${ratio.toFixed(ratio >= 10 ? 0 : 1)}× fewer` : `${fmtPct((on - off) / off, 0)}`;
}

function returnHeadline(off: number | undefined, on: number | undefined): string {
  if (off === undefined || on === undefined || off === 0) return "-";
  const d = (on - off) / off;
  return `${d >= 0 ? "+" : ""}${(d * 100).toFixed(1)}% return`;
}

export function MetricsView() {
  const report = useStore((s) => s.report);
  const setReport = useStore((s) => s.setReport);

  useEffect(() => {
    if (report !== null) return;
    let cancelled = false;
    fetch(httpUrl("/eval/latest"))
      .then((r) => r.json() as Promise<EvalReport>)
      .then((r) => {
        if (!cancelled) setReport(r);
      })
      .catch((e: unknown) => {
        if (!cancelled) setReport({ available: false, message: `Could not load the evaluation report: ${e instanceof Error ? e.message : String(e)}` });
      });
    return () => {
      cancelled = true;
    };
  }, [report, setReport]);

  if (!report) return <div className="panel p-4 text-zinc-400">Loading the evaluation report</div>;
  if (!report.available || !report.before_after) {
    return <div className="panel p-4 text-zinc-300">No evaluation yet. {report.message}</div>;
  }

  const off = report.before_after.off;
  const on = report.before_after.on;
  const seeds = off?.episodes.map((e) => e.seed) ?? on?.episodes.map((e) => e.seed) ?? [];
  const perSeed = seeds.map((seed) => {
    const o = off?.episodes.find((e) => e.seed === seed);
    const n = on?.episodes.find((e) => e.seed === seed);
    return {
      seed,
      violations_off: o?.violations_total ?? 0,
      violations_on: n?.violations_total ?? 0,
      return_off: o?.return ?? 0,
      return_on: n?.return ?? 0,
    };
  });
  const sweep = (report.sweep ?? []).map((p) => ({ ...p, pair: `${p.t_allow.toFixed(1)} / ${p.t_block.toFixed(1)}` }));
  const cal = report.calibration;
  const floorRows = report.floor?.rows ?? [];
  const floorDefault = report.floor?.floor_s ?? 2;
  const baseline = report.baseline ?? null;
  const td = report.thresholds_default;
  const isDefaultPair = (a: number, b: number): boolean => td !== undefined && a === td.t_allow && b === td.t_block;
  const checkers = cal ? Object.keys(cal.by_checker).filter((k) => k in CHECKER_COLOR) : [];
  const p1 = (v: number): string => `${(v * 100).toFixed(1)}%`;

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-auto">
      <div className="grid shrink-0 grid-cols-5 gap-2">
        <Tile
          label="violations per episode"
          headline={violationsHeadline(off?.aggregate.violations_per_episode, on?.aggregate.violations_per_episode)}
          tone="allow"
          off={off?.aggregate.violations_per_episode}
          on={on?.aggregate.violations_per_episode}
          fmt={(v) => v.toFixed(1)}
        />
        <Tile
          label="task return"
          headline={returnHeadline(off?.aggregate.mean_return, on?.aggregate.mean_return)}
          tone="neutral"
          off={off?.aggregate.mean_return}
          on={on?.aggregate.mean_return}
          fmt={(v) => v.toFixed(1)}
        />
        <Tile
          label="crash rate"
          headline={off && on ? `${fmtPct(off.aggregate.crash_rate)} → ${fmtPct(on.aggregate.crash_rate)}` : "-"}
          tone={on && off && on.aggregate.crash_rate < off.aggregate.crash_rate ? "allow" : "neutral"}
          off={off?.aggregate.crash_rate}
          on={on?.aggregate.crash_rate}
          fmt={(v) => fmtPct(v)}
        />
        <Tile
          label="steps escalated"
          headline={on ? `${p1(on.aggregate.escalation_rate)} of steps` : "-"}
          tone="escalate"
          off={off?.aggregate.escalation_rate}
          on={on?.aggregate.escalation_rate}
          fmt={p1}
        />
        <Tile
          label="cost per episode"
          headline={on ? `${fmtUsd(on.aggregate.cost_per_episode_usd)} / episode` : "-"}
          tone="neutral"
          off={off?.aggregate.cost_per_episode_usd}
          on={on?.aggregate.cost_per_episode_usd}
          fmt={fmtUsd}
        />
      </div>

      <div className="grid shrink-0 grid-cols-2 gap-2">
        <Panel title="Violations per seed" subtitle={`${seeds.length} seeds · thresholds ${td?.t_allow} / ${td?.t_block}`}>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={perSeed} barGap={2} barCategoryGap="30%">
              <CartesianGrid stroke={GRID} vertical={false} />
              <XAxis dataKey="seed" tick={TICK} axisLine={{ stroke: GRID }} tickLine={false} />
              <YAxis tick={TICK} axisLine={false} tickLine={false} width={28} />
              <Tooltip contentStyle={TOOLTIP} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
              <Legend wrapperStyle={{ fontSize: 11, color: INK }} />
              <Bar dataKey="violations_off" name="shield off" fill={OFF} radius={[2, 2, 0, 0]} />
              <Bar dataKey="violations_on" name="shield on" fill={ON} radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Panel>
        <Panel title="Task return per seed" subtitle="the cost of safety">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={perSeed} barGap={2} barCategoryGap="30%">
              <CartesianGrid stroke={GRID} vertical={false} />
              <XAxis dataKey="seed" tick={TICK} axisLine={{ stroke: GRID }} tickLine={false} />
              <YAxis tick={TICK} axisLine={false} tickLine={false} width={28} />
              <Tooltip contentStyle={TOOLTIP} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
              <Legend wrapperStyle={{ fontSize: 11, color: INK }} />
              <Bar dataKey="return_off" name="shield off" fill={OFF} radius={[2, 2, 0, 0]} />
              <Bar dataKey="return_on" name="shield on" fill={ON} radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Panel>

        <Panel title="Choosing the thresholds" subtitle="violations per episode against the share of steps escalated">
          <div className="grid grid-cols-[minmax(0,3fr)_minmax(0,2fr)] gap-2">
            <ResponsiveContainer width="100%" height={240}>
              <ScatterChart margin={{ top: 12, right: 16, bottom: 8, left: 0 }}>
                <CartesianGrid stroke={GRID} />
                <XAxis
                  type="number"
                  dataKey="escalation_rate"
                  name="escalation rate"
                  tickFormatter={(v: number) => fmtPct(v)}
                  tick={TICK}
                  axisLine={{ stroke: GRID }}
                  tickLine={false}
                  domain={[0, "auto"]}
                />
                <YAxis type="number" dataKey="violations_per_episode" name="violations per episode" tick={TICK} axisLine={false} tickLine={false} width={36} domain={[0, "auto"]} />
                <Tooltip
                  contentStyle={TOOLTIP}
                  cursor={{ stroke: GRID }}
                  formatter={(v, name) => (String(name) === "escalation rate" ? p1(Number(v)) : String(v ?? ""))}
                  labelFormatter={() => ""}
                />
                <Scatter data={sweep} fill={ON} line={{ stroke: ON, strokeWidth: 2 }} name="t_allow / t_block" />
              </ScatterChart>
            </ResponsiveContainer>
            <table className="self-start text-xs">
              <thead>
                <tr>
                  <th className={TH}>pair</th>
                  <th className={TH_NUM}>escalated</th>
                  <th className={TH_NUM}>violations</th>
                  <th className={TH_NUM}>return</th>
                </tr>
              </thead>
              <tbody>
                {sweep.map((p) => {
                  const dflt = isDefaultPair(p.t_allow, p.t_block);
                  return (
                    <tr key={p.pair} className={`border-t border-zinc-800 ${dflt ? "bg-accent/10 text-zinc-50" : "text-zinc-300"}`}>
                      <td className={`${TD} num whitespace-nowrap`}>
                        {p.pair}
                        {dflt && <span className="ml-1.5 text-[0.625rem] text-accent uppercase">default</span>}
                      </td>
                      <td className={TD_NUM}>{p1(p.escalation_rate)}</td>
                      <td className={TD_NUM}>{p.violations_per_episode.toFixed(2)}</td>
                      <td className={TD_NUM}>{p.mean_return.toFixed(1)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Panel>

        <Panel
          title="Is p(violation) calibrated?"
          subtitle={cal ? `${cal.overall.n} labeled checks · ECE ${cal.overall.ece.toFixed(3)} · Brier ${cal.overall.brier.toFixed(3)}` : ""}
        >
          {cal && (
            <div className="grid grid-cols-[minmax(0,3fr)_minmax(0,2fr)] gap-2">
              <ResponsiveContainer width="100%" height={240}>
                <LineChart margin={{ top: 8, right: 16, bottom: 16, left: 0 }}>
                  <CartesianGrid stroke={GRID} />
                  <XAxis
                    type="number"
                    dataKey="p"
                    domain={[0, 1]}
                    tick={TICK}
                    axisLine={{ stroke: GRID }}
                    tickLine={false}
                    label={{ value: "Jev p(violation)", fill: INK, fontSize: 10, position: "insideBottom", dy: 12 }}
                  />
                  <YAxis
                    type="number"
                    domain={[0, 1]}
                    tick={TICK}
                    axisLine={false}
                    tickLine={false}
                    width={36}
                    label={{ value: "observed", fill: INK, fontSize: 10, angle: -90, position: "insideLeft" }}
                  />
                  <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]} stroke={GRID} strokeWidth={1} />
                  <Tooltip contentStyle={TOOLTIP} />
                  <Line
                    data={reliabilitySeries(cal.overall)}
                    dataKey="observed"
                    name="all rules"
                    stroke={INK}
                    strokeDasharray="4 3"
                    strokeWidth={2}
                    dot={false}
                    isAnimationActive={false}
                  />
                  {checkers.map((name) => {
                    const rel = cal.by_checker[name];
                    if (!rel) return null;
                    return (
                      <Line
                        key={name}
                        data={reliabilitySeries(rel)}
                        dataKey="observed"
                        name={CHECKER_LABEL[name] ?? name}
                        stroke={CHECKER_COLOR[name]}
                        strokeWidth={2}
                        dot={{ r: 3, strokeWidth: 0 }}
                        isAnimationActive={false}
                      />
                    );
                  })}
                </LineChart>
              </ResponsiveContainer>
              <table className="self-start text-xs">
                <thead>
                  <tr>
                    <th className={TH}>rule</th>
                    <th className={TH_NUM}>ECE</th>
                    <th className={TH_NUM}>checks</th>
                    <th className={TH}>labels</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="border-t border-zinc-800 text-zinc-100">
                    <td className={`${TD} flex items-center gap-1.5`}>
                      <span className="h-0.5 w-3 border-t-2 border-dashed" style={{ borderColor: INK }} />
                      all rules
                    </td>
                    <td className={TD_NUM}>{cal.overall.ece.toFixed(3)}</td>
                    <td className={TD_NUM}>{cal.overall.n}</td>
                    <td className={`${TD} text-zinc-400`}>{cal.overall.label_source ?? "checker"}</td>
                  </tr>
                  {checkers.map((name) => {
                    const rel = cal.by_checker[name];
                    if (!rel) return null;
                    return (
                      <tr key={name} className="border-t border-zinc-800 text-zinc-300">
                        <td className={`${TD} flex items-center gap-1.5`}>
                          <span className="h-2 w-2 rounded-full" style={{ background: CHECKER_COLOR[name] }} />
                          {CHECKER_LABEL[name] ?? name}
                        </td>
                        <td className={TD_NUM}>{rel.ece.toFixed(3)}</td>
                        <td className={TD_NUM}>{rel.n}</td>
                        <td className={`${TD} text-zinc-400`}>{rel.label_source ?? "checker"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>

      {floorRows.length > 0 && (
        <Panel
          title="The physics floor"
          subtitle={`a candidate closing on the vehicle ahead in under the floor never runs · default ${floorDefault} s · one row per threshold pair and floor`}
        >
          <table className="w-full text-xs">
            <thead>
              <tr>
                <th className={TH}>pair</th>
                <th className={TH}>floor</th>
                <th className={TH_NUM}>crash rate</th>
                <th className={TH_NUM}>violations per episode</th>
                <th className={TH_NUM}>task return</th>
                <th className={TH_NUM}>steps escalated</th>
                <th className={TH_NUM}>steps floored</th>
              </tr>
            </thead>
            <tbody>
              {floorRows.flatMap((r, ri) =>
                Object.entries(r.by_floor)
                  .sort(([x], [y]) => Number(x) - Number(y))
                  .map(([f, c], fi) => {
                    const dflt = isDefaultPair(r.t_allow, r.t_block) && Number(f) === floorDefault;
                    const band = ri % 2 === 1 ? "bg-zinc-800/30" : "";
                    return (
                      <tr
                        key={`${r.t_allow}-${f}`}
                        className={`${fi === 0 ? "border-t border-zinc-800" : ""} ${band} ${dflt ? "text-zinc-50" : "text-zinc-300"}`}
                      >
                        <td className={`${TD} num`}>
                          {fi === 0 ? `${r.t_allow.toFixed(1)} / ${r.t_block.toFixed(1)}` : ""}
                        </td>
                        <td className={`${TD} num`}>
                          {Number(f) > 0 ? `${f} s` : "off"}
                          {dflt && <span className="ml-1.5 text-[0.625rem] text-accent uppercase">default</span>}
                        </td>
                        <td className={TD_NUM}>{fmtPct(c.crash_rate)}</td>
                        <td className={TD_NUM}>{c.violations_per_episode.toFixed(2)}</td>
                        <td className={TD_NUM}>{c.mean_return.toFixed(1)}</td>
                        <td className={TD_NUM}>{p1(c.escalation_rate)}</td>
                        <td className={TD_NUM}>{p1(c.floored_rate)}</td>
                      </tr>
                    );
                  }),
              )}
            </tbody>
          </table>
        </Panel>
      )}

      {baseline && (
        <Panel
          title="Jev against chat models"
          subtitle={`${baseline.checks} labeled checks sampled from the logs, stratified by rule and label · Jev's answers come from the logs`}
        >
          <div className="grid grid-cols-[minmax(0,3fr)_minmax(0,2fr)] gap-2">
            <ResponsiveContainer width="100%" height={240}>
              <LineChart margin={{ top: 8, right: 16, bottom: 16, left: 0 }}>
                <CartesianGrid stroke={GRID} />
                <XAxis
                  type="number"
                  dataKey="p"
                  domain={[0, 1]}
                  tick={TICK}
                  axisLine={{ stroke: GRID }}
                  tickLine={false}
                  label={{ value: "p(violation)", fill: INK, fontSize: 10, position: "insideBottom", dy: 12 }}
                />
                <YAxis type="number" domain={[0, 1]} tick={TICK} axisLine={false} tickLine={false} width={36} label={{ value: "observed", fill: INK, fontSize: 10, angle: -90, position: "insideLeft" }} />
                <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]} stroke={GRID} strokeWidth={1} />
                <Tooltip contentStyle={TOOLTIP} />
                <Line data={reliabilitySeries(baseline.jev.overall)} dataKey="observed" name="Jev" stroke={ON} strokeDasharray="4 3" strokeWidth={2} dot={false} isAnimationActive={false} />
                {Object.entries(baseline.models).map(([model, s], i) => (
                  <Line
                    key={model}
                    data={reliabilitySeries(s.overall)}
                    dataKey="observed"
                    name={model}
                    stroke={BASELINE_COLOR[i % BASELINE_COLOR.length]}
                    strokeWidth={2}
                    dot={{ r: 3, strokeWidth: 0 }}
                    isAnimationActive={false}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
            <table className="self-start text-xs">
              <thead>
                <tr>
                  <th className={TH}>judge</th>
                  <th className={TH_NUM}>ECE</th>
                  <th className={TH_NUM}>Brier</th>
                  <th className={TH_NUM}>acc</th>
                  <th className={TH_NUM}>p50</th>
                  <th className={TH_NUM}>cost</th>
                </tr>
              </thead>
              <tbody>
                {([["Jev", baseline.jev, ON] as [string, JudgeSummary, string]] as Array<[string, JudgeSummary, string]>)
                  .concat(Object.entries(baseline.models).map(([m, s], i) => [m, s, BASELINE_COLOR[i % BASELINE_COLOR.length] ?? INK]))
                  .map(([name, s, color]) => (
                    <tr key={name} className="border-t border-zinc-800 text-zinc-300">
                      <td className={`${TD} flex items-center gap-1.5`}>
                        <span className="h-2 w-2 rounded-full" style={{ background: color }} />
                        <span className="font-mono">{name}</span>
                        {s.failed ? <span className="text-2xs text-zinc-500">{s.failed} failed</span> : null}
                      </td>
                      <td className={TD_NUM}>{s.overall.ece.toFixed(3)}</td>
                      <td className={TD_NUM}>{s.overall.brier.toFixed(3)}</td>
                      <td className={TD_NUM}>{p1(s.overall.accuracy_at_0_5)}</td>
                      <td className={TD_NUM}>{s.latency_ms_p50 == null ? "n/a" : `${Math.round(s.latency_ms_p50)} ms`}</td>
                      <td className={TD_NUM}>{s.cost_usd == null ? "not priced" : fmtUsd(s.cost_usd)}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}

      <div className="num shrink-0 px-1 pb-1 text-2xs text-zinc-400">
        generated {report.generated_at} · {on?.aggregate.latency_ms_p50 ?? "-"} ms p50 / {on?.aggregate.latency_ms_p95 ?? "-"} ms p95 per step live · operator{" "}
        {on?.aggregate.human.approve ?? 0} approved, {on?.aggregate.human.deny ?? 0} denied, {on?.aggregate.human.override ?? 0} overridden (simulated by the checkers)
      </div>
    </div>
  );
}
