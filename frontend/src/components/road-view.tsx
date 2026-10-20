import { useEffect, useRef } from "react";
import { ACCENT_COLOR, DECISION_CLASS, DECISION_COLOR, DECISION_LABEL, HAZARD_COLOR, fmtSpeed, isLaneNoop, uiScale } from "../format";
import { selectViewPrevStep, selectViewStep, useStore } from "../store";
import type { ActionName, LogRecord, Zone } from "../types";

// Ego-centered view. The road runs left to right; lane 1 (leftmost) is at the top.
export const VIEW_M = 160;
export const EGO_OFFSET_M = 50;
export const GUTTER_PX = 44; // lane labels live here, outside the road surface
const HUD_PX = 40; // the DOM overlay sits in this band
const MIN_LANE_H = 40;
const MAX_LANE_H = 120;
export const LANE_WIDTH_M = 4;
export const CAR_L_M = 5;
export const CAR_W_M = 2.2;

export const SANS = 'Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
export const MONO = '"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';
const TRAFFIC = "#94a3b8";
const ROAD = "#1a1a1e";
const SHOULDER = "#121215";
const EDGE = "#8b8b94";
const LANE_LINE = "#4a4a52";

interface Frame {
  prev: LogRecord | null;
  cur: LogRecord | null;
  t0: number;
  intervalMs: number;
}

/** Arrow vector in px: lane changes span most of a lane, speed changes are fixed lengths scaled by `s`. */
export function arrowFor(action: ActionName, laneH: number, s = 1): [number, number] {
  switch (action) {
    case "LANE_LEFT":
      return [0, -laneH * 0.9];
    case "LANE_RIGHT":
      return [0, laneH * 0.9];
    case "FASTER":
      return [64 * s, 0];
    case "SLOWER":
      return [-48 * s, 0];
    case "IDLE":
      return [0, 0];
  }
}

let hatch: CanvasPattern | null = null;

function hatchPattern(ctx: CanvasRenderingContext2D): CanvasPattern | null {
  if (hatch) return hatch;
  const tile = document.createElement("canvas");
  tile.width = tile.height = 12;
  const t = tile.getContext("2d");
  if (!t) return null;
  t.fillStyle = "rgba(251,146,60,0.10)";
  t.fillRect(0, 0, 12, 12);
  t.strokeStyle = "rgba(251,146,60,0.65)";
  t.lineWidth = 2;
  t.beginPath();
  t.moveTo(-3, 15);
  t.lineTo(15, -3);
  t.moveTo(-3, 3);
  t.lineTo(3, -3);
  t.moveTo(9, 15);
  t.lineTo(15, 9);
  t.stroke();
  hatch = ctx.createPattern(tile, "repeat");
  return hatch;
}

export const lerp = (a: number, b: number, t: number): number => a + (b - a) * t;

/** Two short bars: the action changes nothing (IDLE, or a lane change at the road edge). */
export function drawHold(ctx: CanvasRenderingContext2D, x: number, y: number, color: string, ghost: boolean, s: number): void {
  ctx.save();
  ctx.globalAlpha = ghost ? 0.55 : 1;
  ctx.strokeStyle = color;
  ctx.lineWidth = 2.5 * s;
  ctx.lineCap = "round";
  ctx.setLineDash(ghost ? [2 * s, 2 * s] : []);
  ctx.beginPath();
  ctx.moveTo(x - 3 * s, y - 5 * s);
  ctx.lineTo(x - 3 * s, y + 5 * s);
  ctx.moveTo(x + 3 * s, y - 5 * s);
  ctx.lineTo(x + 3 * s, y + 5 * s);
  ctx.stroke();
  ctx.restore();
}

