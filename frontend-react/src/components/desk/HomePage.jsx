import { useEffect, useMemo, useState } from "react";
import { Activity, BookOpen, TrendingDown, TrendingUp } from "lucide-react";
import { motion } from "framer-motion";
import { api } from "../../api";
import CoinIcon from "../CoinIcon";
import { decoratePositionRow } from "../positions/positionsUtils";
import MarketOutlook from "./MarketOutlook";
import PriceFlashTicker from "./PriceFlashTicker";
import AreaChart from "./AreaChart";
import WatchlistRail from "./WatchlistRail";
import {
  cumulativeSeries,
  formatIst,
  formatPercent,
  formatPrice,
  ledgerMuted,
  ledgerPanel,
  money,
  monthGroups,
  pnlClass,
  pnlPill,
  seriesChangePercent,
  sumVenue,
} from "./deskFormat";

function newerBook(rest, live) {
  if (!live || live.type !== "positions") return rest;
  if (!rest) return live;
  const liveAt = Date.parse(live.updatedAt || "") || 0;
  const restAt = Date.parse(rest.updatedAt || "") || 0;
  return liveAt >= restAt ? live : rest;
}

function sideLabel(side) {
  const value = String(side || "").toUpperCase();
  if (value === "LONG" || value === "BUY") return "Buy";
  if (value === "SHORT" || value === "SELL") return "Sell";
  return value || "—";
}

function sizeLabel(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  return String(number);
}

