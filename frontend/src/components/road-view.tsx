import { useEffect, useRef } from "react";
import { DECISION_COLOR } from "../format";
import { selectLatestStep, selectPreviousStep, useStore } from "../store";
import type { ActionName, LogRecord, Zone } from "../types";

// Ego-centered view. The road runs left to right; lane 1 (leftmost) is at the top.
const VIEW_M = 240;
const EGO_OFFSET_M = 70;
const MIN_LANE_H = 44;
const MAX_LANE_H = 84;
const LANE_WIDTH_M = 4;
const CAR_L_M = 5;
const CAR_W_M = 2.2;

interface Frame {
  prev: LogRecord | null;
  cur: LogRecord | null;
  t0: number;
  intervalMs: number;
}

function arrowFor(action: ActionName, laneH: number): [number, number] {
  switch (action) {
    case "LANE_LEFT":
      return [0, -laneH * 0.85];
    case "LANE_RIGHT":
      return [0, laneH * 0.85];
    case "FASTER":
      return [46, 0];
    case "SLOWER":
      return [-34, 0];
    case "IDLE":
      return [16, 0];
  }
}

let hatch: CanvasPattern | null = null;

function hatchPattern(ctx: CanvasRenderingContext2D): CanvasPattern | null {
  if (hatch) return hatch;
  const tile = document.createElement("canvas");
  tile.width = tile.height = 12;
  const t = tile.getContext("2d");
  if (!t) return null;
  t.fillStyle = "rgba(251,191,36,0.12)";
  t.fillRect(0, 0, 12, 12);
  t.strokeStyle = "rgba(251,191,36,0.7)";
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

const lerp = (a: number, b: number, t: number): number => a + (b - a) * t;

function drawArrow(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  dx: number,
  dy: number,
  color: string,
  ghost: boolean,
): void {
  const len = Math.hypot(dx, dy);
  if (len < 1) return;
  ctx.save();
  ctx.globalAlpha = ghost ? 0.45 : 1;
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  ctx.lineWidth = ghost ? 2 : 3;
  ctx.setLineDash(ghost ? [5, 4] : []);
  ctx.beginPath();
  ctx.moveTo(x, y);
  ctx.lineTo(x + dx, y + dy);
  ctx.stroke();
  const ux = dx / len;
  const uy = dy / len;
  const hx = x + dx;
  const hy = y + dy;
  ctx.setLineDash([]);
  ctx.beginPath();
  ctx.moveTo(hx, hy);
  ctx.lineTo(hx - ux * 9 - uy * 5, hy - uy * 9 + ux * 5);
  ctx.lineTo(hx - ux * 9 + uy * 5, hy - uy * 9 - ux * 5);
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

function drawCar(
  ctx: CanvasRenderingContext2D,
  cx: number,
  cy: number,
  pxPerM: number,
  laneH: number,
  color: string,
  ego: boolean,
): void {
  const w = CAR_L_M * pxPerM;
  const h = (CAR_W_M / LANE_WIDTH_M) * laneH;
  ctx.save();
  ctx.fillStyle = color;
  ctx.shadowColor = ego ? color : "transparent";
  ctx.shadowBlur = ego ? 14 : 0;
  ctx.beginPath();
  ctx.roundRect(cx - w / 2, cy - h / 2, w, h, 3);
  ctx.fill();
  ctx.shadowBlur = 0;
  ctx.fillStyle = ego ? "#0e7490" : "#1e293b";
  ctx.fillRect(cx + w * 0.15, cy - h / 2 + 3, w * 0.2, h - 6);
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

  const pxPerM = W / VIEW_M;
  const LANE_H = Math.max(MIN_LANE_H, Math.min(MAX_LANE_H, (H - 48) / laneCount));
  const roadH = laneCount * LANE_H;
  const roadTop = Math.max(16, (H - roadH) / 2);
  const laneToY = (lane: number): number => roadTop + (lane - 0.5) * LANE_H;

  ctx.fillStyle = "#1c1c20";
  ctx.fillRect(0, roadTop, W, roadH);
  for (let i = 0; i <= laneCount; i++) {
    const y = roadTop + i * LANE_H;
    const edge = i === 0 || i === laneCount;
    ctx.strokeStyle = edge ? "#71717a" : "#3f3f46";
    ctx.lineWidth = edge ? 2 : 1;
    ctx.setLineDash(edge ? [] : [14, 12]);
    ctx.beginPath();
    ctx.moveTo(0, y + 0.5);
    ctx.lineTo(W, y + 0.5);
    ctx.stroke();
  }
  ctx.setLineDash([]);
  ctx.textBaseline = "middle";
  const drawLaneLabels = (): void => {
    ctx.font = "10px ui-monospace, monospace";
    for (let lane = 1; lane <= laneCount; lane++) {
      ctx.fillStyle = "rgba(24,24,27,0.85)";
      ctx.fillRect(2, laneToY(lane) - 7, 42, 14);
      ctx.fillStyle = "#71717a";
      ctx.fillText(`lane ${lane}`, 6, laneToY(lane));
    }
  };

  const cur = f.cur;
  if (!cur) {
    ctx.fillStyle = "#71717a";
    ctx.font = "12px ui-monospace, monospace";
    ctx.textAlign = "center";
    ctx.fillText("waiting for the first step", W / 2, roadTop + roadH + 24);
    ctx.textAlign = "left";
    drawLaneLabels();
    return;
  }
  const prev = f.prev ?? cur;
  const alpha = Math.min(1, Math.max(0, (performance.now() - f.t0) / f.intervalMs));
  const egoX = lerp(prev.ego.x_m, cur.ego.x_m, alpha);
  const egoLane = lerp(prev.ego.lane, cur.ego.lane, alpha);
  const xToPx = (xm: number): number => (xm - egoX + EGO_OFFSET_M) * pxPerM;

  const pattern = hatchPattern(ctx);
  for (const z of zones) {
    const x0 = Math.max(0, xToPx(z.start_m));
    const x1 = Math.min(W, xToPx(z.end_m));
    if (x1 <= 0 || x0 >= W) continue;
    const y = roadTop + (z.lane - 1) * LANE_H;
    ctx.fillStyle = pattern ?? "rgba(251,191,36,0.25)";
    ctx.fillRect(x0, y + 1, x1 - x0, LANE_H - 2);
    ctx.strokeStyle = "rgba(251,191,36,0.9)";
    ctx.lineWidth = 1.5;
    ctx.strokeRect(x0 + 0.5, y + 1.5, x1 - x0 - 1, LANE_H - 3);
    ctx.fillStyle = "#fbbf24";
    ctx.font = "bold 10px ui-monospace, monospace";
    ctx.fillText(`${z.name.toUpperCase()}  lane ${z.lane} closed`, x0 + 6, y + 10);
  }

  const prevById = new Map(prev.vehicles.map((v) => [v.id, v]));
  for (const v of cur.vehicles) {
    const pv = prevById.get(v.id) ?? v;
    const x = xToPx(lerp(pv.x_m, v.x_m, alpha));
    if (x < -30 || x > W + 30) continue;
    drawCar(ctx, x, laneToY(lerp(pv.lane, v.lane, alpha)), pxPerM, LANE_H, "#94a3b8", false);
  }

  const ex = xToPx(egoX);
  const ey = laneToY(egoLane);
  drawCar(ctx, ex, ey, pxPerM, LANE_H, "#22d3ee", true);

  const top = cur.candidates[0]?.action;
  const blocked = top !== undefined && top !== cur.executed;
  if (blocked) {
    const [dx, dy] = arrowFor(top, LANE_H);
    drawArrow(ctx, ex, ey, dx, dy, "#fb7185", true);
  }
  const [dx, dy] = arrowFor(cur.executed, LANE_H);
  drawArrow(ctx, ex + (cur.executed === "FASTER" ? 14 : 0), ey, dx, dy, DECISION_COLOR[cur.decision], false);

  ctx.fillStyle = "#e4e4e7";
  ctx.font = "11px ui-monospace, monospace";
  ctx.fillText(`${cur.ego.speed_mps.toFixed(1)} m/s`, ex - 18, ey + LANE_H * 0.62);
  ctx.fillStyle = "#a1a1aa";
  ctx.fillText(
    `step ${cur.step}   lane ${cur.ego.lane}   x ${Math.round(cur.ego.x_m)} m   ${cur.decision}${blocked ? ` (blocked ${top})` : ""} -> ${cur.executed}`,
    6,
    roadTop - 12,
  );
  drawLaneLabels();
  if (cur.crashed) {
    ctx.fillStyle = "rgba(244,63,94,0.85)";
    ctx.font = "bold 14px ui-monospace, monospace";
    ctx.fillText("CRASH", ex - 22, ey - LANE_H * 0.7);
  }
}

export function RoadView() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const frame = useRef<Frame>({ prev: null, cur: null, t0: 0, intervalMs: 500 });
  const latest = useStore(selectLatestStep);
  const previous = useStore(selectPreviousStep);
  const zones = useStore((s) => s.zones);
  const speed = useStore((s) => s.session?.speed ?? 2);
  const laneCount = useStore((s) => s.hello?.config.lanes_count ?? 4);

  useEffect(() => {
    frame.current = { prev: previous, cur: latest, t0: performance.now(), intervalMs: 1000 / speed };
  }, [latest, previous, speed]);

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

  return (
    <section className="panel flex min-h-[280px] flex-1 flex-col">
      <div className="panel-title">
        <span>Road view</span>
        <span className="font-normal tracking-normal text-zinc-500 normal-case">
          ego-centered · solid arrow executed · dashed arrow blocked
        </span>
      </div>
      <canvas ref={canvasRef} className="block h-full w-full flex-1" />
    </section>
  );
}
