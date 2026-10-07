import { decoratePositionsPayload } from "../components/positions/positionsUtils";
import { formatPnl } from "./tradingFormatters";

export const CRYPTOBRIDGE_LOGO_SRC = "/Cryptobridge.svg";

export function resolveDocumentTitle({
  positionsPayload,
  livePrices,
  authenticated,
}) {
  if (!authenticated) return "CryptoBridge";

  const decorated = positionsPayload
    ? decoratePositionsPayload(positionsPayload, livePrices)
    : null;
  const openCount = decorated?.openCount ?? decorated?.openPositions?.length ?? 0;

  let runningPl = null;
  if (openCount > 0 && decorated?.openUnrealizedPnlUsd != null) {
    runningPl = Number(decorated.openUnrealizedPnlUsd);
  }

  if (openCount > 0 && runningPl != null && Number.isFinite(runningPl)) {
    return `CryptoBridge :: ${formatPnl(runningPl)}`;
  }
  return "CryptoBridge";
}
