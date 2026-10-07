import { livePriceFromTick, lookupLiveTick } from "../../utils/pricePrecision";

export function mergeSpreadExecutionPayload(restPayload, livePayload) {
  if (livePayload?.positions != null) return livePayload;
  return restPayload || livePayload || null;
}

export function mergePositionsPayload(restPayload, livePayload) {
  if (livePayload?.type === "positions") return livePayload;
  return restPayload || livePayload || null;
}

export function formatUsd(value, digits = 2) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "—";
  const sign = num > 0 ? "+" : "";
  return `${sign}${num.toLocaleString("en-IN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}`;
}

export function formatPct(value, digits = 4) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "—";
  return `${Math.abs(num).toFixed(digits)}%`;
}

export function filterAccountsByExchange(accounts, exchange) {
  return (accounts || []).filter(
    (a) => String(a.exchange || a.brokerType || "").toLowerCase().includes(exchange),
  );
}

export function formatHoldCountdown(holdUntilTs, nowMs) {
  if (!holdUntilTs) return null;
  const diff = Number(holdUntilTs) * 1000 - nowMs;
  if (!Number.isFinite(diff)) return null;
  if (diff <= 0) return "Closing soon";
  const totalSec = Math.floor(diff / 1000);
  const min = Math.floor(totalSec / 60);
  const sec = totalSec % 60;
  return `${min}:${String(sec).padStart(2, "0")}`;
}

export function groupByBroker(items) {
  const grouped = { delta: [] };
  for (const item of items || []) {
    const broker = String(item.broker || "delta").toLowerCase();
    if (broker === "delta") grouped.delta.push(item);
  }
  return grouped;
}

export function formatOrderTime(value) {
  if (!value) return "—";
  const num = Number(value);
  if (Number.isFinite(num) && num > 1e10) {
    try {
      return new Date(num).toLocaleString();
    } catch {
      return String(value);
    }
  }
  try {
    return new Date(value).toLocaleString();
  } catch {
    return String(value);
  }
}

export function formatPrice(value, digits = 2) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "—";
  return num.toLocaleString("en-IN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function resolveLiveMarkPrice(row, livePrices = {}) {
  const tick = lookupLiveTick(livePrices, row?.symbol);
  const liveMark = livePriceFromTick(tick);
  return Number.isFinite(liveMark) ? liveMark : Number(row?.markPrice);
}

export function computeLiveUnrealizedPnl(row, livePrices = {}) {
  const liveMark = resolveLiveMarkPrice(row, livePrices);
  const entry = Number(row?.entryPrice);
  const signedSize = Number(row?.signedSize);
  const contractValue = Number(row?.contractValue ?? 1);
  if (
    Number.isFinite(liveMark)
    && Number.isFinite(entry)
    && Number.isFinite(signedSize)
    && signedSize !== 0
    && Number.isFinite(contractValue)
    && contractValue > 0
  ) {
    return (liveMark - entry) * signedSize * contractValue;
  }
  return Number(row?.unrealizedPnlUsd) || 0;
}

export function decoratePositionRow(row, livePrices = {}) {
  if (!row) return row;
  const markPrice = resolveLiveMarkPrice(row, livePrices);
  const unrealizedPnlUsd = computeLiveUnrealizedPnl(row, livePrices);
  return {
    ...row,
    markPrice,
    unrealizedPnlUsd,
  };
}

export function decoratePositionsPayload(payload, livePrices = {}) {
  if (!payload) return payload;
  const openPositions = (payload.openPositions || []).map((row) => decoratePositionRow(row, livePrices));
  const openUnrealizedPnlUsd = openPositions.reduce(
    (sum, row) => sum + (Number(row.unrealizedPnlUsd) || 0),
    0,
  );
  return {
    ...payload,
    openPositions,
    openUnrealizedPnlUsd,
  };
}
