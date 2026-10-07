import { coerceLiveNumber, livePriceFromTick, livePriceKey, recomputeTickDisplayPrice } from "./pricePrecision";

import { toNumberOrNull } from "./accountMargin";

export function hasValidLivePrice(tick) {
  if (!tick || typeof tick !== "object") return false;
  return [tick.price, tick.mark_price, tick.bid, tick.ask].some((value) => {
    const numeric = coerceLiveNumber(value);
    return numeric != null && numeric > 0;
  });
}

function normalizeIncomingTick(tick) {
  if (!tick || typeof tick !== "object") return null;
  const normalized = { ...tick };
  for (const field of ["price", "mark_price", "bid", "ask", "price_digits", "change24h"]) {
    if (!(field in normalized)) continue;
    const numeric = coerceLiveNumber(normalized[field]);
    if (numeric == null) {
      delete normalized[field];
    } else {
      normalized[field] = numeric;
    }
  }
  if (normalized.symbol) {
    normalized.symbol = livePriceKey(normalized.symbol);
  }
  return normalized;
}

/** Merge a partial WS tick onto the previous one — never replace wholesale or pass explicit nulls. */
export function patchLiveTick(previous, incoming) {
  const next = normalizeIncomingTick(incoming);
  if (!next) return previous;

  const merged = previous && hasValidLivePrice(previous) ? { ...previous } : {};
  const symbol = next.symbol || previous?.symbol;
  if (symbol) merged.symbol = symbol;

  for (const field of ["price", "mark_price", "bid", "ask", "price_digits", "change24h"]) {
    if (next[field] == null) continue;
    if (field === "change24h" || field === "price_digits") {
      merged[field] = next[field];
      continue;
    }
    if (next[field] > 0) {
      merged[field] = next[field];
    }
  }

  if (!hasValidLivePrice(merged) && previous && hasValidLivePrice(previous)) {
    return previous;
  }

  const prevTime = Date.parse(previous?.time || "");
  const nextTime = Date.parse(next.time || "");
  const prevTimeMs = Number.isNaN(prevTime) ? 0 : prevTime;
  const nextTimeMs = Number.isNaN(nextTime) ? 0 : nextTime;
  if (next.time && (Number.isNaN(nextTimeMs) || nextTimeMs >= prevTimeMs)) {
    merged.time = next.time;
  } else if (previous?.time && !merged.time) {
    merged.time = previous.time;
  }

  return recomputeTickDisplayPrice(merged);
}

export function mergeLivePrices(previous = {}, incoming = {}) {
  const next = { ...previous };
  Object.entries(incoming || {}).forEach(([symbol, tick]) => {
    const key = livePriceKey(symbol);
    const merged = patchLiveTick(next[key], tick);
    if (!hasValidLivePrice(merged)) return;
    next[key] = merged;
  });
  return next;
}

export function mergeSymbolPriceDigits(previous = {}, livePrices = {}, watchlist = [], resolveInfo = null) {
  const next = { ...previous };
  Object.entries(livePrices || {}).forEach(([symbol, tick]) => {
    if (tick?.price_digits !== null && tick?.price_digits !== undefined) {
      next[livePriceKey(symbol)] = Number(tick.price_digits);
    }
  });
  (watchlist || []).forEach((item) => {
    if (item?.price_digits !== null && item?.price_digits !== undefined) {
      next[livePriceKey(item.symbol)] = Number(item.price_digits);
    }
  });
  if (resolveInfo?.broker_symbol && resolveInfo?.price_digits !== null && resolveInfo?.price_digits !== undefined) {
    next[livePriceKey(resolveInfo.broker_symbol)] = Number(resolveInfo.price_digits);
  }
  return next;
}

export function mergeWatchlistPrices(previous = [], incoming = []) {
  const previousBySymbol = new Map((previous || []).map((item) => [livePriceKey(item.symbol), item]));
  return (incoming || []).map((item) => {
    const symbol = livePriceKey(item.symbol);
    const previousItem = previousBySymbol.get(symbol);
    if (hasValidLivePrice(item) || !previousItem) return item;
    return {
      ...item,
      bid: previousItem.bid,
      ask: previousItem.ask,
      price: previousItem.price,
      time: previousItem.time,
    };
  });
}

