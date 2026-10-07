import { useCallback, useEffect, useState } from "react";
import { api } from "../../api";
import WorkspaceCard from "../ui/WorkspaceCard";
import WorkspaceProgressBar from "../ui/WorkspaceProgressBar";
import { WorkspaceField, WorkspaceInput, WorkspaceSelect } from "../ui/WorkspaceField";
import WorkspaceSubTabs from "../ui/WorkspaceSubTabs";
import {
  dangerButton,
  pageShell,
  pageTitleRow,
  primaryButton,
  secondaryButton,
  textHeading,
  textMuted,
} from "../../utils/workspace/workspaceClasses";

const TABS = [
  { id: "live", label: "Live" },
  { id: "history", label: "History" },
  { id: "backtest", label: "Backtest" },
];

const DEFAULT_FORM = {
  symbols: ["BTCUSD", "ETHUSD"],
  direction: "SHORT",
  maxRisk: "100",
  sizingMode: "max_risk",
  lots: "1",
  chopLength: "14",
  chopMax: "61.8",
  targetR: "3.3",
  sessionStart: "15:30",
  sessionEnd: "23:00",
};

function formFromConfig(config) {
  if (!config) return { ...DEFAULT_FORM, symbols: [...DEFAULT_FORM.symbols] };
  return {
    symbols: Array.isArray(config.symbols) && config.symbols.length ? config.symbols : [...DEFAULT_FORM.symbols],
    direction: config.direction || "SHORT",
    maxRisk: String(config.maxRisk ?? 100),
    sizingMode: config.sizingMode || "max_risk",
    lots: String(config.lots ?? 1),
    chopLength: String(config.chopLength ?? 14),
    chopMax: String(config.chopMax ?? 61.8),
    targetR: String(config.targetR ?? 3.3),
    sessionStart: config.sessionStart || "15:30",
    sessionEnd: config.sessionEnd || "23:00",
  };
}

function bodyFromForm(form) {
  return {
    symbols: form.symbols,
    direction: form.direction,
    maxRisk: Number(form.maxRisk),
    sizingMode: form.sizingMode,
    lots: Number(form.lots),
    chopLength: Number(form.chopLength),
    chopMax: Number(form.chopMax),
    targetR: Number(form.targetR),
    sessionStart: form.sessionStart,
    sessionEnd: form.sessionEnd,
  };
}

function istToday() {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

function daysAgoIst(days) {
  const today = istToday();
  const [year, month, day] = today.split("-").map(Number);
  const utc = Date.UTC(year, month - 1, day, 6, 30) - days * 24 * 60 * 60 * 1000;
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(utc));
}

function formatMoney(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  return number.toFixed(2);
}

function formatBar(unix) {
  if (!unix) return "—";
  return new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata",
    hour: "2-digit",
    minute: "2-digit",
    day: "2-digit",
    month: "short",
  }).format(new Date(Number(unix) * 1000));
}

