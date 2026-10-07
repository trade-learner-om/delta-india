import { useState } from "react";
import { api } from "../../api";

export default function SettingsPage({ token, me, deltaAccounts, mt5Accounts, onReload, onNotify }) {
  const [deltaForm, setDeltaForm] = useState({ apiKey: "", apiSecret: "" });
  const [mt5Form, setMt5Form] = useState({ login: "", password: "", server: "", terminalPath: "" });
  const [symbol, setSymbol] = useState("");
  const [venue, setVenue] = useState("crypto");

  const addDelta = async () => {
    await api("/accounts", { method: "POST", token, body: deltaForm });
    setDeltaForm({ apiKey: "", apiSecret: "" });
    onNotify("success", "Delta account added.");
    onReload();
  };

  const addMt5 = async () => {
    await api("/mt5/accounts", { method: "POST", token, body: mt5Form });
    setMt5Form({ login: "", password: "", server: "", terminalPath: "" });
    onNotify("success", "Forex account added.");
    onReload();
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

  const addSymbol = async () => {
    await api("/watchlist", { method: "POST", token, body: { venue, symbol } });
    setSymbol("");
    onNotify("success", "Added to the watchlist.");
    onReload();
  };

  return (
    <div className="grid gap-4 lg:grid-cols-2">
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
          {["login", "password", "server", "terminalPath"].map((key) => (
            <input
              key={key}
              type={key === "password" ? "password" : "text"}
              className="rounded-lg border border-white/10 bg-[#16181d] px-3 py-2"
              placeholder={key === "terminalPath" ? "terminal64.exe path" : key}
              value={mt5Form[key]}
              onChange={(event) => setMt5Form({ ...mt5Form, [key]: event.target.value })}
            />
          ))}
          <button type="button" onClick={() => addMt5().catch((err) => onNotify("error", err.message))} className="rounded-full bg-[#8eafc4] px-4 py-2 text-sm text-[#16181d]">Add MT5 account</button>
        </div>
      </section>
      <section className="rounded-2xl border border-white/10 bg-[#1e2128] p-5">
        <h2 className="text-xl">Watchlist</h2>
        <div className="mt-4 flex gap-2">
          <select className="rounded-lg border border-white/10 bg-[#16181d] px-3 py-2" value={venue} onChange={(event) => setVenue(event.target.value)}>
            <option value="crypto">Crypto</option>
            <option value="forex">Forex</option>
          </select>
          <input className="flex-1 rounded-lg border border-white/10 bg-[#16181d] px-3 py-2" placeholder="Symbol" value={symbol} onChange={(event) => setSymbol(event.target.value)} />
          <button type="button" onClick={() => addSymbol().catch((err) => onNotify("error", err.message))} className="rounded-full border border-[#8eafc4] px-4 py-2 text-sm text-[#8eafc4]">Add</button>
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
