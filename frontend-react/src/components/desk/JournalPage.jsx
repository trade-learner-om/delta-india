import { useEffect, useMemo, useState } from "react";
import { api, apiUpload } from "../../api";
import TradeDetailModal from "./TradeDetailModal";
import {
  formatIst,
  formatRr,
  istDayKey,
  journalStats,
  ledgerField,
  ledgerMuted,
  ledgerPanel,
  money,
  pnlPill,
} from "./deskFormat";

const PAGE_SIZE = 20;

export default function JournalPage({ token, onNotify, onChanged }) {
  const [saved, setSaved] = useState([]);
  const [recent, setRecent] = useState([]);
  const [open, setOpen] = useState(null);
  const [symbol, setSymbol] = useState("");
  const [day, setDay] = useState("");
  const [side, setSide] = useState("all");
  const [outcome, setOutcome] = useState("all");
  const [page, setPage] = useState(0);

  const load = async () => {
    const [savedData, recentData] = await Promise.all([
      api("/journal", { token }),
      api("/journal/recent", { token }),
    ]);
    setSaved(savedData.entries || []);
    setRecent(recentData.trades || []);
  };

  useEffect(() => {
    if (!token) return;
    load().catch((err) => onNotify("error", err.message || "Journal could not load."));
  }, [token]);

  const stats = journalStats(saved);
  const filtered = useMemo(() => {
    const query = symbol.trim().toUpperCase();
    return saved.filter((trade) => {
      if (query && !String(trade.symbol || "").toUpperCase().includes(query)) return false;
      if (day && istDayKey(trade.exitTimeIst) !== day) return false;
      if (side !== "all" && String(trade.side || "").toUpperCase() !== side) return false;
      const net = Number(trade.netPnl);
      if (outcome === "win" && !(net > 0)) return false;
      if (outcome === "loss" && !(net < 0)) return false;
      return true;
    });
  }, [saved, symbol, day, side, outcome]);
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const visible = filtered.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE);

  useEffect(() => {
    setPage(0);
  }, [symbol, day, side, outcome]);

  const saveTrade = async (trade) => {
    if (trade.savedAt && trade.id) {
      await api(`/journal/${trade.id}`, {
        method: "PATCH",
        token,
        body: { setup: trade.setup, reason: trade.reason },
      });
    } else {
      await api("/journal", {
        method: "POST",
        token,
        body: { sourceTradeId: trade.sourceTradeId, setup: trade.setup, reason: trade.reason },
      });
    }
    onNotify("success", "Journal saved.");
    await load();
    onChanged?.();
  };

  const upload = async (trade, file) => {
    if (!trade?.id || !file) return;
    await apiUpload(`/journal/${trade.id}/chart`, token, file);
    onNotify("success", "Chart snapshot saved.");
    await load();
  };

  const cards = [
    ["Win rate", stats.winRate == null ? "—" : `${stats.winRate.toFixed(1)}%`],
    ["Total P/L", money(stats.total)],
    ["Profit factor", stats.profitFactor == null ? "—" : stats.profitFactor.toFixed(2)],
    ["Total trades", String(stats.trades)],
  ];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {cards.map(([label, value]) => (
          <section key={label} className={`px-4 py-3 ${ledgerPanel}`}>
            <p className={`text-xs uppercase tracking-[0.14em] ${ledgerMuted}`}>{label}</p>
            <p className="mt-2 text-2xl font-semibold">{value}</p>
          </section>
        ))}
      </div>
      <section className={`p-4 ${ledgerPanel}`}>
        <h1 className="text-xl">Recent broker trades</h1>
        <p className={`mt-1 text-sm ${ledgerMuted}`}>Times are shown in IST. Save a trade to keep the setup and the reason.</p>
        <div className="mt-3 divide-y divide-[var(--ledger-border)]">
          {recent.length === 0 ? <p className={`py-3 text-sm ${ledgerMuted}`}>No unsaved broker trades.</p> : null}
          {recent.map((trade) => (
            <button key={trade.sourceTradeId} type="button" onClick={() => setOpen(trade)} className="flex w-full items-center justify-between py-3 text-left">
              <span>
                <span className="block">{trade.symbol}</span>
                <span className={`text-xs ${ledgerMuted}`}>{trade.accountName} · {formatIst(trade.exitTimeIst)}</span>
              </span>
              <span className={pnlPill(trade.netPnl)}>{money(trade.netPnl)}</span>
            </button>
          ))}
        </div>
      </section>
      <section className={`p-4 ${ledgerPanel}`}>
        <div className="grid gap-2 md:grid-cols-4">
          <input className={ledgerField} placeholder="Symbol" value={symbol} onChange={(event) => setSymbol(event.target.value)} />
          <input className={ledgerField} type="date" value={day} onChange={(event) => setDay(event.target.value)} />
          <select className={ledgerField} value={side} onChange={(event) => setSide(event.target.value)}>
            <option value="all">All sides</option>
            <option value="BUY">Buy</option>
            <option value="SELL">Sell</option>
          </select>
          <select className={ledgerField} value={outcome} onChange={(event) => setOutcome(event.target.value)}>
            <option value="all">All outcomes</option>
            <option value="win">Win</option>
            <option value="loss">Loss</option>
          </select>
        </div>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[40rem] text-left text-sm">
            <thead className={`text-xs uppercase tracking-wider ${ledgerMuted}`}>
              <tr>
                {["Time", "Symbol", "Type", "P/L", "Return (R)", "Actions"].map((label) => (
                  <th key={label} className="py-2 font-medium">{label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {visible.length === 0 ? (
                <tr><td colSpan={6} className={`py-6 text-center ${ledgerMuted}`}>No saved trades match these filters.</td></tr>
              ) : null}
              {visible.map((trade) => (
                <tr key={trade.id} className="border-t border-[var(--ledger-border)]">
                  <td className="py-2">{formatIst(trade.exitTimeIst)}</td>
                  <td className="py-2">{trade.symbol}</td>
                  <td className="py-2">{trade.side}</td>
                  <td className="py-2"><span className={pnlPill(trade.netPnl)}>{money(trade.netPnl)}</span></td>
                  <td className="py-2">{formatRr(trade.rr)}</td>
                  <td className="py-2">
                    <button type="button" className="text-xs text-[var(--ledger-accent)]" onClick={() => setOpen(trade)}>Open</button>
                    <label className={`ml-3 text-xs text-[var(--ledger-accent)] ${trade.locked ? "opacity-40" : "cursor-pointer"}`}>
                      Chart
                      <input
                        type="file"
                        accept="image/png,image/jpeg,image/webp"
                        className="hidden"
                        disabled={trade.locked}
                        onChange={(event) => upload(trade, event.target.files?.[0]).catch((err) => onNotify("error", err.message))}
                      />
                    </label>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className={`mt-3 flex items-center justify-between text-sm ${ledgerMuted}`}>
          <span>{filtered.length} trades</span>
          <div className="flex gap-2">
            <button type="button" disabled={page === 0} onClick={() => setPage((current) => current - 1)} className="disabled:opacity-40">Previous</button>
            <span>{page + 1} / {pages}</span>
            <button type="button" disabled={page + 1 >= pages} onClick={() => setPage((current) => current + 1)} className="disabled:opacity-40">Next</button>
          </div>
        </div>
      </section>
      {open ? <TradeDetailModal token={token} trade={open} onClose={() => setOpen(null)} onSaved={saveTrade} /> : null}
    </div>
  );
}
