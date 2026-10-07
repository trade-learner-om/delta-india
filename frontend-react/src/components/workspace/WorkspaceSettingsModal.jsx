import { useEffect, useState } from "react";
import { api } from "../../api";
import CryptoBridgeLogo from "./CryptoBridgeLogo";
import { modalOverlay, modalPanel, subTabBar, secondaryButton, textMuted, textHeading } from "../../utils/workspace/workspaceClasses";
import SettingsAccountsTab from "./settings/SettingsAccountsTab";
import SettingsIpWhitelistTab from "./settings/SettingsIpWhitelistTab";

export default function WorkspaceSettingsModal({
  open,
  token,
  accounts,
  selectedAccountId,
  onClose,
  onSubmitAdd,
  onDeleteAccount,
  onSelectAccount,
  onNotify,
}) {
  const [settingsTab, setSettingsTab] = useState("accounts");
  const [deletingId, setDeletingId] = useState("");
  const [serverIp, setServerIp] = useState("");
  const [serverIpError, setServerIpError] = useState("");
  const [ipCopied, setIpCopied] = useState(false);

  useEffect(() => {
    if (!open) return;
    setSettingsTab("accounts");
    setDeletingId("");
  }, [open]);

  useEffect(() => {
    if (!open || !token) return;
    let cancelled = false;
    api("/meta/public-ip", { token })
      .then((data) => {
        if (cancelled) return;
        if (data?.ip) setServerIp(data.ip);
        else setServerIpError(data?.error || "Server IP unavailable.");
      })
      .catch((err) => {
        if (!cancelled) setServerIpError(err.message || "Server IP unavailable.");
      });
    return () => { cancelled = true; };
  }, [open, token]);

  const copyServerIp = async () => {
    if (!serverIp) return;
    try {
      await navigator.clipboard.writeText(serverIp);
      setIpCopied(true);
      onNotify?.("success", "Copied workstation public server IP to clipboard.");
      window.setTimeout(() => setIpCopied(false), 2000);
    } catch {
      onNotify?.("error", "Could not copy to clipboard.");
    }
  };

  if (!open) return null;

  return (
    <div className={modalOverlay()}>
      <div className={modalPanel("max-w-2xl w-full overflow-hidden")}>
        <div className="flex justify-between items-center px-6 py-5 border-b border-slate-200 dark:border-zinc-800 bg-slate-50 dark:bg-zinc-950">
          <div className="flex items-center gap-2.5">
            <CryptoBridgeLogo size={24} iconOnly />
            <h3 className={`text-base font-bold uppercase tracking-wider ${textHeading()}`}>
              Trading Credentials &amp; Whitelist Settings
            </h3>
          </div>
          <button type="button" onClick={onClose} className={`${textMuted()} hover:text-slate-800 dark:hover:text-zinc-200 transition text-lg font-bold`}>
            &times;
          </button>
        </div>

        <div className={`${subTabBar()} mx-6 mt-0 rounded-none border-x-0 border-t-0 bg-transparent px-0`}>
          {[
            { id: "accounts", label: `Trading Accounts (${accounts.length})` },
            { id: "ip-whitelist", label: "Server Whitelist IP" },
          ].map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setSettingsTab(tab.id)}
              className={`py-3 px-4 text-xs font-bold tracking-wider uppercase border-b-2 transition ${
                settingsTab === tab.id
                  ? "border-lime-500 dark:border-lime-400 text-lime-600 dark:text-lime-400"
                  : `border-transparent ${textMuted()} hover:text-slate-800 dark:hover:text-zinc-200`
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="p-6 space-y-6 max-h-[70vh] overflow-y-auto">
          {settingsTab === "accounts" ? (
            <SettingsAccountsTab
              accounts={accounts}
              selectedAccountId={selectedAccountId}
              onSubmitAdd={onSubmitAdd}
              onDeleteAccount={onDeleteAccount}
              onSelectAccount={onSelectAccount}
              deletingId={deletingId}
              setDeletingId={setDeletingId}
            />
          ) : (
            <SettingsIpWhitelistTab
              serverIp={serverIp}
              serverIpError={serverIpError}
              onCopy={copyServerIp}
              ipCopied={ipCopied}
            />
          )}
        </div>

        <div className="bg-slate-50 dark:bg-zinc-950 px-6 py-4 border-t border-slate-200 dark:border-zinc-800 flex justify-end">
          <button type="button" onClick={onClose} className={secondaryButton()}>
            Close Settings
          </button>
        </div>
      </div>
    </div>
  );
}
