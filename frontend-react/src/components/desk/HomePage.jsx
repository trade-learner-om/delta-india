import { motion } from "framer-motion";
import AreaChart from "./AreaChart";
import WatchlistRail from "./WatchlistRail";
import { cumulativeSeries, formatIst, money, monthGroups, pnlClass, sumVenue } from "./deskFormat";

export default function HomePage({ token, entries, watchlist, livePrices, onOpenTrade, onWatchlistChange, onNotify }) {
  const recent = entries.slice(0, 5);
  const crypto = cumulativeSeries(entries, "crypto");
  const forex = cumulativeSeries(entries, "forex");
  const months = monthGroups(entries);

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_auto]">
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-3">
          {[
            ["Combined", sumVenue(entries)],
            ["Crypto", sumVenue(entries, "crypto")],
            ["Forex", sumVenue(entries, "forex")],
          ].map(([label, value]) => (
            <motion.section
              key={label}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="rounded-2xl border border-white/10 bg-[#1e2128] px-4 py-3"
            >
              <p className="text-xs uppercase tracking-[0.16em] text-[#9a958c]">{label}</p>
              <p className={`mt-2 text-2xl ${pnlClass(value)}`}>{money(value)}</p>
            </motion.section>
          ))}
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <section className="rounded-2xl border border-white/10 bg-[#1e2128] p-4">
            <h2 className="text-sm text-[#9a958c]">Crypto P/L</h2>
            <AreaChart values={crypto} positive={crypto.at(-1) >= 0} />
          </section>
          <section className="rounded-2xl border border-white/10 bg-[#1e2128] p-4">
            <h2 className="text-sm text-[#9a958c]">Forex P/L</h2>
            <AreaChart values={forex} positive={forex.at(-1) >= 0} />
          </section>
        </div>
        <section className="rounded-2xl border border-white/10 bg-[#1e2128] p-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm text-[#9a958c]">Day P/L</h2>
            <p className="text-xs text-[#9a958c]">Sage profit · rose loss · gray flat</p>
          </div>
          <div className="mt-4 space-y-4">
            {months.length === 0 ? <p className="text-sm text-[#9a958c]">Saved trades will fill this grid.</p> : null}
            {months.map((month) => (
              <div key={month.id}>
                <p className="mb-2 text-xs uppercase tracking-[0.14em] text-[#9a958c]">{month.label}</p>
                <div className="flex flex-wrap gap-1.5">
                  {month.days.map((day, index) => {
                    const tone = day.net > 0 ? "bg-[#7d9a84]" : day.net < 0 ? "bg-[#c48b84]" : "bg-[#3a3f48]";
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
        <section className="rounded-2xl border border-white/10 bg-[#1e2128] p-4">
          <h2 className="text-sm text-[#9a958c]">Recent trades</h2>
          <div className="mt-3 divide-y divide-white/5">
            {recent.length === 0 ? <p className="py-3 text-sm text-[#9a958c]">The five newest saved trades appear here.</p> : null}
            {recent.map((trade) => (
              <button
                key={trade.id || trade.sourceTradeId}
                type="button"
                onClick={() => onOpenTrade(trade)}
                className="flex w-full items-center justify-between gap-3 py-3 text-left"
              >
                <span>
                  <span className="block">{trade.symbol}</span>
                  <span className="text-xs text-[#9a958c]">{trade.accountName} · {trade.venue} · {formatIst(trade.exitTimeIst)}</span>
                </span>
                <span className={pnlClass(trade.netPnl)}>{money(trade.netPnl)}</span>
              </button>
            ))}
          </div>
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
