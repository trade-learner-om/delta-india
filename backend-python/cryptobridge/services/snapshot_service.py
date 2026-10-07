from __future__ import annotations
from datetime import datetime, timezone
from typing import Any

from cryptobridge.delta.market_data import DeltaMarketDataService, LiveTicker
from cryptobridge.delta.rest_client import DeltaRestClient, OrderSummary
from cryptobridge.services.account_service import AccountService


def display_price_from_ticker(ticker: LiveTicker) -> float | None:
    if ticker.mark_price is not None:
        return ticker.mark_price
    if ticker.last_price is not None:
        return ticker.last_price
    if ticker.bid is not None and ticker.ask is not None:
        return (ticker.bid + ticker.ask) / 2.0
    if ticker.bid is not None:
        return ticker.bid
    if ticker.ask is not None:
        return ticker.ask
    return None


def live_tick_dict(ticker: LiveTicker) -> dict[str, Any]:
    """Compact tick for WS clients — omit null fields so partial updates do not wipe prior quotes."""
    price = display_price_from_ticker(ticker)
    tick: dict[str, Any] = {
        "symbol": ticker.symbol,
        "price_digits": ticker.price_digits if ticker.price_digits is not None else 2,
        "time": ticker.updated_at.isoformat() if ticker.updated_at else datetime.now(timezone.utc).isoformat(),
    }
    if price is not None:
        tick["price"] = price
    if ticker.mark_price is not None:
        tick["mark_price"] = ticker.mark_price
    if ticker.bid is not None:
        tick["bid"] = ticker.bid
    if ticker.ask is not None:
        tick["ask"] = ticker.ask
    if ticker.change_24h is not None:
        tick["change24h"] = ticker.change_24h
    return tick


class SnapshotService:
    def __init__(
        self,
        account_service: AccountService,
        market: DeltaMarketDataService,
        delta: DeltaRestClient,
    ) -> None:
        self._accounts = account_service
        self._market = market
        self._delta = delta

    def price_update_from(self, ticker: LiveTicker) -> dict[str, Any]:
        tick = live_tick_dict(ticker)
        return {"type": "price", "symbol": ticker.symbol, "tick": tick}

    async def snapshot_for(self, user: dict[str, Any]) -> dict[str, Any]:
        accounts = await self._accounts.list_accounts(user)
        trading_state = await self._load_trading_state(user)
        return self._build_snapshot(user, accounts, trading_state)

    async def _load_trading_state(self, user: dict[str, Any]) -> dict[str, Any]:
        account = await self._accounts.require_selected_account(user)
        if not account:
            return {}
        exchange = str(account.get("exchange") or "delta").lower()
        if exchange != "delta":
            return {"orders": [], "running_pl": 0}
        try:
            api_key, api_secret = self._accounts.credentials_for(account)
            orders = await self._delta.fetch_open_orders(api_key, api_secret)
            positions = await self._delta.fetch_margined_positions(api_key, api_secret)
            running_pl = sum(
                float(p.get("unrealized_pnl") or 0)
                for p in positions
                if p.get("unrealized_pnl") not in (None, "")
            )
            return {
                "orders": [self._to_live_order(o) for o in orders],
                "running_pl": running_pl,
            }
        except Exception:
            return {"orders": [], "running_pl": 0}

    def _build_snapshot(
        self,
        user: dict[str, Any],
        accounts: list[dict],
        trading_state: dict,
    ) -> dict[str, Any]:
        prices: dict[str, Any] = {}
        for symbol, ticker in self._market.latest_tickers.items():
            tick = live_tick_dict(ticker)
            if tick.get("price") is None and not any(tick.get(k) for k in ("mark_price", "bid", "ask")):
                continue
            prices[symbol] = tick
        live = {
            "marketFeedStatus": self._market.status,
            "marketSocketConnected": self._market.socket_connected,
            "activeAccountPresent": bool(user.get("selectedAccountId")),
            "subscribedSymbols": self._market.subscribed_symbols(),
            "lastMarketEventAt": self._market.last_market_event_at.isoformat()
            if self._market.last_market_event_at
            else None,
        }
        me = {
            "displayName": user.get("displayName"),
            "full_name": user.get("displayName"),
            "email": user.get("email"),
            "selectedAccountId": user.get("selectedAccountId"),
            "selected_account_id": user.get("selectedAccountId"),
            "selectedVenue": user.get("selectedVenue"),
            "accounts": [self._to_me_account(a) for a in accounts],
        }
        return {
            "type": "snapshot",
            "me": me,
            "selectedAccountId": user.get("selectedAccountId"),
            "selected_account_id": user.get("selectedAccountId"),
            "accounts": accounts,
            "prices": prices,
            "orders": trading_state.get("orders", []),
            "running_pl": trading_state.get("running_pl", 0),
            "live": live,
        }

    def _to_me_account(self, account: dict) -> dict:
        return {
            "id": account["id"],
            "account_name": account.get("accountName"),
            "account_id": account.get("exchangeUserId"),
            "market_type": account.get("marketType"),
            "broker_type": account.get("brokerType"),
            "exchange": account.get("exchange"),
            "currency_code": account.get("currencyCode"),
            "risk_amount": account.get("riskAmount"),
            "available_margin": account.get("availableMargin"),
            "balance": account.get("balance"),
            "net_equity": account.get("netEquity"),
            "wallet_error": account.get("walletError"),
            "selected": account.get("selected"),
        }

    def _to_live_order(self, order: OrderSummary) -> dict:
        return {
            "id": str(order.id),
            "symbol": order.symbol,
            "order_type": order.order_type,
            "side": order.side,
            "entry": order.limit_price if order.limit_price is not None else order.stop_price,
            "stop_loss": order.stop_loss_price,
            "target": order.take_profit_price,
            "quantity": order.size,
            "status": order.status,
            "unfilled_size": order.unfilled_size,
        }
