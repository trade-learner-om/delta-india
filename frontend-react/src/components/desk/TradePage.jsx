import { useEffect, useState } from "react";
import { api } from "../../api";
import ChoiceSwitch from "./ChoiceSwitch";
import { formatRr, ledgerField, ledgerMuted, ledgerPanel, money, rewardRisk } from "./deskFormat";

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
  const liveRr = rewardRisk(form.side, form.entry, form.stopLoss, form.target);
  const stopDistance = Math.abs(Number(form.entry) - Number(form.stopLoss));

  useEffect(() => {
    setRisk(account?.riskAmount ?? "");
  }, [account?.id, account?.riskAmount, form.venue]);

  const set = (key) => (event) => {
    setPreview(null);
    setForm((current) => ({ ...current, [key]: event.target.value }));
  };

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

  const summary = [
    ["Account", account?.accountName || "—"],
    ["Venue", form.venue],
    ["Risk", Number(risk) > 0 ? money(risk) : "—"],
    ["Quantity", preview?.quantity ?? "—"],
    ["R:R", formatRr(liveRr)],
    ["Stop distance", Number.isFinite(stopDistance) && stopDistance > 0 ? stopDistance : "—"],
  ];

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <section className={`p-6 ${ledgerPanel}`}>
        <h1 className="text-xl">Trade</h1>
        <p className={`mt-1 text-sm ${ledgerMuted}`}>Size comes from the risk amount for this venue.</p>
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
                className={`mt-1 ${ledgerField}`}
                value={risk}
                onChange={(event) => setRisk(event.target.value)}
                onBlur={() => saveRisk().catch((err) => onNotify("error", err.message || "Could not save the risk amount."))}
              />
            ) : (
              <p className={`mt-1 text-sm ${ledgerMuted}`}>Select a {form.venue} account in Settings.</p>
            )}
            {account ? <span className={`mt-1 block text-xs ${ledgerMuted}`}>{account.accountName}</span> : null}
          </label>
          <label className="text-sm">
            Symbol
            <input className={`mt-1 ${ledgerField}`} value={form.symbol} onChange={set("symbol")} />
          </label>
          <ChoiceSwitch
            label="Side"
            tone="side"
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
                <input className={`mt-1 ${ledgerField}`} value={form[key]} onChange={set(key)} />
              </label>
            ))}
          </div>
        </div>
        <div className={`mt-4 p-3 text-sm ${ledgerPanel}`}>
          <p className={ledgerMuted}>Reward to risk</p>
          <p className="mt-1 text-2xl font-semibold">{formatRr(liveRr)}</p>
          <p className={`mt-1 ${ledgerMuted}`}>Quantity {preview?.quantity ?? "appears after preview"}</p>
        </div>
        <div className="mt-5 flex gap-2">
          <button type="button" disabled={pending} onClick={runPreview} className="rounded-full border border-[var(--ledger-accent)] px-4 py-2 text-sm text-[var(--ledger-accent)]">
            Preview
          </button>
          <button
            type="button"
            disabled={pending || !preview}
            onClick={place}
            className="rounded-full bg-[var(--ledger-accent)] px-4 py-2 text-sm text-white transition hover:brightness-110 disabled:opacity-50"
          >
            Place Order
          </button>
        </div>
      </section>
      <section className={`flex min-h-[28rem] flex-col p-6 ${ledgerPanel}`}>
        <h2 className="text-sm uppercase tracking-[0.16em] text-[var(--ledger-muted)]">Risk summary</h2>
        <p className="mt-2 text-2xl">{form.symbol.trim().toUpperCase() || "Symbol"}</p>
        <dl className="mt-6 grid flex-1 content-start gap-3">
          {summary.map(([label, value]) => (
            <div key={label} className="flex items-center justify-between border-b border-[var(--ledger-border)] py-2 text-sm">
              <dt className={ledgerMuted}>{label}</dt>
              <dd className="capitalize">{value}</dd>
            </div>
          ))}
        </dl>
      </section>
    </div>
  );
}
