/**
 * Compare two ST Options backtest runs.
 * Match key: entryTime + direction + optionSymbol
 * Normalize PnL to each run's initial lots: pnl * (runInitialLots / tradeLots)
 */

function tradeKey(trade) {
  return `${trade.entryTime}|${trade.direction}|${trade.optionSymbol}`;
}

function initialLots(run) {
  const settings = run?.settings || run?.result?.settings || {};
  const lots = Number(settings.lots);
  if (Number.isFinite(lots) && lots > 0) return lots;
  const trades = run?.result?.trades || run?.trades || [];
  for (const t of trades) {
    const n = Number(t?.lots);
    if (Number.isFinite(n) && n > 0) return n;
  }
  return 1;
}

function normalizePnl(trade, runLots) {
  const pnl = Number(trade?.pnl);
  const tradeLots = Number(trade?.lots);
  if (!Number.isFinite(pnl)) return null;
  const lots = Number.isFinite(tradeLots) && tradeLots > 0 ? tradeLots : runLots;
  return pnl * (runLots / lots);
}

export function compareBacktestRuns(runA, runB) {
  const settingsA = runA?.settings || runA?.result?.settings || {};
  const settingsB = runB?.settings || runB?.result?.settings || {};
  const tradesA = runA?.result?.trades || runA?.trades || [];
  const tradesB = runB?.result?.trades || runB?.trades || [];
  const lotsA = initialLots(runA);
  const lotsB = initialLots(runB);

  const settingKeys = [
    "underlying",
    "maxRisk",
    "stPeriod",
    "stMultiplier",
    "emaLength",
    "minPremiumPct",
    "stopLossPct",
    "takeProfitPct",
    "breakevenDecayPct",
    "dynamicSizingEnabled",
    "dynAfterLosses",
    "dynIncreasePct",
    "dynMaxRiskPct",
    "dynAfterProfits",
    "dynDecreasePct",
    "strikeSelectMode",
    "strikeType",
    "minPremiumAbs",
    "oneTradePerFormation",
    "skipSetupsAfterTarget",
    "pairHedgeEnabled",
    "pairHedgeMode",
    "pairHedgeDecayPct",
    "from",
    "to",
  ];

  const inputDiffs = settingKeys
    .map((key) => ({
      key,
      a: settingsA[key],
      b: settingsB[key],
      changed: String(settingsA[key] ?? "") !== String(settingsB[key] ?? ""),
    }))
    .filter((row) => row.changed || ["from", "to", "maxRisk", "dynamicSizingEnabled"].includes(row.key));

  const mapA = new Map(tradesA.map((t) => [tradeKey(t), t]));
  const mapB = new Map(tradesB.map((t) => [tradeKey(t), t]));
  const overlapKeys = [...mapA.keys()].filter((k) => mapB.has(k));

  const overlapping = overlapKeys.map((key) => {
    const a = mapA.get(key);
    const b = mapB.get(key);
    const normA = normalizePnl(a, lotsA);
    const normB = normalizePnl(b, lotsB);
    const absDiff = normA != null && normB != null ? normB - normA : null;
    const pctDiff =
      normA != null && normB != null && Math.abs(normA) > 1e-9
        ? ((normB - normA) / Math.abs(normA)) * 100
        : normA === 0 && normB === 0
          ? 0
          : null;
    return {
      key,
      entryTime: a.entryTime,
      direction: a.direction,
      optionSymbol: a.optionSymbol,
      date: a.date,
      lotsA: a.lots,
      lotsB: b.lots,
      pnlA: a.pnl,
      pnlB: b.pnl,
      normA,
      normB,
      absDiff,
      pctDiff,
    };
  });

  const sumA = overlapping.reduce((s, r) => s + (Number(r.normA) || 0), 0);
  const sumB = overlapping.reduce((s, r) => s + (Number(r.normB) || 0), 0);
  const totalAbsDiff = sumB - sumA;
  const totalPctDiff =
    Math.abs(sumA) > 1e-9 ? ((sumB - sumA) / Math.abs(sumA)) * 100 : sumA === 0 && sumB === 0 ? 0 : null;

  let verdict = "Insufficient overlapping trades to compare.";
  if (overlapping.length > 0) {
    if (totalAbsDiff > 0.01) {
      verdict = `Run B outperformed Run A on ${overlapping.length} overlapping trade(s) by ${totalAbsDiff.toFixed(2)} (${
        totalPctDiff == null ? "—" : `${totalPctDiff.toFixed(1)}%`
      }).`;
    } else if (totalAbsDiff < -0.01) {
      verdict = `Run A outperformed Run B on ${overlapping.length} overlapping trade(s) by ${Math.abs(totalAbsDiff).toFixed(2)} (${
        totalPctDiff == null ? "—" : `${Math.abs(totalPctDiff).toFixed(1)}%`
      }).`;
    } else {
      verdict = `Runs are essentially even on ${overlapping.length} overlapping trade(s).`;
    }
  }

  return {
    inputDiffs,
    overlapping,
    onlyInA: tradesA.length - overlapping.length,
    onlyInB: tradesB.length - overlapping.length,
    sumA,
    sumB,
    totalAbsDiff,
    totalPctDiff,
    verdict,
    lotsA,
    lotsB,
  };
}
