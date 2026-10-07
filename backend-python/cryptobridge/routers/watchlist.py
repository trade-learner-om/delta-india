from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from cryptobridge.dependencies import get_user, get_watchlist_service
from cryptobridge.services.watchlist_service import WatchlistService

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


class WatchlistRequest(BaseModel):
    venue: str
    symbol: str


@router.get("")
async def list_watchlist(user=Depends(get_user), watchlist: WatchlistService = Depends(get_watchlist_service)):
    items = await watchlist.list_items(user)
    grouped = {"crypto": [], "forex": []}
    for item in items:
        grouped.setdefault(item["venue"], []).append(item)
    return {"items": items, "grouped": grouped}


@router.post("")
async def add_watchlist(
    body: WatchlistRequest,
    user=Depends(get_user),
    watchlist: WatchlistService = Depends(get_watchlist_service),
):
    return await watchlist.add_item(user, body.venue, body.symbol)


@router.delete("")
async def remove_watchlist(
    venue: str,
    symbol: str,
    user=Depends(get_user),
    watchlist: WatchlistService = Depends(get_watchlist_service),
):
    await watchlist.remove_item(user, venue, symbol)
    return {"ok": True}
