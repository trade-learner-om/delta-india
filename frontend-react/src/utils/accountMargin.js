export function toNumberOrNull(value) {
  if (value === null || value === undefined || value === "") return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

export function readAvailableMargin(account) {
  if (!account) return null;
  const margin = toNumberOrNull(account.available_margin ?? account.availableMargin);
  const netEquity = toNumberOrNull(account.net_equity ?? account.netEquity);
  const roboEquity = toNumberOrNull(account.robo_trading_equity ?? account.roboTradingEquity);
  const accountEquity = [netEquity, roboEquity].filter((value) => value !== null && value > 0);
  const bestEquity = accountEquity.length ? Math.max(...accountEquity) : null;
  if (margin !== null && margin > 0) return margin;
  if (bestEquity !== null) return bestEquity;
  if (margin !== null) return margin;
  return bestEquity;
}

export function readWalletError(account) {
  return account?.wallet_error || account?.walletError || null;
}

export function readAccountCurrency(account, fallback = "USD") {
  return account?.currency_code || account?.currencyCode || fallback;
}

export function formatMargin(value, currency = "USD") {
  const margin = toNumberOrNull(value);
  if (margin === null) return "—";
  return `${margin.toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} ${currency}`;
}
