from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from cryptobridge.dependencies import get_execution_engine, get_user
from cryptobridge.services.execution_engine import ExecutionEngineService

router = APIRouter(prefix="/api/execution", tags=["execution"])


class PreviewRequest(BaseModel):
    symbol: str
    quantity_lots: int = Field(alias="quantityLots")

    model_config = {"populate_by_name": True}


class TradeRequest(BaseModel):
    option_symbol: str = Field(alias="optionSymbol")
    quantity_lots: int = Field(alias="quantityLots")
    entry_spot_level: float = Field(alias="entrySpotLevel")
    spot_stop_level: float = Field(alias="spotStopLevel")
    entry_spot_operator: str | None = Field(default=None, alias="entrySpotOperator")
    spot_stop_operator: str | None = Field(default=None, alias="spotStopOperator")

    model_config = {"populate_by_name": True}


@router.get("/options/search")
async def search_options(
    q: str = Query("", min_length=0),
    user=Depends(get_user),
    engine: ExecutionEngineService = Depends(get_execution_engine),
):
    return {"options": await engine.search_options(q)}


@router.post("/preview")
async def preview_trade(
    body: PreviewRequest,
    user=Depends(get_user),
    engine: ExecutionEngineService = Depends(get_execution_engine),
):
    return await engine.preview_trade(user, body.symbol, body.quantity_lots)


@router.post("/trade")
async def create_trade(
    body: TradeRequest,
    user=Depends(get_user),
    engine: ExecutionEngineService = Depends(get_execution_engine),
):
    monitor = await engine.create_monitor(
        user,
        option_symbol=body.option_symbol,
        quantity_lots=body.quantity_lots,
        entry_spot_level=body.entry_spot_level,
        spot_stop_level=body.spot_stop_level,
        entry_spot_operator=body.entry_spot_operator,
        spot_stop_operator=body.spot_stop_operator,
    )
    return {"monitor": monitor}


@router.get("/monitors")
async def list_monitors(
    user=Depends(get_user),
    engine: ExecutionEngineService = Depends(get_execution_engine),
):
    monitors = await engine.list_monitors(user)
    return {"monitors": monitors}


@router.post("/monitors/{monitor_id}/cancel")
async def cancel_monitor(
    monitor_id: str,
    user=Depends(get_user),
    engine: ExecutionEngineService = Depends(get_execution_engine),
):
    monitor = await engine.cancel_monitor(user, monitor_id)
    return {"monitor": monitor}
