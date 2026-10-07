import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api";
import { formatTimeIst } from "../../utils/optionsDisplayUtils";
import { readSpotPrice } from "../execution/executionUtils";
import WorkspaceCard from "../ui/WorkspaceCard";
import WorkspaceConfirmDialog from "../ui/WorkspaceConfirmDialog";
import WorkspaceSubTabs from "../ui/WorkspaceSubTabs";
import { WorkspaceField, WorkspaceInput, WorkspaceSelect } from "../ui/WorkspaceField";
import WorkspaceProgressBar from "../ui/WorkspaceProgressBar";
import BiasIcon from "./BiasIcon";
import StOptionsBacktestCompareModal from "./StOptionsBacktestCompareModal";
import { StOptionsSummaryGrid, StOptionsTradeTable } from "./StOptionsTradeTable";
import {
  dangerButton,
  modalOverlay,
  modalPanel,
  pageShell,
  pageTitleRow,
  primaryButton,
  secondaryButton,
  textHeading,
  textMuted,
  profitText,
  lossText,
} from "../../utils/workspace/workspaceClasses";

const MAIN_TABS = [
  { id: "live", label: "Live" },
  { id: "backtest", label: "Backtest" },
];

const LIVE_TABS = [
  { id: "running", label: "Running" },
  { id: "history", label: "History" },
];

const HISTORY_PAGE_SIZE = 20;

const EMPTY_LIVE_SUMMARY = {
  trades: 0,
  long: 0,
  short: 0,
  profitCount: 0,
  lossCount: 0,
  maxProfit: 0,
  maxLoss: 0,
  totalProfit: 0,
  totalLoss: 0,
  totalPnl: 0,
  lossToProfit: null,
};

const DEFAULT_FORM = {
  underlying: "BTC",
  maxRisk: "100",
  stPeriod: "10",
  stMultiplier: "3",
  emaLength: "10",
  minPremiumPct: "5",
  stopLossPct: "105",
  takeProfitPct: "95",
  breakevenDecayPct: "40",
  pairHedgeDecayPct: "0",
  maxStDistancePct: "0.3",
};

const DEFAULT_DYN = {
  dynamicSizingEnabled: false,
  dynAfterLosses: "2",
  dynIncreasePct: "10",
  dynMaxRiskPct: "200",
  dynAfterProfits: "2",
  dynDecreasePct: "10",
};

const DEFAULT_BT_STRIKE = {
  strikeSelectMode: "min_pct",
  strikeType: "ATM",
  minPremiumAbs: "50",
  oneTradePerFormation: false,
  skipSetupsAfterTarget: "1",
  maxStDistancePct: "0.3",
  pairHedgeEnabled: false,
  pairHedgeMode: "immediate",
  pairHedgeDecayPct: "40",
  maxRisk: "100",
};

const STRIKE_TYPE_OPTIONS = [
  ...Array.from({ length: 10 }, (_, i) => `OTM${10 - i}`),
  "ATM",
  ...Array.from({ length: 10 }, (_, i) => `ITM${i + 1}`),
];

const BT_CONFIG_STORAGE_KEY = "cryptobridge.stOptions.backtestConfig";
const IST_TZ = "Asia/Kolkata";

function isNotFoundError(err) {
  const text = String(err?.message || err || "").toLowerCase();
  return text === "not found" || text.includes("404");
}

function istYmd(date = new Date()) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: IST_TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

function defaultBacktestDates() {
  const to = istYmd();
  const [y, m, d] = to.split("-").map(Number);
  const utcApprox = Date.UTC(y, m - 1, d, 6, 30);
  const fromDate = new Date(utcApprox - 7 * 24 * 60 * 60 * 1000);
  return { from: istYmd(fromDate), to };
}

