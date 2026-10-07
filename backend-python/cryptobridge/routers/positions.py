from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from cryptobridge.dependencies import get_positions_service, get_user
from cryptobridge.services.positions_service import PositionsService

router = APIRouter(prefix="/api/positions", tags=["positions"])


@router.get("/open")
async def open_positions(
    user=Depends(get_user),
    service: PositionsService = Depends(get_positions_service),
):
    """Unified open positions and orders across all connected Delta accounts."""
    return await service.build_open_payload(user)


@router.get("/history")
async def order_history(
    broker: str = Query(default="all", pattern="^(all|delta)$"),
    user=Depends(get_user),
    service: PositionsService = Depends(get_positions_service),
):
    """Past orders grouped by broker (Delta)."""
    return await service.build_history_payload(user, broker_filter=broker)
