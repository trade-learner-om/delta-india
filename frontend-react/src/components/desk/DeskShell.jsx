import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { api } from "../../api";
import HomePage from "./HomePage";
import JournalPage from "./JournalPage";
import SettingsPage from "./SettingsPage";
import TradeDetailModal from "./TradeDetailModal";
import TradePage from "./TradePage";

const PAGES = [
  ["home", "Home"],
  ["trade", "Trade"],
  ["journal", "Journal"],
  ["settings", "Settings"],
];

export default function DeskShell({ token, me, livePrices, liveStatus, onLogout, onNotify, onSessionRefresh }) {
  const [page, setPage] = useState("home");
  const [entries, setEntries] = useState([]);
  const [watchlist, setWatchlist] = useState([]);
  const [mt5Accounts, setMt5Accounts] = useState([]);
  const [deltaAccounts, setDeltaAccounts] = useState([]);
  const [openTrade, setOpenTrade] = useState(null);

  const reload = async () => {
    const [journal, list, crypto, forex] = await Promise.all([
      api("/journal", { token }),
      api("/watchlist", { token }),
      api("/accounts", { token }),
      api("/mt5/accounts", { token }),
    ]);
    setEntries(journal.entries || []);
    setWatchlist(list.items || []);
    setDeltaAccounts(crypto.accounts || []);
    setMt5Accounts(forex.accounts || []);
  };

  useEffect(() => {
    if (!token) return;
    reload().catch((err) => onNotify("error", err.message || "Dashboard data did not load."));
  }, [token]);

  return (
    <div className="flex h-dvh bg-[#16181d] text-[#e6e2d8]">
      <aside className="flex w-52 shrink-0 flex-col border-r border-white/10 px-4 py-6">
        <p className="px-2 text-lg tracking-wide">Ledger</p>
        <nav className="mt-8 flex flex-col gap-1">
          {PAGES.map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => setPage(id)}
              className={`rounded-xl px-3 py-2 text-left text-sm ${page === id ? "bg-[#24303a] text-[#8eafc4]" : "text-[#9a958c]"}`}
            >
              {label}
            </button>
          ))}
        </nav>
        <div className="mt-auto px-2 text-xs text-[#9a958c]">
          <p>{me?.displayName || me?.email}</p>
          <p className="mt-1 capitalize">{liveStatus}</p>
          <button type="button" className="mt-3 text-[#8eafc4]" onClick={onLogout}>Log out</button>
        </div>
      </aside>
      <main className="min-w-0 flex-1 overflow-y-auto p-6">
        <motion.div key={page} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }}>
          {page === "home" ? (
            <HomePage
              token={token}
              entries={entries}
              watchlist={watchlist}
              livePrices={livePrices}
              onOpenTrade={setOpenTrade}
              onWatchlistChange={reload}
              onNotify={onNotify}
            />
          ) : null}
          {page === "trade" ? (
            <TradePage
              token={token}
              me={me}
              deltaAccounts={deltaAccounts}
              mt5Accounts={mt5Accounts}
              onNotify={onNotify}
              onReload={reload}
            />
          ) : null}
          {page === "journal" ? (
            <JournalPage token={token} onNotify={onNotify} onChanged={reload} />
          ) : null}
          {page === "settings" ? (
            <SettingsPage
              token={token}
              me={me}
              deltaAccounts={deltaAccounts}
              mt5Accounts={mt5Accounts}
              onReload={() => {
                reload();
                onSessionRefresh?.();
              }}
              onNotify={onNotify}
            />
          ) : null}
        </motion.div>
      </main>
      {openTrade ? (
        <TradeDetailModal
          token={token}
          trade={openTrade}
          onClose={() => setOpenTrade(null)}
          onSaved={async (trade) => {
            if (trade.id) {
              await api(`/journal/${trade.id}`, { method: "PATCH", token, body: { setup: trade.setup, reason: trade.reason } });
            }
            await reload();
          }}
        />
      ) : null}
    </div>
  );
}
