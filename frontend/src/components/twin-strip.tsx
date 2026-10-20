import { useEffect, useRef } from "react";
import { DECISION_COLOR, isLaneNoop, uiScale } from "../format";
import { selectViewStep, useStore } from "../store";
import type { LogRecord, TwinStep } from "../types";
import { arrowFor, carSize, drawArrow, drawCar, drawHold, EGO_OFFSET_M, GUTTER_PX, lerp, SANS, VIEW_M } from "./road-view";

// The unshielded twin: the shield-off run of the same seed, drawn faded under the
// road view at the same step index as the live run, so playback and scrubbing
// share one clock. Hidden when the server found no shield-off log for the seed.
// The server scores the twin against the rules the console has on, so its count
// and the live count shown beside it answer the same question.

/** Ground-truth violations of the executed action: how the live counter and the twin both count. */
function executedViolations(r: LogRecord): number {
  const executed = r.candidates.find((c) => c.action === r.executed);
  return executed ? executed.checks.filter((c) => c.ground_truth === true).length : 0;
}

interface TwinFrame {
  prev: TwinStep | null;
  cur: TwinStep | null;
  t0: number;
  intervalMs: number;
}

const CAR = "#6b7280";
const EGO = "#67e8f9";
const ARROW = "#d4d4d8";

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
  const s = uiScale();
  const gutter = GUTTER_PX * s;
  const pxPerM = (W - gutter) / VIEW_M;
  const laneH = Math.max(12, Math.min(24 * s, (H - 14 * s) / laneCount));
  const roadTop = Math.max(4, (H - laneCount * laneH) / 2);
  const laneToY = (lane: number): number => roadTop + (lane - 0.5) * laneH;
  const cur = f.cur;
  const prev = f.prev ?? cur;
  const alpha = cur ? Math.min(1, Math.max(0, (performance.now() - f.t0) / f.intervalMs)) : 0;
  const egoX = cur && prev ? lerp(prev.ego.x_m, cur.ego.x_m, alpha) : 0;
  const xToPx = (xm: number): number => gutter + (xm - egoX + EGO_OFFSET_M) * pxPerM;

  ctx.globalAlpha = 0.6;
  ctx.fillStyle = "#1a1a1e";
  ctx.fillRect(gutter, roadTop, W - gutter, laneCount * laneH);
  const period = 18 * s;
  for (let i = 0; i <= laneCount; i++) {
    const y = roadTop + i * laneH;
    const edge = i === 0 || i === laneCount;
    ctx.strokeStyle = edge ? "#8b8b94" : "#4a4a52";
    ctx.lineWidth = 1;
    ctx.setLineDash(edge ? [] : [10 * s, 8 * s]);
    ctx.lineDashOffset = edge ? 0 : ((egoX - EGO_OFFSET_M) * pxPerM) % period;
    ctx.beginPath();
    ctx.moveTo(gutter, y + 0.5);
    ctx.lineTo(W, y + 0.5);
    ctx.stroke();
  }
  ctx.setLineDash([]);
  ctx.lineDashOffset = 0;
  ctx.globalAlpha = 1;
  ctx.textBaseline = "middle";
  ctx.textAlign = "right";
  ctx.font = `${10 * s}px ${SANS}`;
  ctx.fillStyle = "#71717a";
  for (let lane = 1; lane <= laneCount; lane++) ctx.fillText(String(lane), gutter - 8 * s, laneToY(lane));
  ctx.textAlign = "left";
  if (!cur || !prev) return;

  ctx.save();
  ctx.beginPath();
  ctx.rect(gutter, 0, W - gutter, H);
  ctx.clip();
  ctx.globalAlpha = 0.65;
  const prevById = new Map(prev.vehicles.map((v) => [v.id, v]));
  for (const v of cur.vehicles) {
    const pv = prevById.get(v.id) ?? v;
    const x = xToPx(lerp(pv.x_m, v.x_m, alpha));
    if (x < gutter - 30 || x > W + 30) continue;
    drawCar(ctx, x, laneToY(lerp(pv.lane, v.lane, alpha)), pxPerM, laneH, CAR, false);
  }
  const ex = xToPx(egoX);
  const ey = laneToY(lerp(prev.ego.lane, cur.ego.lane, alpha));
  drawCar(ctx, ex, ey, pxPerM, laneH, EGO, true);
  const [carW, carH] = carSize(pxPerM, laneH).map((v) => v * 1.12) as [number, number];
  if (isLaneNoop(cur.executed, cur.ego.lane, laneCount) || cur.executed === "IDLE") {
    drawHold(ctx, ex, ey + carH / 2 + 7 * s, ARROW, false, s * 0.8);
  } else {
    const [dx, dy] = arrowFor(cur.executed, laneH);
    const ox = cur.executed === "FASTER" ? ex + carW / 2 : cur.executed === "SLOWER" ? ex - carW / 2 : ex;
    drawArrow(ctx, ox, ey, dx * 0.7, dy * 0.7, ARROW, false, s * 0.8);
  }
  ctx.globalAlpha = 1;
  if (cur.crashed || ended) {
    ctx.fillStyle = DECISION_COLOR.all_blocked;
    ctx.font = `700 ${12 * s}px ${SANS}`;
    ctx.fillText("CRASHED", ex + carW / 2 + 8 * s, ey);
  }
  ctx.restore();
}

