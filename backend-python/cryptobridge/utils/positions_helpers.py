from __future__ import annotations

from typing import Any

from cryptobridge.delta.rest_client import OrderSummary, normalize_symbol


def delta_base_coin(row: dict[str, Any]) -> str | None:
    symbol = str(row.get("underlying_asset_symbol") or row.get("symbol") or "")
    normalized = normalize_symbol(symbol)
    if normalized.endswith("USD"):
        normalized = normalized[:-3]
    if normalized.startswith(("C-", "P-")):
        parts = normalized.split("-")
        if len(parts) > 1:
            normalized = parts[1]
    return normalized or None


def _parse_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def position_id(broker: str, account_id: str, symbol: str) -> str:
    return f"{broker}:{account_id}:{symbol}"


def _is_delta_option(symbol: str) -> bool:
    return str(symbol or "")[:2] in ("C-", "P-")


def _option_contract_value(coin: str | None) -> float:
    # Delta options: 1 contract = 0.001 BTC / 0.01 ETH of underlying.
    return 0.01 if str(coin or "").upper() == "ETH" else 0.001


def order_id(broker: str, account_id: str, order_key: str) -> str:
    return f"{broker}:{account_id}:{order_key}"


def delta_position_view(
    pos: dict[str, Any],
    account_id: str,
    *,
    source: str = "broker",
    linked_trade_id: str | None = None,
    trade_type: str | None = None,
) -> dict[str, Any] | None:
    symbol = normalize_symbol(str(pos.get("product_symbol") or pos.get("symbol") or ""))
    size = _parse_float(pos.get("size"))
    if not symbol or size is None or size == 0:
        return None
    side = "LONG" if size > 0 else "SHORT"
    coin = delta_base_coin({"symbol": symbol, "underlying_asset_symbol": pos.get("underlying_asset_symbol")}) or symbol
    entry = _parse_float(pos.get("entry_price") or pos.get("average_entry_price") or pos.get("avg_entry_price"))
    mark = _parse_float(pos.get("mark_price"))
    liq = _parse_float(pos.get("liquidation_price"))
    contract_value = _parse_float(pos.get("contract_value")) or (_option_contract_value(coin) if _is_delta_option(symbol) else 1.0)
    pnl = _parse_float(pos.get("unrealized_pnl") or pos.get("unrealizedPnl"))
    raw_pnl = pnl
    if _is_delta_option(symbol) and entry is not None and mark is not None:
        side_sign = 1.0 if size > 0 else -1.0
        pnl = side_sign * (mark - entry) * contract_value * abs(size)
    funding = _parse_float(pos.get("realized_funding") or pos.get("realizedFunding")) or 0.0
    base_units = abs(size) * contract_value
    signed_base_units = size * contract_value
    return {
        "id": position_id("delta", account_id, symbol),
        "broker": "delta",
        "accountId": account_id,
        "source": source,
        "tradeType": trade_type,
        "linkedTradeId": linked_trade_id,
        "coin": coin,
        "symbol": symbol,
        "side": side,
        "size": abs(size),
        "signedSize": size,
        "contractValue": contract_value,
        "baseUnits": base_units,
        "signedBaseUnits": signed_base_units,
        "entryPrice": entry,
        "markPrice": mark,
        "liquidationPrice": liq,
        "unrealizedPnlUsd": pnl,
        "brokerUnrealizedPnl": raw_pnl,
        "fundingUsd": funding,
        "isSpreadLeg": trade_type == "spread",
    }


def delta_order_view(order: OrderSummary | dict[str, Any], account_id: str) -> dict[str, Any]:
    if isinstance(order, dict):
        order_id_value = order.get("id") or order.get("order_id")
        symbol = normalize_symbol(str(order.get("product_symbol") or order.get("symbol") or ""))
        side = str(order.get("side") or "").upper()
        order_type = str(order.get("order_type") or order.get("type") or "")
        status = str(order.get("state") or order.get("status") or "")
        limit_price = _parse_float(order.get("limit_price") or order.get("average_fill_price"))
        stop_price = _parse_float(order.get("stop_price") or order.get("stopPrice"))
        size = _parse_float(order.get("size"))
        unfilled_size = _parse_float(order.get("unfilled_size") or order.get("unfilledSize"))
        reduce_only = bool(order.get("reduce_only") or order.get("reduceOnly"))
        created_at = order.get("created_at") or order.get("createdAt")
        client_order_id = order.get("client_order_id") or order.get("clientOrderId")
    else:
        order_id_value = order.id
        symbol = order.symbol
        side = order.side
        order_type = order.order_type
        status = order.status
        limit_price = order.limit_price
        stop_price = order.stop_price
        size = order.size
        unfilled_size = order.unfilled_size
        reduce_only = order.reduce_only
        created_at = order.created_at
        client_order_id = order.client_order_id

    return {
        "id": order_id("delta", account_id, str(order_id_value)),
        "broker": "delta",
        "accountId": account_id,
        "orderId": order_id_value,
        "symbol": symbol,
        "coin": delta_base_coin({"symbol": symbol}) or symbol,
        "side": side,
        "orderType": order_type,
        "status": status,
        "price": limit_price,
        "stopPrice": stop_price,
        "size": size,
        "unfilledSize": unfilled_size,
        "reduceOnly": reduce_only,
        "createdAt": created_at,
        "clientOrderId": client_order_id,
    }