export default function CascadeStarPage({ token, onNotify, onSession }) {
  const [tab, setTab] = useState("live");
  const [form, setForm] = useState(DEFAULT_FORM);
  const [enabled, setEnabled] = useState(false);
  const [active, setActive] = useState([]);
  const [scans, setScans] = useState({});
  const [activity, setActivity] = useState([]);
  const [history, setHistory] = useState([]);
  const [pending, setPending] = useState(false);
  const [fromDate, setFromDate] = useState(() => daysAgoIst(7));
  const [toDate, setToDate] = useState(() => istToday());
  const [backtestSymbol, setBacktestSymbol] = useState("BTCUSD");
  const [job, setJob] = useState(null);
  const [runs, setRuns] = useState([]);
  const [result, setResult] = useState(null);

  const applyLive = useCallback((data) => {
    if (!data) return;
    setEnabled(Boolean(data.config?.enabled));
    setActive(data.active || []);
    setScans(data.scans || {});
    setActivity(data.activity || []);
    onSession?.(data);
  }, [onSession]);

  const loadLive = useCallback(async ({ syncForm = false } = {}) => {
    const data = await api("/cascade-star/live", { token });
    applyLive(data);
    if (syncForm && data?.config) setForm(formFromConfig(data.config));
    return data;
  }, [applyLive, token]);

  const loadHistory = useCallback(async () => {
    const data = await api("/cascade-star/history?limit=50", { token });
    setHistory(data?.trades || []);
  }, [token]);

  useEffect(() => {
    let cancelled = false;
    loadLive({ syncForm: true }).catch((error) => {
      if (!cancelled) onNotify?.("error", error.message || "Could not load Cascade Star.");
    });
    return () => {
      cancelled = true;
    };
  }, [loadLive, onNotify]);

  useEffect(() => {
    if (!enabled) return undefined;
    const timer = setInterval(() => {
      loadLive().catch(() => {});
    }, 5000);
    return () => clearInterval(timer);
  }, [enabled, loadLive]);

  useEffect(() => {
    if (tab !== "history") return undefined;
    loadHistory().catch((error) => onNotify?.("error", error.message || "Could not load history."));
    return undefined;
  }, [tab, loadHistory, onNotify]);

  const loadRuns = useCallback(async () => {
    const data = await api("/cascade-star/backtest/runs", { token });
    setRuns(data?.runs || []);
  }, [token]);

  useEffect(() => {
    if (tab !== "backtest") return undefined;
    loadRuns().catch((error) => onNotify?.("error", error.message || "Could not load backtests."));
    api("/cascade-star/backtest/job", { token })
      .then((data) => {
        if (data?.job) setJob(data.job);
        if (data?.job?.result) setResult(data.job.result);
      })
      .catch(() => {});
    return undefined;
  }, [tab, loadRuns, onNotify, token]);

  useEffect(() => {
    if (job?.status !== "processing") return undefined;
    const timer = setInterval(() => {
      api("/cascade-star/backtest/job", { token })
        .then((data) => {
          const next = data?.job;
          if (!next) return;
          setJob(next);
          if (next.result) setResult(next.result);
          if (next.status === "completed") loadRuns().catch(() => {});
          if (next.status === "failed") onNotify?.("error", next.error || "Backtest failed.");
        })
        .catch(() => {});
    }, 1000);
    return () => clearInterval(timer);
  }, [job?.status, loadRuns, onNotify, token]);

  function updateField(key, value) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function toggleSymbol(symbol) {
    setForm((current) => {
      const has = current.symbols.includes(symbol);
      const symbols = has ? current.symbols.filter((item) => item !== symbol) : [...current.symbols, symbol];
      return { ...current, symbols };
    });
  }

  async function handleStartStop() {
    setPending(true);
    try {
      const data = enabled
        ? await api("/cascade-star/stop", { method: "POST", token })
        : await api("/cascade-star/start", { method: "POST", token, body: bodyFromForm(form) });
      applyLive(data);
      if (data?.config) setForm(formFromConfig(data.config));
      onNotify?.("success", enabled ? "Cascade Star stopped." : "Cascade Star started.");
    } catch (error) {
      onNotify?.("error", error.message || "Could not update Cascade Star.");
    } finally {
      setPending(false);
    }
  }

  async function handleSave() {
    setPending(true);
    try {
      const data = await api("/cascade-star/config", { method: "PATCH", token, body: bodyFromForm(form) });
      if (data?.config) setForm(formFromConfig(data.config));
      onNotify?.("success", "Cascade Star settings saved.");
    } catch (error) {
      onNotify?.("error", error.message || "Could not save settings.");
    } finally {
      setPending(false);
    }
  }

  async function handleRunBacktest() {
    setPending(true);
    setResult(null);
    try {
      const data = await api("/cascade-star/backtest", {
        method: "POST",
        token,
        body: {
          ...bodyFromForm(form),
          symbol: backtestSymbol,
          from: fromDate,
          to: toDate,
        },
      });
      setJob(data?.job || { status: "processing", progress: 0 });
    } catch (error) {
      onNotify?.("error", error.message || "Could not start the backtest.");
    } finally {
      setPending(false);
    }
  }

  async function openRun(runId) {
    try {
      const data = await api(`/cascade-star/backtest/runs/${runId}`, { token });
      setResult(data?.run?.result || null);
    } catch (error) {
      onNotify?.("error", error.message || "Could not open that run.");
    }
  }

  const summary = result?.summary;

  return (
    <div className={pageShell()}>
      <div className={pageTitleRow()}>
        <div>
          <h2 className={`text-xl font-black tracking-tight ${textHeading()}`}>Cascade Star</h2>
          <p className={`mt-1 text-sm ${textMuted()}`}>
            5-minute continuation. Three downside bars plus a rejection on the fourth candle is enough to arm the stop.
            A plain fourth candle still waits for the next rejection. Session 15:30–23:00 IST. Entries pause when the Choppiness Index is sideways.
          </p>
        </div>
        <button
          type="button"
          className={enabled ? dangerButton() : primaryButton()}
          onClick={handleStartStop}
          disabled={pending || form.symbols.length === 0}
        >
          {enabled ? "Stop" : "Start"}
        </button>
      </div>

      <WorkspaceSubTabs tabs={TABS} activeId={tab} onChange={setTab} />

      {tab === "live" ? (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,360px)_1fr]">
          <WorkspaceCard>
            <h3 className={`mb-4 text-sm font-bold uppercase tracking-wider ${textHeading()}`}>Settings</h3>
            <div className="space-y-3">
              <WorkspaceField label="Direction">
                <WorkspaceSelect value={form.direction} onChange={(event) => updateField("direction", event.target.value)}>
                  <option value="SHORT">Short</option>
                  <option value="LONG">Long</option>
                </WorkspaceSelect>
              </WorkspaceField>
              <WorkspaceField label="Symbols">
                <div className="flex gap-4 text-sm">
                  {["BTCUSD", "ETHUSD"].map((symbol) => (
                    <label key={symbol} className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={form.symbols.includes(symbol)}
                        onChange={() => toggleSymbol(symbol)}
                      />
                      {symbol}
                    </label>
                  ))}
                </div>
              </WorkspaceField>
              <WorkspaceField label="Sizing">
                <WorkspaceSelect value={form.sizingMode} onChange={(event) => updateField("sizingMode", event.target.value)}>
                  <option value="max_risk">Max risk (USD)</option>
                  <option value="lots">Fixed lots</option>
                </WorkspaceSelect>
              </WorkspaceField>
              {form.sizingMode === "lots" ? (
                <WorkspaceField label="Lots">
                  <WorkspaceInput value={form.lots} onChange={(event) => updateField("lots", event.target.value)} inputMode="numeric" />
                </WorkspaceField>
              ) : (
                <WorkspaceField label="Max risk">
                  <WorkspaceInput value={form.maxRisk} onChange={(event) => updateField("maxRisk", event.target.value)} inputMode="decimal" />
                </WorkspaceField>
              )}
              <div className="grid grid-cols-2 gap-3">
                <WorkspaceField label="Session start">
                  <WorkspaceInput value={form.sessionStart} onChange={(event) => updateField("sessionStart", event.target.value)} />
                </WorkspaceField>
                <WorkspaceField label="Session end">
                  <WorkspaceInput value={form.sessionEnd} onChange={(event) => updateField("sessionEnd", event.target.value)} />
                </WorkspaceField>
                <WorkspaceField label="CHOP length" hint="TradingView default is 14">
                  <WorkspaceInput value={form.chopLength} onChange={(event) => updateField("chopLength", event.target.value)} inputMode="numeric" />
                </WorkspaceField>
                <WorkspaceField label="CHOP max" hint="Skip at or above this. 61.8 is sideways.">
                  <WorkspaceInput value={form.chopMax} onChange={(event) => updateField("chopMax", event.target.value)} inputMode="decimal" />
                </WorkspaceField>
                <WorkspaceField label="Target (R)">
                  <WorkspaceInput value={form.targetR} onChange={(event) => updateField("targetR", event.target.value)} inputMode="decimal" />
                </WorkspaceField>
              </div>
              <button type="button" className={secondaryButton()} onClick={handleSave} disabled={pending}>
                Save settings
              </button>
            </div>
          </WorkspaceCard>

          <div className="space-y-6">
            <WorkspaceCard>
              <h3 className={`mb-3 text-sm font-bold uppercase tracking-wider ${textHeading()}`}>
                {enabled ? "Running" : "Stopped"}
              </h3>
              <div className="space-y-3">
                {(form.symbols.length ? form.symbols : ["BTCUSD", "ETHUSD"]).map((symbol) => {
                  const scan = scans[symbol];
                  return (
                    <div key={symbol} className="rounded-lg border border-slate-200 px-3 py-2 text-sm dark:border-zinc-800">
                      <div className="font-bold">{symbol}</div>
                      <div className={textMuted()}>{scan?.detail || "Waiting for the next scan."}</div>
                      {scan?.chop != null ? (
                        <div className={`text-xs ${textMuted()}`}>CHOP {Number(scan.chop).toFixed(1)} · bar {formatBar(scan.barTime)}</div>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            </WorkspaceCard>

            <WorkspaceCard>
              <h3 className={`mb-3 text-sm font-bold uppercase tracking-wider ${textHeading()}`}>Working trades</h3>
              {active.length === 0 ? (
                <p className={`text-sm ${textMuted()}`}>No pending entry or open position.</p>
              ) : (
                <ul className="space-y-2 text-sm">
                  {active.map((trade) => (
                    <li key={trade.id} className="rounded-lg border border-slate-200 px-3 py-2 dark:border-zinc-800">
                      <div className="font-bold">{trade.symbol} · {trade.direction} · {trade.status}</div>
                      <div className={textMuted()}>
                        Entry {trade.entry} · Stop {trade.stopLoss} · Target {trade.target} · Size {trade.size}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </WorkspaceCard>

            <WorkspaceCard>
              <h3 className={`mb-3 text-sm font-bold uppercase tracking-wider ${textHeading()}`}>Activity</h3>
              {activity.length === 0 ? (
                <p className={`text-sm ${textMuted()}`}>No activity yet.</p>
              ) : (
                <ul className="space-y-1 text-sm">
                  {[...activity].reverse().map((row, index) => (
                    <li key={`${row.at}-${index}`} className={textMuted()}>
                      <span className="font-mono text-xs">{row.at ? new Date(row.at).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata" }) : ""}</span>
                      {" "}
                      {row.message}
                    </li>
                  ))}
                </ul>
              )}
            </WorkspaceCard>
          </div>
        </div>
      ) : tab === "history" ? (
        <WorkspaceCard>
          {history.length === 0 ? (
            <p className={`text-sm ${textMuted()}`}>No finished Cascade Star trades.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className={`text-xs uppercase ${textMuted()}`}>
                  <tr>
                    <th className="py-2 pr-3">Symbol</th>
                    <th className="py-2 pr-3">Side</th>
                    <th className="py-2 pr-3">Status</th>
                    <th className="py-2 pr-3">Entry</th>
                    <th className="py-2 pr-3">Stop</th>
                    <th className="py-2 pr-3">Target</th>
                    <th className="py-2">Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((trade) => (
                    <tr key={trade.id} className="border-t border-slate-200 dark:border-zinc-800">
                      <td className="py-2 pr-3">{trade.symbol}</td>
                      <td className="py-2 pr-3">{trade.direction}</td>
                      <td className="py-2 pr-3">{trade.status}</td>
                      <td className="py-2 pr-3">{trade.entry}</td>
                      <td className="py-2 pr-3">{trade.stopLoss}</td>
                      <td className="py-2 pr-3">{trade.target}</td>
                      <td className="py-2">{trade.exitReason || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </WorkspaceCard>
      ) : (
        <div className="space-y-6">
          <WorkspaceCard>
            <div className="grid gap-3 md:grid-cols-4">
              <WorkspaceField label="From">
                <WorkspaceInput type="date" value={fromDate} onChange={(event) => setFromDate(event.target.value)} />
              </WorkspaceField>
              <WorkspaceField label="To">
                <WorkspaceInput type="date" value={toDate} onChange={(event) => setToDate(event.target.value)} />
              </WorkspaceField>
              <WorkspaceField label="Symbol">
                <WorkspaceSelect value={backtestSymbol} onChange={(event) => setBacktestSymbol(event.target.value)}>
                  <option value="BTCUSD">BTCUSD</option>
                  <option value="ETHUSD">ETHUSD</option>
                </WorkspaceSelect>
              </WorkspaceField>
              <WorkspaceField label="Direction">
                <WorkspaceSelect value={form.direction} onChange={(event) => updateField("direction", event.target.value)}>
                  <option value="SHORT">Short</option>
                  <option value="LONG">Long</option>
                </WorkspaceSelect>
              </WorkspaceField>
            </div>
            <p className={`mt-3 text-xs ${textMuted()}`}>
              Uses the live settings for risk, Choppiness Index, target R, and session. {form.direction} · {form.sizingMode === "lots" ? `${form.lots} lots` : `${form.maxRisk} max risk`} · CHOP {form.chopLength}/{form.chopMax} · {form.targetR}R
            </p>
            <button type="button" className={`${primaryButton()} mt-4`} onClick={handleRunBacktest} disabled={pending || job?.status === "processing"}>
              {job?.status === "processing" ? "Running" : "Run backtest"}
            </button>
            {job?.status === "processing" ? (
              <div className="mt-4">
                <WorkspaceProgressBar value={job.progress} />
                <p className={`mt-2 text-xs ${textMuted()}`}>{job.stage || "Working"} · {job.progress || 0}%</p>
              </div>
            ) : null}
            {job?.status === "failed" ? <p className="mt-3 text-sm text-rose-500">{job.error}</p> : null}
          </WorkspaceCard>

          {summary ? (
            <WorkspaceCard>
              <h3 className={`mb-3 text-sm font-bold uppercase tracking-wider ${textHeading()}`}>Summary</h3>
              <div className="grid grid-cols-2 gap-3 text-sm md:grid-cols-3">
                <div>Trades <span className="font-bold">{summary.trades}</span></div>
                <div>Wins <span className="font-bold">{summary.wins}</span></div>
                <div>Losses <span className="font-bold">{summary.losses}</span></div>
                <div>Net PnL <span className="font-bold">{formatMoney(summary.netPnl)}</span></div>
                <div>Max win <span className="font-bold">{formatMoney(summary.maxWin)}</span></div>
                <div>Max loss <span className="font-bold">{formatMoney(summary.maxLoss)}</span></div>
              </div>
            </WorkspaceCard>
          ) : null}

          <WorkspaceCard>
            <h3 className={`mb-3 text-sm font-bold uppercase tracking-wider ${textHeading()}`}>Trades</h3>
            {(result?.trades || []).length === 0 ? (
              <p className={`text-sm ${textMuted()}`}>No backtest trades yet.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className={`text-xs uppercase ${textMuted()}`}>
                    <tr>
                      <th className="py-2 pr-3">Signal</th>
                      <th className="py-2 pr-3">Exit</th>
                      <th className="py-2 pr-3">Entry</th>
                      <th className="py-2 pr-3">Stop</th>
                      <th className="py-2 pr-3">Target</th>
                      <th className="py-2 pr-3">Size</th>
                      <th className="py-2 pr-3">PnL</th>
                      <th className="py-2">Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.trades.map((trade) => (
                      <tr key={`${trade.signalTime}-${trade.exitTime}`} className="border-t border-slate-200 dark:border-zinc-800">
                        <td className="py-2 pr-3">{formatBar(trade.signalTime)}</td>
                        <td className="py-2 pr-3">{formatBar(trade.exitTime)}</td>
                        <td className="py-2 pr-3">{trade.fillPrice ?? trade.entry}</td>
                        <td className="py-2 pr-3">{trade.stop}</td>
                        <td className="py-2 pr-3">{trade.target}</td>
                        <td className="py-2 pr-3">{trade.size}</td>
                        <td className="py-2 pr-3">{formatMoney(trade.pnl)}</td>
                        <td className="py-2">{trade.exitReason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </WorkspaceCard>

          <WorkspaceCard>
            <h3 className={`mb-3 text-sm font-bold uppercase tracking-wider ${textHeading()}`}>Saved runs</h3>
            {runs.length === 0 ? (
              <p className={`text-sm ${textMuted()}`}>No saved runs.</p>
            ) : (
              <ul className="space-y-2 text-sm">
                {runs.map((run) => (
                  <li key={run.id}>
                    <button type="button" className={secondaryButton()} onClick={() => openRun(run.id)}>
                      {run.symbol} {run.from} → {run.to} · {run.trades ?? 0} trades · {formatMoney(run.netPnl)}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </WorkspaceCard>
        </div>
      )}
    </div>
  );
}