export function TwinStrip() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const frame = useRef<TwinFrame>({ prev: null, cur: null, t0: 0, intervalMs: 500 });
  const twin = useStore((s) => s.twin);
  const liveSteps = useStore((s) => s.steps);
  const constraints = useStore((s) => s.constraints);
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
  // The live run's count up to the view step, so scrubbing moves both numbers together.
  const liveShown = live === null ? 0 : liveSteps.slice(0, live.step + 1).reduce((n, r) => n + executedViolations(r), 0);
  const scored = twin.rules > 0;
  const ruleWord = twin.rules === 1 ? "rule" : "rules";
  // The console and the backend deploy separately; a twin from an older backend has no rule ids.
  const ruleNames = (twin.rule_ids ?? []).map((id) => constraints.find((c) => c.id === id)?.text ?? id);
  const run = twin.run_id ? ` (${twin.run_id})` : "";
  const title = scored
    ? `The same seed with the shield off${run}, scored against the ${twin.rules} ${ruleWord} now on that ${twin.rules === 1 ? "has" : "have"} a checker: ${ruleNames.join("; ")}. Over the whole run it breaks them ${twin.violations_total} ${twin.violations_total === 1 ? "time" : "times"}.`
    : `The same seed with the shield off${run}. None of the rules on has a checker, so there is nothing to count on either side.`;
  return (
    <section className="panel flex h-[8.25rem] shrink-0 flex-col overflow-hidden">
      <div className="panel-title">
        <span className="flex items-center gap-2">
          Without the shield
          <span className="panel-subtitle" title={title}>
            same seed, shield off{cur ? ` · step ${cur.step}` : " · waiting"}
          </span>
        </span>
        <span className="panel-subtitle flex items-center gap-1.5" title={title}>
          {scored ? (
            <>
              <span>shield off</span>
              <span className="num text-sm font-semibold text-blocked">{shown}</span>
              <span>· shield on</span>
              <span className="num text-sm font-semibold text-allow">{liveShown}</span>
              <span>
                · violations so far, {twin.rules} {ruleWord} scored
              </span>
            </>
          ) : (
            <span>no scored rules on</span>
          )}
          {twin.crashed_at !== null && (
            <span>
              · <span className="text-blocked">crashes at step {twin.crashed_at}</span>
            </span>
          )}
        </span>
      </div>
      <canvas ref={canvasRef} className="block min-h-0 w-full flex-1" />
    </section>
  );
}
