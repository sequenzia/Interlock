import type { ReactNode } from "react";

// One candidate's facts as cards and a lanes table, read straight from the JSON Jev was sent:
// nothing here is computed, every cell is a field. Known keys get a short label and a unit; a
// key the backend adds later still shows, under its own name, so no fact goes missing.

type Block = Record<string, unknown>;

const LABEL: Record<string, string> = {
  speed_mps: "speed",
  target_speed_mps: "target speed",
  lane_after: "lane after",
  target_speed_after_mps: "target after",
  lane_changes_last_10_steps_including_this_action: "lane changes, incl. this",
  vehicles_within_50_m: "vehicles within 50 m",
  lane_changes_last_10_steps: "lane changes in 10 steps",
  steps_in_current_lane: "steps in this lane",
  vehicle_ahead_gap_m: "vehicle ahead",
  vehicle_ahead_speed_mps: "its speed",
  vehicle_behind_gap_m: "vehicle behind",
  vehicle_behind_closing_speed_mps: "closing at",
  slower_vehicle_ahead_within_40_m: "slower vehicle within 40 m",
  headway_s: "headway",
  time_to_collision_ahead_s: "time to collision",
  being_tailgated: "tailgated within 10 m",
};

// Units by key. A count whose name ends in its threshold, like vehicles_within_50_m, has none,
// which is why the suffix rule in unitOf() applies only to keys this map does not list.
const UNIT: Record<string, string> = {
  lane: "",
  lane_count: "",
  lane_after: "",
  speed_mps: "m/s",
  target_speed_mps: "m/s",
  target_speed_after_mps: "m/s",
  lane_changes_last_10_steps_including_this_action: "",
  vehicles_within_50_m: "",
  lane_changes_last_10_steps: "",
  steps_in_current_lane: "",
  vehicle_ahead_gap_m: "m",
  vehicle_ahead_speed_mps: "m/s",
  vehicle_behind_gap_m: "m",
  vehicle_behind_closing_speed_mps: "m/s",
  headway_s: "s",
  time_to_collision_ahead_s: "s",
};

// Lane metrics in reading order: what is ahead, what is behind, then the margins.
const LANE_ROWS = [
  "vehicle_ahead_gap_m",
  "vehicle_ahead_speed_mps",
  "vehicle_behind_gap_m",
  "vehicle_behind_closing_speed_mps",
  "slower_vehicle_ahead_within_40_m",
  "headway_s",
  "time_to_collision_ahead_s",
  "being_tailgated",
];
const EDGE_KEYS = ["is_leftmost", "is_rightmost"];
const KNOWN_BLOCKS = new Set(["ego", "action", "lane_after_action", "current_lane", "lane_right_of_lane_after", "traffic", "history", "zones"]);

type Tone = "value" | "none" | "blank" | "yes";
interface Cell {
  text: string;
  tone: Tone;
}
const TONE: Record<Tone, string> = {
  value: "text-zinc-100",
  none: "text-zinc-400",
  blank: "text-zinc-600",
  yes: "font-semibold text-zinc-50",
};
const BLANK: Cell = { text: "-", tone: "blank" };

function asBlock(v: unknown): Block | null {
  return typeof v === "object" && v !== null && !Array.isArray(v) ? (v as Block) : null;
}

