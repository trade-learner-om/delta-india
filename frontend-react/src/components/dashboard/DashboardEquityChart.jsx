import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import WorkspaceCard from "../ui/WorkspaceCard";
import {
  chartSurface,
  textMuted,
  textHeading,
  profitText,
  lossText,
} from "../../utils/workspace/workspaceClasses";
import { useChartTheme, chartHoverTone } from "../../utils/theme/chartTheme";
import {
  RANGE_PRESETS,
  formatDateTime,
  formatPct,
  formatUsd,
} from "./dashboardUtils";

const CHART_RANGES = RANGE_PRESETS.filter((p) => ["1w", "1m", "all"].includes(p.id));

const WIDTH = 640;
const HEIGHT = 240;
const PAD = { top: 16, right: 16, bottom: 28, left: 52 };

function areaUnderLine(points, baselineY) {
  if (!points.length) return "";
  const line = smoothLinePath(points);
  if (!line) return "";
  const last = points[points.length - 1];
  const first = points[0];
  return `${line} L ${last.x.toFixed(2)} ${baselineY} L ${first.x.toFixed(2)} ${baselineY} Z`;
}

function smoothLinePath(points) {
  if (!points.length) return "";
  if (points.length === 1) {
    return `M ${points[0].x.toFixed(2)} ${points[0].y.toFixed(2)}`;
  }
  let d = `M ${points[0].x.toFixed(2)} ${points[0].y.toFixed(2)}`;
  for (let i = 1; i < points.length; i += 1) {
    const prev = points[i - 1];
    const curr = points[i];
    const cpx = (prev.x + curr.x) / 2;
    d += ` C ${cpx.toFixed(2)} ${prev.y.toFixed(2)}, ${cpx.toFixed(2)} ${curr.y.toFixed(2)}, ${curr.x.toFixed(2)} ${curr.y.toFixed(2)}`;
  }
  return d;
}

function formatAxisUsd(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  const abs = Math.abs(n);
  if (abs >= 1000) return `${n < 0 ? "-" : ""}$${(abs / 1000).toFixed(abs >= 10000 ? 0 : 1)}k`;
  return `${n < 0 ? "-" : ""}$${abs.toFixed(abs >= 100 ? 0 : 1)}`;
}

function formatShortDate(ms) {
  if (!Number.isFinite(ms)) return "";
  return new Date(ms).toLocaleDateString("en-IN", {
    timeZone: "Asia/Kolkata",
    day: "2-digit",
    month: "short",
  });
}

function pnlToneClass(value) {
  const n = Number(value);
  if (!Number.isFinite(n) || n === 0) return "text-slate-800 dark:text-zinc-100";
  return n > 0 ? profitText() : lossText();
}

