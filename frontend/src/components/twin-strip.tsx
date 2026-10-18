import { useEffect, useRef } from "react";
import { selectViewStep, useStore } from "../store";
import type { TwinStep } from "../types";
import { arrowFor, drawArrow, drawCar, EGO_OFFSET_M, lerp, VIEW_M } from "./road-view";

// The unshielded twin: the shield-off run of the same seed, drawn faded under the
// road view at the same step index as the live run, so playback and scrubbing
// share one clock. Hidden when the server found no shield-off log for the seed.

interface TwinFrame {
  prev: TwinStep | null;
  cur: TwinStep | null;
  t0: number;
  intervalMs: number;
}

const CAR = "#6b7280";
const EGO = "#67e8f9";
const ARROW = "#a1a1aa";

function renderTwin(canvas: HTMLCanvasElement, f: TwinFrame, laneCount: number, ended: boolean): void {
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
  const laneH = Math.max(14, Math.min(26, (H - 8) / laneCount));
  const roadTop = Math.max(4, (H - laneCount * laneH) / 2);
  const laneToY = (lane: number): number => roadTop + (lane - 0.5) * laneH;

  ctx.globalAlpha = 0.6;
  ctx.fillStyle = "#1c1c20";
  ctx.fillRect(0, roadTop, W, laneCount * laneH);
  for (let i = 0; i <= laneCount; i++) {
    const y = roadTop + i * laneH;
    const edge = i === 0 || i === laneCount;
    ctx.strokeStyle = edge ? "#71717a" : "#3f3f46";
    ctx.lineWidth = 1;
    ctx.setLineDash(edge ? [] : [10, 8]);
    ctx.beginPath();
    ctx.moveTo(0, y + 0.5);
    ctx.lineTo(W, y + 0.5);
    ctx.stroke();
  }
  ctx.setLineDash([]);
  const cur = f.cur;
  if (!cur) {
    ctx.globalAlpha = 1;
    return;
  }
  const prev = f.prev ?? cur;
  const alpha = Math.min(1, Math.max(0, (performance.now() - f.t0) / f.intervalMs));
  const egoX = lerp(prev.ego.x_m, cur.ego.x_m, alpha);
  const egoLane = lerp(prev.ego.lane, cur.ego.lane, alpha);
  const xToPx = (xm: number): number => (xm - egoX + EGO_OFFSET_M) * pxPerM;
  const prevById = new Map(prev.vehicles.map((v) => [v.id, v]));
  for (const v of cur.vehicles) {
    const pv = prevById.get(v.id) ?? v;
    const x = xToPx(lerp(pv.x_m, v.x_m, alpha));
    if (x < -30 || x > W + 30) continue;
    drawCar(ctx, x, laneToY(lerp(pv.lane, v.lane, alpha)), pxPerM, laneH, CAR, false);
  }
  const ex = xToPx(egoX);
  const ey = laneToY(egoLane);
  drawCar(ctx, ex, ey, pxPerM, laneH, EGO, true);
  const [dx, dy] = arrowFor(cur.executed, laneH);
  drawArrow(ctx, ex + (cur.executed === "FASTER" ? 10 : 0), ey, dx * 0.7, dy * 0.7, ARROW, false);
  ctx.globalAlpha = 1;
  if (cur.crashed || ended) {
    ctx.fillStyle = "rgba(244,63,94,0.9)";
    ctx.font = "bold 12px ui-monospace, monospace";
    ctx.fillText("CRASHED", ex - 26, Math.max(10, ey - laneH * 0.9));
  }
}

export function TwinStrip() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const frame = useRef<TwinFrame>({ prev: null, cur: null, t0: 0, intervalMs: 500 });
  const twin = useStore((s) => s.twin);
  const live = useStore(selectViewStep);
  const inspecting = useStore((s) => s.selectedStep);
  const speed = useStore((s) => s.session?.speed ?? 2);
  const seed = useStore((s) => s.session?.seed ?? null);
  const laneCount = useStore((s) => s.hello?.config.lanes_count ?? 4);

  const steps = twin && twin.seed === seed ? twin.steps : [];
  const last = steps.length - 1;
  const index = live === null ? -1 : Math.min(live.step, last);
  const cur = index >= 0 ? (steps[index] ?? null) : null;
  const prev = index > 0 ? (steps[index - 1] ?? cur) : cur;
  const ended = live !== null && live.step > last && last >= 0;

  useEffect(() => {
    const t0 = inspecting === null ? performance.now() : 0;
    frame.current = { prev, cur, t0, intervalMs: 1000 / speed };
  }, [cur, prev, speed, inspecting]);

  useEffect(() => {
    let raf = 0;
    const tick = (): void => {
      const canvas = canvasRef.current;
      if (canvas) renderTwin(canvas, frame.current, laneCount, ended);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [laneCount, ended]);

  if (steps.length === 0 || !twin) return null;
  const shown = cur?.violations_so_far ?? 0;
  const where = cur ? `step ${cur.step}` : "waiting";
  return (
    <section className="panel flex h-[132px] shrink-0 flex-col">
      <div className="panel-title">
        <span>
          Unshielded twin
          <span className="font-normal tracking-normal text-zinc-500 normal-case"> · same seed, shield off, {twin.rules} rules scored</span>
        </span>
        <span className="font-normal tracking-normal text-zinc-500 normal-case tabular-nums">
          {where} · violations so far <span className="text-orange-300">{shown}</span> of {twin.violations_total}
          {twin.crashed_at !== null && (
            <>
              {" "}· <span className="text-rose-300">crashed at step {twin.crashed_at}</span>
            </>
          )}
        </span>
      </div>
      <canvas ref={canvasRef} className="block h-full w-full flex-1" />
    </section>
  );
}
