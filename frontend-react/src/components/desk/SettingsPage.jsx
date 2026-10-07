import { useEffect, useState } from "react";
import { Copy, Eye, EyeOff } from "lucide-react";
import { api } from "../../api";
import { ledgerField, ledgerMuted, ledgerPanel } from "./deskFormat";

const TABS = [
  ["accounts", "API Accounts"],
  ["security", "Security"],
  ["preferences", "Preferences"],
];

export default function SettingsPage({ token, me, theme, onThemeChange, deltaAccounts, mt5Accounts, onReload, onNotify }) {
  const [tab, setTab] = useState("accounts");
  const [deltaForm, setDeltaForm] = useState({ apiKey: "", apiSecret: "" });
  const [showDeltaKey, setShowDeltaKey] = useState(false);
  const [showDeltaSecret, setShowDeltaSecret] = useState(false);
  const [showMt5Password, setShowMt5Password] = useState(false);
  const [mt5Form, setMt5Form] = useState({ login: "", password: "", server: "", terminalPath: "" });
  const [terminalPaths, setTerminalPaths] = useState([]);
  const [terminalNote, setTerminalNote] = useState("");
  const [detecting, setDetecting] = useState(false);
  const [serverIp, setServerIp] = useState("");
  const [serverIpError, setServerIpError] = useState("");
  const [ipCopied, setIpCopied] = useState(false);
  const [deltaOpen, setDeltaOpen] = useState(false);
  const [mt5Open, setMt5Open] = useState(false);

  useEffect(() => {
    if (!token) return undefined;
    let cancelled = false;
    api("/meta/public-ip", { token })
      .then((data) => {
        if (cancelled) return;
        if (data?.ip) setServerIp(data.ip);
        else setServerIpError(data?.error || "Could not read the server IP.");
      })
      .catch((err) => {
        if (!cancelled) setServerIpError(err.message || "Could not read the server IP.");
      });
    return () => { cancelled = true; };
  }, [token]);

  const copyIp = async () => {
    if (!serverIp) return;
    await navigator.clipboard.writeText(serverIp);
    setIpCopied(true);
    window.setTimeout(() => setIpCopied(false), 2000);
  };

  const addDelta = async () => {
    await api("/accounts", { method: "POST", token, body: deltaForm });
    setDeltaForm({ apiKey: "", apiSecret: "" });
    setShowDeltaKey(false);
    setShowDeltaSecret(false);
    setDeltaOpen(false);
    onNotify("success", "Delta account added.");
    onReload();
  };

  const addMt5 = async () => {
    await api("/mt5/accounts", { method: "POST", token, body: mt5Form });
    setMt5Form({ login: "", password: "", server: "", terminalPath: "" });
    setTerminalPaths([]);
    setTerminalNote("");
    setShowMt5Password(false);
    setMt5Open(false);
    onNotify("success", "Forex account added.");
    onReload();
  };

  const detectTerminals = async () => {
    setDetecting(true);
    setTerminalNote("");
    try {
      const data = await api("/mt5/terminals", { token });
      const paths = (data.uniquePaths || []).filter(Boolean);
      setTerminalPaths(paths);
      if (paths.length === 1) {
        setMt5Form((current) => ({ ...current, terminalPath: paths[0] }));
      } else if (!paths.length) {
        setTerminalNote("No running MT5 terminal found. Start it on the machine running the API, then detect again.");
      } else if (data.requiresUniqueInstallPaths) {
        setTerminalNote("Some MT5 windows share one terminal64.exe. Use a separate MT5 folder for each account.");
      }
    } catch (err) {
      setTerminalNote(err.message || "Could not detect a running MT5 terminal.");
    } finally {
      setDetecting(false);
    }
  };

  const select = async (account, nextVenue) => {
    const path = nextVenue === "forex" ? "/mt5/accounts/select" : "/accounts/select";
    await api(path, { method: "POST", token, body: { accountId: account.id } });
    onReload();
  };

  const remove = async (account, nextVenue) => {
    const path = nextVenue === "forex" ? `/mt5/accounts/${account.id}` : `/accounts/${account.id}`;
    await api(path, { method: "DELETE", token });
    onReload();
  };

  const setRisk = async (account, nextVenue, riskAmount) => {
    const path = nextVenue === "forex" ? `/mt5/accounts/${account.id}/risk` : `/accounts/${account.id}/risk`;
    await api(path, { method: "PATCH", token, body: { riskAmount: Number(riskAmount) } });
    onNotify("success", "Risk amount updated.");
    onReload();
  };

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div className={`flex gap-1 p-1 ${ledgerPanel}`}>
        {TABS.map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={`flex-1 rounded-xl px-3 py-2 text-sm ${tab === id ? "bg-[var(--ledger-accent)] text-white" : ledgerMuted}`}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "accounts" ? (
        <section className={`p-5 ${ledgerPanel}`}>
          <h1 className="text-xl">Accounts</h1>
          <p className={`mt-1 text-sm ${ledgerMuted}`}>{me?.email} · one login for crypto and forex</p>
          <AccountList
            title="Crypto"
            accounts={deltaAccounts}
            onAdd={() => setDeltaOpen(true)}
            onSelect={(account) => select(account, "crypto")}
            onDelete={(account) => remove(account, "crypto")}
            onRisk={(account, risk) => setRisk(account, "crypto", risk)}
          />
          <AccountList
            title="Forex"
            accounts={mt5Accounts}
            onAdd={() => setMt5Open(true)}
            onSelect={(account) => select(account, "forex")}
            onDelete={(account) => remove(account, "forex")}
            onRisk={(account, risk) => setRisk(account, "forex", risk)}
          />
        </section>
      ) : null}
      {deltaOpen ? (
        <FormModal title="Add Delta account" onClose={() => setDeltaOpen(false)}>
          <div className={`px-3 py-3 text-sm ${ledgerPanel}`}>
            <p className={`text-xs uppercase tracking-[0.14em] ${ledgerMuted}`}>Whitelist this IP on Delta</p>
            <p className="mt-2 font-mono text-lg text-[var(--ledger-accent)]">{serverIp || serverIpError || "Loading server IP..."}</p>
            <p className={`mt-1 text-xs ${ledgerMuted}`}>Delta allows signed calls only from this server address. Copy it into the API key profile before adding the account.</p>
            <button type="button" disabled={!serverIp} onClick={() => copyIp().catch(() => onNotify("error", "Could not copy the IP."))} className="mt-2 inline-flex items-center gap-1 text-xs text-[var(--ledger-accent)] disabled:opacity-50">
              <Copy size={12} />
              {ipCopied ? "Copied" : "Copy IP"}
            </button>
          </div>
          <SecretField placeholder="Delta API key" value={deltaForm.apiKey} shown={showDeltaKey} onToggle={() => setShowDeltaKey((current) => !current)} onChange={(value) => setDeltaForm({ ...deltaForm, apiKey: value })} />
          <SecretField placeholder="Delta API secret" value={deltaForm.apiSecret} shown={showDeltaSecret} onToggle={() => setShowDeltaSecret((current) => !current)} onChange={(value) => setDeltaForm({ ...deltaForm, apiSecret: value })} />
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => setDeltaOpen(false)} className={`rounded-full px-4 py-2 text-sm ${ledgerMuted}`}>Cancel</button>
            <button type="button" onClick={() => addDelta().catch((err) => onNotify("error", err.message))} className="rounded-full bg-[var(--ledger-accent)] px-4 py-2 text-sm text-white">Add account</button>
          </div>
        </FormModal>
      ) : null}
      {mt5Open ? (
        <FormModal title="Add MT5 account" onClose={() => setMt5Open(false)}>
          <input className={ledgerField} placeholder="login" value={mt5Form.login} onChange={(event) => setMt5Form({ ...mt5Form, login: event.target.value })} />
          <SecretField placeholder="password" value={mt5Form.password} shown={showMt5Password} onToggle={() => setShowMt5Password((current) => !current)} onChange={(value) => setMt5Form({ ...mt5Form, password: value })} />
          <input className={ledgerField} placeholder="server" value={mt5Form.server} onChange={(event) => setMt5Form({ ...mt5Form, server: event.target.value })} />
          <div className="flex gap-2">
            <input
              className={`min-w-0 flex-1 ${ledgerField}`}
              placeholder="terminal64.exe path"
              value={mt5Form.terminalPath}
              onChange={(event) => setMt5Form({ ...mt5Form, terminalPath: event.target.value })}
            />
            <button type="button" disabled={detecting} onClick={detectTerminals} className="rounded-full border border-[var(--ledger-accent)] px-4 py-2 text-sm text-[var(--ledger-accent)] disabled:opacity-50">
              {detecting ? "Detecting..." : "Detect running"}
            </button>
          </div>
          {terminalPaths.length > 1 ? (
            <div className="grid gap-1">
              {terminalPaths.map((path) => (
                <button
                  key={path}
                  type="button"
                  onClick={() => setMt5Form((current) => ({ ...current, terminalPath: path }))}
                  className={`truncate rounded-lg px-3 py-2 text-left text-xs ${mt5Form.terminalPath === path ? "bg-[var(--ledger-accent)]/15 text-[var(--ledger-accent)]" : `${ledgerMuted} bg-[var(--ledger-canvas)]`}`}
                >
                  {path}
                </button>
              ))}
            </div>
          ) : null}
          {terminalNote ? <p className={`text-xs ${ledgerMuted}`}>{terminalNote}</p> : null}
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => setMt5Open(false)} className={`rounded-full px-4 py-2 text-sm ${ledgerMuted}`}>Cancel</button>
            <button type="button" onClick={() => addMt5().catch((err) => onNotify("error", err.message))} className="rounded-full bg-[var(--ledger-accent)] px-4 py-2 text-sm text-white">Add account</button>
          </div>
        </FormModal>
      ) : null}
      {tab === "security" ? (
        <section className={`p-5 ${ledgerPanel}`}>
          <h1 className="text-xl">Security</h1>
          <p className={`mt-3 text-sm ${ledgerMuted}`}>This login stays valid until the coming Saturday at 00:00 IST. Signing in again after that starts a new session.</p>
        </section>
      ) : null}
      {tab === "preferences" ? (
        <section className={`p-5 ${ledgerPanel}`}>
          <h1 className="text-xl">Preferences</h1>
          <p className={`mt-1 text-sm ${ledgerMuted}`}>The same choice is on the sidebar.</p>
          <div className="mt-4 flex gap-2">
            {["dark", "light"].map((choice) => (
              <button
                key={choice}
                type="button"
                onClick={() => onThemeChange(choice)}
                className={`rounded-full px-4 py-2 text-sm capitalize ${theme === choice ? "bg-[var(--ledger-accent)] text-white" : `border border-[var(--ledger-border)] ${ledgerMuted}`}`}
              >
                {choice}
              </button>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}

function SecretField({ placeholder, value, shown, onToggle, onChange }) {
  return (
    <div className="relative">
      <input className={`${ledgerField} pr-10`} placeholder={placeholder} type={shown ? "text" : "password"} value={value} onChange={(event) => onChange(event.target.value)} />
      <button type="button" aria-label={shown ? "Hide" : "Show"} className={`absolute right-3 top-1/2 -translate-y-1/2 ${ledgerMuted}`} onClick={onToggle}>
        {shown ? <EyeOff size={16} /> : <Eye size={16} />}
      </button>
    </div>
  );
}

function FormModal({ title, onClose, children }) {
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div className={`w-full max-w-md space-y-3 p-5 ${ledgerPanel}`} onClick={(event) => event.stopPropagation()}>
        <h2 className="text-lg">{title}</h2>
        {children}
      </div>
    </div>
  );
}

function AccountList({ title, accounts, onAdd, onSelect, onDelete, onRisk }) {
  const rows = accounts || [];
  return (
    <div className="mt-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xs uppercase tracking-[0.16em] text-[var(--ledger-accent)]">{title}</h2>
        <button type="button" onClick={onAdd} className="text-xs text-[var(--ledger-accent)]">Add account</button>
      </div>
      {rows.length === 0 ? <p className={`mt-2 text-sm ${ledgerMuted}`}>None saved yet.</p> : null}
      {rows.map((account) => {
        const badge = account.walletError ? "Disconnected" : account.selected ? "Connected" : "Saved";
        const tone = account.walletError ? "text-[var(--ledger-loss)]" : account.selected ? "text-[var(--ledger-profit)]" : ledgerMuted;
        return (
          <div key={account.id} className={`mt-2 flex items-center justify-between gap-3 px-3 py-2 text-sm ${ledgerPanel}`}>
            <button type="button" onClick={() => onSelect(account)} className="text-left">
              <span className="block">{account.accountName}</span>
              <span className={`text-xs ${tone}`}>{badge}</span>
            </button>
            <input
              className={`w-20 ${ledgerField}`}
              defaultValue={account.riskAmount}
              onBlur={(event) => onRisk(account, event.target.value)}
            />
            <button type="button" className="text-xs text-[var(--ledger-loss)]" onClick={() => onDelete(account)}>Remove</button>
          </div>
        );
      })}
    </div>
  );
}
