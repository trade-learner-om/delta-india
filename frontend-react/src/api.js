import {
  LOCAL_API_BASE,
  LOCAL_WS_BASE,
  PRODUCTION_API_BASE,
  PRODUCTION_WS_BASE,
} from "./config/endpoints";

const PRODUCTION_APP_HOSTS = new Set([
  "crypto.signalbridge.in",
]);

function resolveApiBase() {
  if (typeof window !== "undefined") {
    const hostname = window.location.hostname;
    if (PRODUCTION_APP_HOSTS.has(hostname)) {
      return PRODUCTION_API_BASE;
    }
    if (window.location.protocol === "http:") {
      return `${window.location.origin}/api`;
    }
    if (window.location.protocol === "https:") {
      const configuredHttps = String(import.meta.env.VITE_API_BASE || "").trim();
      if (configuredHttps && !configuredHttps.includes("localhost")) {
        return configuredHttps.replace(/\/$/, "");
      }
      return PRODUCTION_API_BASE;
    }
  }

  const configured = import.meta.env.VITE_API_BASE;
  if (configured) {
    return String(configured).replace(/\/$/, "");
  }
  return PRODUCTION_API_BASE;
}

function resolveWsBase(apiBase) {
  if (typeof window !== "undefined" && PRODUCTION_APP_HOSTS.has(window.location.hostname)) {
    return PRODUCTION_WS_BASE;
  }
  if (typeof window !== "undefined" && window.location.protocol === "http:") {
    return window.location.origin;
  }
  const configured = import.meta.env.VITE_WS_BASE;
  if (configured) {
    const value = String(configured).replace(/\/$/, "");
    if (typeof window !== "undefined" && window.location.protocol === "https:" && value.startsWith("http://localhost")) {
      return PRODUCTION_WS_BASE;
    }
    return value;
  }
  if (apiBase === LOCAL_API_BASE || apiBase.startsWith("http://localhost:") || apiBase.startsWith("http://127.0.0.1:")) {
    return LOCAL_WS_BASE;
  }
  return PRODUCTION_WS_BASE;
}

function toWebSocketUrl(baseUrl) {
  const url = new URL(baseUrl);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString().replace(/\/$/, "");
}

export const API_BASE = resolveApiBase();
export const WS_BASE = resolveWsBase(API_BASE);
export const WS_LIVE_HEARTBEAT_MS = 20000;
export const WS_LIVE_STALE_MS = 45000;

export function isAuthFailureMessage(message) {
  const text = String(message || "").toLowerCase();
  return (
    text.includes("invalid session")
    || text.includes("session expired")
    || text.includes("missing token")
  );
}

export function isLiveSocketAuthFailure(event) {
  return event?.code === 1008;
}

function liveTickTimeMs(tick) {
  const candidates = [tick?.time, tick?.updated_at, tick?.last_tick_at, tick?.price_time];
  for (const value of candidates) {
    const parsed = Date.parse(value || "");
    if (!Number.isNaN(parsed)) return parsed;
  }
  return NaN;
}

export function liveSnapshotHasFreshPrices(payload, staleMs = WS_LIVE_STALE_MS) {
  if (!payload || typeof payload !== "object") return false;
  if (String(payload.type || "").toLowerCase() === "price" && payload.tick) return true;
  const now = Date.now();
  const prices = payload.prices || {};
  for (const tick of Object.values(prices)) {
    const time = liveTickTimeMs(tick);
    if (!Number.isNaN(time) && now - time < staleMs) return true;
  }
  for (const item of payload.watchlist || []) {
    const time = liveTickTimeMs(item);
    if (!Number.isNaN(time) && now - time < staleMs) return true;
  }
  return false;
}

function authHeaders(token, withJson = false) {
  return {
    ...(withJson ? { "Content-Type": "application/json" } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

async function parseResponse(response) {
  const text = await response.text();
  let payload = null;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch {
    payload = text || null;
  }
  if (!response.ok) {
    const detail =
      payload?.detail ||
      payload?.message ||
      payload?.error ||
      (typeof payload === "string" ? payload : `Request failed with HTTP ${response.status}`);
    throw new Error(typeof detail === "string" ? detail : `Request failed with HTTP ${response.status}`);
  }
  return payload;
}

export async function api(path, methodOrOptions = "GET", body, token) {
  const request = async (method, requestBody, requestToken) => {
    let response;
    try {
      response = await fetch(`${API_BASE}${path}`, {
        method,
        headers: authHeaders(requestToken, requestBody !== undefined),
        body: requestBody !== undefined ? JSON.stringify(requestBody) : undefined,
      });
    } catch (error) {
      if (error instanceof TypeError) {
        throw new Error(
          "Network request failed. Check your connection and try again."
        );
      }
      throw error;
    }
    return parseResponse(response);
  };

  if (typeof methodOrOptions === "object") {
    const { method = "GET", body: requestBody, token: requestToken } = methodOrOptions;
    return request(method, requestBody, requestToken);
  }

  return request(methodOrOptions, body, token);
}

export async function apiBlob(path, token) {
  const response = await fetch(`${API_BASE}${path}`, { headers: authHeaders(token) });
  if (!response.ok) {
    throw new Error(`Request failed with HTTP ${response.status}`);
  }
  return response.blob();
}

export async function apiUpload(path, token, file) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      "Content-Type": file.type || "application/octet-stream",
    },
    body: file,
  });
  return parseResponse(response);
}

export function openLiveSocket(token, handlers = {}) {
  const onMessage = typeof handlers === "function" ? handlers : handlers.onMessage;
  const onActivity = typeof handlers === "function" ? undefined : handlers.onActivity;
  const socket = new WebSocket(`${toWebSocketUrl(WS_BASE)}/ws/live?token=${encodeURIComponent(token)}`);
  let heartbeatTimer = null;

  const stopHeartbeat = () => {
    if (heartbeatTimer) {
      window.clearInterval(heartbeatTimer);
      heartbeatTimer = null;
    }
  };

  const startHeartbeat = () => {
    stopHeartbeat();
    heartbeatTimer = window.setInterval(() => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "ping" }));
      }
    }, WS_LIVE_HEARTBEAT_MS);
  };

  const noteActivity = () => {
    onActivity?.();
  };

  socket.addEventListener("open", () => {
    startHeartbeat();
    noteActivity();
    handlers.onOpen?.();
  });
  socket.addEventListener("close", (event) => {
    stopHeartbeat();
    handlers.onClose?.(event);
  });
  socket.addEventListener("error", (event) => {
    handlers.onError?.(event);
  });
  socket.addEventListener("message", (event) => {
    noteActivity();
    try {
      const payload = JSON.parse(event.data);
      if (payload?.type === "ping") {
        if (socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ type: "pong" }));
        }
        return;
      }
      if (payload?.type === "pong") return;
      onMessage?.(payload);
    } catch {
      // ignore malformed payloads
    }
  });

  socket.stopHeartbeat = stopHeartbeat;
  socket.sendPing = () => {
    if (socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: "ping" }));
    }
  };

  return socket;
}
