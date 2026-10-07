export const SESSION_COOKIE = "cryptobridge_session";
const LEGACY_TOKEN_KEY = "cryptobridge.token";

export function nextSaturdayMidnightIst(now = new Date()) {
  const istOffsetMs = (5 * 60 + 30) * 60 * 1000;
  const ist = new Date(now.getTime() + istOffsetMs);
  const daysAhead = (6 - ist.getUTCDay() + 7) % 7;
  const midnightUtc = Date.UTC(ist.getUTCFullYear(), ist.getUTCMonth(), ist.getUTCDate() + daysAhead) - istOffsetMs;
  if (midnightUtc <= now.getTime()) {
    return new Date(midnightUtc + 7 * 24 * 60 * 60 * 1000);
  }
  return new Date(midnightUtc);
}

export function readSessionCookie() {
  if (typeof document === "undefined") return "";
  const row = document.cookie
    .split("; ")
    .find((part) => part.startsWith(`${SESSION_COOKIE}=`));
  if (!row) return "";
  return decodeURIComponent(row.slice(SESSION_COOKIE.length + 1));
}

export function writeSessionCookie(token, expiresAt) {
  if (typeof document === "undefined") return;
  if (!token) {
    document.cookie = `${SESSION_COOKIE}=; Path=/; Max-Age=0; SameSite=Lax`;
    return;
  }
  const expiry = expiresAt ? new Date(expiresAt) : nextSaturdayMidnightIst();
  const when = Number.isNaN(expiry.getTime()) ? nextSaturdayMidnightIst() : expiry;
  document.cookie = `${SESSION_COOKIE}=${encodeURIComponent(token)}; Path=/; Expires=${when.toUTCString()}; SameSite=Lax`;
}

export function clearLegacyToken() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(LEGACY_TOKEN_KEY);
}
