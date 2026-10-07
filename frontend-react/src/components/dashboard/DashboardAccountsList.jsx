import WorkspaceCard from "../ui/WorkspaceCard";
import { readAvailableMargin } from "../../utils/accountMargin";
import { cardInner, textMuted, textHeading, textBody } from "../../utils/workspace/workspaceClasses";

export default function DashboardAccountsList({ accounts, selectedAccountId, onSelectAccount }) {
  return (
    <WorkspaceCard className="space-y-4">
      <div className="flex justify-between items-center">
        <h3 className={`text-sm font-bold uppercase tracking-wider ${textHeading()}`}>Delta India Profiles</h3>
        <span className={`px-2 py-0.5 bg-slate-200 dark:bg-zinc-800 rounded text-[10px] font-mono ${textMuted()}`}>MongoDB synced</span>
      </div>
      <div className="space-y-3">
        {accounts.map((account) => {
          const name = account.accountName || account.account_name || "Account";
          const margin = readAvailableMargin(account);
          const balance = Number(account.balance);
          const isSelected = account.id === selectedAccountId;
          return (
            <button
              key={account.id}
              type="button"
              onClick={() => onSelectAccount(account.id)}
              className={`w-full p-3.5 rounded-xl border transition text-left flex justify-between items-center ${
                isSelected
                  ? `${cardInner()} border-lime-500/50 dark:border-lime-400/50 shadow-md shadow-lime-400/5`
                  : `${cardInner("opacity-90")} hover:border-slate-300 dark:hover:border-zinc-700`
              }`}
            >
              <div>
                <div className="flex items-center gap-2">
                  <span className={`font-bold text-xs ${textHeading()}`}>{name}</span>
                  {isSelected ? <span className="w-1.5 h-1.5 rounded-full bg-lime-500 dark:bg-lime-400 animate-ping" /> : null}
                </div>
                <span className={`text-[10px] block ${textMuted()}`}>
                  UID: {account.exchangeUserId || account.exchange_user_id || "—"}
                </span>
              </div>
              <div className="text-right">
                <span className={`font-mono text-xs font-bold block ${textHeading()}`}>
                  ${Number.isFinite(balance) ? balance.toFixed(2) : "—"}
                </span>
                <span className={`text-[9px] block font-mono ${textMuted()}`}>
                  Avail: {margin != null ? `$${margin.toFixed(0)}` : "—"}
                </span>
              </div>
            </button>
          );
        })}
      </div>
    </WorkspaceCard>
  );
}
