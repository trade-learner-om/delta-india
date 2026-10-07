export function money(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  const sign = number > 0 ? "+" : number < 0 ? "-" : "";
  const amount = Math.abs(number).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return `${sign}$${amount}`;
}

export function pnlClass(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || number === 0) return "text-[#9a958c]";
  return number > 0 ? "text-[#7d9a84]" : "text-[#c48b84]";
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
    .filter((entry) => entry.venue === venue && entry.exitTimeIst)
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
