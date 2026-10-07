from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from cryptobridge.delta.market_data import DeltaMarketDataService, LiveTicker
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
        self.status = "Idle"

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
        cursor = self._watchlist.find({"venue": "forex"})
        by_user: dict[str, list[str]] = {}
        async for item in cursor:
            by_user.setdefault(str(item.get("userId") or ""), []).append(str(item.get("symbol") or ""))
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
                if not symbol:
                    continue
                try:
                    tick = await asyncio.to_thread(self._client.symbol_tick, credentials, symbol)
                except LocalMt5Error as exc:
                    log.info("MT5 tick skipped for %s: %s", symbol, exc)
                    self.status = "Terminal offline"
                    continue
                if not tick or not tick.get("last"):
                    continue
                ticker = LiveTicker(
                    symbol=str(tick["symbol"]),
                    last_price=tick.get("last"),
                    mark_price=tick.get("last"),
                    bid=tick.get("bid"),
                    ask=tick.get("ask"),
                    change_24h=None,
                    updated_at=datetime.now(timezone.utc),
                    price_digits=tick.get("digits"),
                )
                self._market.latest_tickers[ticker.symbol] = ticker
                await self._market.price_broadcaster.publish(ticker)
                published = True
        self.status = "Live" if published else self.status