export default function HomePage({ token, entries, watchlist, livePrices, positionsPayload, forecasts, onOpenTrade, onWatchlistChange, onNotify, onOpenJournal }) {
  const [restBook, setRestBook] = useState(null);
  useEffect(() => {
    if (!token) return undefined;
    let cancelled = false;
    const load = () => {
      api("/positions/open", { token })
        .then((data) => {
          if (!cancelled) setRestBook(data);
        })
        .catch(() => {});
    };
    load();
    const timer = setInterval(load, 10000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [token]);

  const book = useMemo(() => newerBook(restBook, positionsPayload), [restBook, positionsPayload]);
  const positions = useMemo(
    () => (book?.openPositions || []).map((row) => decoratePositionRow(row, livePrices)),
    [book, livePrices],
  );
  const orders = book?.openOrders || [];
  const recent = entries.slice(0, 5);
  const crypto = cumulativeSeries(entries, "crypto");
  const forex = cumulativeSeries(entries, "forex");
  const combined = cumulativeSeries(entries);
  const months = monthGroups(entries);
  const cards = [
    ["Combined", sumVenue(entries), combined],
    ["Crypto", sumVenue(entries, "crypto"), crypto],
    ["Forex", sumVenue(entries, "forex"), forex],
  ];

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_auto]">
      <div className="space-y-4">
        {positions.length || orders.length ? (
          <div className={`grid gap-3 ${positions.length && orders.length ? "md:grid-cols-2" : ""}`}>
            {positions.length ? <RunningPositions rows={positions} /> : null}
            {orders.length ? <PendingOrders rows={orders} /> : null}
          </div>
        ) : null}
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          {cards.map(([label, value, series]) => {
            const change = seriesChangePercent(series);
            const TrendIcon = Number(value) > 0 ? TrendingUp : Number(value) < 0 ? TrendingDown : Activity;
            return (
              <motion.section
                key={label}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className={`relative overflow-hidden px-4 py-3 ${ledgerPanel}`}
              >
                <div className="pointer-events-none relative z-10">
                  <p className={`flex items-center gap-1.5 text-xs uppercase tracking-[0.16em] ${ledgerMuted}`}>
                    <TrendIcon size={14} className={pnlClass(value)} />
                    {label}
                  </p>
                  <div className="mt-2 flex items-end justify-between gap-2">
                    <p className={`text-2xl font-semibold ${pnlClass(value)}`}>{money(value)}</p>
                    {change != null ? <span className={pnlPill(change)}>{formatPercent(change)}</span> : null}
                  </div>
                </div>
                <div className="absolute inset-x-2 bottom-0 opacity-80">
                  <AreaChart values={series} positive={(series.at(-1) ?? 0) >= 0} className="h-12" quiet />
                </div>
              </motion.section>
            );
          })}
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <section className={`p-4 ${ledgerPanel}`}>
            <h2 className={`flex items-center gap-1.5 text-sm ${ledgerMuted}`}>
              {(crypto.at(-1) ?? 0) >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
              Crypto P/L
            </h2>
            <AreaChart values={crypto} positive={(crypto.at(-1) ?? 0) >= 0} />
          </section>
          <section className={`p-4 ${ledgerPanel}`}>
            <h2 className={`flex items-center gap-1.5 text-sm ${ledgerMuted}`}>
              {(forex.at(-1) ?? 0) >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
              Forex P/L
            </h2>
            <AreaChart values={forex} positive={(forex.at(-1) ?? 0) >= 0} />
          </section>
        </div>
        <div className="grid gap-3 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
          <section className={`p-4 ${ledgerPanel}`}>
            <h2 className={`flex items-center gap-1.5 text-sm ${ledgerMuted}`}>
              <Activity size={14} />
              Equity
            </h2>
            <AreaChart values={combined} positive={(combined.at(-1) ?? 0) >= 0} className="h-56" />
          </section>
          <section className={`p-4 ${ledgerPanel}`}>
            <div className="flex items-center justify-between">
              <h2 className={`text-sm ${ledgerMuted}`}>Day P/L</h2>
              <p className={`text-xs ${ledgerMuted}`}>Profit · loss · flat</p>
            </div>
            <div className="mt-4 space-y-4">
              {months.length === 0 ? (
                <EmptyState title="No day squares yet" body="Saved trades fill this grid." onAction={onOpenJournal} />
              ) : null}
              {months.map((month) => (
                <div key={month.id}>
                  <p className={`mb-2 text-xs uppercase tracking-[0.14em] ${ledgerMuted}`}>{month.label}</p>
                  <div className="flex flex-wrap gap-1.5">
                    {month.days.map((day, index) => {
                      const tone = day.net > 0 ? "bg-[var(--ledger-profit)]" : day.net < 0 ? "bg-[var(--ledger-loss)]" : "bg-slate-400/40";
                      return (
                        <motion.span
                          key={day.key}
                          title={`${day.key} ${money(day.net)}`}
                          initial={{ opacity: 0, scale: 0.8 }}
                          animate={{ opacity: 1, scale: 1 }}
                          transition={{ delay: index * 0.02 }}
                          className={`h-3.5 w-3.5 rounded-[3px] ${tone}`}
                        />
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>
        <MarketOutlook token={token} livePrices={livePrices} forecasts={forecasts} />
        <section className={`p-4 ${ledgerPanel}`}>
          <h2 className={`text-sm ${ledgerMuted}`}>Recent trades</h2>
          {recent.length === 0 ? (
            <EmptyState title="No saved trades" body="The five newest saved trades appear in this table." onAction={onOpenJournal} />
          ) : (
            <table className="mt-3 w-full text-left text-sm">
              <thead className={`text-xs uppercase tracking-wider ${ledgerMuted}`}>
                <tr>
                  <th className="py-2 font-medium">Symbol</th>
                  <th className="py-2 font-medium">Account</th>
                  <th className="py-2 font-medium">Venue</th>
                  <th className="py-2 font-medium">Time</th>
                  <th className="py-2 text-right font-medium">P/L</th>
                </tr>
              </thead>
              <tbody>
                {recent.map((trade) => (
                  <tr
                    key={trade.id || trade.sourceTradeId}
                    className="cursor-pointer border-t border-[var(--ledger-border)]"
                    onClick={() => onOpenTrade(trade)}
                  >
                    <td className="py-2">
                      <span className="inline-flex items-center gap-2">
                        <CoinIcon coin={trade.symbol} size={18} />
                        {trade.symbol}
                      </span>
                    </td>
                    <td className="py-2">{trade.accountName}</td>
                    <td className={`py-2 capitalize ${ledgerMuted}`}>{trade.venue}</td>
                    <td className={`py-2 ${ledgerMuted}`}>{formatIst(trade.exitTimeIst)}</td>
                    <td className="py-2 text-right"><span className={pnlPill(trade.netPnl)}>{money(trade.netPnl)}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>
      <WatchlistRail
        token={token}
        watchlist={watchlist}
        livePrices={livePrices}
        onChanged={onWatchlistChange}
        onNotify={onNotify}
      />
    </div>
  );
}

function RunningPositions({ rows }) {
  return (
    <section className={`p-4 ${ledgerPanel}`}>
      <h2 className={`text-sm ${ledgerMuted}`}>Running positions</h2>
      <table className="mt-3 w-full text-left text-sm">
        <thead className={`text-xs uppercase tracking-wider ${ledgerMuted}`}>
          <tr>
            <th className="py-2 font-medium">Symbol</th>
            <th className="py-2 font-medium">Side</th>
            <th className="py-2 text-right font-medium">Size</th>
            <th className="py-2 text-right font-medium">Entry</th>
            <th className="py-2 text-right font-medium">Mark</th>
            <th className="py-2 text-right font-medium">P/L</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className="border-t border-[var(--ledger-border)]">
              <td className="py-2">
                <span className="block">{row.symbol}</span>
                <span className={`block text-xs capitalize ${ledgerMuted}`}>{row.accountName} · {row.venue}</span>
              </td>
              <td className="py-2">{sideLabel(row.side)}</td>
              <td className="py-2 text-right">{sizeLabel(row.size)}</td>
              <td className="py-2 text-right">{formatPrice(row.entryPrice)}</td>
              <td className="py-2 text-right">
                <PriceFlashTicker value={row.markPrice}>{formatPrice(row.markPrice)}</PriceFlashTicker>
              </td>
              <td className="py-2 text-right">
                <PriceFlashTicker value={row.unrealizedPnlUsd}>
                  <span className={pnlPill(row.unrealizedPnlUsd)}>{money(row.unrealizedPnlUsd)}</span>
                </PriceFlashTicker>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function PendingOrders({ rows }) {
  return (
    <section className={`p-4 ${ledgerPanel}`}>
      <h2 className={`text-sm ${ledgerMuted}`}>Pending orders</h2>
      <table className="mt-3 w-full text-left text-sm">
        <thead className={`text-xs uppercase tracking-wider ${ledgerMuted}`}>
          <tr>
            <th className="py-2 font-medium">Symbol</th>
            <th className="py-2 font-medium">Side</th>
            <th className="py-2 font-medium">Type</th>
            <th className="py-2 text-right font-medium">Price</th>
            <th className="py-2 text-right font-medium">Size</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className="border-t border-[var(--ledger-border)]">
              <td className="py-2">
                <span className="block">{row.symbol}</span>
                <span className={`block text-xs capitalize ${ledgerMuted}`}>{row.accountName} · {row.venue}</span>
              </td>
              <td className="py-2">{sideLabel(row.side)}</td>
              <td className={`py-2 capitalize ${ledgerMuted}`}>{row.orderType || "—"}</td>
              <td className="py-2 text-right">{formatPrice(row.price)}</td>
              <td className="py-2 text-right">{sizeLabel(row.size ?? row.unfilledSize)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function EmptyState({ title, body, onAction }) {
  return (
    <div className="flex flex-col items-center px-4 py-8 text-center">
      <BookOpen size={22} className={ledgerMuted} />
      <p className="mt-2 text-sm">{title}</p>
      <p className={`mt-1 text-sm ${ledgerMuted}`}>{body}</p>
      <button type="button" onClick={onAction} className="mt-3 rounded-full bg-[var(--ledger-accent)] px-4 py-2 text-sm text-white">
        + Log Trade
      </button>
    </div>
  );
}
