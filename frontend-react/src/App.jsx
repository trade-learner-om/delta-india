import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  openLiveSocket,
  WS_LIVE_STALE_MS,
  isAuthFailureMessage,
  isLiveSocketAuthFailure,
} from "./api";
import DeskShell from "./components/desk/DeskShell";
import AuthPanel from "./components/workspace/AuthPanel";
import WorkspaceToast from "./components/workspace/WorkspaceToast";
import {
  mergeLivePrices,
  normalizeAccounts,
  normalizeMe,
  patchAccountMargin,
} from "./utils/liveMerge";
import { livePriceKey } from "./utils/pricePrecision";
import { resolveDocumentTitle } from "./utils/documentTitle";
import { clearLegacyToken, readSessionCookie, writeSessionCookie } from "./utils/token";

const EMPTY_TERMINAL = { watchList: [], fsmEngines: [] };

function loadToken() {
  clearLegacyToken();
  return readSessionCookie();
}

function saveToken(token, expiresAt) {
  clearLegacyToken();
  writeSessionCookie(token, expiresAt);
}

function buildWatchList(livePrices, positionsPayload) {
  const symbols = new Set();
  Object.keys(livePrices || {}).forEach((symbol) => {
    if (symbol) symbols.add(symbol);
  });
  (positionsPayload?.openPositions || []).forEach((row) => {
    const symbol = row?.symbol || row?.productSymbol;
    if (symbol) symbols.add(symbol);
  });
  return Array.from(symbols).sort();
}

function buildFsmEngines(positionsPayload) {
  return (positionsPayload?.openPositions || []).map((row) => ({
    id: row.id || row.positionId || row.symbol,
    symbol: row.symbol || row.productSymbol,
    side: row.side || row.direction,
    size: row.size ?? row.quantity,
    status: row.status || "open",
  }));
}

