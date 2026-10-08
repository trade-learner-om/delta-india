import PriceFlashTicker from "./PriceFlashTicker";
import { formatPrice, ledgerMuted, ledgerPanel, money, pnlPill } from "./deskFormat";

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

function PendingOrders({ rows }) {
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
              <td className={`py-2 capitalize ${ledgerMuted}`}>{row.orderType || "—"}</td>
              <td className="py-2 text-right">{formatPrice(row.price)}</td>
              <td className="py-2 text-right">{sizeLabel(row.size ?? row.unfilledSize)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

export default function OpenBookTiles({ positions = [], orders = [] }) {
  if (!positions.length && !orders.length) return null;
  return (
    <div className={`grid gap-3 ${positions.length && orders.length ? "md:grid-cols-2" : ""}`}>
      {positions.length ? <RunningPositions rows={positions} /> : null}
      {orders.length ? <PendingOrders rows={orders} /> : null}
    </div>
  );
}
