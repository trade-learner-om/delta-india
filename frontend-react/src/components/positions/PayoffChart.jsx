import { useEffect, useMemo, useRef, useState } from "react";
import { formatPnl } from "../../utils/tradingFormatters";
import { chartSurface, chartEmptyState, textMuted, textBody } from "../../utils/workspace/workspaceClasses";
import { chartHoverTone, useChartTheme } from "../../utils/theme/chartTheme";

const W = 680;
const H = 300;
const PAD = { top: 28, right: 28, bottom: 48, left: 58 };

function scaleLinear(value, domain, range) {
  const [d0, d1] = domain;
  const [r0, r1] = range;
  if (d1 === d0) return (r0 + r1) / 2;
  return r0 + ((value - d0) / (d1 - d0)) * (r1 - r0);
}

function invertLinear(value, domain, range) {
  const [d0, d1] = domain;
  const [r0, r1] = range;
  if (r1 === r0) return (d0 + d1) / 2;
  return d0 + ((value - r0) / (r1 - r0)) * (d1 - d0);
}

function formatAxisSpot(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "—";
  if (num >= 1000) return `${(num / 1000).toFixed(1)}k`;
  return num.toFixed(0);
}

function formatBreakevenLabel(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "—";
  return num.toLocaleString("en-IN", { maximumFractionDigits: 0 });
}

