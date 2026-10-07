import { compareBacktestRuns } from "../src/utils/stOptionsBacktestCompare.js";

function run(id, settings, trades) {
  return { id, settings, result: { settings, trades } };
}

const shared = [
  { entryTime: 100, direction: "LONG", optionSymbol: "P-BTC-1", date: "d1", lots: 2, pnl: 100 },
  { entryTime: 200, direction: "SHORT", optionSymbol: "C-BTC-1", date: "d2", lots: 1, pnl: -50 },
];

const a = run("a", { lots: 1, quantity: 1, from: "2026-01-01", to: "2026-01-07" }, shared);
const b = run(
  "b",
  { lots: 1, quantity: 2, from: "2026-01-01", to: "2026-01-07", dynMaxLots: 5 },
  [
    { ...shared[0], lots: 4, pnl: 200 }, // same key; normalize 200 * (1/4) = 50 vs A's 100*(1/2)=50
    { ...shared[1], lots: 1, pnl: -25 },
  ],
);

const comparison = compareBacktestRuns(a, b);
if (comparison.overlapping.length !== 2) {
  throw new Error(`expected 2 overlapping, got ${comparison.overlapping.length}`);
}
const first = comparison.overlapping[0];
if (Math.abs(first.normA - 50) > 1e-6 || Math.abs(first.normB - 50) > 1e-6) {
  throw new Error(`normalize mismatch ${first.normA} ${first.normB}`);
}
console.log("stOptionsBacktestCompare ok");
