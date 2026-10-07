import { useMemo } from "react";
import { useTheme } from "./ThemeContext";

const LIGHT = {
  grid: "#e2e8f0",
  axis: "#cbd5e1",
  axisText: "#64748b",
  zeroLine: "#94a3b8",
  dotStroke: "#ffffff",
  breakevenLine: "#94a3b8",
  donutTrack: "#e2e8f0",
  linePositive: "#059669",
  lineNegative: "#e11d48",
  equityLine: "#65a30d",
  equityFill: "#84cc16",
  payoffLine: "#65a30d",
  spotLine: "#65a30d",
  hoverPositive: {
    line: "#059669",
    dot: "#059669",
    panel: "#ecfdf5",
    panelAccent: "#6ee7b7",
    subtext: "#047857",
    text: "#064e3b",
  },
  hoverNegative: {
    line: "#dc2626",
    dot: "#dc2626",
    panel: "#fff1f2",
    panelAccent: "#fca5a5",
    subtext: "#be123c",
    text: "#881337",
  },
};

const DARK = {
  grid: "#3f3f46",
  axis: "#52525b",
  axisText: "#71717a",
  zeroLine: "#52525b",
  dotStroke: "#18181b",
  breakevenLine: "#71717a",
  donutTrack: "#27272a",
  linePositive: "#10b981",
  lineNegative: "#f43f5e",
  equityLine: "#bef264",
  equityFill: "#bef264",
  payoffLine: "#a3e635",
  spotLine: "#a3e635",
  hoverPositive: {
    line: "#059669",
    dot: "#059669",
    panel: "#052e2b",
    panelAccent: "#6ee7b7",
    subtext: "#a7f3d0",
    text: "#ecfdf5",
  },
  hoverNegative: {
    line: "#dc2626",
    dot: "#dc2626",
    panel: "#3b0a0a",
    panelAccent: "#fca5a5",
    subtext: "#fecdd3",
    text: "#fff1f2",
  },
};

export function useChartTheme() {
  const { isDark } = useTheme();
  return useMemo(() => (isDark ? DARK : LIGHT), [isDark]);
}

export function chartHoverTone(value, colors) {
  return Number(value) >= 0 ? colors.hoverPositive : colors.hoverNegative;
}
