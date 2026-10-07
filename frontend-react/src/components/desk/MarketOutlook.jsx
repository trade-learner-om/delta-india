import { useEffect, useState } from "react";
import { AlertTriangle, BrainCircuit, Coins, Globe } from "lucide-react";
import { api } from "../../api";
import CoinIcon from "../CoinIcon";
import { livePriceFromTick, lookupLiveTick } from "../../utils/pricePrecision";
import { formatPrice, ledgerMuted, ledgerPanel } from "./deskFormat";
import PriceFlashTicker from "./PriceFlashTicker";

export const CAUTION = "Caution: These probabilities are AI-generated market simulations for educational purposes only. Do not initiate trades based on these results.";

const HORIZONS = [
  ["horizon_1h", "1H"],
  ["horizon_4h", "4H"],
  ["horizon_24h", "24H"],
];

const TILES = [
  {
    title: "Crypto Market Overview",
    venue: "crypto",
    Icon: Coins,
    symbols: ["BTCUSD", "ETHUSD", "SOLUSD"],
  },
  {
    title: "Forex Market Overview",
    venue: "forex",
    Icon: Globe,
    symbols: ["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDCAD", "USDCHF", "USDJPY", "EURJPY", "GBPJPY", "XAUUSD", "XAGUSD"],
  },
];

export default function MarketOutlook({ token, livePrices }) {
  const [rows, setRows] = useState({});

  useEffect(() => {
    if (!token) return undefined;
    let cancelled = false;
    const symbols = TILES.flatMap((tile) => tile.symbols);
    setRows(Object.fromEntries(symbols.map((symbol) => [symbol, { status: "loading" }])));
    symbols.forEach((symbol) => {
      api(`/ai-predictions?symbol=${encodeURIComponent(symbol)}`, { token })
        .then((data) => {
          if (!cancelled) setRows((current) => ({ ...current, [symbol]: { status: "ready", data } }));
        })
        .catch((err) => {
          if (!cancelled) setRows((current) => ({ ...current, [symbol]: { status: "error", error: err.message || "Forecast unavailable." } }));
        });
    });
    return () => {
      cancelled = true;
    };
  }, [token]);

  return (
    <div className="grid gap-4 xl:grid-cols-2">
      {TILES.map((tile) => (
        <section key={tile.venue} className={`space-y-3 p-4 ${ledgerPanel}`}>
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <tile.Icon size={16} />
            {tile.title}
          </h2>
          <div className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-300">
            <AlertTriangle size={14} className="shrink-0" />
            <p>{CAUTION}</p>
          </div>
          <div className="space-y-3">
            {tile.symbols.map((symbol) => (
              <ForecastRow key={symbol} symbol={symbol} row={rows[symbol]} livePrices={livePrices} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function ForecastRow({ symbol, row, livePrices }) {
  const price = livePriceFromTick(lookupLiveTick(livePrices, symbol));
  return (
    <article className="rounded-xl border border-[var(--ledger-border)] p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="inline-flex items-center gap-2 text-sm font-semibold">
          <CoinIcon coin={symbol} size={18} />
          {symbol}
          <BrainCircuit size={14} className={ledgerMuted} />
        </p>
        <PriceFlashTicker value={price} className={`text-sm ${ledgerMuted}`}>
          {price == null ? "—" : formatPrice(price)}
        </PriceFlashTicker>
      </div>
      {row?.status === "loading" || !row ? <p className={`mt-2 text-xs ${ledgerMuted}`}>Loading forecast…</p> : null}
      {row?.status === "error" ? <p className="mt-2 text-xs text-[var(--ledger-loss)]">{row.error}</p> : null}
      {row?.status === "ready" ? (
        <div className="mt-3 space-y-2">
          {HORIZONS.map(([key, label]) => (
            <HorizonBar key={key} label={label} horizon={row.data?.[key]} />
          ))}
          {row.data?.technical_rationale ? <p className={`text-xs ${ledgerMuted}`}>{row.data.technical_rationale}</p> : null}
        </div>
      ) : null}
    </article>
  );
}

function HorizonBar({ label, horizon }) {
  const bullish = Number(horizon?.bullish);
  const bearish = Number(horizon?.bearish);
  const width = Number.isFinite(bullish) ? Math.max(0, Math.min(100, bullish)) : 0;
  return (
    <div>
      <div className="mb-1 flex items-center justify-between gap-2 text-[11px]">
        <span className={ledgerMuted}>{label}</span>
        <span className="flex gap-1">
          <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 font-semibold text-[var(--ledger-profit)]">
            Bull {Number.isFinite(bullish) ? bullish : "—"}%
          </span>
          <span className="rounded-full bg-rose-500/10 px-2 py-0.5 font-semibold text-[var(--ledger-loss)]">
            Bear {Number.isFinite(bearish) ? bearish : "—"}%
          </span>
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-[var(--ledger-canvas)]">
        <div className="h-full bg-[var(--ledger-profit)]" style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}
