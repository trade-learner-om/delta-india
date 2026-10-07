import { useEffect, useState } from "react";
import { api } from "../../api";
import ChoiceSwitch from "./ChoiceSwitch";

const EMPTY = { venue: "crypto", symbol: "", side: "BUY", orderType: "MARKET", entry: "", stopLoss: "", target: "" };

function accountForVenue(venue, deltaAccounts, mt5Accounts) {
  const list = venue === "forex" ? mt5Accounts : deltaAccounts;
  return (list || []).find((account) => account.selected) || ((list || []).length === 1 ? list[0] : null);
}

export default function TradePage({ token, deltaAccounts, mt5Accounts, onNotify, onReload }) {
  const [form, setForm] = useState(EMPTY);
  const [preview, setPreview] = useState(null);
  const [pending, setPending] = useState(false);
  const [risk, setRisk] = useState("");
  const account = accountForVenue(form.venue, deltaAccounts, mt5Accounts);

  useEffect(() => {
    setRisk(account?.riskAmount ?? "");
  }, [account?.id, account?.riskAmount, form.venue]);

  const set = (key) => (event) => setForm((current) => ({ ...current, [key]: event.target.value }));

  const body = {
    venue: form.venue,
    symbol: form.symbol.trim().toUpperCase(),
    side: form.side,
    orderType: form.orderType,
    entry: form.entry === "" ? null : Number(form.entry),
    stopLoss: form.stopLoss === "" ? null : Number(form.stopLoss),
    target: form.target === "" ? null : Number(form.target),
  };

  const ensureSelected = async () => {
    if (!account || account.selected) return;
    const path = form.venue === "forex" ? "/mt5/accounts/select" : "/accounts/select";
    await api(path, { method: "POST", token, body: { accountId: account.id } });
    onReload?.();
  };

  const saveRisk = async () => {
    if (!account) return;
    const next = Number(risk);
    if (!Number.isFinite(next) || next <= 0) {
      onNotify("error", "Risk amount must be greater than 0.");
      setRisk(account.riskAmount ?? "");
      return;
    }
    if (next === Number(account.riskAmount)) return;
    const path = form.venue === "forex" ? `/mt5/accounts/${account.id}/risk` : `/accounts/${account.id}/risk`;
    await api(path, { method: "PATCH", token, body: { riskAmount: next } });
    onNotify("success", "Risk amount saved.");
    onReload?.();
  };

  const runPreview = async () => {
    setPending(true);
    try {
      await ensureSelected();
      const result = await api("/orders/preview", { method: "POST", token, body });
      setPreview(result);
    } catch (err) {
      setPreview(null);
      onNotify("error", err.message || "Could not size this order.");
    } finally {
      setPending(false);
    }
  };

  const place = async () => {
    setPending(true);
    try {
      await ensureSelected();
      await api("/orders", { method: "POST", token, body });
      onNotify("success", "Order sent.");
      setPreview(null);
    } catch (err) {
      onNotify("error", err.message || "Order was not sent.");
    } finally {
      setPending(false);
    }
  };

  return (
    <section className="mx-auto max-w-xl rounded-2xl border border-white/10 bg-[#1e2128] p-6">
      <h1 className="text-xl">Trade</h1>
      <p className="mt-1 text-sm text-[#9a958c]">Size comes from the risk amount for this venue.</p>
      <div className="mt-5 grid gap-3">
        <ChoiceSwitch
          label="Venue"
          value={form.venue}
          onChange={(venue) => {
            setForm((current) => ({ ...current, venue }));
            setPreview(null);
            const next = accountForVenue(venue, deltaAccounts, mt5Accounts);
            if (next && !next.selected) {
              const path = venue === "forex" ? "/mt5/accounts/select" : "/accounts/select";
              api(path, { method: "POST", token, body: { accountId: next.id } })
                .then(() => onReload?.())
                .catch((err) => onNotify("error", err.message || "Could not select that account."));
            }
          }}
          options={[["crypto", "Crypto"], ["forex", "Forex"]]}
        />
        <label className="text-sm">
          Risk amount (USD)
          {account ? (
            <input
              className="mt-1 w-full rounded-lg border border-white/10 bg-[#16181d] px-3 py-2"
              value={risk}
              onChange={(event) => setRisk(event.target.value)}
              onBlur={() => saveRisk().catch((err) => onNotify("error", err.message || "Could not save the risk amount."))}
            />
          ) : (
            <p className="mt-1 text-sm text-[#9a958c]">Select a {form.venue} account in Settings.</p>
          )}
          {account ? <span className="mt-1 block text-xs text-[#9a958c]">{account.accountName}</span> : null}
        </label>
        <label className="text-sm">
          Symbol
          <input className="mt-1 w-full rounded-lg border border-white/10 bg-[#16181d] px-3 py-2" value={form.symbol} onChange={set("symbol")} />
        </label>
        <ChoiceSwitch
          label="Side"
          value={form.side}
          onChange={(side) => setForm((current) => ({ ...current, side }))}
          options={[["BUY", "Buy"], ["SELL", "Sell"]]}
        />
        <ChoiceSwitch
          label="Order"
          value={form.orderType}
          onChange={(orderType) => setForm((current) => ({ ...current, orderType }))}
          options={[["MARKET", "Market"], ["LIMIT", "Limit"], ["SL", "Stop"]]}
        />
        <div className="grid grid-cols-3 gap-3">
          {["entry", "stopLoss", "target"].map((key) => (
            <label key={key} className="text-sm capitalize">
              {key === "stopLoss" ? "Stop" : key}
              <input className="mt-1 w-full rounded-lg border border-white/10 bg-[#16181d] px-3 py-2" value={form[key]} onChange={set(key)} />
            </label>
          ))}
        </div>
      </div>
      {preview ? (
        <p className="mt-4 text-sm text-[#e6e2d8]">
          {preview.accountName}: quantity {preview.quantity}
          {preview.rr != null ? `, R ${preview.rr}` : ""}
        </p>
      ) : null}
      <div className="mt-5 flex gap-2">
        <button type="button" disabled={pending} onClick={runPreview} className="rounded-full border border-[#8eafc4] px-4 py-2 text-sm text-[#8eafc4]">
          Preview
        </button>
        <button type="button" disabled={pending || !preview} onClick={place} className="rounded-full bg-[#8eafc4] px-4 py-2 text-sm text-[#16181d] disabled:opacity-50">
          Place order
        </button>
      </div>
    </section>
  );
}
