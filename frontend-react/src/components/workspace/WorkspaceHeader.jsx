import { useMemo, useRef } from "react";
import { lookupLiveTick, spotDisplayPrice } from "../../utils/pricePrecision";
import { formatSpotPrice, tickColorClass, useHeldTickDirection } from "../../utils/workspace/workspaceFormatters";
import { formatMargin, readAccountCurrency, readAvailableMargin } from "../../utils/accountMargin";
import { headerShell } from "../../utils/workspace/workspaceClasses";
import CryptoBridgeLogo from "./CryptoBridgeLogo";
import ThemeSwitcher from "./ThemeSwitcher";

const SPOT_CHIP_CLASS =
  "bg-zinc-50 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 px-3 py-1 rounded flex items-center gap-2 shadow-sm min-w-[9.5rem]";

function SpotChip({ label, livePrices, symbol }) {
  const tick = lookupLiveTick(livePrices, symbol);
  const price = spotDisplayPrice(tick);
  const direction = useHeldTickDirection(price);
  const lastDisplayRef = useRef(null);
  const formatted = formatSpotPrice(livePrices, symbol);
  if (formatted) {
    lastDisplayRef.current = formatted;
  }
  const display = formatted || lastDisplayRef.current;

  return (
    <div className={SPOT_CHIP_CLASS}>
      <span className="text-zinc-500 dark:text-zinc-400 font-extrabold">{label}</span>
      <span className={`font-bold font-mono tabular-nums ${tickColorClass(direction)}`}>
        {display ? `$${display}` : "—"}
      </span>
    </div>
  );
}

function connectionLabel(liveStatus) {
  if (liveStatus === "connected") return "Live Feed";
  if (liveStatus === "reconnecting") return "Reconnecting";
  return "Offline";
}

export default function WorkspaceHeader({
  liveStatus,
  livePrices,
  accounts,
  selectedAccountId,
  onAccountChange,
  onOpenSettings,
  onLogout,
  switchingAccount,
}) {
  const accountOptions = useMemo(
    () => accounts.map((account) => ({
      id: account.id,
      label: account.account_name || account.accountName || "Account",
      margin: readAvailableMargin(account),
      currency: readAccountCurrency(account),
      selected: account.id === selectedAccountId,
    })),
    [accounts, selectedAccountId],
  );

  const connected = liveStatus === "connected" || liveStatus === "reconnecting";

  return (
    <header className={headerShell()}>
      <div className="flex items-center gap-4">
        <CryptoBridgeLogo size={40} subtitle="Delta India Gateway" />
        <div className="h-8 w-px bg-zinc-200 dark:bg-zinc-700 hidden sm:block" />
        <div className="hidden sm:flex items-center gap-3 font-mono text-xs shrink-0">
          <SpotChip label="BTCUSD" livePrices={livePrices} symbol="BTCUSD" />
          <SpotChip label="ETHUSD" livePrices={livePrices} symbol="ETHUSD" />
        </div>
      </div>

      <div className="flex items-center gap-3">
        <div
          className="flex items-center gap-2 px-3 py-1.5 bg-zinc-50 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded text-xs font-mono font-bold text-zinc-700 dark:text-zinc-300"
          title="WebSocket connection status"
        >
          <span className="relative flex h-2 w-2">
            {connected ? (
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
            ) : null}
            <span className={`relative inline-flex rounded-full h-2 w-2 ${connected ? "bg-emerald-500" : "bg-red-500"}`} />
          </span>
          <span className="text-[10px] uppercase">{connectionLabel(liveStatus)}</span>
        </div>

        <div className="flex items-center gap-2 bg-zinc-50 dark:bg-zinc-800 px-3 py-1.5 rounded border border-zinc-200 dark:border-zinc-700 font-sans shadow-sm">
          <span className="text-[10px] text-zinc-500 dark:text-zinc-400 font-extrabold uppercase hidden lg:inline">Broker Route:</span>
          <select
            value={selectedAccountId}
            onChange={(event) => onAccountChange(event.target.value)}
            disabled={switchingAccount}
            className="bg-transparent text-xs text-zinc-900 dark:text-zinc-100 font-bold focus:outline-none cursor-pointer disabled:opacity-50"
          >
            {accountOptions.map((account) => (
              <option key={account.id} value={account.id} className="bg-white dark:bg-zinc-900 text-zinc-800 dark:text-zinc-200">
                {account.label}
                {account.margin != null ? ` (${formatMargin(account.margin, account.currency)})` : ""}
                {account.selected ? " ★" : ""}
              </option>
            ))}
          </select>
        </div>

        <ThemeSwitcher />

        <button
          type="button"
          onClick={onOpenSettings}
          className="p-2 rounded bg-zinc-100 dark:bg-zinc-800 hover:bg-zinc-200 dark:hover:bg-zinc-700 text-zinc-600 dark:text-zinc-300 hover:text-zinc-900 dark:hover:text-zinc-100 transition"
          title="Configure accounts and IP whitelist"
        >
          <svg fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4" aria-hidden="true">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z"
            />
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
        </button>

        <button
          type="button"
          onClick={onLogout}
          className="p-2 rounded bg-red-50 dark:bg-red-950/50 hover:bg-red-100 dark:hover:bg-red-900/50 text-red-500 hover:text-red-700 dark:hover:text-red-400 transition"
          title="Disconnect session"
        >
          <svg fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" className="w-4 h-4">
            <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15m3 0l3-3m0 0l-3-3m3 3H9" />
          </svg>
        </button>
      </div>
    </header>
  );
}
