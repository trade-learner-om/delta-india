from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from cryptobridge.delta.market_data import DeltaMarketDataService
from cryptobridge.delta.rest_client import DeltaRestClient
from cryptobridge.exceptions import http_error
from cryptobridge.mt5.client import LocalMt5Error
from cryptobridge.services.mt5_account_service import Mt5AccountService

_PERPETUAL_TTL_SECONDS = 300


def filter_suggestions(symbols: list[str], query: str, owned: set[str], limit: int = 12) -> list[str]:
    needle = str(query or "").strip().upper()
    if len(needle) < 2:
        return []
    prefix: list[str] = []
    contains: list[str] = []
    for symbol in symbols:
        name = str(symbol or "").strip().upper()
        if not name or name in owned:
            continue
        if name.startswith(needle):
            prefix.append(name)
        elif needle in name:
            contains.append(name)
    return (prefix + contains)[:limit]


class WatchlistService:
    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        market: DeltaMarketDataService,
        delta: DeltaRestClient | None = None,
        mt5_accounts: Mt5AccountService | None = None,
    ) -> None:
        self._items = db.user_watchlist
        self._market = market
        self._delta = delta
        self._mt5 = mt5_accounts
        self._perpetuals: list[str] | None = None
        self._perpetuals_at = 0.0

    async def ensure_indexes(self) -> None:
        await self._items.create_index([("userId", 1), ("venue", 1), ("symbol", 1)], unique=True)

    async def list_items(self, user: dict[str, Any]) -> list[dict[str, Any]]:
        cursor = self._items.find({"userId": user["id"]}).sort([("venue", 1), ("symbol", 1)])
        return [self._view(doc) async for doc in cursor]

    async def add_item(self, user: dict[str, Any], venue: str, symbol: str) -> dict[str, Any]:
        venue = _venue(venue)
        symbol = str(symbol or "").strip().upper()
        if not symbol:
            raise http_error(400, "Symbol is required.")
        now = datetime.now(timezone.utc)
        await self._items.update_one(
            {"userId": user["id"], "venue": venue, "symbol": symbol},
            {"$setOnInsert": {"userId": user["id"], "venue": venue, "symbol": symbol, "createdAt": now}},
            upsert=True,
        )
        if venue == "crypto":
            await self._market.ensure_symbols({symbol})
        doc = await self._items.find_one({"userId": user["id"], "venue": venue, "symbol": symbol})
        return self._view(doc)

    async def remove_item(self, user: dict[str, Any], venue: str, symbol: str) -> None:
        await self._items.delete_one(
            {"userId": user["id"], "venue": _venue(venue), "symbol": str(symbol or "").strip().upper()}
        )

    async def suggest(self, user: dict[str, Any], venue: str, query: str, *, include_owned: bool = False) -> dict[str, Any]:
        venue = _venue(venue)
        owned = set() if include_owned else {
            str(item.get("symbol") or "")
            for item in await self.list_items(user)
            if item.get("venue") == venue
        }
        if venue == "crypto":
            try:
                symbols = filter_suggestions(await self._perpetual_symbols(), query, owned)
            except Exception:
                return {"suggestions": [], "message": "Delta symbols are unavailable right now."}
            return {"suggestions": [{"symbol": symbol, "venue": "crypto"} for symbol in symbols], "message": None}
        return await self._suggest_forex(user, query, owned)

    async def _perpetual_symbols(self) -> list[str]:
        now = time.monotonic()
        if self._perpetuals is not None and now - self._perpetuals_at < _PERPETUAL_TTL_SECONDS:
            return self._perpetuals
        if self._delta is None:
            return []
        rows = await self._delta.list_perpetual_symbols()
        self._perpetuals = [row["symbol"] for row in rows]
        self._perpetuals_at = now
        return self._perpetuals

    async def _suggest_forex(self, user: dict[str, Any], query: str, owned: set[str]) -> dict[str, Any]:
        if len(str(query or "").strip()) < 2:
            return {"suggestions": [], "message": None}
        if self._mt5 is None:
            return {"suggestions": [], "message": "The MT5 terminal is offline."}
        account = await self._mt5.connected_account(user)
        if account is None:
            return {"suggestions": [], "message": "Add a forex account before searching symbols."}
        try:
            names = self._mt5.search_symbols(account, query)
        except LocalMt5Error:
            return {
                "suggestions": [],
                "message": "The MT5 terminal is offline. Start it on the machine running the API.",
            }
        symbols = filter_suggestions(names, query, owned)
        return {"suggestions": [{"symbol": symbol, "venue": "forex"} for symbol in symbols], "message": None}

    async def crypto_symbols(self) -> set[str]:
        cursor = self._items.find({"venue": "crypto"})
        return {str(doc.get("symbol") or "") async for doc in cursor if doc.get("symbol")}

    @staticmethod
    def _view(doc: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(doc["_id"]),
            "venue": doc.get("venue"),
            "symbol": doc.get("symbol"),
        }


def _venue(value: str) -> str:
    venue = str(value or "").strip().lower()
    if venue not in {"crypto", "forex"}:
        raise http_error(400, "venue must be crypto or forex.")
    return venue