function readLocalBtConfig() {
  try {
    const raw = localStorage.getItem(BT_CONFIG_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch {
    return null;
  }
}

function writeLocalBtConfig(form) {
  try {
    localStorage.setItem(
      BT_CONFIG_STORAGE_KEY,
      JSON.stringify({
        ...btBodyFromForm(form),
        from: form.from,
        to: form.to,
      }),
    );
  } catch {
    /* ignore quota */
  }
}

const GEAR_ICON = (
  <svg fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4" aria-hidden="true">
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z"
    />
    <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
  </svg>
);

function settingsFromConfig(config) {
  if (!config) return { ...DEFAULT_FORM };
  return {
    underlying: config.underlying || "BTC",
    maxRisk: String(config.maxRisk ?? 100),
    stPeriod: String(config.stPeriod ?? 10),
    stMultiplier: String(config.stMultiplier ?? 3),
    emaLength: String(config.emaLength ?? 10),
    minPremiumPct: String(config.minPremiumPct ?? 5),
    stopLossPct: String(config.stopLossPct ?? 105),
    takeProfitPct: String(config.takeProfitPct ?? 95),
    breakevenDecayPct: String(config.breakevenDecayPct ?? 40),
    pairHedgeDecayPct: String(config.pairHedgeDecayPct ?? 0),
    maxStDistancePct: String(config.maxStDistancePct ?? 0.3),
  };
}

function btSettingsFromConfig(config) {
  const base = settingsFromConfig(config);
  return {
    ...base,
    maxRisk: String(config?.maxRisk ?? DEFAULT_BT_STRIKE.maxRisk),
    dynamicSizingEnabled: Boolean(config?.dynamicSizingEnabled),
    dynAfterLosses: String(config?.dynAfterLosses ?? DEFAULT_DYN.dynAfterLosses),
    dynIncreasePct: String(config?.dynIncreasePct ?? DEFAULT_DYN.dynIncreasePct),
    dynMaxRiskPct: String(config?.dynMaxRiskPct ?? DEFAULT_DYN.dynMaxRiskPct),
    dynAfterProfits: String(config?.dynAfterProfits ?? DEFAULT_DYN.dynAfterProfits),
    dynDecreasePct: String(config?.dynDecreasePct ?? DEFAULT_DYN.dynDecreasePct),
    strikeSelectMode: config?.strikeSelectMode || DEFAULT_BT_STRIKE.strikeSelectMode,
    strikeType: config?.strikeType || DEFAULT_BT_STRIKE.strikeType,
    minPremiumAbs: String(config?.minPremiumAbs ?? DEFAULT_BT_STRIKE.minPremiumAbs),
    oneTradePerFormation: Boolean(config?.oneTradePerFormation),
    skipSetupsAfterTarget: String(
      config?.skipSetupsAfterTarget ?? DEFAULT_BT_STRIKE.skipSetupsAfterTarget,
    ),
    maxStDistancePct: String(config?.maxStDistancePct ?? DEFAULT_BT_STRIKE.maxStDistancePct),
    pairHedgeEnabled: Boolean(config?.pairHedgeEnabled),
    pairHedgeMode: config?.pairHedgeMode || DEFAULT_BT_STRIKE.pairHedgeMode,
    pairHedgeDecayPct: String(config?.pairHedgeDecayPct ?? DEFAULT_BT_STRIKE.pairHedgeDecayPct),
  };
}

function bodyFromForm(form) {
  return {
    underlying: form.underlying,
    maxRisk: Number(form.maxRisk),
    stPeriod: Number(form.stPeriod),
    stMultiplier: Number(form.stMultiplier),
    emaLength: Number(form.emaLength),
    minPremiumPct: Number(form.minPremiumPct),
    stopLossPct: Number(form.stopLossPct),
    takeProfitPct: Number(form.takeProfitPct),
    breakevenDecayPct: Number(form.breakevenDecayPct),
    pairHedgeDecayPct: Number(form.pairHedgeDecayPct),
    maxStDistancePct: Number(form.maxStDistancePct),
  };
}

function btBodyFromForm(form) {
  return {
    underlying: form.underlying,
    maxRisk: Number(form.maxRisk),
    stPeriod: Number(form.stPeriod),
    stMultiplier: Number(form.stMultiplier),
    emaLength: Number(form.emaLength),
    minPremiumPct: Number(form.minPremiumPct),
    stopLossPct: Number(form.stopLossPct),
    takeProfitPct: Number(form.takeProfitPct),
    breakevenDecayPct: Number(form.breakevenDecayPct),
    dynamicSizingEnabled: Boolean(form.dynamicSizingEnabled),
    dynAfterLosses: Number(form.dynAfterLosses),
    dynIncreasePct: Number(form.dynIncreasePct),
    dynMaxRiskPct: Number(form.dynMaxRiskPct),
    dynAfterProfits: Number(form.dynAfterProfits),
    dynDecreasePct: Number(form.dynDecreasePct),
    strikeSelectMode: form.strikeSelectMode || DEFAULT_BT_STRIKE.strikeSelectMode,
    strikeType: form.strikeType || DEFAULT_BT_STRIKE.strikeType,
    minPremiumAbs: Number(form.minPremiumAbs),
    oneTradePerFormation: Boolean(form.oneTradePerFormation),
    skipSetupsAfterTarget: Number(form.skipSetupsAfterTarget),
    maxStDistancePct: Number(form.maxStDistancePct),
    pairHedgeEnabled: Boolean(form.pairHedgeEnabled),
    pairHedgeMode: form.pairHedgeMode || DEFAULT_BT_STRIKE.pairHedgeMode,
    pairHedgeDecayPct: Number(form.pairHedgeDecayPct),
  };
}

function formatCountdown(seconds) {
  const s = Math.max(0, Number(seconds) || 0);
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${String(r).padStart(2, "0")}`;
}

function phaseLabel(phase) {
  switch (phase) {
    case "watching":
      return "Looking for a setup";
    case "entry_ready":
      return "Setup ready — waiting for the next hour";
    case "managing_opens":
      return "Managing open positions";
    case "stopped":
      return "Off";
    default:
      return phase || "—";
  }
}

function sideLabel(direction) {
  if (direction === "LONG") return "Long-side";
  if (direction === "SHORT") return "Short-side";
  return direction || "—";
}

function fmtSummaryMoney(n) {
  if (n == null || Number.isNaN(Number(n))) return "—";
  return Number(n).toFixed(2);
}

function computeLiveStrategySummary(history = []) {
  const closed = history || [];
  let profitCount = 0;
  let lossCount = 0;
  let totalProfit = 0;
  let totalLoss = 0;
  let maxProfit = 0;
  let maxLoss = 0;
  let longClosed = 0;
  let shortClosed = 0;
  for (const trade of closed) {
    if (trade.direction === "LONG") longClosed += 1;
    else if (trade.direction === "SHORT") shortClosed += 1;
    const pnl = Number(trade.pnl);
    if (!Number.isFinite(pnl)) continue;
    if (pnl > 0) {
      profitCount += 1;
      totalProfit += pnl;
      if (pnl > maxProfit) maxProfit = pnl;
    } else if (pnl < 0) {
      lossCount += 1;
      totalLoss += pnl;
      if (pnl < maxLoss) maxLoss = pnl;
    }
  }
  const lossAbs = Math.abs(totalLoss);
  const lossToProfit = totalProfit > 0 ? lossAbs / totalProfit : null;
  const totalPnl = totalProfit + totalLoss;
  return {
    trades: closed.length,
    long: longClosed,
    short: shortClosed,
    profitCount,
    lossCount,
    maxProfit,
    maxLoss,
    totalProfit,
    totalLoss,
    totalPnl,
    lossToProfit,
  };
}

function LiveStrategySummaryStrip({ summary }) {
  if (!summary) return null;
  const items = [
    { label: "Trades", value: summary.trades },
    { label: "Long", value: summary.long },
    { label: "Short", value: summary.short },
    { label: "Profit count", value: summary.profitCount },
    { label: "Loss count", value: summary.lossCount },
    { label: "Max profit", value: fmtSummaryMoney(summary.maxProfit), raw: summary.maxProfit },
    { label: "Max loss", value: fmtSummaryMoney(summary.maxLoss), raw: summary.maxLoss },
    { label: "Total profit", value: fmtSummaryMoney(summary.totalProfit), raw: summary.totalProfit },
    { label: "Total loss", value: fmtSummaryMoney(summary.totalLoss), raw: summary.totalLoss },
    {
      label: "Loss to Profit",
      value: summary.lossToProfit == null ? "—" : summary.lossToProfit.toFixed(2),
    },
  ];
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 xl:grid-cols-10 gap-1.5">
      {items.map((item) => (
        <div
          key={item.label}
          className="rounded border border-slate-200 dark:border-zinc-800 bg-white/80 dark:bg-zinc-900/80 px-2 py-1.5"
        >
          <p className={`text-[9px] font-bold uppercase tracking-wide ${textMuted()}`}>{item.label}</p>
          <p
            className={`text-sm font-mono font-semibold tabular-nums ${
              item.raw != null && Number(item.raw) !== 0
                ? Number(item.raw) > 0
                  ? profitText()
                  : lossText()
                : "text-slate-800 dark:text-zinc-100"
            }`}
          >
            {item.value}
          </p>
        </div>
      ))}
    </div>
  );
}

function EngineStatusPanel({ status, enabled }) {
  const [countdown, setCountdown] = useState(null);
  useEffect(() => {
    if (status?.secondsToNextBarClose == null) {
      setCountdown(null);
      return undefined;
    }
    setCountdown(Number(status.secondsToNextBarClose));
    const id = window.setInterval(() => {
      setCountdown((prev) => (prev == null ? prev : Math.max(0, prev - 1)));
    }, 1000);
    return () => window.clearInterval(id);
  }, [status?.secondsToNextBarClose, status?.lastTickAt, status?.nextBarCloseIst]);

  if (!status) return null;
  const long = status.long || {};
  const short = status.short || {};
  const activity = status.activity || [];
  const secondsLeft = countdown != null ? countdown : status.secondsToNextBarClose;
  return (
    <WorkspaceCard className="flex flex-1 flex-col min-h-0 space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3 shrink-0">
        <div>
          <p className={`text-[10px] font-bold uppercase tracking-widest ${textMuted()}`}>Market watch</p>
          <p className="mt-1 text-sm font-semibold text-slate-800 dark:text-zinc-100">
            {enabled ? phaseLabel(status.phase) : "Off"}
          </p>
        </div>
        <div className={`text-right text-xs font-mono ${textMuted()}`}>
          <p>Checks again in {formatCountdown(secondsLeft)}</p>
          <p>{status.nextBarCloseIst || "—"}</p>
        </div>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs shrink-0">
        <div>
          <p className={textMuted()}>Underlying</p>
          <p className="font-semibold">{status.underlying || "—"}</p>
        </div>
        <div>
          <p className={textMuted()}>Max risk / min. option price</p>
          <p className="font-semibold font-mono">
            {status.maxRisk ?? "—"} · {status.minPremiumPct ?? "—"}%
          </p>
        </div>
        <div>
          <p className={textMuted()}>Bias</p>
          <p className="font-semibold flex items-center min-h-[1.25rem]">
            <BiasIcon
              colour={
                status.sentiment === "LONG" || String(status.sentimentLabel || "").toLowerCase() === "up"
                  ? "green"
                  : status.sentiment === "SHORT" || String(status.sentimentLabel || "").toLowerCase() === "down"
                    ? "red"
                    : null
              }
              sentiment={status.sentiment}
            />
          </p>
        </div>
        <div>
          <p className={textMuted()}>Next decision</p>
          <p className="font-semibold font-mono text-[11px]">{status.nextBarCloseIst || "—"}</p>
        </div>
      </div>
      <div className="grid md:grid-cols-2 gap-3 shrink-0">
        <div className="rounded-lg border border-slate-200 dark:border-zinc-800 p-3 space-y-1">
          <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500 dark:text-zinc-500">
            Long-side {long.open ? "· Open" : long.ready ? "· Ready" : ""}
          </p>
          <p className="text-sm text-slate-800 dark:text-zinc-100">{long.detail || "—"}</p>
        </div>
        <div className="rounded-lg border border-slate-200 dark:border-zinc-800 p-3 space-y-1">
          <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500 dark:text-zinc-500">
            Short-side {short.open ? "· Open" : short.ready ? "· Ready" : ""}
          </p>
          <p className="text-sm text-slate-800 dark:text-zinc-100">{short.detail || "—"}</p>
        </div>
      </div>
      <div className="flex flex-1 flex-col min-h-0">
        <p className={`text-[10px] font-bold uppercase tracking-widest mb-2 shrink-0 ${textMuted()}`}>Updates</p>
        {activity.length ? (
          <ul className="flex-1 min-h-[12rem] overflow-auto space-y-1.5 text-sm">
            {[...activity].reverse().map((row, idx) => (
              <li
                key={`${row.at}-${idx}`}
                className={
                  (row.level === "warn"
                    ? "text-rose-600 dark:text-rose-400"
                    : row.level === "success"
                      ? "text-emerald-700 dark:text-emerald-400"
                      : "text-slate-700 dark:text-zinc-300")
                  + (/·\s*result\s/i.test(String(row.userMessage || row.message || ""))
                    ? " font-bold"
                    : "")
                }
              >
                <span className={`text-[11px] font-mono opacity-70 font-normal ${textMuted()}`}>
                  {formatTimeIst(row.at)}
                </span>
                {"  "}
                {row.userMessage || row.message}
              </li>
            ))}
          </ul>
        ) : (
          <p className={`text-sm ${textMuted()}`}>
            {enabled ? "Waiting for the next market check…" : "Turn the strategy on to see live updates."}
          </p>
        )}
      </div>
    </WorkspaceCard>
  );
}

function SettingsForm({
  form,
  setForm,
  disabled,
  showAdvanced = false,
  showBrackets = false,
  showDynamicSizing = false,
  hedgeEditableWhileLocked = false,
}) {
  const strikeMode = form.strikeSelectMode || "min_pct";
  const hedgeDisabled = hedgeEditableWhileLocked ? false : disabled;
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <WorkspaceField label="Underlying">
          <WorkspaceSelect
            value={form.underlying}
            disabled={disabled}
            onChange={(e) => setForm((f) => ({ ...f, underlying: e.target.value }))}
          >
            <option value="BTC">BTC</option>
            <option value="ETH">ETH</option>
          </WorkspaceSelect>
        </WorkspaceField>
        <WorkspaceField label="Max risk ($)">
          <WorkspaceInput
            type="number"
            min="1"
            step="1"
            disabled={disabled}
            value={form.maxRisk}
            onChange={(e) => setForm((f) => ({ ...f, maxRisk: e.target.value }))}
          />
        </WorkspaceField>
        {!showDynamicSizing ? (
          <WorkspaceField label="Minimum option price (%)">
            <WorkspaceInput
              type="number"
              min="0.1"
              step="0.1"
              disabled={disabled}
              value={form.minPremiumPct}
              onChange={(e) => setForm((f) => ({ ...f, minPremiumPct: e.target.value }))}
            />
          </WorkspaceField>
        ) : (
          <WorkspaceField label="Strike selection">
            <WorkspaceSelect
              value={strikeMode}
              disabled={disabled}
              onChange={(e) => setForm((f) => ({ ...f, strikeSelectMode: e.target.value }))}
            >
              <option value="fixed">Strike type</option>
              <option value="min_pct">Min % of underlying</option>
              <option value="supertrend">SuperTrend line</option>
              <option value="min_abs">Minimum premium</option>
            </WorkspaceSelect>
          </WorkspaceField>
        )}
      </div>
      {showDynamicSizing ? (
        <div className="space-y-3 rounded-xl border border-slate-200 dark:border-zinc-800 p-3">
          {strikeMode === "fixed" ? (
            <>
              <WorkspaceField label="Strike type">
                <WorkspaceSelect
                  value={form.strikeType || "ATM"}
                  disabled={disabled}
                  onChange={(e) => setForm((f) => ({ ...f, strikeType: e.target.value }))}
                >
                  {STRIKE_TYPE_OPTIONS.map((opt) => (
                    <option key={opt} value={opt}>
                      {opt}
                    </option>
                  ))}
                </WorkspaceSelect>
              </WorkspaceField>
              <p className={`text-xs ${textMuted()}`}>
                Expiry is automatic: same day before 05:30 IST, next day at/after 05:30. No fallback if premium is
                missing.
              </p>
            </>
          ) : null}
          {strikeMode === "min_pct" ? (
            <WorkspaceField label="Minimum option price (%)">
              <WorkspaceInput
                type="number"
                min="0.1"
                step="0.1"
                disabled={disabled}
                value={form.minPremiumPct}
                onChange={(e) => setForm((f) => ({ ...f, minPremiumPct: e.target.value }))}
              />
            </WorkspaceField>
          ) : null}
          {strikeMode === "min_abs" ? (
            <WorkspaceField label="Minimum premium (absolute)">
              <WorkspaceInput
                type="number"
                min="0.1"
                step="1"
                disabled={disabled}
                value={form.minPremiumAbs}
                onChange={(e) => setForm((f) => ({ ...f, minPremiumAbs: e.target.value }))}
              />
            </WorkspaceField>
          ) : null}
          {strikeMode === "supertrend" ? (
            <p className={`text-xs ${textMuted()}`}>ATM snapped to the SuperTrend line; T0/T1 eligibility unchanged.</p>
          ) : null}
          <label className="flex items-center gap-2 text-sm font-semibold">
            <input
              type="checkbox"
              className="rounded border-slate-300"
              checked={Boolean(form.oneTradePerFormation)}
              disabled={disabled}
              onChange={(e) => setForm((f) => ({ ...f, oneTradePerFormation: e.target.checked }))}
            />
            One trade per SuperTrend formation
          </label>
          <p className={`text-xs ${textMuted()}`}>
            When on, after any exit on a side, that side will not re-enter until ST colour changes.
          </p>
          <WorkspaceField label="Skip next setup after Target hit">
            <WorkspaceInput
              type="number"
              min="0"
              step="1"
              disabled={disabled}
              value={form.skipSetupsAfterTarget}
              onChange={(e) => setForm((f) => ({ ...f, skipSetupsAfterTarget: e.target.value }))}
            />
          </WorkspaceField>
          <p className={`text-xs ${textMuted()}`}>
            After a take-profit on a side, skip the next N entry signals on that side (0 = off). Long and
            Short are independent.
          </p>
          <WorkspaceField label="Max close→ST distance %">
            <WorkspaceInput
              type="number"
              min="0"
              step="0.05"
              disabled={disabled}
              value={form.maxStDistancePct}
              onChange={(e) => setForm((f) => ({ ...f, maxStDistancePct: e.target.value }))}
            />
          </WorkspaceField>
          <p className={`text-xs ${textMuted()}`}>
            After EMA/ST pullback geometry, skip entry when |close − ST line| / close exceeds this % (0 =
            off). Default 0.3.
          </p>
          <label className="flex items-center gap-2 text-sm font-semibold">
            <input
              type="checkbox"
              className="rounded border-slate-300"
              checked={Boolean(form.pairHedgeEnabled)}
              disabled={disabled}
              onChange={(e) => setForm((f) => ({ ...f, pairHedgeEnabled: e.target.checked }))}
            />
            Pair hedge (same-strike opposite)
          </label>
          <p className={`text-xs ${textMuted()}`}>
            When on, also short the opposite option at the same strike/expiry (PUT↔CALL).
          </p>
          {form.pairHedgeEnabled ? (
            <div className="space-y-3 pl-1">
              <WorkspaceField label="Hedge entry">
                <select
                  className="w-full rounded-lg border border-slate-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 py-2 text-sm"
                  disabled={disabled}
                  value={form.pairHedgeMode || "immediate"}
                  onChange={(e) => setForm((f) => ({ ...f, pairHedgeMode: e.target.value }))}
                >
                  <option value="immediate">Short both immediately</option>
                  <option value="on_decay">Short opposite after main decays %</option>
                </select>
              </WorkspaceField>
              {form.pairHedgeMode === "on_decay" ? (
                <WorkspaceField label="Main decay % before hedge">
                  <WorkspaceInput
                    type="number"
                    min="0"
                    max="99"
                    step="1"
                    disabled={disabled}
                    value={form.pairHedgeDecayPct}
                    onChange={(e) => setForm((f) => ({ ...f, pairHedgeDecayPct: e.target.value }))}
                  />
                </WorkspaceField>
              ) : (
                <p className={`text-xs ${textMuted()}`}>
                  Favor exit when PE ≈ CE premiums; main stop closes both. Solo take-profit is off for
                  the pair.
                </p>
              )}
              {form.pairHedgeMode === "on_decay" ? (
                <p className={`text-xs ${textMuted()}`}>
                  After the hedge opens, both legs close together when the main hits target or stop.
                </p>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
      {showBrackets ? (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <WorkspaceField label="Stop loss (% premium rise)">
              <WorkspaceInput
                type="number"
                min="1"
                step="1"
                disabled={disabled}
                value={form.stopLossPct}
                onChange={(e) => setForm((f) => ({ ...f, stopLossPct: e.target.value }))}
              />
            </WorkspaceField>
            <WorkspaceField label="Take profit (% premium melt)">
              <WorkspaceInput
                type="number"
                min="1"
                max="99.9"
                step="0.1"
                disabled={disabled}
                value={form.takeProfitPct}
                onChange={(e) => setForm((f) => ({ ...f, takeProfitPct: e.target.value }))}
              />
            </WorkspaceField>
          </div>
          <WorkspaceField label="Move SL to BE after decay % (0 = off)">
            <WorkspaceInput
              type="number"
              min="0"
              max="99.9"
              step="1"
              disabled={disabled}
              value={form.breakevenDecayPct}
              onChange={(e) => setForm((f) => ({ ...f, breakevenDecayPct: e.target.value }))}
            />
          </WorkspaceField>
          {!showDynamicSizing ? (
            <>
              <WorkspaceField label="Max close→ST distance %">
                <WorkspaceInput
                  type="number"
                  min="0"
                  step="0.05"
                  disabled={disabled}
                  value={form.maxStDistancePct}
                  onChange={(e) => setForm((f) => ({ ...f, maxStDistancePct: e.target.value }))}
                />
              </WorkspaceField>
              <p className={`text-xs ${textMuted()}`}>
                After EMA/ST pullback geometry, skip entry when |close − ST line| / close exceeds this % (0 =
                off). Default 0.3.
              </p>
              <WorkspaceField label="Hedge after decay % (0 = off)">
                <WorkspaceInput
                  type="number"
                  min="0"
                  max="99"
                  step="1"
                  disabled={hedgeDisabled}
                  value={form.pairHedgeDecayPct ?? "0"}
                  onChange={(e) => setForm((f) => ({ ...f, pairHedgeDecayPct: e.target.value }))}
                />
              </WorkspaceField>
              <p className={`text-xs ${textMuted()}`}>
                Short the same-strike opposite option after the main premium melts this %. Editable while the
                strategy is running. 0 disables new hedges; an open hedge is left until target, stop, or max
                loss. Combined pair loss at −max risk closes both legs.
              </p>
            </>
          ) : null}
        </div>
      ) : null}
      {showDynamicSizing ? (
        <div className="space-y-3 rounded-xl border border-slate-200 dark:border-zinc-800 p-3">
          <label className="flex items-center gap-2 text-sm font-semibold">
            <input
              type="checkbox"
              className="rounded border-slate-300"
              checked={Boolean(form.dynamicSizingEnabled)}
              disabled={disabled}
              onChange={(e) => setForm((f) => ({ ...f, dynamicSizingEnabled: e.target.checked }))}
            />
            Dynamic position sizing
          </label>
          {form.dynamicSizingEnabled ? (
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              <WorkspaceField label="After losses">
                <WorkspaceInput
                  type="number"
                  min="1"
                  disabled={disabled}
                  value={form.dynAfterLosses}
                  onChange={(e) => setForm((f) => ({ ...f, dynAfterLosses: e.target.value }))}
                />
              </WorkspaceField>
              <WorkspaceField label="Add % of base risk">
                <WorkspaceInput
                  type="number"
                  min="0"
                  step="1"
                  disabled={disabled}
                  value={form.dynIncreasePct}
                  onChange={(e) => setForm((f) => ({ ...f, dynIncreasePct: e.target.value }))}
                />
              </WorkspaceField>
              <WorkspaceField label="Max risk % of base">
                <WorkspaceInput
                  type="number"
                  min="100"
                  step="1"
                  disabled={disabled}
                  value={form.dynMaxRiskPct}
                  onChange={(e) => setForm((f) => ({ ...f, dynMaxRiskPct: e.target.value }))}
                />
              </WorkspaceField>
              <WorkspaceField label="After profits">
                <WorkspaceInput
                  type="number"
                  min="1"
                  disabled={disabled}
                  value={form.dynAfterProfits}
                  onChange={(e) => setForm((f) => ({ ...f, dynAfterProfits: e.target.value }))}
                />
              </WorkspaceField>
              <WorkspaceField label="Reduce % of base risk">
                <WorkspaceInput
                  type="number"
                  min="0"
                  step="1"
                  disabled={disabled}
                  value={form.dynDecreasePct}
                  onChange={(e) => setForm((f) => ({ ...f, dynDecreasePct: e.target.value }))}
                />
              </WorkspaceField>
            </div>
          ) : null}
        </div>
      ) : null}
      {showAdvanced ? (
        <div className="space-y-3">
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            <WorkspaceField label="Trend length (ST period)">
              <WorkspaceInput
                type="number"
                min="1"
                disabled={disabled}
                value={form.stPeriod}
                onChange={(e) => setForm((f) => ({ ...f, stPeriod: e.target.value }))}
              />
            </WorkspaceField>
            <WorkspaceField label="Trend sensitivity (ST mult)">
              <WorkspaceInput
                type="number"
                min="0.1"
                step="0.1"
                disabled={disabled}
                value={form.stMultiplier}
                onChange={(e) => setForm((f) => ({ ...f, stMultiplier: e.target.value }))}
              />
            </WorkspaceField>
            <WorkspaceField label="Pullback filter (EMA)">
              <WorkspaceInput
                type="number"
                min="1"
                disabled={disabled}
                value={form.emaLength}
                onChange={(e) => setForm((f) => ({ ...f, emaLength: e.target.value }))}
              />
            </WorkspaceField>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function StrategySettingsModal({
  open,
  title = "Strategy settings",
  form,
  setForm,
  disabled,
  pending,
  showAdvanced,
  onRequestAdvanced,
  onHideAdvanced,
  onSave,
  onClose,
  showDynamicSizing = false,
  hedgeEditableWhileLocked = false,
}) {
  if (!open) return null;
  const saveDisabled = pending || (disabled && !hedgeEditableWhileLocked);
  return (
    <div className={modalOverlay()} role="dialog" aria-modal="true" aria-labelledby="st-options-settings-title">
      <div className={modalPanel("max-w-2xl w-full overflow-hidden")}>
        <div className="px-6 py-5 border-b border-slate-200 dark:border-zinc-800 flex items-center justify-between gap-3">
          <h3 id="st-options-settings-title" className={`text-base font-bold uppercase tracking-wider ${textHeading()}`}>
            {title}
          </h3>
          <button
            type="button"
            className="p-2 rounded bg-zinc-100 dark:bg-zinc-800 hover:bg-zinc-200 dark:hover:bg-zinc-700 text-zinc-600 dark:text-zinc-300"
            onClick={onClose}
            title="Close"
          >
            <span className="sr-only">Close</span>
            <svg fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" className="w-4 h-4">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="p-6 space-y-4 max-h-[70vh] overflow-y-auto">
          {hedgeEditableWhileLocked ? (
            <p className={`text-xs ${textMuted()}`}>
              Strategy is on — only <strong>Hedge after decay %</strong> can be changed. Other settings stay locked.
            </p>
          ) : null}
          <SettingsForm
            form={form}
            setForm={setForm}
            disabled={disabled}
            showAdvanced={showAdvanced}
            showBrackets
            showDynamicSizing={showDynamicSizing}
            hedgeEditableWhileLocked={hedgeEditableWhileLocked}
          />
          <button
            type="button"
            className={`text-[11px] font-semibold underline-offset-2 hover:underline ${textMuted()}`}
            onClick={() => (showAdvanced ? onHideAdvanced() : onRequestAdvanced())}
          >
            {showAdvanced ? "Hide advanced" : "Advanced"}
          </button>
        </div>
        <div className="bg-slate-50 dark:bg-zinc-950 px-6 py-4 border-t border-slate-200 dark:border-zinc-800 flex justify-end gap-3">
          <button type="button" className={secondaryButton()} onClick={onClose}>
            Close
          </button>
          <button type="button" className={primaryButton()} disabled={saveDisabled} onClick={onSave}>
            Save
          </button>
        </div>
      </div>
    </div>
  );
}

function ActiveTradeCard({
  trade,
  hedgeDecayPct = 0,
  onForceClose,
  forceClosePending,
  biasColour,
}) {
  const live = trade.livePremium;
  const entry = trade.premiumReceived;
  const contractValue =
    trade.contractValue != null && Number(trade.contractValue) > 0
      ? Number(trade.contractValue)
      : trade.underlying === "ETH"
        ? 0.01
        : 0.001;
  const lots = Number(trade.lots || 1);
  const fallbackPnl =
    live != null && entry != null
      ? (Number(entry) - Number(live)) * lots * contractValue
      : null;
  const pnlHint = trade.pairLivePnl != null ? Number(trade.pairLivePnl) : fallbackPnl;
  const hedgeStatus = String(trade.hedgeStatus || "none");
  const hedgeOpen = hedgeStatus === "open" && Boolean(trade.hedgeSymbol);
  const entryPending = String(trade.status || "") === "pending_entry";
  const showForceClose = trade.closeError === "product_missing" && typeof onForceClose === "function";
  const mainPnl = trade.livePnl != null ? Number(trade.livePnl) : fallbackPnl;
  const hedgePnl = trade.hedgeLivePnl != null ? Number(trade.hedgeLivePnl) : null;
  const estAtStop =
    trade.estimatedPnlAtStop != null
      ? Number(trade.estimatedPnlAtStop)
      : entry != null && trade.stopPremium != null
        ? (Number(entry) - Number(trade.stopPremium)) * lots * contractValue
        : null;
  const estAtTarget =
    trade.estimatedPnlAtTarget != null
      ? Number(trade.estimatedPnlAtTarget)
      : entry != null && trade.targetPremium != null
        ? (Number(entry) - Number(trade.targetPremium)) * lots * contractValue
        : null;
  const bias = trade.stColour || biasColour;
  const fmtEst = (n) => (n == null || Number.isNaN(Number(n)) ? "—" : Number(n).toFixed(2));
  const estClass = (n) =>
    n == null || Number.isNaN(Number(n)) ? "" : Number(n) >= 0 ? profitText() : lossText();
  const pnlStrip = (
    <div className="grid grid-cols-3 gap-2 text-xs font-mono rounded-lg border border-slate-200 dark:border-zinc-800 px-3 py-2">
      <div>
        <p className={textMuted()}>Open (est.)</p>
        <p className={`font-bold tabular-nums ${estClass(mainPnl ?? pnlHint)}`}>
          {fmtEst(mainPnl ?? pnlHint)}
        </p>
      </div>
      <div>
        <p className={textMuted()}>Est. loss (stop)</p>
        <p className={`font-bold tabular-nums ${estClass(estAtStop)}`}>{fmtEst(estAtStop)}</p>
      </div>
      <div>
        <p className={textMuted()}>Est. profit (target)</p>
        <p className={`font-bold tabular-nums ${estClass(estAtTarget)}`}>{fmtEst(estAtTarget)}</p>
      </div>
    </div>
  );
  const mainBlock = (
    <div className="space-y-2">
      <p className="text-[10px] font-bold uppercase tracking-widest text-slate-600 dark:text-zinc-300">
        Main · {trade.optionSymbol}
      </p>
      <div className="grid grid-cols-2 gap-2 text-xs font-mono">
        <div>
          <p className={textMuted()}>Quantity</p>
          <p className="font-bold">{trade.lots != null ? Number(trade.lots) : "—"}</p>
        </div>
        <div>
          <p className={textMuted()}>Received</p>
          <p className="font-bold">{entry != null ? Number(entry).toFixed(2) : "—"}</p>
        </div>
        <div>
          <p className={textMuted()}>Live price</p>
          <p className="font-bold">{live != null ? Number(live).toFixed(2) : "—"}</p>
        </div>
        <div>
          <p className={textMuted()}>Protect at / Target</p>
          <p>
            {trade.stopPremium != null ? Number(trade.stopPremium).toFixed(2) : "—"} /{" "}
            {trade.targetPremium != null ? Number(trade.targetPremium).toFixed(2) : "—"}
          </p>
        </div>
        <div>
          <p className={textMuted()}>Strike / Expiry</p>
          <p>
            {trade.strike} · {trade.expiryDate}
          </p>
        </div>
        <div>
          <p className={textMuted()}>Main result (est.)</p>
          <p className={mainPnl == null ? "" : mainPnl >= 0 ? profitText() : lossText()}>
            {mainPnl == null ? "—" : mainPnl.toFixed(2)}
          </p>
        </div>
      </div>
    </div>
  );
  const hedgeBlock = hedgeOpen ? (
    <div className="space-y-2">
      <p className="text-[10px] font-bold uppercase tracking-widest text-slate-600 dark:text-zinc-300">
        Hedge · {trade.hedgeSymbol}
      </p>
      <div className="grid grid-cols-2 gap-2 text-xs font-mono">
        <div>
          <p className={textMuted()}>Quantity</p>
          <p className="font-bold">
            {trade.hedgeLots != null ? Number(trade.hedgeLots) : Number(trade.lots || 1)}
          </p>
        </div>
        <div>
          <p className={textMuted()}>Received</p>
          <p className="font-bold">
            {trade.hedgePremiumReceived != null
              ? Number(trade.hedgePremiumReceived).toFixed(2)
              : "—"}
          </p>
        </div>
        <div>
          <p className={textMuted()}>Live price</p>
          <p className="font-bold">
            {trade.hedgeLivePremium != null ? Number(trade.hedgeLivePremium).toFixed(2) : "—"}
          </p>
        </div>
        <div>
          <p className={textMuted()}>Protect at</p>
          <p className="font-bold">
            {trade.hedgeStopPremium != null ? Number(trade.hedgeStopPremium).toFixed(2) : "—"}
          </p>
        </div>
        <div>
          <p className={textMuted()}>Hedge result (est.)</p>
          <p className={hedgePnl == null ? "" : hedgePnl >= 0 ? profitText() : lossText()}>
            {hedgePnl == null ? "—" : hedgePnl.toFixed(2)}
          </p>
        </div>
      </div>
    </div>
  ) : null;
  return (
    <WorkspaceCard className="w-full space-y-2">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-bold uppercase tracking-widest text-lime-600 dark:text-lime-400">
          {sideLabel(trade.direction)}
          {hedgeOpen ? " · hedged" : ""}
          {entryPending ? " · confirming entry" : ""}
        </p>
        <span className={`text-[10px] uppercase font-bold inline-flex items-center gap-1 ${textMuted()}`}>
          Bias <BiasIcon colour={bias} className="w-6 h-6" />
        </span>
      </div>
      {pnlStrip}
      {entryPending ? (
        <p className={`text-[11px] ${lossText()}`}>
          Confirming fill — broker stop/target attach as soon as the position is verified
        </p>
      ) : null}
      {hedgeOpen ? (
        <div className="grid md:grid-cols-2 gap-3">
          <div className="rounded-lg border border-slate-200 dark:border-zinc-800 px-3 py-2">
            {mainBlock}
          </div>
          <div className="rounded-lg border border-slate-200 dark:border-zinc-800 px-3 py-2">
            {hedgeBlock}
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-2 text-xs font-mono">
          <div>
            <p className={textMuted()}>Quantity</p>
            <p className="font-bold">{trade.lots != null ? Number(trade.lots) : "—"}</p>
          </div>
          <div>
            <p className={textMuted()}>Received</p>
            <p className="font-bold">{entry != null ? Number(entry).toFixed(2) : "—"}</p>
          </div>
          <div>
            <p className={textMuted()}>Live price</p>
            <p className="font-bold">{live != null ? Number(live).toFixed(2) : "—"}</p>
          </div>
          <div>
            <p className={textMuted()}>Protect at / Target</p>
            <p>
              {trade.stopPremium != null ? Number(trade.stopPremium).toFixed(2) : "—"} /{" "}
              {trade.targetPremium != null ? Number(trade.targetPremium).toFixed(2) : "—"}
            </p>
          </div>
          <div className="col-span-2">
            <p className={textMuted()}>Strike / Expiry</p>
            <p>
              {trade.strike} · {trade.expiryDate}
            </p>
          </div>
        </div>
      )}
      {hedgeOpen ? (
        <div className="text-xs font-mono">
          <p className={textMuted()}>Combined pair result (est.)</p>
          <p className={pnlHint == null ? "" : pnlHint >= 0 ? profitText() : lossText()}>
            {pnlHint == null ? "—" : pnlHint.toFixed(2)}
          </p>
        </div>
      ) : null}
      {hedgeStatus === "pending" ? (
        <p className={`text-[11px] ${textMuted()}`}>Hedge pending fill…</p>
      ) : null}
      {!hedgeOpen && hedgeStatus === "none" && Number(hedgeDecayPct) > 0 ? (
        <p className={`text-[11px] ${textMuted()}`}>
          Hedge armed after {Number(hedgeDecayPct)}% main decay
        </p>
      ) : null}
      {showForceClose ? (
        <div className="pt-1 space-y-1">
          <p className={`text-[11px] ${lossText()}`}>Broker close failed — contract no longer exists.</p>
          <button
            type="button"
            className={dangerButton()}
            disabled={forceClosePending}
            onClick={() => onForceClose(trade)}
          >
            Force close
          </button>
        </div>
      ) : null}
    </WorkspaceCard>
  );
}

export default function StOptionsPage({ token, onNotify, stOptionsSession, onStOptionsSession, livePrices = {} }) {
  const [mainTab, setMainTab] = useState("live");
  const [liveTab, setLiveTab] = useState("running");
  const [form, setForm] = useState(DEFAULT_FORM);
  const dates0 = useMemo(() => defaultBacktestDates(), []);
  const [btForm, setBtForm] = useState({
    ...DEFAULT_FORM,
    ...DEFAULT_DYN,
    ...DEFAULT_BT_STRIKE,
    from: dates0.from,
    to: dates0.to,
  });
  const [history, setHistory] = useState([]);
  const [historyPool, setHistoryPool] = useState([]);
  const [historySummary, setHistorySummary] = useState(EMPTY_LIVE_SUMMARY);
  const [historyNextCursor, setHistoryNextCursor] = useState(null);
  const [historyHasMore, setHistoryHasMore] = useState(false);
  const [historyLoadingMore, setHistoryLoadingMore] = useState(false);
  const [pending, setPending] = useState(false);
  const [localJob, setLocalJob] = useState(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [btShowAdvanced, setBtShowAdvanced] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [btSettingsOpen, setBtSettingsOpen] = useState(false);
  const [advancedConfirmOpen, setAdvancedConfirmOpen] = useState(false);
  const [btAdvancedConfirmOpen, setBtAdvancedConfirmOpen] = useState(false);
  const [forceCloseTrade, setForceCloseTrade] = useState(null);
  const [showForceCloseActions, setShowForceCloseActions] = useState(false);
  const [savedRuns, setSavedRuns] = useState([]);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [viewedResult, setViewedResult] = useState(null);
  const [compareOpen, setCompareOpen] = useState(false);
  const [compareA, setCompareA] = useState("");
  const [compareB, setCompareB] = useState("");
  const [compareRuns, setCompareRuns] = useState([]);
  const lastSyncedBacktestJobKey = useRef(null);

  const config = stOptionsSession?.config;
  const active = stOptionsSession?.active || [];
  const indicator = stOptionsSession?.indicator;
  const backtestJob = stOptionsSession?.backtestJob || localJob;
  const status = stOptionsSession?.status;
  const enabled = Boolean(config?.enabled);
  const hasProductMissing = active.some((t) => t.closeError === "product_missing");
  const showForceClose = showForceCloseActions || hasProductMissing;

  useEffect(() => {
    // Do not clobber in-progress Strategy settings edits with 15s WS snapshots.
    if (config && !settingsOpen) setForm(settingsFromConfig(config));
  }, [config, settingsOpen]);

  const refreshLive = useCallback(async () => {
    if (!token) return;
    const data = await api("/st-options/live", { token });
    onStOptionsSession?.(data);
  }, [token, onStOptionsSession]);

  const applyHistoryPage = useCallback((data, { append = false } = {}) => {
    const raw = data.trades || [];
    const serverPaged =
      Object.prototype.hasOwnProperty.call(data, "hasMore") ||
      Object.prototype.hasOwnProperty.call(data, "nextCursor");

    if (!serverPaged) {
      // Older API returns up to ~200 rows with no cursor — window client-side.
      const pool = append ? raw : raw;
      const visible = pool.slice(0, HISTORY_PAGE_SIZE);
      setHistoryPool(pool);
      setHistory(visible);
      setHistoryNextCursor(null);
      setHistoryHasMore(pool.length > visible.length);
      setHistorySummary(
        data.summary
          ? { ...EMPTY_LIVE_SUMMARY, ...data.summary }
          : computeLiveStrategySummary(pool),
      );
      return;
    }

    setHistoryPool([]);
    setHistory((prev) => (append ? [...prev, ...raw] : raw));
    setHistoryNextCursor(data.nextCursor || null);
    setHistoryHasMore(Boolean(data.hasMore));
    if (data.summary) {
      setHistorySummary({
        ...EMPTY_LIVE_SUMMARY,
        ...data.summary,
      });
    } else if (!append) {
      setHistorySummary(computeLiveStrategySummary(raw));
    }
  }, []);

  const refreshHistory = useCallback(async () => {
    if (!token) return;
    const data = await api(`/st-options/history?limit=${HISTORY_PAGE_SIZE}`, { token });
    applyHistoryPage(data, { append: false });
  }, [token, applyHistoryPage]);

  const loadMoreHistory = useCallback(async () => {
    if (!historyHasMore || historyLoadingMore) return;

    // Client-side window over a full pool (legacy API).
    if (!historyNextCursor && historyPool.length > history.length) {
      const nextLen = Math.min(history.length + HISTORY_PAGE_SIZE, historyPool.length);
      setHistory(historyPool.slice(0, nextLen));
      setHistoryHasMore(nextLen < historyPool.length);
      return;
    }

    if (!token || !historyNextCursor) return;
    setHistoryLoadingMore(true);
    try {
      const q = new URLSearchParams({
        limit: String(HISTORY_PAGE_SIZE),
        cursor: historyNextCursor,
      });
      const data = await api(`/st-options/history?${q.toString()}`, { token });
      applyHistoryPage(data, { append: true });
    } finally {
      setHistoryLoadingMore(false);
    }
  }, [
    token,
    historyHasMore,
    historyNextCursor,
    historyLoadingMore,
    historyPool,
    history.length,
    applyHistoryPage,
  ]);

  const refreshBacktestRuns = useCallback(async () => {
    if (!token) return;
    try {
      const data = await api("/st-options/backtest/runs", { token });
      setSavedRuns(data.runs || []);
    } catch (err) {
      if (isNotFoundError(err)) {
        setSavedRuns([]);
        return;
      }
      throw err;
    }
  }, [token]);

  const loadBacktestConfig = useCallback(async () => {
    if (!token) return;
    const apply = (cfg) => {
      setBtForm((prev) => ({
        ...prev,
        ...btSettingsFromConfig(cfg),
        from: cfg?.from || prev.from || dates0.from,
        to: cfg?.to || prev.to || dates0.to,
      }));
    };
    try {
      const data = await api("/st-options/backtest/config", { token });
      apply(data.config);
    } catch (err) {
      if (isNotFoundError(err)) {
        apply(readLocalBtConfig() || {});
        return;
      }
      throw err;
    }
  }, [token, dates0.from, dates0.to]);

  useEffect(() => {
    if (!token) return undefined;
    let cancelled = false;
    (async () => {
      try {
        await refreshLive();
        const hist = await api(`/st-options/history?limit=${HISTORY_PAGE_SIZE}`, { token });
        if (!cancelled) applyHistoryPage(hist, { append: false });
      } catch (err) {
        if (!cancelled) onNotify?.("error", err.message || "Failed to load strategy");
      }
      try {
        await loadBacktestConfig();
        await refreshBacktestRuns();
      } catch (err) {
        if (!cancelled && !isNotFoundError(err)) {
          onNotify?.("error", err.message || "Failed to load backtest settings");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, refreshLive, onNotify, loadBacktestConfig, refreshBacktestRuns, applyHistoryPage]);

  useEffect(() => {
    if (liveTab === "history" || liveTab === "running") refreshHistory().catch(() => {});
  }, [liveTab, refreshHistory]);

  useEffect(() => {
    if (!backtestJob) return;
    if (backtestJob.status !== "completed" && backtestJob.status !== "failed") return;

    setLocalJob(backtestJob);
    if (backtestJob.status !== "completed" || !backtestJob.result) return;

    const jobKey =
      backtestJob.runId ||
      backtestJob.id ||
      `${backtestJob.status}:${backtestJob.finishedAt || ""}:${backtestJob.progress ?? ""}`;
    const isNewCompletion = lastSyncedBacktestJobKey.current !== jobKey;
    if (isNewCompletion) {
      lastSyncedBacktestJobKey.current = jobKey;
      refreshBacktestRuns().catch(() => {});
    }
    // Live WS keeps re-publishing the latest completed job — never clobber a
    // saved-run selection. Only sync latest into the viewer on Latest / first hydrate.
    if (selectedRunId) return;
    if (isNewCompletion) {
      setViewedResult(backtestJob.result);
    } else {
      setViewedResult((prev) => prev ?? backtestJob.result);
    }
  }, [backtestJob, refreshBacktestRuns, selectedRunId]);

  const liveSummary = historySummary;
  const underlyingCoin = config?.underlying || form.underlying || "BTC";
  const liveMarketPrice = useMemo(
    () => readSpotPrice(livePrices, underlyingCoin),
    [livePrices, underlyingCoin],
  );
  const marketPriceDisplay =
    liveMarketPrice != null
      ? Number(liveMarketPrice).toFixed(2)
      : indicator?.close != null
        ? Number(indicator.close).toFixed(2)
        : "—";

  const requestAdvanced = () => {
    if (showAdvanced) {
      setShowAdvanced(false);
      return;
    }
    setAdvancedConfirmOpen(true);
  };

  const requestBtAdvanced = () => {
    if (btShowAdvanced) {
      setBtShowAdvanced(false);
      return;
    }
    setBtAdvancedConfirmOpen(true);
  };

  const confirmAdvanced = () => {
    setShowAdvanced(true);
    setAdvancedConfirmOpen(false);
  };

  const confirmBtAdvanced = () => {
    setBtShowAdvanced(true);
    setBtAdvancedConfirmOpen(false);
  };

  const saveConfig = async () => {
    setPending(true);
    try {
      // While running, only hedge decay is editable — patch that field alone.
      const body = enabled
        ? { pairHedgeDecayPct: Number(form.pairHedgeDecayPct) }
        : bodyFromForm(form);
      const data = await api("/st-options/config", {
        method: "PATCH",
        token,
        body,
      });
      // Prefer a fresh live snapshot so we don't stomp WS-updated `active`
      // (e.g. hedge just opened) with a stale pre-save session object.
      try {
        const live = await api("/st-options/live", { token });
        onStOptionsSession?.(live);
        if (live.config) setForm(settingsFromConfig(live.config));
      } catch {
        onStOptionsSession?.((current) => ({
          ...(current || {}),
          config: data.config,
        }));
        setForm(settingsFromConfig(data.config));
      }
      onNotify?.("success", "Settings saved.");
      setSettingsOpen(false);
    } catch (err) {
      onNotify?.("error", err.message || "Save failed");
    } finally {
      setPending(false);
    }
  };

  const saveBtConfig = async () => {
    setPending(true);
    try {
      const data = await api("/st-options/backtest/config", {
        method: "PATCH",
        token,
        body: btBodyFromForm(btForm),
      });
      setBtForm((prev) => ({
        ...prev,
        ...btSettingsFromConfig(data.config),
        from: prev.from,
        to: prev.to,
      }));
      writeLocalBtConfig(btForm);
      onNotify?.("success", "Backtest settings saved.");
      setBtSettingsOpen(false);
    } catch (err) {
      if (isNotFoundError(err)) {
        writeLocalBtConfig(btForm);
        onNotify?.(
          "error",
          "Backtest settings API not on server yet — saved in this browser only. Redeploy the backend from arbitrage.",
        );
        setBtSettingsOpen(false);
      } else {
        onNotify?.("error", err.message || "Save failed");
      }
    } finally {
      setPending(false);
    }
  };

  const toggleEngine = async () => {
    setPending(true);
    try {
      const data = enabled
        ? await api("/st-options/stop", { method: "POST", token })
        : await api("/st-options/start", {
            method: "POST",
            token,
            body: bodyFromForm(form),
          });
      onStOptionsSession?.(data);
      const leftover = !enabled ? 0 : (data.active || []).length;
      if (enabled) {
        const missing =
          (data.closeFailures || []).some((f) => f.reason === "product_missing")
          || (data.active || []).some((t) => t.closeError === "product_missing");
        if (missing) setShowForceCloseActions(true);
        onNotify?.(
          leftover > 0 ? "error" : "success",
          leftover > 0
            ? missing
              ? `Strategy turned off — ${leftover} position(s) still open (contract missing). Use Force close.`
              : `Strategy turned off — ${leftover} position(s) still open (close failed).`
            : "Strategy turned off — positions closed."
        );
        refreshHistory().catch(() => {});
      } else {
        onNotify?.("success", "Strategy turned on.");
      }
    } catch (err) {
      onNotify?.("error", err.message || "Could not update strategy");
    } finally {
      setPending(false);
    }
  };

  const closeLeftoverLegs = async () => {
    setPending(true);
    try {
      const data = await api("/st-options/stop", { method: "POST", token });
      onStOptionsSession?.(data);
      const leftover = (data.active || []).length;
      const failures = data.closeFailures || [];
      const missing = failures.some((f) => f.reason === "product_missing")
        || (data.active || []).some((t) => t.closeError === "product_missing");
      if (missing) setShowForceCloseActions(true);
      onNotify?.(
        leftover > 0 ? "error" : "success",
        leftover > 0
          ? missing
            ? `Still ${leftover} open position(s) — contract missing. Use Force close.`
            : `Still ${leftover} open position(s) — close failed. Retry Close positions.`
          : "Open positions closed."
      );
      refreshHistory().catch(() => {});
    } catch (err) {
      onNotify?.("error", err.message || "Could not close positions");
    } finally {
      setPending(false);
    }
  };

  const confirmForceClose = async () => {
    if (!forceCloseTrade?.id) return;
    setPending(true);
    try {
      const data = await api(`/st-options/trades/${forceCloseTrade.id}/force-close`, {
        method: "POST",
        token,
      });
      onStOptionsSession?.(data);
      setForceCloseTrade(null);
      if (!(data.active || []).length) setShowForceCloseActions(false);
      onNotify?.("success", "Position force-closed in records.");
      refreshHistory().catch(() => {});
    } catch (err) {
      onNotify?.("error", err.message || "Force close failed");
    } finally {
      setPending(false);
    }
  };

  const runBacktest = async () => {
    if (!btForm.from || !btForm.to) {
      onNotify?.("error", "Select from and to dates.");
      return;
    }
    setPending(true);
    try {
      try {
        await api("/st-options/backtest/config", {
          method: "PATCH",
          token,
          body: btBodyFromForm(btForm),
        });
      } catch (err) {
        if (!isNotFoundError(err)) throw err;
        writeLocalBtConfig(btForm);
      }
      const job = await api("/st-options/backtest", {
        method: "POST",
        token,
        body: {
          ...btBodyFromForm(btForm),
          from: btForm.from,
          to: btForm.to,
        },
      });
      setLocalJob({ ...job, progress: 0, stage: "starting", trace: [] });
      setViewedResult(null);
      setSelectedRunId("");
      onNotify?.("success", "Backtest started.");
    } catch (err) {
      onNotify?.("error", err.message || "Backtest failed to start");
    } finally {
      setPending(false);
    }
  };

  const loadSavedRun = async (runId) => {
    if (!runId) {
      setSelectedRunId("");
      setViewedResult(backtestJob?.result || null);
      return;
    }
    setPending(true);
    try {
      const data = await api(`/st-options/backtest/runs/${runId}`, { token });
      setSelectedRunId(runId);
      setViewedResult(data.run?.result || null);
      const settings = data.run?.settings || {};
      if (settings.from || settings.to) {
        setBtForm((prev) => ({
          ...prev,
          ...btSettingsFromConfig(settings),
          from: settings.from || prev.from,
          to: settings.to || prev.to,
        }));
      }
    } catch (err) {
      onNotify?.("error", err.message || "Could not load run");
    } finally {
      setPending(false);
    }
  };

  const openCompare = async () => {
    setPending(true);
    try {
      await refreshBacktestRuns();
      const list = await api("/st-options/backtest/runs", { token });
      const summaries = list.runs || [];
      const detailed = [];
      for (const item of summaries.slice(0, 20)) {
        const data = await api(`/st-options/backtest/runs/${item.id}`, { token });
        if (data.run) detailed.push(data.run);
      }
      setCompareRuns(detailed);
      setCompareA(detailed[0]?.id || "");
      setCompareB(detailed[1]?.id || "");
      setCompareOpen(true);
    } catch (err) {
      onNotify?.("error", err.message || "Could not load runs for compare");
    } finally {
      setPending(false);
    }
  };

  const result = viewedResult || backtestJob?.result;
  const progress = Number(backtestJob?.progress || 0);

  const stColour = String(indicator?.stColour || "").toLowerCase();
  const stIsGreen = stColour === "green";
  const stIsRed = stColour === "red";
  const pageTintClass =
    mainTab === "live" && liveTab === "running"
      ? stIsGreen
        ? "st-options-page--green"
        : stIsRed
          ? "st-options-page--red"
          : ""
      : "";
  const stAccentText = stIsGreen
    ? "text-emerald-700 dark:text-emerald-300"
    : stIsRed
      ? "text-rose-700 dark:text-rose-300"
      : "text-slate-700 dark:text-zinc-200";

  return (
    <div className={`${pageShell()} ${pageTintClass} min-h-full flex flex-col`.trim()}>
      <div className={`${pageTitleRow()} shrink-0`}>
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight">ST Options</h1>
          {indicator && mainTab === "live" ? (
            <p className="text-sm mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1">
              <span className={textMuted()}>As of</span>
              <span className={`font-semibold tracking-tight ${stAccentText}`}>
                {indicator.barTimeIst || "—"}
              </span>
              <span className={`${textMuted()} opacity-50`}>·</span>
              <span className={textMuted()}>Bias</span>
              <BiasIcon colour={indicator.stColour} className="w-7 h-7" />
              <span className={`${textMuted()} opacity-50`}>·</span>
              <span className={textMuted()}>Market</span>
              <span className="font-semibold font-mono tracking-tight text-slate-800 dark:text-zinc-100">
                {marketPriceDisplay}
              </span>
            </p>
          ) : (
            <p className={`text-sm mt-1 ${textMuted()}`}>Automated options strategy — BTC / ETH</p>
          )}
        </div>
        <WorkspaceSubTabs tabs={MAIN_TABS} activeId={mainTab} onChange={setMainTab} className="w-full md:w-auto" />
      </div>

      {mainTab === "live" ? (
        <div className={liveTab === "running" ? "flex flex-1 flex-col min-h-0 gap-4" : "space-y-4"}>
          <WorkspaceSubTabs tabs={LIVE_TABS} activeId={liveTab} onChange={setLiveTab} className="w-full md:w-auto shrink-0" />

          {liveTab === "running" ? (
            <div className="flex flex-1 flex-col gap-4 min-h-0">
              <WorkspaceCard className="shrink-0">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="space-y-1">
                    <p className="text-xs font-bold uppercase tracking-widest text-slate-500 dark:text-zinc-500">
                      Strategy {enabled ? "· On" : "· Off"}
                    </p>
                    <p className="text-sm">
                      <span className={textMuted()}>Total PnL </span>
                      <span
                        className={`font-mono font-bold tabular-nums ${
                          Number(liveSummary.totalPnl) > 0
                            ? profitText()
                            : Number(liveSummary.totalPnl) < 0
                              ? lossText()
                              : "text-slate-800 dark:text-zinc-100"
                        }`}
                      >
                        {fmtSummaryMoney(liveSummary.totalPnl)}
                      </span>
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      className="p-2 rounded bg-zinc-100 dark:bg-zinc-800 hover:bg-zinc-200 dark:hover:bg-zinc-700 text-zinc-600 dark:text-zinc-300 hover:text-zinc-900 dark:hover:text-zinc-100 transition"
                      title="Strategy settings"
                      aria-label="Strategy settings"
                      onClick={() => setSettingsOpen(true)}
                    >
                      {GEAR_ICON}
                    </button>
                    <button
                      type="button"
                      className={enabled ? dangerButton() : primaryButton()}
                      disabled={pending}
                      onClick={toggleEngine}
                    >
                      {enabled ? "Turn off" : "Turn on"}
                    </button>
                  </div>
                </div>
              </WorkspaceCard>

              <div className="shrink-0">
                <LiveStrategySummaryStrip summary={liveSummary} />
              </div>

              {enabled || status ? (
                <div className="flex flex-1 flex-col min-h-0">
                  <EngineStatusPanel status={status} enabled={enabled} />
                </div>
              ) : null}

              {!enabled && !active.length ? (
                <p className={`text-sm shrink-0 ${textMuted()}`}>No open positions. Turn the strategy on to start watching.</p>
              ) : null}

              <div className="w-full space-y-4 shrink-0">
                {enabled && active.length
                  ? active.map((trade) => (
                      <ActiveTradeCard
                        key={trade.id}
                        trade={trade}
                        biasColour={indicator?.stColour}
                        hedgeDecayPct={form.pairHedgeDecayPct}
                        forceClosePending={pending}
                        onForceClose={
                          trade.closeError === "product_missing"
                            ? (t) => setForceCloseTrade(t)
                            : undefined
                        }
                      />
                    ))
                  : null}
                {!enabled && active.length > 0 ? (
                  <WorkspaceCard className="w-full space-y-3">
                    <p className="text-xs font-bold uppercase tracking-widest text-rose-600 dark:text-rose-400">
                      Strategy off — {active.length} open position{active.length === 1 ? "" : "s"} still tracked
                    </p>
                    <p className={`text-sm ${textMuted()}`}>
                      These positions are still open. Use Close positions to flatten them.
                      {showForceClose
                        ? " If the contract no longer exists, use Force close to clear the record."
                        : ""}
                    </p>
                    <div className="w-full space-y-3">
                      {active.map((trade) => (
                        <ActiveTradeCard
                          key={trade.id}
                          trade={trade}
                          biasColour={indicator?.stColour}
                          hedgeDecayPct={form.pairHedgeDecayPct}
                          forceClosePending={pending}
                          onForceClose={
                            showForceClose || trade.closeError === "product_missing"
                              ? (t) => setForceCloseTrade(t)
                              : undefined
                          }
                        />
                      ))}
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        className={dangerButton()}
                        disabled={pending}
                        onClick={closeLeftoverLegs}
                      >
                        Close positions
                      </button>
                      {showForceClose
                        ? active.map((trade) => (
                            <button
                              key={`force-${trade.id}`}
                              type="button"
                              className={secondaryButton()}
                              disabled={pending}
                              onClick={() => setForceCloseTrade(trade)}
                            >
                              Force close {trade.optionSymbol || trade.id}
                            </button>
                          ))
                        : null}
                    </div>
                  </WorkspaceCard>
                ) : null}
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              <StOptionsTradeTable
                trades={history}
                emptyMessage="No closed live trades yet."
                badge={`${history.length}${
                  Number(historySummary.trades) > 0 ? ` / ${historySummary.trades}` : ""
                }`}
                bodyClassName="max-h-[min(28rem,55vh)] overflow-auto"
              />
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className={`text-xs ${textMuted()}`}>
                  Showing {history.length}
                  {Number(historySummary.trades) > 0 ? ` of ${historySummary.trades}` : ""} closed trades
                  {historyHasMore ? " · more available" : ""}
                </p>
                {historyHasMore ? (
                  <button
                    type="button"
                    className={secondaryButton()}
                    disabled={historyLoadingMore || pending}
                    onClick={() =>
                      loadMoreHistory().catch((err) =>
                        onNotify?.("error", err.message || "Failed to load more"),
                      )
                    }
                  >
                    {historyLoadingMore ? "Loading…" : "Load more"}
                  </button>
                ) : null}
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-4">
          <WorkspaceCard className="space-y-4">
            <div className="flex flex-wrap items-end gap-3">
              <div className="min-w-[9rem]">
                <WorkspaceField label="From">
                  <WorkspaceInput
                    type="date"
                    value={btForm.from}
                    onChange={(e) => setBtForm((f) => ({ ...f, from: e.target.value }))}
                  />
                </WorkspaceField>
              </div>
              <div className="min-w-[9rem]">
                <WorkspaceField label="To">
                  <WorkspaceInput
                    type="date"
                    value={btForm.to}
                    onChange={(e) => setBtForm((f) => ({ ...f, to: e.target.value }))}
                  />
                </WorkspaceField>
              </div>
              <div className="min-w-[14rem] flex-1">
                <WorkspaceField label="Saved runs">
                  <WorkspaceSelect
                    value={selectedRunId}
                    onChange={(e) => loadSavedRun(e.target.value)}
                    disabled={pending}
                  >
                    <option value="">Latest / current job</option>
                    {savedRuns.map((run) => (
                      <option key={run.id} value={run.id}>
                        {(run.from || "?") + " → " + (run.to || "?")} · PnL {Number(run.totalPnl || 0).toFixed(2)} ·{" "}
                        {run.totalTrades ?? 0} trades
                      </option>
                    ))}
                  </WorkspaceSelect>
                </WorkspaceField>
              </div>
              <div className="flex items-center gap-2 pb-0.5">
                <button
                  type="button"
                  className="p-2 rounded bg-zinc-100 dark:bg-zinc-800 hover:bg-zinc-200 dark:hover:bg-zinc-700 text-zinc-600 dark:text-zinc-300"
                  title="Backtest settings"
                  aria-label="Backtest settings"
                  onClick={() => setBtSettingsOpen(true)}
                >
                  {GEAR_ICON}
                </button>
                <button
                  type="button"
                  className={secondaryButton()}
                  disabled={pending || savedRuns.length < 2}
                  onClick={openCompare}
                >
                  Compare
                </button>
                <button
                  type="button"
                  className={primaryButton()}
                  disabled={pending || backtestJob?.status === "processing"}
                  onClick={runBacktest}
                >
                  Run backtest
                </button>
              </div>
            </div>
            {btForm.dynamicSizingEnabled ? (
              <p className={`text-xs ${textMuted()}`}>
                Dynamic sizing on — after {btForm.dynAfterLosses} losses +{btForm.dynIncreasePct}% of base risk
                (cap {btForm.dynMaxRiskPct}%); after {btForm.dynAfterProfits} profits −{btForm.dynDecreasePct}% of
                base. Lots sized from max risk ${btForm.maxRisk} and stop loss {btForm.stopLossPct}%.
              </p>
            ) : null}
            {backtestJob?.status === "processing" ? (
              <div className="space-y-2">
                <WorkspaceProgressBar value={progress} />
                <p className={`text-xs ${textMuted()}`}>
                  {backtestJob.stage || "processing"} · {progress}%
                </p>
              </div>
            ) : null}
            {backtestJob?.status === "failed" ? (
              <p className={`text-sm ${lossText()}`}>{backtestJob.error || "Backtest failed"}</p>
            ) : null}
            {(backtestJob?.trace || []).length ? (
              <pre className={`text-[10px] font-mono max-h-32 overflow-auto ${textMuted()}`}>
                {(backtestJob.trace || []).slice(-12).join("\n")}
              </pre>
            ) : null}
          </WorkspaceCard>

          {result?.summary ? <StOptionsSummaryGrid summary={result.summary} /> : null}
          {result?.diagnostics && Number(result?.summary?.totalTrades || 0) === 0 ? (
            <p className={`text-sm ${textMuted()}`}>
              {Number(result.diagnostics.entrySignals || 0)} signals,{" "}
              {Number(result.diagnostics.skippedNoContract || 0) +
                Number(result.diagnostics.skippedNoPremium || 0)}{" "}
              skipped
              {Number(result.diagnostics.skippedNoPremium || 0) > 0
                ? ` — ${result.diagnostics.skippedNoPremium} no suitable option price (try lowering Minimum option price %)`
                : ""}
              {Number(result.diagnostics.skippedNoContract || 0) > 0
                ? ` — ${result.diagnostics.skippedNoContract} no matching contract`
                : ""}
              .
            </p>
          ) : null}
          {result?.trades ? <StOptionsTradeTable trades={result.trades} /> : null}
        </div>
      )}

      <StrategySettingsModal
        open={settingsOpen}
        form={form}
        setForm={setForm}
        disabled={enabled || pending}
        hedgeEditableWhileLocked={enabled && !pending}
        pending={pending}
        showAdvanced={showAdvanced}
        onRequestAdvanced={requestAdvanced}
        onHideAdvanced={() => setShowAdvanced(false)}
        onSave={saveConfig}
        onClose={() => {
          setSettingsOpen(false);
          if (config) setForm(settingsFromConfig(config));
        }}
      />

      <StrategySettingsModal
        open={btSettingsOpen}
        title="Backtest settings"
        form={btForm}
        setForm={setBtForm}
        disabled={pending || backtestJob?.status === "processing"}
        pending={pending}
        showAdvanced={btShowAdvanced}
        onRequestAdvanced={requestBtAdvanced}
        onHideAdvanced={() => setBtShowAdvanced(false)}
        onSave={saveBtConfig}
        onClose={() => setBtSettingsOpen(false)}
        showDynamicSizing
      />

      <StOptionsBacktestCompareModal
        open={compareOpen}
        runs={compareRuns}
        runAId={compareA}
        runBId={compareB}
        onChangeA={setCompareA}
        onChangeB={setCompareB}
        onClose={() => setCompareOpen(false)}
      />

      <WorkspaceConfirmDialog
        open={advancedConfirmOpen}
        title="Advanced settings"
        confirmLabel="Show Advanced"
        onConfirm={confirmAdvanced}
        onCancel={() => setAdvancedConfirmOpen(false)}
        danger
      >
        <p>
          Changing Advanced settings is <strong>not recommended</strong>. These values change when setups open or
          close and can make results harder to reason about.
        </p>
        <p className={textMuted()}>Only continue if you understand the consequences.</p>
      </WorkspaceConfirmDialog>

      <WorkspaceConfirmDialog
        open={btAdvancedConfirmOpen}
        title="Advanced backtest settings"
        confirmLabel="Show Advanced"
        onConfirm={confirmBtAdvanced}
        onCancel={() => setBtAdvancedConfirmOpen(false)}
        danger
      >
        <p>
          Changing Advanced settings is <strong>not recommended</strong>. These values change when setups open or
          close and can make results harder to reason about.
        </p>
        <p className={textMuted()}>Only continue if you understand the consequences.</p>
      </WorkspaceConfirmDialog>

      <WorkspaceConfirmDialog
        open={Boolean(forceCloseTrade)}
        title="Force close position"
        confirmLabel="Force close"
        onConfirm={confirmForceClose}
        onCancel={() => setForceCloseTrade(null)}
        danger
      >
        <p>
          This marks <strong>{forceCloseTrade?.optionSymbol || "the position"}</strong> closed in CryptoBridge
          records without sending a broker order. Use only when the contract no longer exists and Close positions
          failed.
        </p>
      </WorkspaceConfirmDialog>
    </div>
  );
}
