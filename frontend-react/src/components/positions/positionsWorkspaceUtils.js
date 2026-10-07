export function computePositionsTotals(positions = []) {
  let totPnl = 0;
  let btcContracts = 0;
  let ethContracts = 0;
  for (const pos of positions) {
    totPnl += Number(pos.unrealizedPnlUsd) || 0;
    const symbol = String(pos.symbol || "");
    if (symbol.startsWith("BTC")) btcContracts += 1;
    if (symbol.startsWith("ETH")) ethContracts += 1;
  }
  return { totPnl, btcContracts, ethContracts, count: positions.length };
}
