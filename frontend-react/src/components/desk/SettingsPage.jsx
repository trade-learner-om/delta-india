import { useEffect, useState } from "react";
import { api } from "../../api";

export default function SettingsPage({ token, me, deltaAccounts, mt5Accounts, onReload, onNotify }) {
  const [deltaForm, setDeltaForm] = useState({ apiKey: "", apiSecret: "" });
  const [mt5Form, setMt5Form] = useState({ login: "", password: "", server: "", terminalPath: "" });
  const [terminalPaths, setTerminalPaths] = useState([]);
  const [terminalNote, setTerminalNote] = useState("");
  const [detecting, setDetecting] = useState(false);
  const [serverIp, setServerIp] = useState("");
  const [serverIpError, setServerIpError] = useState("");
  const [ipCopied, setIpCopied] = useState(false);

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
    onNotify("success", "Delta account added.");
    onReload();
  };

  const addMt5 = async () => {
    await api("/mt5/accounts", { method: "POST", token, body: mt5Form });
    setMt5Form({ login: "", password: "", server: "", terminalPath: "" });
    setTerminalPaths([]);
    setTerminalNote("");
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
        setTerminalNote("");
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
    <div className="mx-auto max-w-3xl">
      <section className="rounded-2xl border border-white/10 bg-[#1e2128] p-5">
        <h1 className="text-xl">Accounts</h1>
        <p className="mt-1 text-sm text-[#9a958c]">{me?.email} · one login for crypto and forex</p>
        <AccountList
          title="Crypto"
          accounts={deltaAccounts}
          selectedVenue={me?.selectedVenue}
          onSelect={(account) => select(account, "crypto")}
          onDelete={(account) => remove(account, "crypto")}
          onRisk={(account, risk) => setRisk(account, "crypto", risk)}
        />
        <div className="mt-4 rounded-xl bg-[#16181d] px-3 py-3 text-sm">
          <p className="text-xs uppercase tracking-[0.14em] text-[#9a958c]">Whitelist this IP on Delta</p>
          <p className="mt-2 font-mono text-lg text-[#8eafc4]">{serverIp || serverIpError || "Loading server IP..."}</p>
          <p className="mt-1 text-xs text-[#9a958c]">Delta allows signed calls only from this server address. Copy it into the API key profile before adding the account.</p>
          <button type="button" disabled={!serverIp} onClick={() => copyIp().catch(() => onNotify("error", "Could not copy the IP."))} className="mt-2 text-xs text-[#8eafc4] disabled:opacity-50">
            {ipCopied ? "Copied" : "Copy IP"}
          </button>
        </div>
        <div className="mt-4 grid gap-2">
          <input className="rounded-lg border border-white/10 bg-[#16181d] px-3 py-2" placeholder="Delta API key" value={deltaForm.apiKey} onChange={(event) => setDeltaForm({ ...deltaForm, apiKey: event.target.value })} />
          <input className="rounded-lg border border-white/10 bg-[#16181d] px-3 py-2" placeholder="Delta API secret" type="password" value={deltaForm.apiSecret} onChange={(event) => setDeltaForm({ ...deltaForm, apiSecret: event.target.value })} />
          <button type="button" onClick={() => addDelta().catch((err) => onNotify("error", err.message))} className="rounded-full bg-[#8eafc4] px-4 py-2 text-sm text-[#16181d]">Add Delta account</button>
        </div>
        <AccountList
          title="Forex"
          accounts={mt5Accounts}
          selectedVenue={me?.selectedVenue}
          onSelect={(account) => select(account, "forex")}
          onDelete={(account) => remove(account, "forex")}
          onRisk={(account, risk) => setRisk(account, "forex", risk)}
        />
        <div className="mt-4 grid gap-2">
          {["login", "password", "server"].map((key) => (
            <input
              key={key}
              type={key === "password" ? "password" : "text"}
              className="rounded-lg border border-white/10 bg-[#16181d] px-3 py-2"
              placeholder={key}
              value={mt5Form[key]}
              onChange={(event) => setMt5Form({ ...mt5Form, [key]: event.target.value })}
            />
          ))}
          <div className="flex gap-2">
            <input
              className="min-w-0 flex-1 rounded-lg border border-white/10 bg-[#16181d] px-3 py-2"
              placeholder="terminal64.exe path"
              value={mt5Form.terminalPath}
              onChange={(event) => setMt5Form({ ...mt5Form, terminalPath: event.target.value })}
            />
            <button
              type="button"
              disabled={detecting}
              onClick={detectTerminals}
              className="rounded-full border border-[#8eafc4] px-4 py-2 text-sm text-[#8eafc4] disabled:opacity-50"
            >
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
                  className={`truncate rounded-lg px-3 py-2 text-left text-xs ${mt5Form.terminalPath === path ? "bg-[#24303a] text-[#8eafc4]" : "bg-[#16181d] text-[#9a958c]"}`}
                >
                  {path}
                </button>
              ))}
            </div>
          ) : null}
          {terminalNote ? <p className="text-xs text-[#9a958c]">{terminalNote}</p> : null}
          <button type="button" onClick={() => addMt5().catch((err) => onNotify("error", err.message))} className="rounded-full bg-[#8eafc4] px-4 py-2 text-sm text-[#16181d]">Add MT5 account</button>
        </div>
      </section>
    </div>
  );
}

function AccountList({ title, accounts, selectedVenue, onSelect, onDelete, onRisk }) {
  return (
    <div className="mt-6">
      <h2 className="text-xs uppercase tracking-[0.16em] text-[#8eafc4]">{title}</h2>
      {(accounts || []).map((account) => (
        <div key={account.id} className="mt-2 flex items-center justify-between gap-3 rounded-xl bg-[#16181d] px-3 py-2 text-sm">
          <button type="button" onClick={() => onSelect(account)} className="text-left">
            <span className="block">{account.accountName}</span>
            <span className="text-xs text-[#9a958c]">{account.selected && selectedVenue ? "Selected" : "Select"}</span>
          </button>
          <input
            className="w-20 rounded-lg border border-white/10 bg-[#1e2128] px-2 py-1"
            defaultValue={account.riskAmount}
            onBlur={(event) => onRisk(account, event.target.value)}
          />
          <button type="button" className="text-xs text-[#c48b84]" onClick={() => onDelete(account)}>Remove</button>
        </div>
      ))}
    </div>
  );
}
