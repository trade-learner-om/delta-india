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
const RECENT_PAGE_SIZE = 10;

function isoDay(value) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function defaultRange() {
  const to = new Date();
  const from = new Date();
  from.setDate(to.getDate() - 7);
  return { from: isoDay(from), to: isoDay(to) };
}

export default function JournalPage({ token, deltaAccounts = [], mt5Accounts = [], onNotify, onChanged }) {
  const [saved, setSaved] = useState([]);
  const [recent, setRecent] = useState([]);
  const [fetched, setFetched] = useState(false);
  const [query, setQuery] = useState(null);
  const [fetchOpen, setFetchOpen] = useState(false);
  const [selected, setSelected] = useState([]);
  const [range, setRange] = useState(defaultRange);
  const [fetching, setFetching] = useState(false);
  const [open, setOpen] = useState(null);
  const [symbol, setSymbol] = useState("");
  const [day, setDay] = useState("");
  const [side, setSide] = useState("all");
  const [outcome, setOutcome] = useState("all");
  const [page, setPage] = useState(0);
  const [recentPage, setRecentPage] = useState(0);

  const accounts = [
    ...deltaAccounts.map((account) => ({ id: account.id, name: account.accountName, venue: "Crypto" })),
    ...mt5Accounts.map((account) => ({ id: account.id, name: account.accountName, venue: "Forex" })),
  ];

  const loadSaved = async () => {
    const savedData = await api("/journal", { token });
    setSaved(savedData.entries || []);
  };

  const fetchRecent = async (next) => {
    const params = new URLSearchParams();
    next.accountIds.forEach((id) => params.append("accountId", id));
    params.set("from", next.from);
    params.set("to", next.to);
    const recentData = await api(`/journal/recent?${params.toString()}`, { token });
    setRecent(recentData.trades || []);
    setQuery(next);
    setFetched(true);
    setRecentPage(0);
  };

  useEffect(() => {
    if (!token) return;
    loadSaved().catch((err) => onNotify("error", err.message || "Journal could not load."));
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
  const recentPages = Math.max(1, Math.ceil(recent.length / RECENT_PAGE_SIZE));
  const visibleRecent = recent.slice(recentPage * RECENT_PAGE_SIZE, recentPage * RECENT_PAGE_SIZE + RECENT_PAGE_SIZE);

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
        body: {
          sourceTradeId: trade.sourceTradeId,
          setup: trade.setup,
          reason: trade.reason,
          from: query?.from,
          to: query?.to,
          accountId: query?.accountIds || [],
        },
      });
    }
    onNotify("success", "Journal saved.");
    await loadSaved();
    if (query) await fetchRecent(query);
    onChanged?.();
  };

  const upload = async (trade, file) => {
    if (!trade?.id || !file) return;
    await apiUpload(`/journal/${trade.id}/chart`, token, file);
    onNotify("success", "Chart snapshot saved.");
    await loadSaved();
  };

  const openFetch = () => {
    setRange(query ? { from: query.from, to: query.to } : defaultRange());
    setSelected(query?.accountIds || []);
    setFetchOpen(true);
  };

  const toggleAccount = (id) => {
    setSelected((current) => (current.includes(id) ? current.filter((item) => item !== id) : [...current, id]));
  };

  const confirmFetch = async () => {
    if (selected.length === 0) {
      onNotify("error", "Select at least one account.");
      return;
    }
    if (!range.from || !range.to || range.to < range.from) {
      onNotify("error", "Choose a from date and a to date.");
      return;
    }
    setFetching(true);
    try {
      await fetchRecent({ accountIds: selected, from: range.from, to: range.to });
      setFetchOpen(false);
    } catch (err) {
      onNotify("error", err.message || "Broker trades could not be loaded.");
    } finally {
      setFetching(false);
    }
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
        <div className="flex items-start justify-between gap-3">
          <div>
            <h1 className="text-xl">Recent broker trades</h1>
            <p className={`mt-1 text-sm ${ledgerMuted}`}>Times are shown in IST. Save a trade to keep the setup and the reason.</p>
          </div>
          <button type="button" onClick={openFetch} className="rounded-lg bg-[var(--ledger-accent)] px-3 py-2 text-sm text-white">
            Fetch trades
          </button>
        </div>
        <div className="mt-3 divide-y divide-[var(--ledger-border)]">
          {!fetched ? <p className={`py-3 text-sm ${ledgerMuted}`}>Choose accounts and a date range to load broker trades.</p> : null}
          {fetched && recent.length === 0 ? <p className={`py-3 text-sm ${ledgerMuted}`}>None were found for that range.</p> : null}
          {visibleRecent.map((trade) => (
            <button key={trade.sourceTradeId} type="button" onClick={() => setOpen(trade)} className="flex w-full items-center justify-between py-3 text-left">
              <span>
                <span className="block">{trade.symbol} <span className={`text-xs ${ledgerMuted}`}>{trade.venue}</span></span>
                <span className={`text-xs ${ledgerMuted}`}>{trade.accountName} · {formatIst(trade.exitTimeIst)}</span>
              </span>
              <span className={pnlPill(trade.netPnl)}>{money(trade.netPnl)}</span>
            </button>
          ))}
        </div>
        {recent.length > RECENT_PAGE_SIZE ? (
          <div className={`mt-3 flex items-center justify-between text-sm ${ledgerMuted}`}>
            <span>{recent.length} trades</span>
            <div className="flex gap-2">
              <button type="button" disabled={recentPage === 0} onClick={() => setRecentPage((current) => current - 1)} className="disabled:opacity-40">Previous</button>
              <span>{recentPage + 1} / {recentPages}</span>
              <button type="button" disabled={recentPage + 1 >= recentPages} onClick={() => setRecentPage((current) => current + 1)} className="disabled:opacity-40">Next</button>
            </div>
          </div>
        ) : null}
      </section>
      {fetchOpen ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4">
          <div className={`w-full max-w-md p-4 ${ledgerPanel}`}>
            <h2 className="text-lg">Fetch trades</h2>
            <p className={`mt-1 text-sm ${ledgerMuted}`}>Select one or more accounts and the dates to search.</p>
            <div className="mt-3 max-h-48 space-y-2 overflow-y-auto">
              {accounts.length === 0 ? <p className={`text-sm ${ledgerMuted}`}>No accounts are saved yet.</p> : null}
              {accounts.map((account) => (
                <label key={`${account.venue}-${account.id}`} className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={selected.includes(account.id)} onChange={() => toggleAccount(account.id)} />
                  <span>{account.name}</span>
                  <span className={ledgerMuted}>{account.venue}</span>
                </label>
              ))}
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2">
              <label className="text-sm">
                <span className={ledgerMuted}>From</span>
                <input className={`mt-1 ${ledgerField}`} type="date" value={range.from} onChange={(event) => setRange((current) => ({ ...current, from: event.target.value }))} />
              </label>
              <label className="text-sm">
                <span className={ledgerMuted}>To</span>
                <input className={`mt-1 ${ledgerField}`} type="date" value={range.to} onChange={(event) => setRange((current) => ({ ...current, to: event.target.value }))} />
              </label>
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" onClick={() => setFetchOpen(false)} className={`rounded-lg px-3 py-2 text-sm ${ledgerMuted}`}>Cancel</button>
              <button type="button" disabled={fetching} onClick={confirmFetch} className="rounded-lg bg-[var(--ledger-accent)] px-3 py-2 text-sm text-white disabled:opacity-50">
                {fetching ? "Fetching…" : "Fetch"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
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
