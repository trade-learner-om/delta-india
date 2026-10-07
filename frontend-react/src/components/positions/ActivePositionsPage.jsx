import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../../api";
import {
  decoratePositionsPayload,
  groupByBroker,
  mergePositionsPayload,
} from "./positionsUtils";
import { buildSelectedPositionsPayoff } from "./positionsPayoff";
import { computePositionsTotals } from "./positionsWorkspaceUtils";
import { pageShell, pageTitleRow, primaryButton, accentText, textHeading, textMuted } from "../../utils/workspace/workspaceClasses";
import PositionsSubTabs from "./PositionsSubTabs";
import PositionsKpiRow from "./PositionsKpiRow";
import PositionsOpenLedger from "./PositionsOpenLedger";
import PositionsOpenOrdersTable from "./PositionsOpenOrdersTable";
import PositionsPastOrdersTable from "./PositionsPastOrdersTable";
import PositionsPayoffTab from "./PositionsPayoffTab";

export default function ActivePositionsPage({ token, onNotify, positionsPayload, livePrices = {} }) {
  const [restPayload, setRestPayload] = useState(null);
  const [historyPayload, setHistoryPayload] = useState(null);
  const [loading, setLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [tab, setTab] = useState("open");
  const [selectedIds, setSelectedIds] = useState([]);

  const loadOpen = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const data = await api("/positions/open", { token });
      setRestPayload(data);
    } catch (err) {
      onNotify?.("error", err.message || "Could not load positions.");
    } finally {
      setLoading(false);
    }
  }, [token, onNotify]);

  const loadHistory = useCallback(async () => {
    if (!token) return;
    setHistoryLoading(true);
    try {
      const data = await api("/positions/history?broker=all", { token });
      setHistoryPayload(data);
    } catch (err) {
      onNotify?.("error", err.message || "Could not load order history.");
    } finally {
      setHistoryLoading(false);
    }
  }, [token, onNotify]);

  useEffect(() => {
    loadOpen();
  }, [loadOpen]);

  useEffect(() => {
    if (tab === "history") loadHistory();
  }, [tab, loadHistory]);

  const rawPayload = useMemo(
    () => mergePositionsPayload(restPayload, positionsPayload),
    [restPayload, positionsPayload],
  );
  const payload = useMemo(
    () => decoratePositionsPayload(rawPayload, livePrices),
    [rawPayload, livePrices],
  );

  const brokerPositions = payload?.openPositions || [];
  const openOrders = payload?.openOrders || [];
  const ordersByBroker = useMemo(() => groupByBroker(openOrders), [openOrders]);
  const historyOrders = historyPayload?.ordersByBroker?.delta || [];
  const totals = useMemo(() => computePositionsTotals(brokerPositions), [brokerPositions]);

  useEffect(() => {
    setSelectedIds((current) => current.filter((id) => brokerPositions.some((row) => row.id === id)));
  }, [brokerPositions]);

  const selectedRows = useMemo(
    () => brokerPositions.filter((row) => selectedIds.includes(row.id)),
    [brokerPositions, selectedIds],
  );

  const payoff = useMemo(() => {
    if (tab !== "payoff" || selectedRows.length === 0) return null;
    return buildSelectedPositionsPayoff(selectedRows, livePrices);
  }, [tab, selectedRows, livePrices]);

  const refresh = () => {
    loadOpen();
    if (tab === "history") loadHistory();
  };

  const toggleRow = (id) => {
    setSelectedIds((current) => (current.includes(id) ? current.filter((item) => item !== id) : [...current, id]));
  };
  const toggleAll = () => {
    setSelectedIds((current) => (current.length === brokerPositions.length ? [] : brokerPositions.map((row) => row.id)));
  };

  const accounts = payload?.accounts || [];

  return (
    <div className={pageShell()}>
      <div className={pageTitleRow()}>
        <div>
          <p className={`text-[10px] font-bold uppercase tracking-wider ${accentText()}`}>Live execution</p>
          <h1 className={`text-2xl font-extrabold tracking-tight ${textHeading()}`}>Active Positions</h1>
          <p className={`text-xs mt-1 ${textMuted()}`}>All open Delta positions and orders across connected accounts.</p>
        </div>
        <button
          type="button"
          onClick={refresh}
          disabled={loading || historyLoading}
          className={primaryButton()}
        >
          {loading || historyLoading ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      <PositionsSubTabs
        activeId={tab}
        onChange={setTab}
        openCount={payload?.openCount ?? brokerPositions.length}
        pastCount={historyOrders.length}
      />

      {tab === "open" ? (
        <div className="space-y-6">
          <PositionsKpiRow totals={totals} />
          <PositionsOpenLedger
            rows={brokerPositions}
            accounts={accounts}
            loading={loading}
            selectedIds={selectedIds}
            onToggleRow={toggleRow}
            onToggleAll={toggleAll}
          />
          <PositionsOpenOrdersTable orders={ordersByBroker.delta} />
        </div>
      ) : null}

      {tab === "history" ? (
        <PositionsPastOrdersTable orders={historyOrders} loading={historyLoading} />
      ) : null}

      {tab === "payoff" ? (
        <div className="space-y-4">
          {selectedIds.length === 0 ? (
            <p className={`text-xs ${textMuted()}`}>Select positions on the Open tab, then return here to simulate payoff.</p>
          ) : (
            <p className={`text-xs ${textMuted()}`}>{selectedIds.length} position(s) selected for payoff.</p>
          )}
          <PositionsPayoffTab payoff={payoff} selectedCount={selectedIds.length} />
        </div>
      ) : null}
    </div>
  );
}
