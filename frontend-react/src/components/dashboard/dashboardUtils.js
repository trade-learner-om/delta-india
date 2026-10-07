import { readAvailableMargin } from "../../utils/accountMargin";
import { formatUsd } from "../positions/positionsUtils";

export { formatUsd };

export const DASHBOARD_HISTORY_PAGE_SIZE = 100;
export const DASHBOARD_HISTORY_MAX = 200;

export async function fetchDashboardTradeHistory(apiFn, token, maxTrades = DASHBOARD_HISTORY_MAX) {
  if (!token) return [];
  let all = [];
  let cursor = null;
  while (all.length < maxTrades) {
    const params = new URLSearchParams({ limit: String(DASHBOARD_HISTORY_PAGE_SIZE) });
    if (cursor) params.set("cursor", cursor);
    const data = await apiFn(`/st-options/history?${params.toString()}`, { token });
    const batch = data.trades || [];
    all = all.concat(batch);
    const serverPaged =
      Object.prototype.hasOwnProperty.call(data, "hasMore") ||
      Object.prototype.hasOwnProperty.call(data, "nextCursor");
    if (!serverPaged) {
      return all.slice(0, maxTrades);
    }
    if (!data.hasMore || !data.nextCursor || !batch.length) break;
    cursor = data.nextCursor;
  }
  return all.slice(0, maxTrades);
}

export function mergeDashboardPositions(restPayload, wsPayload) {
  const merged = wsPayload?.type === "positions" ? wsPayload : restPayload || wsPayload || null;
  if ((merged?.openPositions || []).length) return merged;
  if ((restPayload?.openPositions || []).length) return restPayload;
  return merged;
}

export const RANGE_PRESETS = [
  { id: "1d", label: "1D", days: 1 },
  { id: "1w", label: "1W", days: 7 },
  { id: "1m", label: "1M", days: 30 },
  { id: "1y", label: "1Y", days: 365 },
  { id: "all", label: "All", days: null },
];

export function scopeAccounts(accounts, scopeId) {
  if (!scopeId || scopeId === "all") return accounts || [];
  return (accounts || []).filter((account) => account.id === scopeId);
}

export function accountScopeLabel(scopeId, accounts) {
  if (!scopeId || scopeId === "all") {
    const count = (accounts || []).length;
    return count === 1 ? "1 exchange" : `Across ${count} exchanges`;
  }
  const account = (accounts || []).find((item) => item.id === scopeId);
  return account?.accountName || account?.account_name || "Selected account";
}

export function totalEstimatedBalance(accounts) {
  return (accounts || []).reduce((sum, account) => {
    const margin = readAvailableMargin(account);
    return sum + (margin ?? 0);
  }, 0);
}

export function parseTs(value) {
  if (value == null || value === "") return null;
  if (typeof value === "number" && Number.isFinite(value)) {
    const ms = value < 1e12 ? value * 1000 : value;
    return Number.isFinite(ms) ? ms : null;
  }
  const raw = String(value).trim();
  if (/^\d+$/.test(raw)) {
    const n = Number(raw);
    if (Number.isFinite(n)) {
      const ms = n < 1e12 ? n * 1000 : n;
      return Number.isFinite(ms) ? ms : null;
    }
  }
  const ts = Date.parse(value);
  return Number.isFinite(ts) ? ts : null;
}

export function tradePnl(trade) {
  const realized = Number(trade?.realizedPnlUsd) || 0;
  const funding = Number(trade?.fundingCollectedUsd) || 0;
  const unrealized = trade?.status === "open" ? Number(trade?.unrealizedPnlUsd) || 0 : 0;
  return realized + funding + unrealized;
}

export function closedTradePnl(trade) {
  return (Number(trade?.realizedPnlUsd) || 0) + (Number(trade?.fundingCollectedUsd) || 0);
}