export function drawArrow(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  dx: number,
  dy: number,
  color: string,
  ghost: boolean,
  s = 1,
): void {
  const len = Math.hypot(dx, dy);
  if (len < 1) {
    drawHold(ctx, x, y, color, ghost, s);
    return;
  }
  const ux = dx / len;
  const uy = dy / len;
  const hx = x + dx;
  const hy = y + dy;
  const head = 9 * s;
  const half = 5 * s;
  ctx.save();
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  if (!ghost) {
    // A dark halo keeps the arrow legible over cars and hatching.
    ctx.strokeStyle = "rgba(0,0,0,0.6)";
    ctx.lineWidth = 7 * s;
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(hx - ux * head * 0.5, hy - uy * head * 0.5);
    ctx.stroke();
  }
  ctx.globalAlpha = ghost ? 0.7 : 1;
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  ctx.lineWidth = (ghost ? 2.5 : 3.5) * s;
  ctx.setLineDash(ghost ? [5 * s, 4 * s] : []);
  ctx.beginPath();
  ctx.moveTo(x, y);
  ctx.lineTo(hx - ux * head * 0.6, hy - uy * head * 0.6);
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.beginPath();
  ctx.moveTo(hx, hy);
  ctx.lineTo(hx - ux * head - uy * half, hy - uy * head + ux * half);
  ctx.lineTo(hx - ux * head + uy * half, hy - uy * head - ux * half);
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

/** Car box in px: true length along x, height capped so the car reads as a car, not a tile. */
export function carSize(pxPerM: number, laneH: number): [number, number] {
  const len = Math.max(18, CAR_L_M * pxPerM);
  const h = Math.min(laneH * 0.55, len / 1.6);
  return [len, h];
}

export function drawCar(
  ctx: CanvasRenderingContext2D,
  cx: number,
  cy: number,
  pxPerM: number,
  laneH: number,
  color: string,
  ego: boolean,
): void {
  const [len, h] = carSize(pxPerM, laneH);
  const k = ego ? 1.12 : 1;
  const w = len * k;
  const hh = h * k;
  const x0 = cx - w / 2;
  const y0 = cy - hh / 2;
  ctx.save();
  ctx.shadowColor = ego ? color : "rgba(0,0,0,0.6)";
  ctx.shadowBlur = ego ? 18 : 5;
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.roundRect(x0, y0, w, hh, hh * 0.3);
  ctx.fill();
  ctx.shadowBlur = 0;
  // Cabin: a darker band behind the midpoint. The front is the right end.
  ctx.fillStyle = ego ? "rgba(8,47,73,0.85)" : "rgba(15,23,42,0.75)";
  ctx.beginPath();
  ctx.roundRect(cx - w * 0.22, y0 + hh * 0.14, w * 0.4, hh * 0.72, hh * 0.18);
  ctx.fill();
  // Headlights front, taillights rear: the direction of travel at a glance.
  const lightH = Math.max(2, hh * 0.22);
  const lightW = Math.max(1.5, w * 0.06);
  ctx.fillStyle = "#fef3c7";
  ctx.fillRect(x0 + w - lightW - 0.5, y0 + hh * 0.12, lightW, lightH);
  ctx.fillRect(x0 + w - lightW - 0.5, y0 + hh * 0.88 - lightH, lightW, lightH);
  ctx.fillStyle = "#f43f5e";
  ctx.fillRect(x0 + 0.5, y0 + hh * 0.12, lightW, lightH);
  ctx.fillRect(x0 + 0.5, y0 + hh * 0.88 - lightH, lightW, lightH);
  if (ego) {
    ctx.strokeStyle = "rgba(255,255,255,0.9)";
    ctx.lineWidth = 1.25;
    ctx.beginPath();
    ctx.roundRect(x0, y0, w, hh, hh * 0.3);
    ctx.stroke();
  }
  ctx.restore();
}

function render(canvas: HTMLCanvasElement, f: Frame, zones: Zone[], laneCount: number): void {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  const W = Math.max(1, Math.floor(rect.width));
  const H = Math.max(1, Math.floor(rect.height));
  if (canvas.width !== W * dpr || canvas.height !== H * dpr) {
    canvas.width = W * dpr;
    canvas.height = H * dpr;
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, H);

  const s = uiScale();
  const gutter = GUTTER_PX * s;
  const hudH = HUD_PX * s;
  const pxPerM = (W - gutter) / VIEW_M;
  const LANE_H = Math.max(MIN_LANE_H * s, Math.min(MAX_LANE_H * s, (H - hudH - 10 * s) / laneCount));
  const roadH = laneCount * LANE_H;
  const roadTop = hudH + Math.max(0, (H - hudH - roadH) / 2);
  const laneToY = (lane: number): number => roadTop + (lane - 0.5) * LANE_H;

  const cur = f.cur;
  const prev = f.prev ?? cur;
  const alpha = cur ? Math.min(1, Math.max(0, (performance.now() - f.t0) / f.intervalMs)) : 0;
  const egoX = cur && prev ? lerp(prev.ego.x_m, cur.ego.x_m, alpha) : 0;
  const egoLane = cur && prev ? lerp(prev.ego.lane, cur.ego.lane, alpha) : 1;
  const xToPx = (xm: number): number => gutter + (xm - egoX + EGO_OFFSET_M) * pxPerM;

  // Shoulders, then the surface, then world-fixed lane dashes that scroll with the ego.
  ctx.fillStyle = SHOULDER;
  ctx.fillRect(gutter, roadTop - 8 * s, W - gutter, roadH + 16 * s);
  ctx.fillStyle = ROAD;
  ctx.fillRect(gutter, roadTop, W - gutter, roadH);
  const period = 26 * s;
  for (let i = 0; i <= laneCount; i++) {
    const y = roadTop + i * LANE_H;
    const edge = i === 0 || i === laneCount;
    ctx.strokeStyle = edge ? EDGE : LANE_LINE;
    ctx.lineWidth = edge ? 2 : 1.25;
    ctx.setLineDash(edge ? [] : [14 * s, 12 * s]);
    ctx.lineDashOffset = edge ? 0 : ((egoX - EGO_OFFSET_M) * pxPerM) % period;
    ctx.beginPath();
    ctx.moveTo(gutter, y + 0.5);
    ctx.lineTo(W, y + 0.5);
    ctx.stroke();
  }
  ctx.setLineDash([]);
  ctx.lineDashOffset = 0;

  ctx.textBaseline = "middle";
  ctx.textAlign = "right";
  ctx.font = `${11 * s}px ${SANS}`;
  ctx.fillStyle = "#a1a1aa";
  for (let lane = 1; lane <= laneCount; lane++) ctx.fillText(`lane ${lane}`, gutter - 8 * s, laneToY(lane));
  ctx.textAlign = "left";

  if (!cur) {
    const msg = "waiting for the first step";
    ctx.font = `${13 * s}px ${SANS}`;
    const tw = ctx.measureText(msg).width;
    const mx = gutter + (W - gutter) / 2;
    const my = roadTop + roadH / 2;
    ctx.fillStyle = "rgba(9,9,11,0.85)";
    ctx.beginPath();
    ctx.roundRect(mx - tw / 2 - 12 * s, my - 12 * s, tw + 24 * s, 24 * s, 6 * s);
    ctx.fill();
    ctx.fillStyle = "#a1a1aa";
    ctx.textAlign = "center";
    ctx.fillText(msg, mx, my);
    ctx.textAlign = "left";
    return;
  }

  // Everything on the road is clipped to the road, so nothing bleeds into the gutter.
  ctx.save();
  ctx.beginPath();
  ctx.rect(gutter, 0, W - gutter, H);
  ctx.clip();

  const pattern = hatchPattern(ctx);
  for (const z of zones) {
    const x0 = Math.max(gutter, xToPx(z.start_m));
    const x1 = Math.min(W, xToPx(z.end_m));
    if (x1 <= gutter || x0 >= W) continue;
    const y = roadTop + (z.lane - 1) * LANE_H;
    ctx.fillStyle = pattern ?? "rgba(251,146,60,0.25)";
    ctx.fillRect(x0, y + 1, x1 - x0, LANE_H - 2);
    ctx.strokeStyle = "rgba(251,146,60,0.9)";
    ctx.lineWidth = 1.5;
    ctx.strokeRect(x0 + 0.5, y + 1.5, x1 - x0 - 1, LANE_H - 3);
    if (x1 - x0 > 40 * s) {
      const label = `${z.name.toUpperCase()} · lane ${z.lane} closed`;
      ctx.font = `600 ${10.5 * s}px ${SANS}`;
      const tw = ctx.measureText(label).width;
      let lx = x0 + 8 * s;
      if (lx + tw > x1 - 8 * s) lx = Math.max(gutter + 8 * s, x1 - 8 * s - tw);
      const ly = y + 10 * s;
      ctx.fillStyle = "rgba(9,9,11,0.8)";
      ctx.beginPath();
      ctx.roundRect(lx - 4 * s, ly - 7 * s, tw + 8 * s, 14 * s, 3);
      ctx.fill();
      ctx.fillStyle = HAZARD_COLOR;
      ctx.fillText(label, lx, ly);
    }
  }

  const prevById = new Map((prev ?? cur).vehicles.map((v) => [v.id, v]));
  for (const v of cur.vehicles) {
    const pv = prevById.get(v.id) ?? v;
    const x = xToPx(lerp(pv.x_m, v.x_m, alpha));
    if (x < gutter - 40 || x > W + 40) continue;
    drawCar(ctx, x, laneToY(lerp(pv.lane, v.lane, alpha)), pxPerM, LANE_H, TRAFFIC, false);
  }

  const ex = xToPx(egoX);
  const ey = laneToY(egoLane);
  drawCar(ctx, ex, ey, pxPerM, LANE_H, ACCENT_COLOR, true);
  const [carW, carH] = carSize(pxPerM, LANE_H).map((v) => v * 1.12) as [number, number];

  const origin = (action: ActionName): [number, number] => {
    switch (action) {
      case "FASTER":
        return [ex + carW / 2 + 2, ey];
      case "SLOWER":
        return [ex - carW / 2 - 2, ey];
      case "LANE_LEFT":
        return [ex, ey - carH / 2 - 2];
      case "LANE_RIGHT":
        return [ex, ey + carH / 2 + 2];
      case "IDLE":
        return [ex, ey];
    }
  };
  const vector = (action: ActionName): [number, number] =>
    isLaneNoop(action, cur.ego.lane, laneCount) ? [0, 0] : arrowFor(action, LANE_H, s);

  const top = cur.candidates[0]?.action;
  const blocked = top !== undefined && top !== cur.executed;
  const floored = top !== undefined && (cur.floor?.removed ?? []).includes(top);
  const color = DECISION_COLOR[cur.decision];
  const ghostColor = floored ? DECISION_COLOR.fallback : DECISION_COLOR.all_blocked;
  let ghostDy = 0;
  if (blocked) {
    const [gdx, gdy] = vector(top);
    ghostDy = gdy;
    if (gdx === 0 && gdy === 0) drawHold(ctx, ex, ey + carH / 2 + 9 * s, ghostColor, true, s);
    else {
      const [ox, oy] = origin(top);
      drawArrow(ctx, ox, oy, gdx, gdy, ghostColor, true, s);
    }
  }
  const [dx, dy] = vector(cur.executed);
  if (dx === 0 && dy === 0) {
    drawHold(ctx, ex, ghostDy > 0 ? ey - carH / 2 - 9 * s : ey + carH / 2 + 9 * s, color, false, s);
  } else {
    const [ox, oy] = origin(cur.executed);
    drawArrow(ctx, ox, oy, dx, dy, color, false, s);
  }

  // The decision chip: what the policy wanted, what ran. Above and to the right of the car.
  const chip = blocked ? `${top} ✕ → ${cur.executed}` : `${cur.executed} ✓`;
  ctx.font = `600 ${11 * s}px ${MONO}`;
  const tw = ctx.measureText(chip).width;
  const chipH = 18 * s;
  let cx0 = ex + carW / 2 + 10 * s;
  if (cx0 + tw + 14 * s > W - 4) cx0 = Math.max(gutter + 4, W - 4 - tw - 14 * s);
  const cy0 = Math.max(roadTop + 2, ey - carH / 2 - chipH - 4 * s);
  ctx.fillStyle = "rgba(9,9,11,0.88)";
  ctx.strokeStyle = color;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.roundRect(cx0, cy0, tw + 14 * s, chipH, 4 * s);
  ctx.fill();
  ctx.stroke();
  ctx.fillStyle = color;
  ctx.fillText(chip, cx0 + 7 * s, cy0 + chipH / 2);

  if (cur.crashed) {
    ctx.font = `700 ${14 * s}px ${SANS}`;
    ctx.fillStyle = DECISION_COLOR.all_blocked;
    ctx.fillText("CRASH", Math.max(gutter + 6, ex - carW / 2 - 64 * s), ey - carH / 2 - 10 * s);
  }
  ctx.restore();
}

function ArrowGlyph({ dashed, className }: { dashed: boolean; className?: string }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 22 8" className={`h-2 w-5 ${className ?? (dashed ? "text-blocked" : "text-zinc-100")}`}>
      <path d="M1 4h15" stroke="currentColor" strokeWidth="2" strokeDasharray={dashed ? "3 2" : undefined} strokeLinecap="round" />
      <path d="M15 1l5 3-5 3z" fill="currentColor" />
    </svg>
  );
}

