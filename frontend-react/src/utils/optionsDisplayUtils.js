const IST_TIMEZONE = "Asia/Kolkata";

/** Parse API datetimes; naive ISO strings are treated as UTC (Mongo/BSON convention). */
export function parseApiDateTime(value) {
  if (value == null || value === "") return null;
  if (typeof value === "number" && Number.isFinite(value)) {
    const ms = value < 1e12 ? value * 1000 : value;
    const date = new Date(ms);
    return Number.isNaN(date.getTime()) ? null : date;
  }
  const raw = String(value).trim();
  if (/^\d+$/.test(raw)) {
    const n = Number(raw);
    if (Number.isFinite(n)) {
      const ms = n < 1e12 ? n * 1000 : n;
      const date = new Date(ms);
      return Number.isNaN(date.getTime()) ? null : date;
    }
  }
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(raw) && !/(?:Z|[+-]\d{2}:\d{2})$/i.test(raw)) {
    const date = new Date(`${raw}Z`);
    return Number.isNaN(date.getTime()) ? null : date;
  }
  const date = new Date(raw);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatDateTime(value) {
  const date = parseApiDateTime(value);
  if (!date) return value ? String(value) : "—";
  return date.toLocaleString("en-IN", {
    timeZone: IST_TIMEZONE,
    day: "2-digit",
    month: "short",
    year: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  });
}

/** Compact IST clock for activity feeds (HH:mm:ss). */
export function formatTimeIst(value) {
  const date = parseApiDateTime(value);
  if (!date) return "—";
  return date.toLocaleTimeString("en-IN", {
    timeZone: IST_TIMEZONE,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

export function formatDateLabel(value) {
  if (!value) return "—";
  const date = parseApiDateTime(value) || new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleDateString("en-IN", {
    timeZone: IST_TIMEZONE,
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
  });
}

export const EXPIRY_OPTIONS = [
  { value: "next_day", label: "Next day" },
  { value: "plus_2_day", label: "+2 day" },
  { value: "weekly", label: "Weekly" },
  { value: "monthly", label: "Monthly" },
  { value: "next_month", label: "Next month" },
];

export function moneynessLabel(value) {
  if (value === "ATM") return "ATM";
  return value.replace("_", " ");
}