export function filterTradesByRange(trades, rangeId, customFrom, customTo) {
  const now = Date.now();
  const preset = RANGE_PRESETS.find((item) => item.id === rangeId);
  let fromTs = null;
  let toTs = now;

  if (customFrom) fromTs = parseTs(customFrom);
  if (customTo) toTs = parseTs(customTo) || now;
  if (!customFrom && preset?.days) {
    fromTs = now - preset.days * 24 * 60 * 60 * 1000;
  }

  return (trades || []).filter((trade) => {
    const opened = parseTs(trade.openedAt);
    const closed = parseTs(trade.closedAt);
    const anchor = closed ?? opened;
    if (!anchor) return rangeId === "all";
    if (fromTs && anchor < fromTs) return false;
    if (toTs && anchor > toTs) return false;
    return true;
  });
}

export function buildDashboardModel({
  accounts = [],
  scopeId = "all",
  positionsPayload = null,
  tradeHistory = [],
  rangeId = "all",
  customFrom = "",
  customTo = "",
}) {
  const scopedAccounts = scopeAccounts(accounts, scopeId);
  const estimatedBalance = totalEstimatedBalance(scopedAccounts);
  const allTrades = normalizeTradeHistory(tradeHistory);
  const openPositions = buildDashboardOpenPositions(positionsPayload);
  const rangedTrades = filterTradesByRange(allTrades, rangeId, customFrom, customTo);
  const closedTrades = rangedTrades.filter((trade) => trade.status === "closed");
  const realizedAndTrackedPnl = closedTrades.reduce((sum, trade) => sum + closedTradePnl(trade), 0);
  const liveOpenPnl = positionsPayload?.openUnrealizedPnlUsd ?? sumOpenPositionPnl(openPositions);
  const liveOpenFunding = positionsPayload?.openFundingUsd ?? 0;
  const totalPnl = realizedAndTrackedPnl + (Number(liveOpenPnl) || 0) + (Number(liveOpenFunding) || 0);
  const winners = closedTrades.filter((trade) => closedTradePnl(trade) > 0);
  const losers = closedTrades.filter((trade) => closedTradePnl(trade) < 0);
  const winRate = closedTrades.length ? (winners.length / closedTrades.length) * 100 : 0;

  const gains = winners.map((trade) => closedTradePnl(trade));
  const losses = losers.map((trade) => Math.abs(closedTradePnl(trade)));
  const avgGain = gains.length ? gains.reduce((a, b) => a + b, 0) / gains.length : null;
  const avgLoss = losses.length ? losses.reduce((a, b) => a + b, 0) / losses.length : null;
  const bigWin = gains.length ? Math.max(...gains) : null;
  const bigLoss = losses.length ? Math.max(...losses) : null;
  const riskReward = avgGain != null && avgLoss ? avgGain / avgLoss : null;

  const equityCurve = buildEquityCurve(closedTrades);
  const { maxDrawdownPct, maxDrawdownUsd } = maxDrawdown(equityCurve);
  const closedPnl = closedTrades.reduce((sum, trade) => sum + closedTradePnl(trade), 0);
  const roiPct = estimatedBalance > 0 ? (totalPnl / estimatedBalance) * 100 : 0;
  const allocation = buildAllocation(openPositions);
  const holding = holdingStats(closedTrades);
  const sharpe = sharpeRatio(closedTrades);

  return {
    estimatedBalance,
    balanceSubtitle: accountScopeLabel(scopeId, accounts),
    openPositionCount: positionsPayload?.openCount ?? openPositions.length,
    totalPnl,
    closedPnl,
    openPositions,
    winRate,
    closedCount: closedTrades.length,
    profitableCount: winners.length,
    losingCount: losers.length,
    avgGain,
    avgLoss,
    bigWin,
    bigLoss,
    riskReward,
    maxDrawdownPct,
    maxDrawdownUsd,
    roiPct,
    equityCurve,
    allocation,
    holding,
    sharpe,
    rangeId,
    tableRows: buildTableRows(rangedTrades),
  };
}

function buildDashboardOpenPositions(positionsPayload) {
  const brokerCards = positionsPayload?.openPositions || [];
  return brokerCards.map((row) => ({
    id: row.id,
    coin: row.coin,
    symbol: row.symbol || row.coin,
    source: row.source === "app" ? "app" : "broker",
    status: "open",
    unrealizedPnlUsd: Number(row.unrealizedPnlUsd) || 0,
    quantityCoin: row.signedSize ?? row.size,
    signedSize: row.signedSize,
    size: row.size,
    contractValue: row.contractValue,
    price: row.entryPrice,
    marketPrice: row.markPrice,
    accountId: row.accountId || null,
  }));
}

