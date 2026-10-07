import { useEffect, useMemo, useState } from "react";
import { api } from "../../api";
import { pageShell } from "../../utils/workspace/workspaceClasses";
import { decoratePositionsPayload } from "../positions/positionsUtils";
import {
  buildDashboardModel,
  computePortfolioMetrics,
  fetchDashboardTradeHistory,
  mergeDashboardPositions,
} from "./dashboardUtils";
import DashboardKpiGrid from "./DashboardKpiGrid";
import DashboardEquityChart from "./DashboardEquityChart";
import DashboardRecentTrades from "./DashboardRecentTrades";
import DashboardAccountsList from "./DashboardAccountsList";
import DashboardPositionsPreview from "./DashboardPositionsPreview";

export default function DashboardPage({
  token,
  me,
  accounts,
  positionsPayload,
  livePrices,
  onNavigate,
  onAccountSelect,
}) {
  const [tradeHistory, setTradeHistory] = useState([]);
  const [restPositionsPayload, setRestPositionsPayload] = useState(null);
  const [rangeId, setRangeId] = useState("1m");

  const rawPositions = useMemo(
    () => mergeDashboardPositions(restPositionsPayload, positionsPayload),
    [restPositionsPayload, positionsPayload],
  );

  const decoratedPositions = useMemo(
    () => decoratePositionsPayload(rawPositions, livePrices),
    [rawPositions, livePrices],
  );

  const selectedAccountId = me?.selectedAccountId || me?.selected_account_id || "";

  const metrics = useMemo(
    () => computePortfolioMetrics({
      accounts,
      positionsPayload: decoratedPositions,
      selectedAccountId,
    }),
    [accounts, decoratedPositions, selectedAccountId],
  );

  const model = useMemo(
    () => buildDashboardModel({
      accounts,
      scopeId: "all",
      positionsPayload: decoratedPositions,
      tradeHistory,
      rangeId,
    }),
    [accounts, decoratedPositions, tradeHistory, rangeId],
  );

  useEffect(() => {
    if (!token) {
      setTradeHistory([]);
      return undefined;
    }
    let cancelled = false;
    (async () => {
      try {
        const trades = await fetchDashboardTradeHistory(api, token);
        if (!cancelled) setTradeHistory(trades);
      } catch {
        if (!cancelled) setTradeHistory([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  useEffect(() => {
    if (!token) {
      setRestPositionsPayload(null);
      return undefined;
    }
    let cancelled = false;
    (async () => {
      try {
        const data = await api("/positions/open", { token });
        if (!cancelled) setRestPositionsPayload(data);
      } catch {
        if (!cancelled) setRestPositionsPayload(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const openPositions = model.openPositions;

  return (
    <div className={`${pageShell()} space-y-6`}>
      <DashboardKpiGrid metrics={metrics} accountCount={accounts.length} />
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <DashboardEquityChart
          points={model.equityCurve}
          rangeId={rangeId}
          onRangeChange={setRangeId}
          closedPnl={model.closedPnl}
          winRate={model.winRate}
          maxDrawdownUsd={model.maxDrawdownUsd}
          closedCount={model.closedCount}
        />
        <DashboardRecentTrades trades={tradeHistory} />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <DashboardAccountsList
          accounts={accounts}
          selectedAccountId={selectedAccountId}
          onSelectAccount={onAccountSelect}
        />
        <DashboardPositionsPreview
          positions={openPositions}
          accounts={accounts}
          onNavigate={onNavigate}
        />
      </div>
    </div>
  );
}
