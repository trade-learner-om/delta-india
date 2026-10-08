import { useState } from "react";
import { api } from "../../api";
import PriceFlashTicker from "./PriceFlashTicker";
import { formatPrice, ledgerField, ledgerMuted, ledgerPanel, money, pnlPill } from "./deskFormat";

function sideLabel(side) {
  const value = String(side || "").toUpperCase();
  if (value === "LONG" || value === "BUY") return "Buy";
  if (value === "SHORT" || value === "SELL") return "Sell";
  return value || "—";
}

function sizeLabel(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  return String(number);
}

function RunningPositions({ rows }) {
  return (
    <section className={`p-4 ${ledgerPanel}`}>
      <h2 className={`text-sm ${ledgerMuted}`}>Running positions</h2>
      <table className="mt-3 w-full text-left text-sm">
        <thead className={`text-xs uppercase tracking-wider ${ledgerMuted}`}>
          <tr>
            <th className="py-2 font-medium">Symbol</th>
            <th className="py-2 font-medium">Side</th>
            <th className="py-2 text-right font-medium">Size</th>
            <th className="py-2 text-right font-medium">Entry</th>
            <th className="py-2 text-right font-medium">Mark</th>
            <th className="py-2 text-right font-medium">P/L</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className="border-t border-[var(--ledger-border)]">
              <td className="py-2">
                <span className="block">{row.symbol}</span>
                <span className={`block text-xs capitalize ${ledgerMuted}`}>{row.accountName} · {row.venue}</span>
              </td>
              <td className="py-2">{sideLabel(row.side)}</td>
              <td className="py-2 text-right">{sizeLabel(row.size)}</td>
              <td className="py-2 text-right">{formatPrice(row.entryPrice)}</td>
              <td className="py-2 text-right">
                <PriceFlashTicker value={row.markPrice}>{formatPrice(row.markPrice)}</PriceFlashTicker>
              </td>
              <td className="py-2 text-right">
                <PriceFlashTicker value={row.unrealizedPnlUsd}>
                  <span className={pnlPill(row.unrealizedPnlUsd)}>{money(row.unrealizedPnlUsd)}</span>
                </PriceFlashTicker>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function orderPrice(row) {
  const price = Number(row?.price);
  if (Number.isFinite(price) && price > 0) return price;
  const stop = Number(row?.stopPrice);
  return Number.isFinite(stop) && stop > 0 ? stop : null;
}

function orderSize(row) {
  const size = Number(row?.size ?? row?.unfilledSize);
  return Number.isFinite(size) && size > 0 ? size : null;
}

function PendingOrders({ rows, token, onNotify, onChanged }) {
  const [editingId, setEditingId] = useState("");
  const [confirmId, setConfirmId] = useState("");
  const [draft, setDraft] = useState({ price: "", size: "" });
  const [busyId, setBusyId] = useState("");

  const beginEdit = (row) => {
    setConfirmId("");
    setEditingId(row.id);
    setDraft({
      price: orderPrice(row) == null ? "" : String(orderPrice(row)),
      size: orderSize(row) == null ? "" : String(orderSize(row)),
    });
  };

  const cancelOrder = async (row) => {
    setBusyId(row.id);
    try {
      await api("/orders/pending/cancel", {
        method: "POST",
        token,
        body: { venue: row.venue, accountId: row.accountId, orderId: row.orderId },
      });
      onNotify?.("success", "Order cancelled.");
      setConfirmId("");
      onChanged?.();
    } catch (err) {
      onNotify?.("error", err.message || "Order was not cancelled.");
    } finally {
      setBusyId("");
    }
  };

  const saveOrder = async (row) => {
    const price = Number(draft.price);
    const size = Number(draft.size);
    if (!(price > 0) || !(size > 0)) {
      onNotify?.("error", "Price and size must be greater than zero.");
      return;
    }
    setBusyId(row.id);
    try {
      await api("/orders/pending/edit", {
        method: "POST",
        token,
        body: { venue: row.venue, accountId: row.accountId, orderId: row.orderId, price, size },
      });
      onNotify?.("success", "Order updated.");
      setEditingId("");
      onChanged?.();
    } catch (err) {
      onNotify?.("error", err.message || "Order was not updated.");
    } finally {
      setBusyId("");
    }
  };

  return (
    <section className={`p-4 ${ledgerPanel}`}>
      <h2 className={`text-sm ${ledgerMuted}`}>Pending orders</h2>
      <table className="mt-3 w-full text-left text-sm">
        <thead className={`text-xs uppercase tracking-wider ${ledgerMuted}`}>
          <tr>
            <th className="py-2 font-medium">Symbol</th>
            <th className="py-2 font-medium">Side</th>
            <th className="py-2 font-medium">Type</th>
            <th className="py-2 text-right font-medium">Price</th>
            <th className="py-2 text-right font-medium">Size</th>
            <th className="py-2 text-right font-medium">Actions</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const editing = editingId === row.id;
            const confirming = confirmId === row.id;
            const busy = busyId === row.id;
            return (
              <tr key={row.id} className="border-t border-[var(--ledger-border)]">
                <td className="py-2">
                  <span className="block">{row.symbol}</span>
                  <span className={`block text-xs capitalize ${ledgerMuted}`}>{row.accountName} · {row.venue}</span>
                </td>
                <td className="py-2">{sideLabel(row.side)}</td>
                <td className={`py-2 capitalize ${ledgerMuted}`}>{row.orderType || "—"}</td>
                <td className="py-2 text-right">
                  {editing ? (
                    <input
                      aria-label={`Price for ${row.symbol}`}
                      value={draft.price}
                      onChange={(event) => setDraft((current) => ({ ...current, price: event.target.value }))}
                      className={`${ledgerField} ml-auto w-28 text-right`}
                    />
                  ) : formatPrice(orderPrice(row))}
                </td>
                <td className="py-2 text-right">
                  {editing ? (
                    <input
                      aria-label={`Size for ${row.symbol}`}
                      value={draft.size}
                      onChange={(event) => setDraft((current) => ({ ...current, size: event.target.value }))}
                      className={`${ledgerField} ml-auto w-24 text-right`}
                    />
                  ) : sizeLabel(orderSize(row))}
                </td>
                <td className="py-2 text-right">
                  <div className="flex justify-end gap-2">
                    {editing ? (
                      <>
                        <button type="button" disabled={busy} onClick={() => saveOrder(row)} className="rounded-full bg-[var(--ledger-accent)] px-3 py-1 text-xs text-white disabled:opacity-50">Save</button>
                        <button type="button" disabled={busy} onClick={() => setEditingId("")} className="rounded-full border border-[var(--ledger-border)] px-3 py-1 text-xs">Close</button>
                      </>
                    ) : confirming ? (
                      <>
                        <button type="button" disabled={busy} onClick={() => cancelOrder(row)} className="rounded-full bg-[var(--ledger-loss)] px-3 py-1 text-xs text-white disabled:opacity-50">Confirm</button>
                        <button type="button" disabled={busy} onClick={() => setConfirmId("")} className="rounded-full border border-[var(--ledger-border)] px-3 py-1 text-xs">Keep</button>
                      </>
                    ) : (
                      <>
                        <button type="button" disabled={busy} onClick={() => beginEdit(row)} className="rounded-full border border-[var(--ledger-border)] px-3 py-1 text-xs">Edit</button>
                        <button type="button" disabled={busy} onClick={() => { setEditingId(""); setConfirmId(row.id); }} className="rounded-full border border-[var(--ledger-loss)] px-3 py-1 text-xs text-[var(--ledger-loss)]">Cancel</button>
                      </>
                    )}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}

export default function OpenBookTiles({ positions = [], orders = [], token, onNotify, onChanged }) {
  if (!positions.length && !orders.length) return null;
  return (
    <div className={`grid gap-3 ${positions.length && orders.length ? "md:grid-cols-2" : ""}`}>
      {positions.length ? <RunningPositions rows={positions} /> : null}
      {orders.length ? <PendingOrders rows={orders} token={token} onNotify={onNotify} onChanged={onChanged} /> : null}
    </div>
  );
}