function sumOpenPositionPnl(openPositions) {
  return (openPositions || []).reduce((sum, item) => sum + (Number(item.unrealizedPnlUsd) || 0), 0);
}

function buildEquityCurve(closedTrades) {
  const sorted = [...closedTrades]
    .filter((trade) => parseTs(trade.closedAt))
    .sort((a, b) => parseTs(a.closedAt) - parseTs(b.closedAt));

  if (!sorted.length) return [];

  let cumulative = 0;
  const points = [
    {
      time: parseTs(sorted[0].closedAt) - 86400000,
      value: 0,
      tradePnl: 0,
      symbol: null,
      direction: null,
      isBaseline: true,
    },
  ];
  for (const trade of sorted) {
    const tradePnl = closedTradePnl(trade);
    cumulative += tradePnl;
    points.push({
      time: parseTs(trade.closedAt),
      value: cumulative,
      tradePnl,
      symbol: trade.symbol || null,
      direction: trade.direction || null,
      isBaseline: false,
    });
  }
  return points;
}

function maxDrawdown(curve) {
  if (!curve.length) return { maxDrawdownPct: 0, maxDrawdownUsd: 0 };
  let peak = curve[0].value;
  let maxDd = 0;
  for (const point of curve) {
    peak = Math.max(peak, point.value);
    const dd = peak - point.value;
    maxDd = Math.max(maxDd, dd);
  }
  const pct = peak > 0 ? (maxDd / peak) * 100 : 0;
  return { maxDrawdownPct: pct, maxDrawdownUsd: maxDd };
}

function buildAllocation(openPositions) {
  const byCoin = {};
  for (const trade of openPositions) {
    const coin = trade.symbol || trade.coin || "Other";
    const notional = (Number(trade.price) || 0) * (Number(trade.quantityCoin) || 0);
    byCoin[coin] = (byCoin[coin] || 0) + notional;
  }
  const total = Object.values(byCoin).reduce((sum, value) => sum + value, 0);
  if (!total) return [];
  return Object.entries(byCoin)
    .map(([coin, value]) => ({ coin, value, pct: (value / total) * 100 }))
    .sort((a, b) => b.value - a.value);
}

function holdingStats(closedTrades) {
  const durations = closedTrades
    .map((trade) => {
      const opened = parseTs(trade.openedAt);
      const closed = parseTs(trade.closedAt);
      if (!opened || !closed) return null;
      return { ms: closed - opened, pnl: closedTradePnl(trade) };
    })
    .filter(Boolean);

  if (!durations.length) {
    return { winners: null, losers: null, biggestWin: null, biggestLoss: null };
  }

  const winnerDurations = durations.filter((item) => item.pnl > 0).map((item) => item.ms);
  const loserDurations = durations.filter((item) => item.pnl < 0).map((item) => item.ms);
  const pnls = durations.map((item) => item.pnl);

  return {
    winners: winnerDurations.length ? averageMs(winnerDurations) : null,
    losers: loserDurations.length ? averageMs(loserDurations) : null,
    biggestWin: pnls.length ? Math.max(...pnls) : null,
    biggestLoss: pnls.length ? Math.min(...pnls) : null,
  };
}