function Cell({ label, value }: { label: string; value: string }) {
  return (
    <span className="flex items-baseline gap-1">
      <span className="stat-label">{label}</span>
      <span className="num text-xs text-zinc-50">{value}</span>
    </span>
  );
}

export function RoadView() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const frame = useRef<Frame>({ prev: null, cur: null, t0: 0, intervalMs: 500 });
  const latest = useStore(selectViewStep);
  const previous = useStore(selectViewPrevStep);
  const inspecting = useStore((s) => s.selectedStep);
  const liveZones = useStore((s) => s.zones);
  const zones = inspecting === null ? liveZones : (latest?.zones ?? liveZones);
  const speed = useStore((s) => s.session?.speed ?? 2);
  const laneCount = useStore((s) => s.hello?.config.lanes_count ?? 4);

  useEffect(() => {
    // While inspecting, jump straight to the frame instead of animating into it.
    const t0 = inspecting === null ? performance.now() : 0;
    frame.current = { prev: previous, cur: latest, t0, intervalMs: 1000 / speed };
  }, [latest, previous, speed, inspecting]);

  useEffect(() => {
    let raf = 0;
    const tick = (): void => {
      const canvas = canvasRef.current;
      if (canvas) render(canvas, frame.current, zones, laneCount);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [zones, laneCount]);

  const top = latest?.candidates[0]?.action;
  const blocked = latest !== null && top !== undefined && top !== latest.executed;
  const floored = latest !== null && top !== undefined && (latest.floor?.removed ?? []).includes(top);

  return (
    <section className="relative flex min-h-[15rem] flex-1 flex-col overflow-hidden rounded-md bg-[#0c0c0e]">
      <canvas ref={canvasRef} className="block min-h-0 w-full flex-1" />
      <div className="pointer-events-none absolute inset-x-0 top-0 flex items-start gap-3 px-3 pt-2">
        <div className="flex min-w-0 items-center gap-3">
          <span className="text-2xs font-semibold tracking-[0.08em] whitespace-nowrap text-zinc-300 uppercase">Road view</span>
          {latest && (
            <div className="enter flex min-w-0 items-center gap-3 overflow-hidden rounded-md border border-zinc-800/80 bg-zinc-950/75 px-2.5 py-1 whitespace-nowrap backdrop-blur">
              <Cell label="step" value={String(latest.step)} />
              <Cell label="lane" value={String(latest.ego.lane)} />
              <Cell label="speed" value={fmtSpeed(latest.ego.speed_mps)} />
              <span className={`badge ${DECISION_CLASS[latest.decision]}`}>
                {DECISION_LABEL[latest.decision]}
                {blocked && (
                  <span className="font-mono normal-case">
                    · {top} {floored ? "under the floor" : "blocked"}
                  </span>
                )}
              </span>
              {latest.human && (
                <span className="badge border-escalate/40 text-escalate">
                  operator {latest.human.decision}
                  {latest.human.action && <span className="font-mono"> {latest.human.action}</span>}
                </span>
              )}
            </div>
          )}
        </div>
      </div>
      {/* The legend sits in the quiet band under the last lane; while inspecting the road is at its shortest, so it goes. */}
      {inspecting === null && (
      <div className="pointer-events-none absolute right-3 bottom-2">
        <div className="flex shrink-0 items-center gap-3 rounded-md border border-zinc-800/80 bg-zinc-950/75 px-2.5 py-1 text-2xs text-zinc-400 backdrop-blur">
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-3.5 rounded-sm bg-accent" />
            you
          </span>
          <span className="flex items-center gap-1.5">
            <ArrowGlyph dashed={false} />
            ran
          </span>
          <span className="flex items-center gap-1.5">
            <ArrowGlyph dashed />
            blocked
          </span>
          <span className="flex items-center gap-1.5">
            <ArrowGlyph dashed className="text-fallback" />
            floored
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-3.5 rounded-sm border border-hazard/80 bg-[repeating-linear-gradient(135deg,rgba(251,146,60,0.6)_0_2px,transparent_2px_5px)]" />
            closed lane
          </span>
        </div>
      </div>
      )}
    </section>
  );
}
