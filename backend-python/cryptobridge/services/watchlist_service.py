from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from cryptobridge.delta.market_data import DeltaMarketDataService
from cryptobridge.exceptions import http_error


class WatchlistService:
    def __init__(self, db: AsyncIOMotorDatabase, market: DeltaMarketDataService) -> None:
        self._items = db.user_watchlist
        self._market = market

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
