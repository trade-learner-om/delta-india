from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from cryptobridge.delta.market_data import DeltaMarketDataService
from cryptobridge.dependencies import get_market_service, get_mt5_price_feed, get_user
from cryptobridge.exceptions import http_error
from cryptobridge.services.mt5_price_feed import Mt5PriceFeed

router = APIRouter(prefix="/api/market", tags=["market"])


class SubscribeRequest(BaseModel):
    venue: str
    symbol: str


@router.post("/subscribe")
async def subscribe_symbol(
    body: SubscribeRequest,
    user=Depends(get_user),
    market: DeltaMarketDataService = Depends(get_market_service),
    feed: Mt5PriceFeed = Depends(get_mt5_price_feed),
):
    venue = str(body.venue or "").strip().lower()
    symbol = str(body.symbol or "").strip().upper()
    if not symbol:
        raise http_error(400, "Symbol is required.")
    if venue == "crypto":
        await market.ensure_symbols({symbol})
        return {"ok": True, "symbol": symbol, "venue": venue}
    if venue == "forex":
        await feed.watch(user, symbol)
        return {"ok": True, "symbol": symbol, "venue": venue}
    raise http_error(400, "venue must be crypto or forex.")