function formatPnlLabel(value) {
  return formatPnl(value);
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function interpolatePoint(p0, p1, spot) {
  if (!p0 || !p1 || p1.spot === p0.spot) return { spot, pnl: p0?.pnl ?? p1?.pnl ?? 0 };
  const ratio = (spot - p0.spot) / (p1.spot - p0.spot);
  return {
    spot,
    pnl: p0.pnl + ratio * (p1.pnl - p0.pnl),
  };
}

function sliceVisiblePoints(points, minSpot, maxSpot) {
  if (!Array.isArray(points) || points.length < 2) return points || [];
  const visible = [];
  for (let i = 0; i < points.length - 1; i += 1) {
    const p0 = points[i];
    const p1 = points[i + 1];

    if (p0.spot <= minSpot && p1.spot >= minSpot) {
      visible.push(interpolatePoint(p0, p1, minSpot));
    }
    if (p0.spot >= minSpot && p0.spot <= maxSpot) {
      visible.push(p0);
    }
    if (p0.spot <= maxSpot && p1.spot >= maxSpot) {
      visible.push(interpolatePoint(p0, p1, maxSpot));
      break;
    }
  }
  const last = points[points.length - 1];
  if (last.spot >= minSpot && last.spot <= maxSpot) visible.push(last);
  return visible.length >= 2 ? visible : points;
}

function pointAtSpot(points, spot) {
  const left = points.findLast?.((item) => item.spot <= spot)
    ?? [...points].reverse().find((item) => item.spot <= spot)
    ?? points[0];
  const right = points.find((item) => item.spot >= spot) ?? points[points.length - 1];
  return interpolatePoint(left, right, spot);
}

function focusedDomain(payoff, fallbackSpot) {
  const points = payoff?.points || [];
  if (!points.length) return null;
  const fullMin = points[0].spot;
  const fullMax = points[points.length - 1].spot;
  const strike = Number(payoff?.strike || fallbackSpot || points[Math.floor(points.length / 2)]?.spot || fullMin);
  const liveSpot = Number(fallbackSpot ?? payoff?.spot ?? strike);
  const breakevens = Array.isArray(payoff?.breakevens) ? payoff.breakevens.filter(Number.isFinite) : [];

  let minSpot;
  let maxSpot;
  if (breakevens.length >= 2) {
    const pad = Math.max((breakevens[breakevens.length - 1] - breakevens[0]) * 0.75, strike * 0.08, 150);
    minSpot = Math.min(breakevens[0], strike, liveSpot) - pad;
    maxSpot = Math.max(breakevens[breakevens.length - 1], strike, liveSpot) + pad;
  } else {
    const fullSpan = fullMax - fullMin;
    const focusSpan = Math.max(fullSpan * 0.8, strike * 0.35, 500);
    minSpot = strike - focusSpan / 2;
    maxSpot = strike + focusSpan / 2;
  }

  minSpot = clamp(minSpot, fullMin, fullMax - 1);
  maxSpot = clamp(maxSpot, fullMin + 1, fullMax);
  if (maxSpot <= minSpot) {
    minSpot = fullMin;
    maxSpot = fullMax;
  }
  return { min: minSpot, max: maxSpot, fullMin, fullMax };
}

export default function PayoffChart({ payoff, spot, loading = false, title = "Payoff at sell-leg expiry" }) {
  const colors = useChartTheme();
  const [zoomDomain, setZoomDomain] = useState(null);
  const [hoveredSpot, setHoveredSpot] = useState(null);
  const containerRef = useRef(null);

  useEffect(() => {
    setZoomDomain(focusedDomain(payoff, spot));
  }, [payoff, spot]);

  useEffect(() => {
    const handlePointerDown = (event) => {
      if (!containerRef.current?.contains(event.target)) {
        setHoveredSpot(null);
      }
    };
    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, []);

  const chart = useMemo(() => {
    const points = payoff?.points || [];
    if (!points.length) return null;

    const fullMin = points[0].spot;
    const fullMax = points[points.length - 1].spot;
    const domain = zoomDomain || { min: fullMin, max: fullMax, fullMin, fullMax };
    const visiblePoints = sliceVisiblePoints(points, domain.min, domain.max);
    const spots = visiblePoints.map((p) => p.spot);
    const pnls = visiblePoints.map((p) => p.pnl);
    const strike = payoff?.strike;
    const spotMin = Math.min(...spots, strike ?? Infinity, spot ?? Infinity);
    const spotMax = Math.max(...spots, strike ?? 0, spot ?? 0);
    const pnlMin = Math.min(...pnls, payoff?.stopPnl ?? 0, payoff?.targetPnl ?? 0, 0);
    const pnlMax = Math.max(...pnls, payoff?.stopPnl ?? 0, payoff?.targetPnl ?? 0, 0);
    const padSpot = (spotMax - spotMin) * 0.1 || spotMax * 0.05 || 250;
    const padPnl = (pnlMax - pnlMin) * 0.35 || Math.max(Math.abs(pnlMax || 0), Math.abs(pnlMin || 0)) * 0.35 || 25;

    const xScale = (s) => scaleLinear(s, [spotMin - padSpot, spotMax + padSpot], [PAD.left, W - PAD.right]);
    const yScale = (p) => scaleLinear(p, [pnlMin - padPnl, pnlMax + padPnl], [H - PAD.bottom, PAD.top]);

    const linePath = visiblePoints
      .map((p, i) => `${i === 0 ? "M" : "L"}${xScale(p.spot).toFixed(1)},${yScale(p.pnl).toFixed(1)}`)
      .join(" ");

    const zeroY = yScale(0);
    const areaToZero = `${linePath} L${xScale(visiblePoints[visiblePoints.length - 1].spot).toFixed(1)},${zeroY.toFixed(1)} L${xScale(visiblePoints[0].spot).toFixed(1)},${zeroY.toFixed(1)} Z`;

    const liveSpot = spot ?? payoff?.spot;
    const spotX = liveSpot != null ? xScale(liveSpot) : null;
    const strikeX = strike != null ? xScale(strike) : null;

    const rawPnlMax = Math.max(...pnls);
    const peakIdx = pnls.indexOf(rawPnlMax);
    const peakX = xScale(visiblePoints[peakIdx].spot);
    const peakY = yScale(visiblePoints[peakIdx].pnl);
    const breakevenValues = payoff?.breakevens || [];
    const breakevens = breakevenValues
      .filter((b) => b >= domain.min && b <= domain.max)
      .map((b) => ({ value: b, x: xScale(b) }))
      .sort((a, b) => a.x - b.x);
    const plotLeft = PAD.left;
    const plotRight = W - PAD.right;
    const xDomainMin = spotMin - padSpot;
    const xDomainMax = spotMax + padSpot;
    const yDomainMin = pnlMin - padPnl;
    const yDomainMax = pnlMax + padPnl;

    return {
      linePath,
      areaToZero,
      zeroY,
      spotX,
      liveSpot,
      strikeX,
      xScale,
      yScale,
      xDomainMin,
      xDomainMax,
      yDomainMin,
      yDomainMax,
      visiblePoints,
      targetY: payoff?.targetPnl != null ? yScale(payoff.targetPnl) : null,
      stopY: payoff?.stopPnl != null ? yScale(payoff.stopPnl) : null,
      breakevens,
      peakX,
      peakY,
      plotLeft,
      plotRight,
      hasProfit: rawPnlMax > 0,
      hasLoss: Math.min(...pnls) < 0,
      domain,
      canResetZoom: Math.abs(domain.min - domain.fullMin) > 1 || Math.abs(domain.max - domain.fullMax) > 1,
    };
  }, [payoff, spot, zoomDomain]);

  if (!chart) {
    if (loading) {
      return (
        <div className={`mx-auto aspect-[680/300] w-full max-w-[680px] flex-col gap-3 ${chartEmptyState("flex")}`}>
          <span className="h-8 w-8 animate-spin rounded-full border-2 border-slate-300 dark:border-zinc-700 border-t-lime-500 dark:border-t-lime-400" />
          <span>Subscribing to CE &amp; PE legs — waiting for live prices…</span>
        </div>
      );
    }
    return (
      <div className={`mx-auto aspect-[680/300] w-full max-w-[680px] ${chartEmptyState()}`}>
        Payoff chart unavailable
      </div>
    );
  }

  const xTicks = 5;
  const yTicks = 4;
  const breakevenLabel = (payoff?.breakevens || [])
    .map((value) => formatBreakevenLabel(value))
    .join(" · ");
  const activeHoverPoint = hoveredSpot != null ? pointAtSpot(chart.visiblePoints, hoveredSpot) : null;
  const activeHover = activeHoverPoint
    ? {
        spot: activeHoverPoint.spot,
        pnl: activeHoverPoint.pnl,
        x: chart.xScale(activeHoverPoint.spot),
        y: chart.yScale(activeHoverPoint.pnl),
      }
    : null;
  const hoverTone = chartHoverTone(activeHover?.pnl ?? 0, colors);

  const handleWheel = (event) => {
    if (!chart?.domain) return;
    event.preventDefault();
    const rect = event.currentTarget.getBoundingClientRect();
    const ratio = clamp((event.clientX - rect.left) / rect.width, 0, 1);
    const currentMin = chart.domain.min;
    const currentMax = chart.domain.max;
    const currentSpan = currentMax - currentMin;
    const fullSpan = chart.domain.fullMax - chart.domain.fullMin;
    const anchor = currentMin + ratio * currentSpan;
    const nextSpan = clamp(
      event.deltaY < 0 ? currentSpan * 0.85 : currentSpan * 1.35,
      Math.max(fullSpan * 0.08, 100),
      fullSpan,
    );
    let nextMin = anchor - ratio * nextSpan;
    let nextMax = nextMin + nextSpan;
    if (nextMin < chart.domain.fullMin) {
      nextMin = chart.domain.fullMin;
      nextMax = nextMin + nextSpan;
    }
    if (nextMax > chart.domain.fullMax) {
      nextMax = chart.domain.fullMax;
      nextMin = nextMax - nextSpan;
    }
    setZoomDomain({
      min: nextMin,
      max: nextMax,
      fullMin: chart.domain.fullMin,
      fullMax: chart.domain.fullMax,
    });
  };

  const handlePointerMove = (event) => {
    if (!chart) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const svgX = ((event.clientX - rect.left) / rect.width) * W;
    const clampedX = clamp(svgX, PAD.left, W - PAD.right);
    const hoverSpot = invertLinear(
      clampedX,
      [chart.xDomainMin, chart.xDomainMax],
      [PAD.left, W - PAD.right],
    );
    const point = pointAtSpot(chart.visiblePoints, hoverSpot);
    setHoveredSpot(point.spot);
  };

  return (
    <div ref={containerRef} className={chartSurface("p-4")}>
      <div className={`mb-2 flex flex-wrap items-center justify-between gap-2 text-xs ${textMuted()}`}>
        <span className={`font-semibold uppercase tracking-wider ${textBody()}`}>{title}</span>
        <div className="flex flex-wrap items-center gap-2">
          {chart.canResetZoom ? (
            <button
              type="button"
              onClick={() => setZoomDomain(focusedDomain(payoff, spot))}
              className={`rounded-full border border-slate-300 dark:border-zinc-700 bg-slate-100 dark:bg-zinc-900 px-2 py-0.5 font-medium ${textMuted()} hover:bg-slate-200 dark:hover:bg-zinc-800`}
            >
              Reset zoom
            </button>
          ) : null}
          {breakevenLabel ? (
            <span className={`rounded-full border border-slate-200 dark:border-zinc-800 bg-slate-100 dark:bg-zinc-900 px-2 py-0.5 font-medium ${textBody()}`}>
              Breakeven {breakevenLabel}
            </span>
          ) : null}
          {chart.liveSpot != null ? (
            <span className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full bg-lime-400/10 border border-lime-400/20 px-2.5 py-1 text-lime-600 dark:text-lime-400">
              <span className="text-[10px] font-semibold uppercase tracking-[0.16em]">Spot</span>
              <span className="text-[11px] font-medium">{Number(chart.liveSpot).toLocaleString()}</span>
            </span>
          ) : null}
        </div>
      </div>
      <div className="mx-auto w-full max-w-[680px]">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          preserveAspectRatio="xMidYMid meet"
          className="block h-auto w-full cursor-ew-resize"
          role="img"
          aria-label="Position payoff diagram"
          onWheel={handleWheel}
          onPointerMove={handlePointerMove}
        >
        <defs>
          <linearGradient id="payoffGain" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#10b981" stopOpacity="0.35" />
            <stop offset="100%" stopColor="#10b981" stopOpacity="0.02" />
          </linearGradient>
          <linearGradient id="payoffLoss" x1="0" y1="1" x2="0" y2="0">
            <stop offset="0%" stopColor="#f43f5e" stopOpacity="0.3" />
            <stop offset="100%" stopColor="#f43f5e" stopOpacity="0.04" />
          </linearGradient>
          <clipPath id="aboveZero">
            <rect x={PAD.left} y={PAD.top} width={W - PAD.right - PAD.left} height={Math.max(chart.zeroY - PAD.top, 0)} />
          </clipPath>
          <clipPath id="belowZero">
            <rect x={PAD.left} y={chart.zeroY} width={W - PAD.right - PAD.left} height={Math.max(H - PAD.bottom - chart.zeroY, 0)} />
          </clipPath>
        </defs>

        {Array.from({ length: yTicks + 1 }, (_, i) => {
          const pnl = chart.yDomainMin + (i / yTicks) * (chart.yDomainMax - chart.yDomainMin);
          const y = chart.yScale(pnl);
          return (
            <g key={`yg-${i}`}>
              <line x1={PAD.left} y1={y} x2={W - PAD.right} y2={y} stroke={colors.grid} strokeWidth="0.6" opacity="0.55" />
              <text x={PAD.left - 7} y={y + 3} textAnchor="end" fill={colors.axisText} className="text-[8px]">
                {formatPnlLabel(pnl)}
              </text>
            </g>
          );
        })}

        {Array.from({ length: xTicks + 1 }, (_, i) => {
          const s = chart.xDomainMin + (i / xTicks) * (chart.xDomainMax - chart.xDomainMin);
          const x = chart.xScale(s);
          return (
            <text key={`xg-${i}`} x={x} y={H - 15} textAnchor="middle" fill={colors.axisText} className="text-[8px]">
              {formatAxisSpot(s)}
            </text>
          );
        })}

        <line
          x1={PAD.left}
          y1={chart.zeroY}
          x2={W - PAD.right}
          y2={chart.zeroY}
          stroke={colors.zeroLine}
          strokeWidth="0.7"
          strokeDasharray="4 4"
          opacity="0.65"
        />

        {chart.targetY != null ? (
          <line x1={PAD.left} y1={chart.targetY} x2={W - PAD.right} y2={chart.targetY} stroke="#10b981" strokeWidth="0.7" strokeDasharray="4 4" opacity="0.42" />
        ) : null}
        {chart.stopY != null ? (
          <line x1={PAD.left} y1={chart.stopY} x2={W - PAD.right} y2={chart.stopY} stroke="#f43f5e" strokeWidth="0.7" strokeDasharray="4 4" opacity="0.42" />
        ) : null}

        <path d={chart.areaToZero} fill="url(#payoffGain)" clipPath="url(#aboveZero)" />
        <path d={chart.areaToZero} fill="url(#payoffLoss)" clipPath="url(#belowZero)" />
        <path d={chart.linePath} fill="none" stroke={colors.payoffLine} strokeWidth="1.1" strokeLinejoin="round" />

        {chart.breakevens.map((be, i) => (
          <g key={`be-${i}`}>
            <line x1={be.x} y1={PAD.top} x2={be.x} y2={H - PAD.bottom} stroke={colors.breakevenLine} strokeWidth="0.6" strokeDasharray="3 4" opacity="0.35" />
            <circle cx={be.x} cy={chart.zeroY} r="2.6" fill={colors.dotStroke} stroke={colors.axisText} strokeWidth="1" />
            <text x={be.x} y={H - 23} textAnchor="middle" fill={colors.axisText} className="text-[7px] font-medium">
              {formatBreakevenLabel(be.value)}
            </text>
          </g>
        ))}

        {chart.hasProfit ? (
          <circle cx={chart.peakX} cy={chart.peakY} r="2.75" fill="#10b981" stroke={colors.dotStroke} strokeWidth="1.2" />
        ) : null}

        {chart.spotX != null ? (
          <g>
            <line
              x1={chart.spotX}
              y1={PAD.top}
              x2={chart.spotX}
              y2={H - PAD.bottom}
              stroke={colors.spotLine}
              strokeWidth="0.7"
              strokeDasharray="4 5"
              opacity="0.5"
            />
            <text x={chart.spotX} y={PAD.top - 3} textAnchor="middle" fill={colors.spotLine} className="text-[8px] font-medium uppercase tracking-[0.14em]">
              Spot
            </text>
          </g>
        ) : null}

        {activeHover ? (
          <g pointerEvents="none">
            <line
              x1={activeHover.x}
              y1={PAD.top}
              x2={activeHover.x}
              y2={H - PAD.bottom}
              stroke={hoverTone.line}
              strokeWidth="0.7"
              strokeDasharray="3 4"
              opacity="0.45"
            />
            <circle cx={activeHover.x} cy={activeHover.y} r="2.3" fill={hoverTone.dot} stroke={colors.dotStroke} strokeWidth="0.9" />
            <g transform={`translate(${clamp(activeHover.x + 8, PAD.left + 6, W - 132)},${clamp(activeHover.y - 34, PAD.top + 6, H - PAD.bottom - 30)})`}>
              <rect width="122" height="30" rx="9" fill={hoverTone.panel} fillOpacity="0.92" />
              <text x="9" y="12" className="text-[7px] font-semibold uppercase tracking-[0.14em]" fill={hoverTone.subtext}>
                Price {formatBreakevenLabel(activeHover.spot)}
              </text>
              <text x="9" y="23" className="text-[8px] font-medium" fill={hoverTone.text}>
                Projected PnL {formatPnlLabel(activeHover.pnl)}
              </text>
              <circle cx="111" cy="15" r="3.2" fill={hoverTone.panelAccent} opacity="0.9" />
            </g>
          </g>
        ) : null}
        <rect
          x={PAD.left}
          y={PAD.top}
          width={W - PAD.left - PAD.right}
          height={H - PAD.top - PAD.bottom}
          fill="transparent"
        />
        </svg>
      </div>
    </div>
  );
}