def forex_position_view(row: dict[str, Any], account_id: str, account_name: str) -> dict[str, Any] | None:
    symbol = str(row.get("symbol") or "")
    size = _parse_float(row.get("size"))
    if not symbol or size is None or size == 0:
        return None
    side = "LONG" if str(row.get("side") or "").upper() in {"BUY", "LONG"} else "SHORT"
    signed = abs(size) if side == "LONG" else -abs(size)
    ticket = row.get("ticket")
    return {
        "id": position_id("mt5", account_id, f"{ticket}:{symbol}"),
        "broker": "mt5",
        "venue": "forex",
        "accountId": account_id,
        "accountName": account_name,
        "symbol": symbol,
        "side": side,
        "size": abs(size),
        "signedSize": signed,
        "contractValue": None,
        "entryPrice": _parse_float(row.get("entryPrice")),
        "markPrice": _parse_float(row.get("markPrice")),
        "unrealizedPnlUsd": _parse_float(row.get("unrealizedPnl")) or 0.0,
    }


def forex_order_view(row: dict[str, Any], account_id: str, account_name: str) -> dict[str, Any] | None:
    symbol = str(row.get("symbol") or "")
    ticket = row.get("ticket")
    if not symbol or ticket in (None, ""):
        return None
    return {
        "id": order_id("mt5", account_id, str(ticket)),
        "broker": "mt5",
        "venue": "forex",
        "accountId": account_id,
        "accountName": account_name,
        "orderId": ticket,
        "symbol": symbol,
        "side": str(row.get("side") or "").upper(),
        "orderType": str(row.get("orderType") or ""),
        "status": "pending",
        "price": _parse_float(row.get("price")),
        "size": _parse_float(row.get("size")),
    }


def is_open_order_status(status: str) -> bool:
    normalized = str(status or "").upper()
    return normalized in {"PENDING", "OPEN", "PARTIALLY_FILLED", "PARTIALLY FILLED"}


def is_history_order_status(status: str) -> bool:
    normalized = str(status or "").upper()
    return normalized in {"CLOSED", "CANCELLED", "CANCELED", "FILLED", "REJECTED", "EXPIRED"}


def group_orders_by_broker(orders: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {"delta": []}
    for row in orders:
        broker = str(row.get("broker") or "").lower()
        if broker in grouped:
            grouped[broker].append(row)
    grouped["delta"].sort(key=lambda item: str(item.get("createdAt") or ""), reverse=True)
    return grouped
def compute_open_totals(positions: list[dict[str, Any]]) -> dict[str, float]:
    pnl = 0.0
    funding = 0.0
    for pos in positions:
        pnl += float(pos.get("unrealizedPnlUsd") or 0)
        funding += float(pos.get("fundingUsd") or 0)
    return {"openUnrealizedPnlUsd": round(pnl, 4), "openFundingUsd": round(funding, 4)}


def position_watch_symbols(positions: list[dict[str, Any]]) -> set[str]:
    """Public + index symbols needed for live mark/PnL on open positions."""
    symbols: set[str] = set()
    for pos in positions:
        sym = normalize_symbol(str(pos.get("symbol") or ""))
        if sym:
            symbols.add(sym)
        coin = str(pos.get("coin") or "").strip().upper()
        if coin and not coin.endswith("USD"):
            symbols.add(f"{coin}USD")
    return symbols


def enrich_broker_position_mark(
    pos: dict[str, Any],
    latest_tickers: dict[str, Any],
) -> dict[str, Any]:
    """Overlay a live public mark when the private positions cache is stale."""
    symbol = normalize_symbol(str(pos.get("product_symbol") or pos.get("symbol") or ""))
    ticker = latest_tickers.get(symbol)
    if ticker is None:
        return pos
    mark = None
    for attr in ("mark_price", "last_price"):
        value = getattr(ticker, attr, None)
        if isinstance(value, (int, float)) and value > 0:
            mark = float(value)
            break
    if mark is None:
        bid = getattr(ticker, "bid", None)
        ask = getattr(ticker, "ask", None)
        if isinstance(bid, (int, float)) and isinstance(ask, (int, float)) and bid > 0 and ask > 0:
            mark = (float(bid) + float(ask)) / 2.0
    if mark is None:
        return pos
    merged = dict(pos)
    merged["mark_price"] = mark
    return merged