function averageMs(values) {
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function sharpeRatio(closedTrades) {
  const returns = closedTrades.map((trade) => closedTradePnl(trade));
  if (returns.length < 2) return null;
  const mean = returns.reduce((sum, value) => sum + value, 0) / returns.length;
  const variance = returns.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (returns.length - 1);
  const std = Math.sqrt(variance);
  if (!std) return null;
  return (mean / std) * Math.sqrt(returns.length);
}

function buildTableRows(trades) {
  return [...trades]
    .sort((a, b) => (parseTs(b.openedAt) || 0) - (parseTs(a.openedAt) || 0))
    .map((trade) => ({
      id: trade.id,
      symbol: trade.symbol,
      tradeType: trade.tradeType,
      qty: trade.quantityCoin,
      entryPrice: trade.price,
      marketPrice: trade.marketPrice ?? trade.price,
      stopLoss: "—",
      target: "—",
      pnl: tradePnl(trade),
      entryAt: trade.openedAt,
      exitAt: trade.closedAt,
      source: trade.source || "—",
      status: trade.status,
    }));
}

function normalizeTradeHistory(trades) {
  return (trades || []).map((trade) => {
    // ST Options closed live trades
    if (trade.optionSymbol != null || trade.stColour != null || trade.premiumReceived != null) {
      const exitAt = trade.exitTime ?? trade.closedAt ?? null;
      const entryAt = trade.entryTime ?? trade.openedAt ?? null;
      return {
        id: trade.id,
        symbol: trade.optionSymbol || trade.underlying || "ST Options",
        coin: trade.underlying || "BTC",
        tradeType: trade.direction === "LONG" ? "ST Long" : trade.direction === "SHORT" ? "ST Short" : "ST Options",
        quantityCoin: Number(trade.lots) || 0,
        price: Number(trade.premiumReceived) || 0,
        marketPrice: Number(trade.exitPrice) || Number(trade.premiumReceived) || 0,
        realizedPnlUsd: Number(trade.pnl) || Number(trade.realizedPnl) || 0,
        fundingCollectedUsd: 0,
        unrealizedPnlUsd: 0,
        openedAt: entryAt,
        closedAt: exitAt,
        source: "st-options",
        status: trade.status === "open" ? "open" : "closed",
        direction: trade.direction,
      };
    }
    // Legacy spread-shaped rows
    return {
      id: trade.id,
      symbol: trade.sellSymbol || trade.strikeLabel || trade.underlying || "Calendar Spread",
      coin: trade.underlying || "BTC",
      tradeType: trade.mode === "live_order" ? "Live Calendar" : "Forward Calendar",
      quantityCoin: Number(trade.quantity) || 0,
      price: Number(trade.debit) || 0,
      marketPrice: Number(trade.debit) || 0,
      realizedPnlUsd: Number(trade.realizedPnl) || 0,
      fundingCollectedUsd: 0,
      unrealizedPnlUsd: Number(trade.runningPnl) || 0,
      openedAt: trade.entryTime,
      closedAt: trade.exitTime,
      source: "app",
      status: trade.status === "open" ? "open" : "closed",
    };
  });
}

export function formatDuration(ms) {
  if (ms == null || !Number.isFinite(ms)) return "—";
  const hours = Math.floor(ms / 3600000);
  const days = Math.floor(hours / 24);
  if (days > 0) return `${days}d ${hours % 24}h`;
  const minutes = Math.floor((ms % 3600000) / 60000);
  return `${hours}h ${minutes}m`;
}

export function formatPct(value, digits = 2) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "—";
  return `${num.toFixed(digits)}%`;
}

export function formatDateTime(value) {
  if (value == null || value === "") return "—";
  let date;
  if (typeof value === "number" && Number.isFinite(value)) {
    date = new Date(value < 1e12 ? value * 1000 : value);
  } else {
    date = new Date(value);
  }
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("en-IN", {
    timeZone: "Asia/Kolkata",
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function computePortfolioMetrics({ accounts = [], positionsPayload = null, selectedAccountId = "" }) {
  const openPositions = positionsPayload?.openPositions || [];
  const totalPnl = Number(positionsPayload?.openUnrealizedPnlUsd) || openPositions.reduce(
    (sum, row) => sum + (Number(row.unrealizedPnlUsd) || 0),
    0,
  );
  const totalEquity = accounts.reduce((sum, account) => {
    const equity = Number(account.netEquity ?? account.net_equity ?? account.balance);
    return sum + (Number.isFinite(equity) ? equity : 0);
  }, 0);
  const totalNotional = openPositions.reduce((sum, row) => {
    const notional = Math.abs(Number(row.signedSize) || 0) * (Number(row.markPrice) || Number(row.entryPrice) || 0) * (Number(row.contractValue) || 1);
    return sum + (Number.isFinite(notional) ? notional : 0);
  }, 0);
  const activeAccount = accounts.find((account) => account.id === selectedAccountId) || accounts[0] || null;
  return {
    totalPnl,
    totalEquity,
    totalNotional,
    openCount: positionsPayload?.openCount ?? openPositions.length,
    activeAccount,
    availableMargin: readAvailableMargin(activeAccount),
  };
}