function asNumber(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

function metres(v: unknown): string {
  const n = asNumber(v);
  return n === null ? "?" : n.toFixed(1);
}

function unitOf(key: string): string {
  const unit = UNIT[key];
  if (unit !== undefined) return unit;
  if (key.endsWith("_mps")) return "m/s";
  if (key.endsWith("_m")) return "m";
  if (key.endsWith("_s")) return "s";
  return "";
}

function labelOf(key: string): string {
  return LABEL[key] ?? key.replace(/_(mps|m|s)$/, "").replace(/_/g, " ");
}

/** One value as text: yes or no, a number with its unit, none for a null, a dash for a missing field. */
function cell(key: string, v: unknown): Cell {
  if (v === undefined) return BLANK;
  if (v === null) return { text: "none", tone: "none" };
  if (typeof v === "boolean") return v ? { text: "yes", tone: "yes" } : { text: "no", tone: "value" };
  const n = asNumber(v);
  if (n !== null) {
    const unit = unitOf(key);
    return { text: unit === "" ? String(n) : `${n.toFixed(1)} ${unit}`, tone: "value" };
  }
  return { text: typeof v === "string" ? v : JSON.stringify(v), tone: "value" };
}

/**
 * A lane metric. A null gap means no vehicle within 200 m; a null that only follows from that
 * (its speed, headway) is a dash; a null time to collision with a vehicle ahead means not closing.
 */
function laneCell(key: string, block: Block): Cell {
  const v = block[key];
  if (v === null) {
    if (key === "time_to_collision_ahead_s") {
      return asNumber(block.vehicle_ahead_gap_m) !== null ? { text: "not closing", tone: "none" } : BLANK;
    }
    if (key !== "vehicle_ahead_gap_m" && key !== "vehicle_behind_gap_m") return BLANK;
  }
  return cell(key, v);
}

function edgeCell(block: Block): Cell {
  const left = block.is_leftmost;
  const right = block.is_rightmost;
  if (typeof left !== "boolean" && typeof right !== "boolean") return BLANK;
  if (left && right) return { text: "only lane", tone: "value" };
  if (left) return { text: "leftmost", tone: "value" };
  if (right) return { text: "rightmost", tone: "value" };
  return { text: "no", tone: "value" };
}

/** Lane and lane count fold into one "3 of 4" row. */
function egoBlock(ego: Block): Block {
  const { lane, lane_count: count, ...rest } = ego;
  return { lane: count === undefined ? lane : `${String(lane)} of ${String(count)}`, ...rest };
}

/** A label and its value. The label may wrap inside its cell; the value never does. */
function Pair({ label, value, valueClass, title }: { label: ReactNode; value: string; valueClass: string; title: string }) {
  return (
    <div className="flex min-w-0 flex-wrap items-baseline gap-x-1.5" title={title}>
      <span className="text-zinc-400">{label}</span>
      <span className={`num whitespace-nowrap ${valueClass}`}>{value}</span>
    </div>
  );
}

function pairs(block: Block, skip: string[] = []): ReactNode[] {
  return Object.keys(block)
    .filter((k) => !skip.includes(k))
    .map((k) => {
      const c = cell(k, block[k]);
      return <Pair key={k} label={labelOf(k)} value={c.text} valueClass={TONE[c.tone]} title={k} />;
    });
}

/** A labelled row of pairs: the title in a fixed column so the groups line up, the pairs in three columns, two when the pane is narrow. */
function Group({ title, note, children }: { title: ReactNode; note?: ReactNode; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[4.5rem_minmax(0,1fr)] gap-x-2">
      <div className="stat-label pt-px">{title}</div>
      <div className="flex min-w-0 flex-col gap-y-0.5">
        {note && <div>{note}</div>}
        <div className="grid grid-cols-3 gap-x-3 gap-y-0.5 max-[1440px]:grid-cols-2">{children}</div>
      </div>
    </div>
  );
}

interface LaneColumn {
  lane: number | null;
  when: string;
  block: Block;
}

interface LaneRow {
  key: string;
  label: string;
  cell: (block: Block) => Cell;
}

export function FactsTable({ facts }: { facts: Record<string, unknown> }) {
  const ego = asBlock(facts.ego);
  const action = asBlock(facts.action);
  const traffic: Block = { ...(asBlock(facts.traffic) ?? {}), ...(asBlock(facts.history) ?? {}) };
  const zones = Array.isArray(facts.zones) ? facts.zones.map(asBlock).filter((z): z is Block => z !== null) : [];
  const extras: [string, Block][] = [];
  for (const [k, v] of Object.entries(facts)) {
    const b = asBlock(v);
    if (b && !KNOWN_BLOCKS.has(k)) extras.push([k, b]);
  }

  const laneNow = ego ? asNumber(ego.lane) : null;
  const laneAfter = action ? asNumber(action.lane_after) : null;
  const columns: LaneColumn[] = [];
  const current = asBlock(facts.current_lane);
  const after = asBlock(facts.lane_after_action);
  const right = asBlock(facts.lane_right_of_lane_after);
  if (current) columns.push({ lane: laneNow, when: "now", block: current });
  if (after) columns.push({ lane: laneAfter, when: "after", block: after });
  if (right) columns.push({ lane: laneAfter === null ? null : laneAfter + 1, when: "to the right", block: right });
  const present = new Set(columns.flatMap((c) => Object.keys(c.block)));
  const laneRow = (k: string): LaneRow => ({ key: k, label: labelOf(k), cell: (b) => laneCell(k, b) });
  const rows: LaneRow[] = [
    ...LANE_ROWS.filter((k) => present.has(k)).map(laneRow),
    ...[...present].filter((k) => !LANE_ROWS.includes(k) && !EDGE_KEYS.includes(k)).map(laneRow),
  ];
  if (EDGE_KEYS.some((k) => present.has(k))) rows.push({ key: "edge", label: "road edge", cell: edgeCell });

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-auto text-xs leading-snug">
      <div className="flex flex-col gap-1">
        {ego && <Group title="ego">{pairs(egoBlock(ego))}</Group>}
        {action && (
          <Group
            title="action"
            note={
              <>
                <span className="font-mono text-zinc-100">{String(action.name ?? "")}</span>
                {typeof action.meaning === "string" && <span className="text-zinc-300">, {action.meaning}</span>}
              </>
            }
          >
            {pairs(action, ["name", "meaning"])}
          </Group>
        )}
        {Object.keys(traffic).length > 0 && <Group title="traffic">{pairs(traffic)}</Group>}
        <Group title="zones">
          {zones.length === 0 ? (
            <span className="text-zinc-400">none ahead</span>
          ) : (
            // A zone reads as one line: name, lane, extent, and whether this action enters it.
            zones.map((z, i) => {
              const enters = z.action_enters_zone === true;
              return (
                <div key={i} className="col-span-full flex flex-wrap items-baseline gap-x-1.5" title="name, lane, starts_in_m, ends_in_m, action_enters_zone">
                  <span className="text-zinc-100">{String(z.name ?? "zone")}</span>
                  <span className="text-zinc-400">· lane</span>
                  <span className="num text-zinc-100">{String(z.lane ?? "?")}</span>
                  <span className="text-zinc-400">·</span>
                  <span className="num whitespace-nowrap text-zinc-100">
                    {metres(z.starts_in_m)} to {metres(z.ends_in_m)} m
                  </span>
                  <span className="text-zinc-400">ahead · this action enters it</span>
                  <span className={`num ${enters ? "font-semibold text-hazard" : "text-zinc-100"}`}>{enters ? "yes" : "no"}</span>
                </div>
              );
            })
          )}
        </Group>
        {extras.map(([k, b]) => (
          <Group key={k} title={labelOf(k)}>
            {pairs(b)}
          </Group>
        ))}
      </div>
      {columns.length > 0 && (
        <table className="w-full border-separate border-spacing-y-0.5">
          <thead className="text-left">
            <tr>
              <th className="stat-label px-1 font-normal">lanes</th>
              {columns.map((c, i) => (
                <th key={i} className="px-1 font-normal whitespace-nowrap">
                  <span className="num text-zinc-200">lane {c.lane ?? "?"}</span>
                  <span className="text-zinc-400"> · {c.when}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.key}>
                <td className="px-1 whitespace-nowrap text-zinc-400" title={row.key}>
                  {row.label}
                </td>
                {columns.map((c, i) => {
                  const k = row.cell(c.block);
                  return (
                    <td key={i} className={`num px-1 whitespace-nowrap ${TONE[k.tone]}`}>
                      {k.text}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
