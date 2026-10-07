import { useEffect, useMemo, useState } from "react";
import { api } from "../../api";
import { readAvailableMargin, formatMargin } from "../../utils/accountMargin";
import { pageShell, primaryButton, textMuted } from "../../utils/workspace/workspaceClasses";
import WorkspaceCard from "../ui/WorkspaceCard";
import { WorkspaceField, WorkspaceInput } from "../ui/WorkspaceField";
import TradeEconomics from "../TradeEconomics";
import ExecutionOptionSearch from "./ExecutionOptionSearch";
import ExecutionMonitorTable from "./ExecutionMonitorTable";
import {
  formatOptionPrice,
  lotsHint,
  readOptionLivePrice,
  readSpotPrice,
  willExecuteImmediately,
} from "./executionUtils";

export default function ExecutionPage({
  token,
  me,
  accounts,
  livePrices,
  executionMonitors,
  onNotify,
}) {
  const [selectedOption, setSelectedOption] = useState(null);
  const [quantityLots, setQuantityLots] = useState("1");
  const [entrySpotLevel, setEntrySpotLevel] = useState("");
  const [spotStopLevel, setSpotStopLevel] = useState("");
  const [preview, setPreview] = useState(null);
  const [pending, setPending] = useState(false);

  const selectedAccountId = me?.selectedAccountId || me?.selected_account_id || "";
  const selectedAccount = useMemo(
    () => (accounts || []).find((row) => row.id === selectedAccountId) || null,
    [accounts, selectedAccountId],
  );

  const underlying = selectedOption?.underlying || "";
  const optionLivePrice = useMemo(
    () => readOptionLivePrice(livePrices, selectedOption?.symbol),
    [livePrices, selectedOption?.symbol],
  );
  const spotPrice = useMemo(
    () => readSpotPrice(livePrices, underlying),
    [livePrices, underlying],
  );
  const availableMargin = readAvailableMargin(selectedAccount);
  const immediate = willExecuteImmediately(selectedOption, spotPrice);

  useEffect(() => {
    if (!token || !selectedOption?.symbol) {
      setPreview(null);
      return undefined;
    }
    const lots = Number(quantityLots);
    if (!Number.isFinite(lots) || lots < 1) {
      setPreview(null);
      return undefined;
    }
    const handle = window.setTimeout(async () => {
      try {
        const data = await api("/execution/preview", {
          method: "POST",
          token,
          body: { symbol: selectedOption.symbol, quantityLots: Math.floor(lots) },
        });
        setPreview(data);
      } catch {
        setPreview(null);
      }
    }, 300);
    return () => window.clearTimeout(handle);
  }, [token, selectedOption, quantityLots]);

  const handleExecute = async () => {
    if (!selectedOption) {
      onNotify?.("error", "Select an option first.");
      return;
    }
    if (!selectedAccountId) {
      onNotify?.("error", "Select a trading account first.");
      return;
    }
    const lots = Number(quantityLots);
    const entry = Number(entrySpotLevel);
    const stop = Number(spotStopLevel);
    if (!Number.isFinite(lots) || lots < 1) {
      onNotify?.("error", "Enter a valid quantity in lots.");
      return;
    }
    if (!Number.isFinite(entry) || entry <= 0) {
      onNotify?.("error", "Enter a valid entry spot level.");
      return;
    }
    if (!Number.isFinite(stop) || stop <= 0) {
      onNotify?.("error", "Enter a valid spot stop-loss level.");
      return;
    }
    setPending(true);
    try {
      const data = await api("/execution/trade", {
        method: "POST",
        token,
        body: {
          optionSymbol: selectedOption.symbol,
          quantityLots: Math.floor(lots),
          entrySpotLevel: entry,
          spotStopLevel: stop,
        },
      });
      onNotify?.("success", `Monitor armed: ${data.monitor?.status || "Pending Trigger"}`);
      setEntrySpotLevel("");
      setSpotStopLevel("");
    } catch (err) {
      onNotify?.("error", err.message || "Could not arm monitor.");
    } finally {
      setPending(false);
    }
  };

  const handleCancel = async (monitorId) => {
    if (!monitorId) return;
    setPending(true);
    try {
      await api(`/execution/monitors/${monitorId}/cancel`, { method: "POST", token });
      onNotify?.("success", "Monitor cancelled.");
    } catch (err) {
      onNotify?.("error", err.message || "Cancel failed.");
    } finally {
      setPending(false);
    }
  };

  return (
    <div className={`${pageShell()} space-y-6`}>
      <div>
        <h1 className="text-lg font-extrabold tracking-tight">Execution</h1>
        <p className={`text-sm ${textMuted()}`}>
          Sell BTC/ETH options with spot-triggered entry and spot-index stop-loss monitoring.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <WorkspaceCard>
          <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-zinc-500 mb-4">
            Option Setup
          </h2>
          <ExecutionOptionSearch
            token={token}
            livePrices={livePrices}
            selected={selectedOption}
            onSelect={setSelectedOption}
          />
          {selectedOption ? (
            <div className="mt-4 rounded-lg border border-lime-400/40 bg-lime-400/10 px-3 py-2.5">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className={`text-[10px] font-bold uppercase tracking-wider ${textMuted()}`}>
                    Selected to sell
                  </p>
                  <p className="font-mono text-sm font-semibold truncate">{selectedOption.symbol}</p>
                  <p className={`text-xs ${textMuted()}`}>
                    {selectedOption.underlying} {selectedOption.optionType} · strike {selectedOption.strikePrice}
                  </p>
                </div>
                <div className="text-right shrink-0">
                  <p className={`text-[10px] font-bold uppercase tracking-wider ${textMuted()}`}>Live premium</p>
                  <p className="font-mono text-sm font-bold text-lime-700 dark:text-lime-400 tabular-nums">
                    {optionLivePrice != null ? `$${formatOptionPrice(optionLivePrice)}` : "—"}
                  </p>
                </div>
              </div>
            </div>
          ) : null}
          <div className="mt-4 grid grid-cols-2 gap-3">
            <WorkspaceField label="Side">
              <WorkspaceInput value="Sell" readOnly />
            </WorkspaceField>
            <WorkspaceField label="Quantity (lots)" hint={lotsHint(underlying)}>
              <WorkspaceInput
                type="number"
                min="1"
                step="1"
                value={quantityLots}
                onChange={(event) => setQuantityLots(event.target.value)}
              />
            </WorkspaceField>
          </div>
        </WorkspaceCard>

        <WorkspaceCard>
          <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-zinc-500 mb-4">
            Spot Risk Control
          </h2>
          <div className="space-y-3">
            <WorkspaceField label={`Current ${underlying || "spot"} price`}>
              <WorkspaceInput value={spotPrice != null ? String(spotPrice) : "—"} readOnly />
            </WorkspaceField>
            <WorkspaceField label="Entry spot level">
              <WorkspaceInput
                type="number"
                step="any"
                value={entrySpotLevel}
                onChange={(event) => setEntrySpotLevel(event.target.value)}
                placeholder="Trigger level for sell entry"
              />
            </WorkspaceField>
            <WorkspaceField label="Stop-loss on spot">
              <WorkspaceInput
                type="number"
                step="any"
                value={spotStopLevel}
                onChange={(event) => setSpotStopLevel(event.target.value)}
                placeholder="Square off when spot breaches"
              />
            </WorkspaceField>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <span className={`block text-[10px] uppercase font-bold ${textMuted()}`}>Available margin</span>
                <span className="font-semibold">{formatMargin(availableMargin)}</span>
              </div>
              <div>
                <span className={`block text-[10px] uppercase font-bold ${textMuted()}`}>Required margin</span>
                <span className="font-semibold">
                  {preview?.required_margin != null
                    ? formatMargin(preview.required_margin, preview.margin_currency || "USD")
                    : "—"}
                </span>
              </div>
            </div>
            <TradeEconomics preview={preview} />
            {immediate ? (
              <p className="text-xs font-semibold text-amber-700 dark:text-amber-300">
                This trade will execute immediately once armed (option is in the money vs current spot).
              </p>
            ) : null}
            <button
              type="button"
              className={primaryButton("w-full")}
              disabled={pending || !selectedOption}
              onClick={handleExecute}
            >
              Execute &amp; Monitor
            </button>
          </div>
        </WorkspaceCard>
      </div>

      <ExecutionMonitorTable
        monitors={executionMonitors}
        onCancel={handleCancel}
        pending={pending}
      />
    </div>
  );
}
