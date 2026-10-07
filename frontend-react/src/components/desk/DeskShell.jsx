import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { BookOpen, LayoutDashboard, LogOut, Moon, Settings, Sun, TrendingUp } from "lucide-react";
import { api, apiUpload } from "../../api";
import { applyThemeClass, readStoredTheme, writeStoredTheme } from "../../utils/theme/themeStorage";
import { ledgerMuted, ledgerPanel } from "./deskFormat";
import HomePage from "./HomePage";
import JournalPage from "./JournalPage";
import SettingsPage from "./SettingsPage";
import TradeDetailModal from "./TradeDetailModal";
import TradePage from "./TradePage";

const PAGES = [
  ["home", "Home", LayoutDashboard],
  ["trade", "Trade", TrendingUp],
  ["journal", "Journal", BookOpen],
  ["settings", "Settings", Settings],
];

applyThemeClass(readStoredTheme());

export default function DeskShell({ token, me, livePrices, liveStatus, onLogout, onNotify, onSessionRefresh }) {
  const [page, setPage] = useState("home");
  const [theme, setTheme] = useState(readStoredTheme);
  const [entries, setEntries] = useState([]);
  const [watchlist, setWatchlist] = useState([]);
  const [mt5Accounts, setMt5Accounts] = useState([]);
  const [deltaAccounts, setDeltaAccounts] = useState([]);
  const [openTrade, setOpenTrade] = useState(null);

  useEffect(() => {
    applyThemeClass(theme);
    writeStoredTheme(theme);
  }, [theme]);

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

  const connected = liveStatus === "connected";
  const name = me?.displayName || me?.email || "Account";

  return (
    <div className="flex h-screen overflow-hidden bg-[var(--ledger-canvas)] text-[var(--ledger-text)]">
      <aside className="flex w-60 shrink-0 flex-col border-r border-[var(--ledger-border)] bg-[var(--ledger-surface)] px-3 py-5">
        <p className="px-3 text-lg tracking-wide">Ledger</p>
        <nav className="mt-8 flex flex-col gap-1">
          {PAGES.map(([id, label, Icon]) => {
            const active = page === id;
            return (
              <button
                key={id}
                type="button"
                onClick={() => setPage(id)}
                className={`flex items-center gap-3 rounded-xl px-3 py-2 text-left text-sm ${active ? "bg-[var(--ledger-accent)]/10 text-[var(--ledger-accent)] shadow-[inset_3px_0_0_var(--ledger-accent)]" : ledgerMuted}`}
              >
                <Icon size={16} />
                {label}
              </button>
            );
          })}
        </nav>
        <div className={`mt-auto ${ledgerPanel} p-3`}>
          <p className="truncate text-sm">{name}</p>
          <p className={`mt-1 flex items-center gap-2 text-xs capitalize ${ledgerMuted}`}>
            <span className={`h-2 w-2 rounded-full ${connected ? "bg-[var(--ledger-profit)]" : "bg-[var(--ledger-muted)]"}`} />
            {liveStatus}
          </p>
          <div className="mt-3 flex items-center justify-between">
            <button
              type="button"
              className={`inline-flex items-center gap-1 text-xs ${ledgerMuted}`}
              onClick={() => setTheme((current) => (current === "dark" ? "light" : "dark"))}
            >
              {theme === "dark" ? <Sun size={14} /> : <Moon size={14} />}
              {theme === "dark" ? "Light" : "Dark"}
            </button>
            <button type="button" className="inline-flex items-center gap-1 text-xs text-[var(--ledger-accent)]" onClick={onLogout}>
              <LogOut size={14} />
              Log out
            </button>
          </div>
        </div>
      </aside>
      <main className="min-w-0 flex-1 overflow-y-auto p-6">
        <motion.div key={page} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }} className="space-y-6">
          {page === "home" ? (
            <HomePage
              token={token}
              entries={entries}
              watchlist={watchlist}
              livePrices={livePrices}
              onOpenTrade={setOpenTrade}
              onWatchlistChange={reload}
              onNotify={onNotify}
              onOpenJournal={() => setPage("journal")}
            />
          ) : null}
          {page === "trade" ? (
            <TradePage
              token={token}
              deltaAccounts={deltaAccounts}
              mt5Accounts={mt5Accounts}
              livePrices={livePrices}
              onNotify={onNotify}
              onReload={reload}
            />
          ) : null}
          {page === "journal" ? (
            <JournalPage
              token={token}
              deltaAccounts={deltaAccounts}
              mt5Accounts={mt5Accounts}
              onNotify={onNotify}
              onChanged={reload}
            />
          ) : null}
          {page === "settings" ? (
            <SettingsPage
              token={token}
              me={me}
              theme={theme}
              onThemeChange={setTheme}
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
            const saved = trade.id
              ? await api(`/journal/${trade.id}`, { method: "PATCH", token, body: { setup: trade.setup, reason: trade.reason, stopLoss: trade.stopLoss ?? null } })
              : trade;
            await reload();
            return saved;
          }}
          onUploadChart={async (trade, file) => {
            if (!trade?.id || !file) return;
            await apiUpload(`/journal/${trade.id}/chart`, token, file);
            onNotify("success", "Chart snapshot saved.");
            await reload();
          }}
        />
      ) : null}
    </div>
  );
}
