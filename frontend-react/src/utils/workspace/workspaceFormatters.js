import { useEffect, useRef, useState } from "react";
import { lookupLiveTick, spotDisplayPrice } from "../pricePrecision";

export function formatUsd2(value, { signed = false } = {}) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "—";
  const formatted = num.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  if (signed && num > 0) return `+${formatted}`;
  return formatted;
}

export function formatUsdWithSymbol(value, { signed = false } = {}) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "—";
  const prefix = signed && num > 0 ? "+$" : num < 0 ? "-$" : "$";
  return `${prefix}${formatUsd2(Math.abs(num))}`;
}

export function formatSpotPrice(livePrices, symbol) {
  const tick = lookupLiveTick(livePrices, symbol);
  const price = spotDisplayPrice(tick);
  if (price == null) return null;
  return Number(price).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export function useTickDirection(price, { holdMs = 600 } = {}) {
  const prevRef = useRef(price);
  const [direction, setDirection] = useState(null);

  useEffect(() => {
    const prev = prevRef.current;
    if (price != null && prev != null && price !== prev) {
      setDirection(price >= prev ? "up" : "down");
    }
    prevRef.current = price;
  }, [price]);

  useEffect(() => {
    if (direction == null || holdMs == null || holdMs <= 0) return undefined;
    const timer = window.setTimeout(() => setDirection(null), holdMs);
    return () => window.clearTimeout(timer);
  }, [direction, price, holdMs]);

  return direction;
}

/** Last up/down move — stays green or red until the next opposite tick (no fade to neutral). */
export function useHeldTickDirection(price) {
  return useTickDirection(price, { holdMs: 0 });
}

export function tickColorClass(direction) {
  if (direction === "up") return "text-emerald-600 dark:text-emerald-400";
  if (direction === "down") return "text-red-600 dark:text-red-400";
  return "text-zinc-900 dark:text-zinc-100";
}

export function pnlColorClass(value) {
  const num = Number(value);
  if (!Number.isFinite(num) || num === 0) return "text-slate-600 dark:text-zinc-300";
  return num > 0 ? "text-lime-600 dark:text-lime-400" : "text-red-600 dark:text-red-400";
}