export default function DashboardEquityChart({
  points,
  rangeId = "1m",
  onRangeChange,
  closedPnl = 0,
  winRate = 0,
  maxDrawdownUsd = 0,
  closedCount = 0,
}) {
  const colors = useChartTheme();
  const reactId = useId();
  const gradPos = `eq-pos-${reactId.replace(/:/g, "")}`;
  const gradNeg = `eq-neg-${reactId.replace(/:/g, "")}`;
  const [hoverIndex, setHoverIndex] = useState(null);
  const [drawn, setDrawn] = useState(false);
  const pathRef = useRef(null);

  const plotW = WIDTH - PAD.left - PAD.right;
  const plotH = HEIGHT - PAD.top - PAD.bottom;

  const plotted = useMemo(() => {
    const source = Array.isArray(points) ? points : [];
    if (!source.length) return [];
    const values = source.map((point) => Number(point.value) || 0);
    const min = Math.min(0, ...values);
    const max = Math.max(0, ...values);
    const span = max - min || 1;
    return source.map((point, index) => {
      const ratio = source.length === 1 ? 0.5 : index / (source.length - 1);
      const value = Number(point.value) || 0;
      return {
        ...point,
        x: PAD.left + ratio * plotW,
        y: PAD.top + plotH - ((value - min) / span) * plotH,
        value,
        tradePnl: Number(point.tradePnl) || 0,
      };
    });
  }, [points, plotW, plotH]);

  const valueDomain = useMemo(() => {
    if (!plotted.length) return { min: 0, max: 0 };
    const values = plotted.map((p) => p.value);
    return { min: Math.min(0, ...values), max: Math.max(0, ...values) };
  }, [plotted]);

  const zeroY = useMemo(() => {
    const { min, max } = valueDomain;
    const span = max - min || 1;
    return PAD.top + plotH - ((0 - min) / span) * plotH;
  }, [valueDomain, plotH]);

  const linePath = useMemo(() => smoothLinePath(plotted), [plotted]);
  const areaPath = useMemo(
    () => areaUnderLine(plotted, zeroY),
    [plotted, zeroY],
  );

  const yTicks = useMemo(() => {
    const { min, max } = valueDomain;
    const span = max - min || 1;
    const steps = 4;
    return Array.from({ length: steps + 1 }, (_, i) => {
      const value = min + (span * i) / steps;
      const y = PAD.top + plotH - ((value - min) / span) * plotH;
      return { value, y };
    });
  }, [valueDomain, plotH]);

  const xTicks = useMemo(() => {
    if (plotted.length < 2) return plotted.map((p) => ({ x: p.x, time: p.time }));
    const count = Math.min(4, plotted.length);
    const ticks = [];
    for (let i = 0; i < count; i += 1) {
      const idx = Math.round((i / (count - 1)) * (plotted.length - 1));
      ticks.push({ x: plotted[idx].x, time: plotted[idx].time });
    }
    return ticks;
  }, [plotted]);

  const tradeMarkers = useMemo(
    () => plotted.filter((p) => !p.isBaseline),
    [plotted],
  );

  useEffect(() => {
    setDrawn(false);
    setHoverIndex(null);
    const path = pathRef.current;
    if (!path || !linePath) {
      setDrawn(true);
      return undefined;
    }
    const length = path.getTotalLength();
    path.style.strokeDasharray = String(length);
    path.style.strokeDashoffset = String(length);
    path.style.transition = "none";
    // Force layout before animating
    void path.getBoundingClientRect();
    path.style.transition = "stroke-dashoffset 0.6s ease-out";
    path.style.strokeDashoffset = "0";
    const t = window.setTimeout(() => setDrawn(true), 620);
    return () => window.clearTimeout(t);
  }, [linePath, rangeId]);

  const onMouseMove = useCallback(
    (event) => {
      if (!tradeMarkers.length) return;
      const rect = event.currentTarget.getBoundingClientRect();
      const relativeX = ((event.clientX - rect.left) / rect.width) * WIDTH;
      let nearest = 0;
      let distance = Number.POSITIVE_INFINITY;
      tradeMarkers.forEach((point, index) => {
        const delta = Math.abs(point.x - relativeX);
        if (delta < distance) {
          distance = delta;
          nearest = index;
        }
      });
      // Map to full plotted index
      const target = tradeMarkers[nearest];
      const fullIdx = plotted.findIndex((p) => p === target);
      setHoverIndex(fullIdx >= 0 ? fullIdx : null);
    },
    [tradeMarkers, plotted],
  );

  const hoverPoint = hoverIndex == null ? null : plotted[hoverIndex];
  const hoverTone = hoverPoint ? chartHoverTone(hoverPoint.tradePnl || hoverPoint.value, colors) : null;

  return (
    <WorkspaceCard className="lg:col-span-2 space-y-3">
      <div className="flex flex-wrap justify-between items-start gap-3">
        <div>
          <h3 className={`text-sm font-bold uppercase tracking-wider ${textHeading()}`}>
            Equity Performance Wave
          </h3>
          <p className={`text-xs ${textMuted()}`}>
            Cumulative closed ST Options P&L — hover a point for trade detail
          </p>
        </div>
        <div className="flex gap-1.5 font-mono text-xs">
          {CHART_RANGES.map((preset) => {
            const active = rangeId === preset.id;
            return (
              <button
                key={preset.id}
                type="button"
                onClick={() => onRangeChange?.(preset.id)}
                className={
                  active
                    ? "px-2.5 py-1 bg-lime-400 text-zinc-950 font-bold rounded-lg shadow-sm"
                    : `px-2.5 py-1 bg-slate-200 dark:bg-zinc-800 rounded-lg ${textMuted()} hover:bg-slate-300 dark:hover:bg-zinc-700`
                }
              >
                {preset.label}
              </button>
            );
          })}
        </div>
      </div>

      <div
        className={`h-60 w-full ${chartSurface("p-1 relative overflow-hidden")}`}
        onMouseMove={onMouseMove}
        onMouseLeave={() => setHoverIndex(null)}
      >
        {!plotted.length ? (
          <div className={`flex h-full items-center justify-center text-xs ${textMuted()}`}>
            No equity data in this range.
          </div>
        ) : (
          <>
            <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="w-full h-full" role="img">
              <defs>
                <linearGradient id={gradPos} x1="0%" y1="0%" x2="0%" y2="100%">
                  <stop offset="0%" stopColor={colors.equityFill} stopOpacity="0.35" />
                  <stop offset="100%" stopColor={colors.equityFill} stopOpacity="0" />
                </linearGradient>
                <linearGradient id={gradNeg} x1="0%" y1="100%" x2="0%" y2="0%">
                  <stop offset="0%" stopColor={colors.lineNegative} stopOpacity="0.28" />
                  <stop offset="100%" stopColor={colors.lineNegative} stopOpacity="0" />
                </linearGradient>
                <clipPath id={`${gradPos}-clip-hi`}>
                  <rect x={PAD.left} y={PAD.top} width={plotW} height={Math.max(0, zeroY - PAD.top)} />
                </clipPath>
                <clipPath id={`${gradPos}-clip-lo`}>
                  <rect
                    x={PAD.left}
                    y={zeroY}
                    width={plotW}
                    height={Math.max(0, PAD.top + plotH - zeroY)}
                  />
                </clipPath>
              </defs>

              {yTicks.map((tick) => (
                <g key={`y-${tick.value}`}>
                  <line
                    x1={PAD.left}
                    x2={PAD.left + plotW}
                    y1={tick.y}
                    y2={tick.y}
                    stroke={colors.grid}
                    strokeWidth="1"
                    strokeDasharray="3 4"
                  />
                  <text
                    x={PAD.left - 8}
                    y={tick.y + 3}
                    textAnchor="end"
                    fill={colors.axisText}
                    fontSize="10"
                    fontFamily="ui-monospace, monospace"
                  >
                    {formatAxisUsd(tick.value)}
                  </text>
                </g>
              ))}

              {xTicks.map((tick, i) => (
                <text
                  key={`x-${i}-${tick.time}`}
                  x={tick.x}
                  y={HEIGHT - 8}
                  textAnchor="middle"
                  fill={colors.axisText}
                  fontSize="10"
                  fontFamily="ui-monospace, monospace"
                >
                  {formatShortDate(tick.time)}
                </text>
              ))}

              <line
                x1={PAD.left}
                x2={PAD.left + plotW}
                y1={zeroY}
                y2={zeroY}
                stroke={colors.zeroLine}
                strokeWidth="1.25"
                strokeDasharray="4 3"
              />

              <path
                d={areaPath}
                fill={`url(#${gradPos})`}
                clipPath={`url(#${gradPos}-clip-hi)`}
                opacity={drawn ? 1 : 0}
                style={{ transition: "opacity 0.45s ease-out" }}
              />
              <path
                d={areaPath}
                fill={`url(#${gradNeg})`}
                clipPath={`url(#${gradPos}-clip-lo)`}
                opacity={drawn ? 1 : 0}
                style={{ transition: "opacity 0.45s ease-out" }}
              />

              <path
                ref={pathRef}
                d={linePath}
                fill="none"
                stroke={colors.equityLine}
                strokeWidth="2.5"
                strokeLinejoin="round"
                strokeLinecap="round"
              />

              {tradeMarkers.map((point, i) => {
                const win = point.tradePnl >= 0;
                return (
                  <circle
                    key={`m-${i}-${point.time}`}
                    cx={point.x}
                    cy={point.y}
                    r={hoverPoint === point ? 5 : 3.25}
                    fill={win ? colors.linePositive : colors.lineNegative}
                    stroke={colors.dotStroke}
                    strokeWidth="1.5"
                    opacity={drawn ? 1 : 0}
                    style={{ transition: "opacity 0.35s ease-out, r 0.15s ease-out" }}
                  />
                );
              })}

              {hoverPoint ? (
                <line
                  x1={hoverPoint.x}
                  x2={hoverPoint.x}
                  y1={PAD.top}
                  y2={PAD.top + plotH}
                  stroke={hoverTone.line}
                  strokeWidth="1.25"
                  strokeDasharray="3 3"
                />
              ) : null}
            </svg>

            {hoverPoint && !hoverPoint.isBaseline ? (
              <div
                className="pointer-events-none absolute z-10 rounded-lg border px-2.5 py-2 text-[10px] font-mono shadow-md"
                style={{
                  left: `min(calc(${(hoverPoint.x / WIDTH) * 100}% + 8px), calc(100% - 11rem))`,
                  top: 10,
                  background: hoverTone.panel,
                  borderColor: hoverTone.panelAccent,
                  color: hoverTone.text,
                }}
              >
                <p className="font-bold">{formatDateTime(hoverPoint.time)}</p>
                {hoverPoint.symbol ? (
                  <p style={{ color: hoverTone.subtext }}>{hoverPoint.symbol}</p>
                ) : null}
                <p>
                  Cum{" "}
                  <span className="font-bold">
                    {formatUsd(hoverPoint.value)}
                  </span>
                </p>
                <p>
                  Trade{" "}
                  <span className="font-bold">
                    {hoverPoint.tradePnl >= 0 ? "+" : ""}
                    {formatUsd(hoverPoint.tradePnl)}
                  </span>
                </p>
              </div>
            ) : null}
          </>
        )}
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 border-t border-slate-200 dark:border-zinc-800 pt-3">
        <Stat
          label="Total P&L"
          value={formatUsd(closedPnl)}
          valueClass={pnlToneClass(closedPnl)}
        />
        <Stat label="Win rate" value={formatPct(winRate, 1)} />
        <Stat
          label="Max drawdown"
          value={maxDrawdownUsd > 0 ? formatUsd(-Math.abs(maxDrawdownUsd)) : formatUsd(0)}
          valueClass={maxDrawdownUsd > 0 ? lossText() : undefined}
        />
        <Stat label="Trades" value={String(closedCount)} />
      </div>
    </WorkspaceCard>
  );
}

function Stat({ label, value, valueClass }) {
  return (
    <div>
      <p className={`text-[10px] uppercase tracking-wider font-semibold ${textMuted()}`}>{label}</p>
      <p className={`text-sm font-mono font-bold tabular-nums ${valueClass || textHeading()}`}>
        {value}
      </p>
    </div>
  );
}
