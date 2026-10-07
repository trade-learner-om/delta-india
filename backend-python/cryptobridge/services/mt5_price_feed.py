from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from cryptobridge.delta.market_data import DeltaMarketDataService, LiveTicker
from cryptobridge.exceptions import http_error
from cryptobridge.mt5.client import LocalMt5Error, Mt5Client
from cryptobridge.services.mt5_account_service import Mt5AccountService

log = logging.getLogger(__name__)
POLL_SECONDS = 3.0


class Mt5PriceFeed:
    """Poll MT5 ticks for forex watchlist symbols and publish them on the shared price socket."""

    def __init__(self, db, market: DeltaMarketDataService, accounts: Mt5AccountService, client: Mt5Client) -> None:
        self._watchlist = db.user_watchlist
        self._accounts = accounts
        self._market = market
        self._client = client
        self._task: asyncio.Task | None = None
        self._ticket: dict[str, set[str]] = {}
        self.status = "Idle"

    async def watch(self, user: dict, symbol: str) -> None:
        name = str(symbol or "").strip().upper()
        if not name:
            raise http_error(400, "Symbol is required.")
        account = await self._accounts.connected_account(user)
        if account is None:
            raise http_error(400, "Add a forex account before requesting a quote.")
        user_id = str(user["id"])
        self._ticket.setdefault(user_id, set()).add(name)
        try:
            await self._publish_one(self._accounts.credentials_for(account), name)
        except LocalMt5Error as exc:
            raise http_error(400, str(exc)) from exc

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("MT5 price poll failed")
                self.status = "Error"
            await asyncio.sleep(POLL_SECONDS)

    async def _poll_once(self) -> None:
        by_user: dict[str, set[str]] = {}
        cursor = self._watchlist.find({"venue": "forex"})
        async for item in cursor:
            symbol = str(item.get("symbol") or "").strip().upper()
            user_id = str(item.get("userId") or "")
            if user_id and symbol:
                by_user.setdefault(user_id, set()).add(symbol)
        for user_id, symbols in self._ticket.items():
            if user_id and symbols:
                by_user.setdefault(user_id, set()).update(symbols)
        if not by_user:
            self.status = "Idle"
            return
        published = False
        for user_id, symbols in by_user.items():
            account = await self._accounts._accounts.find_one({"userId": user_id})
            if not account:
                continue
            credentials = self._accounts.credentials_for(account)
            for symbol in symbols:
                try:
                    if await self._publish_one(credentials, symbol):
                        published = True
                except LocalMt5Error as exc:
                    log.info("MT5 tick skipped for %s: %s", symbol, exc)
                    self.status = "Terminal offline"
        self.status = "Live" if published else self.status

    async def _publish_one(self, credentials: dict, requested: str) -> bool:
        tick = await asyncio.to_thread(self._client.symbol_tick, credentials, requested)
        if not tick or not tick.get("last"):
            return False
        requested_name = str(requested or "").strip().upper()
        resolved = str(tick.get("symbol") or requested_name).strip().upper()
        names: list[str] = []
        for name in (requested_name, resolved):
            if name and name not in names:
                names.append(name)
        for name in names:
            ticker = LiveTicker(
                symbol=name,
                last_price=tick.get("last"),
                mark_price=tick.get("last"),
                bid=tick.get("bid"),
                ask=tick.get("ask"),
                change_24h=tick.get("change24h"),
                updated_at=datetime.now(timezone.utc),
                price_digits=tick.get("digits"),
            )
            self._market.latest_tickers[name] = ticker
            await self._market.price_broadcaster.publish(ticker)
        return True
