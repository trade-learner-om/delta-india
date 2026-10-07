import { useState } from "react";
import { api } from "../../api";

const EMPTY = { venue: "crypto", symbol: "", side: "BUY", orderType: "MARKET", entry: "", stopLoss: "", target: "" };

export default function TradePage({ token, onNotify }) {
  const [form, setForm] = useState(EMPTY);
  const [preview, setPreview] = useState(null);
  const [pending, setPending] = useState(false);

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

  const runPreview = async () => {
    setPending(true);
    try {
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
      <p className="mt-1 text-sm text-[#9a958c]">Size comes from the selected account’s risk amount.</p>
      <div className="mt-5 grid gap-3">
        <label className="text-sm">
          Venue
          <select className="mt-1 w-full rounded-lg border border-white/10 bg-[#16181d] px-3 py-2" value={form.venue} onChange={set("venue")}>
            <option value="crypto">Crypto</option>
            <option value="forex">Forex</option>
          </select>
        </label>
        <label className="text-sm">
          Symbol
          <input className="mt-1 w-full rounded-lg border border-white/10 bg-[#16181d] px-3 py-2" value={form.symbol} onChange={set("symbol")} />
        </label>
        <div className="grid grid-cols-2 gap-3">
          <label className="text-sm">
            Side
            <select className="mt-1 w-full rounded-lg border border-white/10 bg-[#16181d] px-3 py-2" value={form.side} onChange={set("side")}>
              <option value="BUY">Buy</option>
              <option value="SELL">Sell</option>
            </select>
          </label>
          <label className="text-sm">
            Order
            <select className="mt-1 w-full rounded-lg border border-white/10 bg-[#16181d] px-3 py-2" value={form.orderType} onChange={set("orderType")}>
              <option value="MARKET">Market</option>
              <option value="LIMIT">Limit</option>
              <option value="SL">Stop</option>
            </select>
          </label>
        </div>
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