export function patchWatchlistPrice(watchlist = [], tick = {}) {
  const symbol = livePriceKey(tick.symbol);
  if (!symbol || !hasValidLivePrice(tick)) {
    return watchlist;
  }
  let updated = false;
  const next = (watchlist || []).map((item) => {
    if (livePriceKey(item.symbol) !== symbol) {
      return item;
    }
    updated = true;
    const displayPrice = livePriceFromTick(tick) ?? tick.price ?? item.price;
    return {
      ...item,
      price: displayPrice,
      mark_price: tick.mark_price ?? item.mark_price,
      bid: tick.bid ?? item.bid,
      ask: tick.ask ?? item.ask,
      time: tick.time ?? item.time,
      change24h: tick.change24h ?? item.change24h,
      price_digits: tick.price_digits ?? item.price_digits,
    };
  });
  return updated ? next : watchlist;
}

export function normalizeAccounts(accounts = []) {
  return accounts.map((account) => ({
    ...account,
    id: account.id,
    account_name: account.account_name || account.accountName,
    accountName: account.accountName || account.account_name,
    risk_amount: account.risk_amount ?? account.riskAmount ?? 100,
    planner_risk_amount:
      account.planner_risk_amount ?? account.plannerRiskAmount ?? null,
    available_margin: toNumberOrNull(account.available_margin ?? account.availableMargin),
    balance: toNumberOrNull(account.balance),
    net_equity: toNumberOrNull(account.net_equity ?? account.netEquity),
    market_type: account.market_type || "INDIAN_CRYPTO",
    broker_type: account.broker_type || "DELTA",
    currency_code: account.currency_code || account.currencyCode || "USD",
  }));
}

export function normalizeMe(me, snapshot) {
  if (!me && !snapshot?.me) return null;
  const base = { ...(snapshot?.me || {}), ...(me || {}) };
  return {
    ...base,
    full_name: base.full_name || base.displayName,
    displayName: base.displayName || base.full_name,
    selected_account_id: base.selected_account_id || base.selectedAccountId || snapshot?.selected_account_id || snapshot?.selectedAccountId,
    accounts: normalizeAccounts(base.accounts || snapshot?.accounts || []),
  };
}

export function patchAccountMargin(accounts = [], marginUpdate = {}) {
  const accountId = marginUpdate.account_id || marginUpdate.accountId;
  if (!accountId) return accounts;
  return accounts.map((account) => {
    if (account.id !== accountId) return account;
    const incomingMargin = toNumberOrNull(marginUpdate.available_margin ?? marginUpdate.availableMargin);
    const existingMargin = toNumberOrNull(account.available_margin ?? account.availableMargin);
    if (
      incomingMargin === 0 &&
      existingMargin > 0 &&
      !(marginUpdate.wallet_error || marginUpdate.walletError)
    ) {
      return account;
    }
    const next = {
      ...account,
      available_margin: toNumberOrNull(marginUpdate.available_margin ?? marginUpdate.availableMargin),
      availableMargin: toNumberOrNull(marginUpdate.available_margin ?? marginUpdate.availableMargin),
      balance: toNumberOrNull(marginUpdate.balance),
      net_equity: toNumberOrNull(marginUpdate.net_equity ?? marginUpdate.netEquity),
      netEquity: toNumberOrNull(marginUpdate.net_equity ?? marginUpdate.netEquity),
      currency_code: marginUpdate.currency_code || marginUpdate.currencyCode || account.currency_code,
      currencyCode: marginUpdate.currency_code || marginUpdate.currencyCode || account.currencyCode,
    };
    if (marginUpdate.wallet_error || marginUpdate.walletError) {
      next.wallet_error = marginUpdate.wallet_error || marginUpdate.walletError;
      next.walletError = next.wallet_error;
    } else {
      delete next.wallet_error;
      delete next.walletError;
    }
    return next;
  });
}
