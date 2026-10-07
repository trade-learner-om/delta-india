/**
 * Regression checks for USD money formatting (always 2 decimal places).
 * Run: node scripts/test-trading-formatters.mjs
 */
import { formatPnl, formatPremium, formatUsdMoney } from "../src/utils/tradingFormatters.js";

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

assert(formatUsdMoney(1234.5) === "1,234.50", `formatUsdMoney: ${formatUsdMoney(1234.5)}`);
assert(formatPremium(642.88) === "642.88", `formatPremium: ${formatPremium(642.88)}`);
assert(formatPnl(200.77) === "+200.77", `formatPnl positive: ${formatPnl(200.77)}`);
assert(formatPnl(0) === "0.00", `formatPnl zero: ${formatPnl(0)}`);
assert(formatPnl(-15.1) === "-15.10", `formatPnl negative: ${formatPnl(-15.1)}`);

console.log("trading-formatters regression checks passed");
