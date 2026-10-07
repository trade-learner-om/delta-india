export const ledgerPanel = "rounded-2xl border border-[var(--ledger-border)] bg-[var(--ledger-surface)] text-[var(--ledger-text)]";
export const ledgerField = "w-full rounded-lg border border-[var(--ledger-border)] bg-[var(--ledger-canvas)] px-3 py-2 text-sm text-[var(--ledger-text)] outline-none focus:border-[var(--ledger-accent)]";
export const ledgerMuted = "text-[var(--ledger-muted)]";

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 });

export function money(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  const sign = number > 0 ? "+" : number < 0 ? "-" : "";
  return `${sign}${usd.format(Math.abs(number))}`;
}

export function formatPrice(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  const digits = Math.abs(number) >= 100 ? 2 : 5;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: digits,
  }).format(number);
}

export function formatPercent(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return null;
  const sign = number > 0 ? "+" : "";
  return `${sign}${number.toFixed(1)}%`;
}

export function seriesChangePercent(values) {
  if (!values || values.length < 2) return null;
  const first = Number(values[0]);
  const last = Number(values[values.length - 1]);
  if (!Number.isFinite(first) || !Number.isFinite(last) || first === 0) return null;
  return ((last - first) / Math.abs(first)) * 100;
}

export function realizedRr(side, entry, stop, exitPrice) {
  const entryValue = Number(entry);
  const stopValue = Number(stop);
  const exitValue = Number(exitPrice);
  if (![entryValue, stopValue, exitValue].every((item) => Number.isFinite(item) && item > 0)) return null;
  const sell = ["SELL", "SHORT"].includes(String(side).toUpperCase());
  const risk = sell ? stopValue - entryValue : entryValue - stopValue;
  const reward = sell ? entryValue - exitValue : exitValue - entryValue;
  if (risk <= 0) return null;
  return reward / risk;
}

export function formatRealizedR(ratio) {
  if (ratio == null || ratio === "") return "—";
  const number = Number(ratio);
  if (!Number.isFinite(number)) return "—";
  const sign = number > 0 ? "+" : "";
  return `${sign}${number.toFixed(2)}R`;
}

export function roundToStep(price, step = 0.05) {
  const number = Number(price);
  if (!Number.isFinite(number) || number <= 0) return null;
  return Number((Math.round(number / step) * step).toFixed(2));
}

export function targetPriceFromR(side, entry, stop, multiple) {
  const entryValue = Number(entry);
  const stopValue = Number(stop);
  const rewardMultiple = Number(multiple);
  if (![entryValue, stopValue, rewardMultiple].every((item) => Number.isFinite(item) && item > 0)) return null;
  const distance = Math.abs(entryValue - stopValue);
  if (distance <= 0) return null;
  const sell = ["SELL", "SHORT"].includes(String(side).toUpperCase());
  const raw = sell ? entryValue - rewardMultiple * distance : entryValue + rewardMultiple * distance;
  if (raw <= 0) return null;
  return roundToStep(raw);
}

export function rewardRisk(side, entry, stop, target) {
  const entryValue = Number(entry);
  const stopValue = Number(stop);
  const targetValue = Number(target);
  if (![entryValue, stopValue, targetValue].every((item) => Number.isFinite(item) && item > 0)) return null;
  const risk = String(side).toUpperCase() === "SELL" ? stopValue - entryValue : entryValue - stopValue;
  const reward = String(side).toUpperCase() === "SELL" ? entryValue - targetValue : targetValue - entryValue;
  if (risk <= 0 || reward <= 0) return null;
  return reward / risk;
}

export function formatRr(ratio) {
  if (ratio == null || ratio === "") return "—";
  const number = Number(ratio);
  if (!Number.isFinite(number)) return "—";
  return `1:${number.toFixed(1)}`;
}

export function pnlClass(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || number === 0) return ledgerMuted;
  return number > 0 ? "text-[var(--ledger-profit)]" : "text-[var(--ledger-loss)]";
}

export function pnlPill(value) {
  const number = Number(value);
  const base = "inline-flex rounded px-2 py-0.5 text-xs font-medium";
  if (!Number.isFinite(number) || number === 0) return `${base} bg-slate-500/10 ${ledgerMuted}`;
  if (number > 0) return `${base} bg-emerald-500/10 text-[var(--ledger-profit)]`;
  return `${base} bg-rose-500/10 text-[var(--ledger-loss)]`;
}

export function journalStats(entries) {
  const rows = entries || [];
  const wins = rows.filter((entry) => Number(entry.netPnl) > 0);
  const losses = rows.filter((entry) => Number(entry.netPnl) < 0);
  const won = wins.reduce((total, entry) => total + Number(entry.netPnl || 0), 0);
  const lost = losses.reduce((total, entry) => total + Math.abs(Number(entry.netPnl || 0)), 0);
  return {
    winRate: rows.length ? (wins.length / rows.length) * 100 : null,
    total: rows.reduce((sum, entry) => sum + Number(entry.netPnl || 0), 0),
    profitFactor: lost > 0 ? won / lost : null,
    trades: rows.length,
  };
}

export function formatIst(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata",
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function istDayKey(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

export function monthGroups(entries) {
  const totals = new Map();
  entries.forEach((entry) => {
    const key = istDayKey(entry.exitTimeIst);
    if (!key) return;
    totals.set(key, (totals.get(key) || 0) + Number(entry.netPnl || 0));
  });
  const months = new Map();
  totals.forEach((net, key) => {
    const [year, month] = key.split("-");
    const id = `${year}-${month}`;
    if (!months.has(id)) {
      const label = new Date(`${id}-01T00:00:00+05:30`).toLocaleDateString("en-IN", {
        month: "short",
        year: "numeric",
        timeZone: "Asia/Kolkata",
      });
      months.set(id, { id, label, days: [] });
    }
    months.get(id).days.push({ key, net });
  });
  return Array.from(months.values())
    .sort((a, b) => b.id.localeCompare(a.id))
    .map((month) => ({ ...month, days: month.days.sort((a, b) => a.key.localeCompare(b.key)) }));
}

export function cumulativeSeries(entries, venue) {
  const rows = entries
    .filter((entry) => entry.exitTimeIst && (!venue || entry.venue === venue))
    .slice()
    .sort((a, b) => String(a.exitTimeIst).localeCompare(String(b.exitTimeIst)));
  let running = 0;
  return rows.map((entry) => {
    running += Number(entry.netPnl || 0);
    return running;
  });
}

export function sumVenue(entries, venue) {
  return entries
    .filter((entry) => !venue || entry.venue === venue)
    .reduce((total, entry) => total + Number(entry.netPnl || 0), 0);
}