export default function App() {
  const [token, setToken] = useState(() => loadToken());
  const [mode, setMode] = useState("login");
  const [authForm, setAuthForm] = useState({ displayName: "", email: "", password: "" });
  const [me, setMe] = useState(null);
  const [accounts, setAccounts] = useState([]);
  const [livePrices, setLivePrices] = useState({});
  const [terminal, setTerminal] = useState(EMPTY_TERMINAL);
  const [positionsPayload, setPositionsPayload] = useState(null);
  const [executionMonitors, setExecutionMonitors] = useState([]);
  const [stOptionsSession, setStOptionsSession] = useState(null);
  const [cascadeStarSession, setCascadeStarSession] = useState(null);
  const [currentPage, setCurrentPage] = useState("dashboard");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [toast, setToast] = useState(null);
  const [pending, setPending] = useState(false);
  const [switchingAccount, setSwitchingAccount] = useState(false);
  const [liveStatus, setLiveStatus] = useState("disconnected");
  const socketRef = useRef(null);
  const reconnectTimerRef = useRef(null);
  const reconnectAttemptsRef = useRef(0);
  const lastLiveDataAtRef = useRef(0);
  const staleWatchdogRef = useRef(null);
  const intentionalCloseRef = useRef(false);

  const selectedAccountId = me?.selected_account_id || me?.selectedAccountId || "";

  const notify = useCallback((type, text) => {
    setToast({ type, text });
    window.setTimeout(() => setToast(null), 4000);
  }, []);

  const closeLiveSocket = useCallback(() => {
    intentionalCloseRef.current = true;
    if (reconnectTimerRef.current) {
      window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    const socket = socketRef.current;
    socketRef.current = null;
    socket?.close();
  }, []);

  const clearSession = useCallback((logoutMessage) => {
    closeLiveSocket();
    saveToken("");
    setToken("");
    setMe(null);
    setAccounts([]);
    setLivePrices({});
    setPositionsPayload(null);
    setExecutionMonitors([]);
    setStOptionsSession(null);
    setTerminal(EMPTY_TERMINAL);
    setLiveStatus("disconnected");
    if (logoutMessage) setMessage(logoutMessage);
  }, [closeLiveSocket]);

  const refreshBootstrap = useCallback(async (activeToken) => {
    if (!activeToken) return;
    const [meData, accountsData] = await Promise.all([
      api("/auth/me", { token: activeToken }),
      api("/accounts", { token: activeToken }),
    ]);
    setMe(normalizeMe(meData));
    setAccounts(normalizeAccounts(accountsData.accounts || []));
  }, []);

  const applySnapshot = useCallback((payload) => {
    if (payload.me) setMe(normalizeMe(payload.me));
    if (payload.accounts) setAccounts(normalizeAccounts(payload.accounts));
    if (payload.prices) {
      setLivePrices((current) => mergeLivePrices(current, payload.prices));
    }
    if (payload.live?.marketSocketConnected) {
      setLiveStatus("connected");
      lastLiveDataAtRef.current = Date.now();
    }
  }, []);

  const applyLiveMessage = useCallback((payload) => {
    if (!payload || typeof payload !== "object") return;
    if (payload.type === "snapshot") {
      applySnapshot(payload);
      return;
    }
    if (payload.type === "positions") {
      setPositionsPayload(payload);
      lastLiveDataAtRef.current = Date.now();
      return;
    }
    if (payload.type === "execution_monitor" || payload.topic === "execution") {
      if (Array.isArray(payload.monitors)) {
        setExecutionMonitors(payload.monitors);
      } else if (payload.monitor) {
        setExecutionMonitors((current) => {
          const next = [...(current || [])];
          const index = next.findIndex((row) => row.id === payload.monitor.id);
          if (index >= 0) next[index] = payload.monitor;
          else next.unshift(payload.monitor);
          return next;
        });
      }
      lastLiveDataAtRef.current = Date.now();
      return;
    }
    if (payload.type === "st_options_session" || payload.topic === "st_options") {
      setStOptionsSession((current) => {
        const incomingUpdated = payload.config?.updatedAt
          ? Date.parse(payload.config.updatedAt)
          : NaN;
        const currentUpdated = current?.config?.updatedAt
          ? Date.parse(current.config.updatedAt)
          : NaN;
        const hasIncomingStamp = Number.isFinite(incomingUpdated);
        const hasCurrentStamp = Number.isFinite(currentUpdated);

        // Unstamped WS (e.g. backtest-only) must not overwrite a stamped session.
        if (!hasIncomingStamp && hasCurrentStamp) {
          return {
            ...(current || {}),
            backtestJob:
              payload.backtestJob !== undefined ? payload.backtestJob : current?.backtestJob,
          };
        }

        const preferIncoming =
          !hasCurrentStamp
          || !hasIncomingStamp
          || incomingUpdated >= currentUpdated;

        if (!preferIncoming) {
          // Older config stamp must not resurrect enabled/active, but still allow
          // a same-tick active refresh when the payload carries open trades with
          // newer hedge fields and config stamp is missing on the merge path.
          const incomingActive = Object.prototype.hasOwnProperty.call(payload, "active")
            ? payload.active
            : null;
          const keepActive =
            Array.isArray(incomingActive)
            && incomingActive.some((t) => t && (t.hedgeStatus === "open" || t.hedgeSymbol))
            && !(current?.active || []).some((t) => t && (t.hedgeStatus === "open" || t.hedgeSymbol));
          return {
            ...(current || {}),
            active: keepActive ? incomingActive : current?.active,
            backtestJob:
              payload.backtestJob !== undefined ? payload.backtestJob : current?.backtestJob,
          };
        }

        return {
          ...(current || {}),
          ...payload,
          config: payload.config ?? current?.config,
          active: Object.prototype.hasOwnProperty.call(payload, "active")
            ? payload.active
            : current?.active,
          indicator: Object.prototype.hasOwnProperty.call(payload, "indicator")
            ? payload.indicator
            : current?.indicator,
          status: Object.prototype.hasOwnProperty.call(payload, "status")
            ? payload.status
            : current?.status,
          backtestJob:
            payload.backtestJob !== undefined ? payload.backtestJob : current?.backtestJob,
        };
      });
      lastLiveDataAtRef.current = Date.now();
      return;
    }
    if ((payload.topic === "price" || payload.type === "price") && payload.tick) {
      const symbol = livePriceKey(payload.symbol || payload.tick.symbol);
      setLivePrices((current) => mergeLivePrices(current, { [symbol]: payload.tick }));
      lastLiveDataAtRef.current = Date.now();
      return;
    }
    if (payload.type === "margin") {
      setAccounts((current) => patchAccountMargin(current, payload));
      lastLiveDataAtRef.current = Date.now();
    }
  }, [applySnapshot]);

  useEffect(() => {
    if (!token) return undefined;
    let cancelled = false;
    api("/execution/monitors", { token })
      .then((data) => {
        if (!cancelled) setExecutionMonitors(data.monitors || []);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [token]);

  useEffect(() => {
    setTerminal({
      watchList: buildWatchList(livePrices, positionsPayload),
      fsmEngines: buildFsmEngines(positionsPayload),
    });
  }, [livePrices, positionsPayload]);

  useEffect(() => {
    document.title = resolveDocumentTitle({
      positionsPayload,
      livePrices,
      authenticated: Boolean(token),
    });
  }, [token, positionsPayload, livePrices]);

  useEffect(() => {
    if (!token) return undefined;
    let cancelled = false;
    refreshBootstrap(token).catch((err) => {
      if (!cancelled && isAuthFailureMessage(err.message)) clearSession("Session expired. Please sign in again.");
    });
    return () => { cancelled = true; };
  }, [token, refreshBootstrap, clearSession]);

  useEffect(() => {
    if (!token) return undefined;
    let stopped = false;

    const markLive = () => {
      lastLiveDataAtRef.current = Date.now();
    };

    const connect = () => {
      if (stopped) return;
      if (reconnectTimerRef.current) {
        window.clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      if (socketRef.current) {
        intentionalCloseRef.current = true;
        const previous = socketRef.current;
        socketRef.current = null;
        previous.close();
      }
      intentionalCloseRef.current = false;
      setLiveStatus(reconnectAttemptsRef.current > 0 ? "reconnecting" : "disconnected");
      const socket = openLiveSocket(token, {
        onOpen: () => {
          if (stopped || socketRef.current !== socket) return;
          reconnectAttemptsRef.current = 0;
          markLive();
          setLiveStatus("connected");
        },
        onMessage: (payload) => {
          if (stopped || socketRef.current !== socket) return;
          markLive();
          applyLiveMessage(payload);
        },
        onActivity: () => {
          if (stopped || socketRef.current !== socket) return;
          markLive();
        },
        onClose: (event) => {
          if (stopped) return;
          if (intentionalCloseRef.current) {
            intentionalCloseRef.current = false;
            return;
          }
          if (socketRef.current !== socket) return;
          socketRef.current = null;
          setLiveStatus("disconnected");
          if (isLiveSocketAuthFailure(event)) {
            clearSession("Session expired. Please sign in again.");
            return;
          }
          const delay = Math.min(30000, 1000 * 2 ** reconnectAttemptsRef.current);
          reconnectAttemptsRef.current += 1;
          reconnectTimerRef.current = window.setTimeout(connect, delay);
        },
        onError: () => {
          if (stopped || socketRef.current !== socket) return;
          setLiveStatus("disconnected");
        },
      });
      socketRef.current = socket;
    };

    connect();
    staleWatchdogRef.current = window.setInterval(() => {
      if (stopped) return;
      if (!lastLiveDataAtRef.current) return;
      if (Date.now() - lastLiveDataAtRef.current > WS_LIVE_STALE_MS) {
        intentionalCloseRef.current = false;
        socketRef.current?.close();
      }
    }, 5000);

    return () => {
      stopped = true;
      if (reconnectTimerRef.current) {
        window.clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      if (staleWatchdogRef.current) {
        window.clearInterval(staleWatchdogRef.current);
        staleWatchdogRef.current = null;
      }
      intentionalCloseRef.current = true;
      const socket = socketRef.current;
      socketRef.current = null;
      socket?.close();
    };
  }, [token, applyLiveMessage, clearSession]);

  const handleAuth = async () => {
    setPending(true);
    setMessage("");
    try {
      const path = mode === "login" ? "/auth/login" : "/auth/register";
      const body = mode === "login"
        ? { email: authForm.email, password: authForm.password }
        : { email: authForm.email, password: authForm.password, displayName: authForm.displayName };
      const data = await api(path, { method: "POST", body });
      saveToken(data.token, data.expiresAt);
      setToken(data.token);
      setMe(normalizeMe(data.user || data.me));
      await refreshBootstrap(data.token);
    } catch (err) {
      setMessage(err.message || "Authentication failed.");
    } finally {
      setPending(false);
    }
  };

  const handleLogout = async () => {
    try {
      if (token) await api("/auth/logout", { method: "POST", token });
    } catch {
      // ignore
    }
    clearSession();
  };

  const handleAccountChange = async (accountId) => {
    if (!token || !accountId) return;
    setSwitchingAccount(true);
    try {
      await api("/accounts/select", { method: "POST", token, body: { accountId } });
      setMe((current) => ({ ...current, selected_account_id: accountId, selectedAccountId: accountId }));
      await refreshBootstrap(token);
    } catch (err) {
      notify("error", err.message || "Could not switch account.");
    } finally {
      setSwitchingAccount(false);
    }
  };

  const handleAddAccount = async (form) => {
    if (!token) return;
    await api("/accounts", {
      method: "POST",
      token,
      body: {
        accountName: form.accountName,
        apiKey: form.apiKey,
        apiSecret: form.apiSecret,
        exchange: form.exchange || "delta",
      },
    });
    notify("success", "Account added.");
    await refreshBootstrap(token);
  };

  const handleDeleteAccount = async (accountId) => {
    if (!token) return;
    await api(`/accounts/${accountId}`, { method: "DELETE", token });
    notify("success", "Account removed.");
    await refreshBootstrap(token);
  };

  if (!token) {
    return (
      <AuthPanel
        mode={mode}
        setMode={setMode}
        form={authForm}
        setForm={setAuthForm}
        onSubmit={handleAuth}
        pending={pending}
        message={message}
      />
    );
  }

  return (
    <>
      <WorkspaceToast message={toast?.text} type={toast?.type} />
      <DeskShell
        token={token}
        me={me}
        livePrices={livePrices}
        liveStatus={liveStatus}
        positionsPayload={positionsPayload}
        onLogout={handleLogout}
        onNotify={notify}
        onSessionRefresh={() => refreshBootstrap(token)}
      />
    </>
  );
}
