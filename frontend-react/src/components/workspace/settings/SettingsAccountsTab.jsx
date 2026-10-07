import { useState } from "react";
import { field, primaryButton, cardInner, textMuted, textHeading, accentLabel, secondaryButton, lossText } from "../../../utils/workspace/workspaceClasses";

export default function SettingsAccountsTab({
  accounts,
  selectedAccountId,
  onSubmitAdd,
  onDeleteAccount,
  onSelectAccount,
  deletingId,
  setDeletingId,
}) {
  const [form, setForm] = useState({ accountName: "", apiKey: "", apiSecret: "" });

  const submitAdd = async (event) => {
    event.preventDefault();
    await onSubmitAdd({ ...form, exchange: "delta" });
    setForm({ accountName: "", apiKey: "", apiSecret: "" });
  };

  const deleteAccount = async (account) => {
    const confirmed = window.confirm(`Delete ${account.accountName || account.account_name}?`);
    if (!confirmed) return;
    setDeletingId(account.id);
    try {
      await onDeleteAccount(account.id);
    } finally {
      setDeletingId("");
    }
  };

  return (
    <div className="space-y-6">
      <form onSubmit={submitAdd} className={`space-y-4 ${cardInner("p-5")}`}>
        <h4 className={`text-xs font-bold uppercase tracking-widest ${accentLabel()}`}>Add New Delta India Endpoint</h4>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className={`block text-[10px] font-bold uppercase mb-1 ${textMuted()}`}>Account Name</label>
            <input
              type="text"
              placeholder="e.g., Delta Hedger"
              value={form.accountName}
              onChange={(event) => setForm((current) => ({ ...current, accountName: event.target.value }))}
              className={field("font-sans")}
              required
            />
          </div>
          <div>
            <label className={`block text-[10px] font-bold uppercase mb-1 ${textMuted()}`}>API Key</label>
            <input
              type="text"
              placeholder="dt_live_..."
              value={form.apiKey}
              onChange={(event) => setForm((current) => ({ ...current, apiKey: event.target.value }))}
              className={field()}
              required
            />
          </div>
          <div>
            <label className={`block text-[10px] font-bold uppercase mb-1 ${textMuted()}`}>API Secret</label>
            <input
              type="password"
              placeholder="Private key hash..."
              value={form.apiSecret}
              onChange={(event) => setForm((current) => ({ ...current, apiSecret: event.target.value }))}
              className={field("font-sans")}
              required
            />
          </div>
        </div>
        <div className="flex justify-end pt-2">
          <button type="submit" className={primaryButton()}>
            Securely Store Credentials
          </button>
        </div>
      </form>

      <div className="space-y-3">
        <h4 className={`text-xs font-bold uppercase tracking-wider ${textMuted()}`}>Connected Accounts</h4>
        {accounts.map((account) => {
          const name = account.accountName || account.account_name || "Account";
          const uid = account.exchangeUserId || account.exchange_user_id || "—";
          const isSelected = account.id === selectedAccountId;
          return (
            <div
              key={account.id}
              className={`flex justify-between items-center p-4 ${cardInner("hover:border-slate-300 dark:hover:border-zinc-700 transition")}`}
            >
              <div>
                <div className="flex items-center gap-2">
                  <span className={`font-semibold text-sm ${textHeading()}`}>{name}</span>
                  <span className={`px-1.5 py-0.5 bg-slate-200 dark:bg-zinc-800 rounded text-[9px] uppercase font-bold tracking-wider font-mono ${textMuted()}`}>
                    Delta India
                  </span>
                  {isSelected ? (
                    <span className="px-1.5 py-0.5 bg-lime-500/15 text-lime-600 dark:text-lime-400 border border-lime-500/30 rounded text-[9px] font-bold">
                      ACTIVE SELECTED
                    </span>
                  ) : null}
                </div>
                <div className={`text-[11px] font-mono mt-1 ${textMuted()}`}>UID: {uid}</div>
              </div>
              <div className="flex items-center gap-2.5">
                {!isSelected ? (
                  <button
                    type="button"
                    onClick={() => onSelectAccount(account.id)}
                    className={secondaryButton("!py-1.5")}
                  >
                    Activate
                  </button>
                ) : null}
                <button
                  type="button"
                  onClick={() => deleteAccount(account)}
                  disabled={deletingId === account.id}
                  className={`p-1.5 ${lossText()} hover:text-red-700 dark:hover:text-red-500 hover:bg-red-500/10 rounded-lg transition disabled:opacity-50`}
                  title="Disconnect API link"
                >
                  <svg fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79" />
                  </svg>
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
