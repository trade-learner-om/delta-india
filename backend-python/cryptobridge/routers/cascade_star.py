from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from cryptobridge.dependencies import get_cascade_star_service, get_user
from cryptobridge.services.cascade_star_service import CascadeStarService

router = APIRouter(prefix="/api/cascade-star", tags=["cascade-star"])


class ConfigPatch(BaseModel):
    symbols: list[str] | None = None
    direction: str | None = None
    max_risk: float | None = Field(default=None, alias="maxRisk")
    sizing_mode: str | None = Field(default=None, alias="sizingMode")
    lots: int | None = None
    chop_length: int | None = Field(default=None, alias="chopLength")
    chop_max: float | None = Field(default=None, alias="chopMax")
    target_r: float | None = Field(default=None, alias="targetR")
    session_start: str | None = Field(default=None, alias="sessionStart")
    session_end: str | None = Field(default=None, alias="sessionEnd")
    fill_timeout_bars: int | None = Field(default=None, alias="fillTimeoutBars")

    model_config = {"populate_by_name": True}


def _patch_payload(body: ConfigPatch) -> dict:
    return {
        "symbols": body.symbols,
        "direction": body.direction,
        "maxRisk": body.max_risk,
        "sizingMode": body.sizing_mode,
        "lots": body.lots,
        "chopLength": body.chop_length,
        "chopMax": body.chop_max,
        "targetR": body.target_r,
        "sessionStart": body.session_start,
        "sessionEnd": body.session_end,
        "fillTimeoutBars": body.fill_timeout_bars,
    }


@router.get("/meta")
async def meta(
    user=Depends(get_user),
    service: CascadeStarService = Depends(get_cascade_star_service),
):
    return service.meta()


@router.get("/config")
async def get_config(
    user=Depends(get_user),
    service: CascadeStarService = Depends(get_cascade_star_service),
):
    return {"config": await service.get_config(user)}


@router.patch("/config")
async def patch_config(
    body: ConfigPatch,
    user=Depends(get_user),
    service: CascadeStarService = Depends(get_cascade_star_service),
):
    return {"config": await service.patch_config(user, _patch_payload(body))}


@router.post("/start")
async def start(
    body: ConfigPatch | None = None,
    user=Depends(get_user),
    service: CascadeStarService = Depends(get_cascade_star_service),
):
    patch = _patch_payload(body) if body is not None else {}
    return await service.start_live(user, patch)


@router.post("/stop")
async def stop(
    user=Depends(get_user),
    service: CascadeStarService = Depends(get_cascade_star_service),
):
    return await service.stop_live(user)


@router.get("/live")
async def live(
    user=Depends(get_user),
    service: CascadeStarService = Depends(get_cascade_star_service),
):
    return await service.live_snapshot(user)


@router.get("/history")
async def history(
    limit: int = Query(default=50, ge=1, le=200),
    user=Depends(get_user),
    service: CascadeStarService = Depends(get_cascade_star_service),
):
    return {"trades": await service.history(user, limit)}


class BacktestRequest(BaseModel):
    from_date: str = Field(alias="from")
    to_date: str = Field(alias="to")
    symbol: str | None = None
    direction: str | None = None
    max_risk: float | None = Field(default=None, alias="maxRisk")
    sizing_mode: str | None = Field(default=None, alias="sizingMode")
    lots: int | None = None
    chop_length: int | None = Field(default=None, alias="chopLength")
    chop_max: float | None = Field(default=None, alias="chopMax")
    target_r: float | None = Field(default=None, alias="targetR")
    session_start: str | None = Field(default=None, alias="sessionStart")
    session_end: str | None = Field(default=None, alias="sessionEnd")
    fill_timeout_bars: int | None = Field(default=None, alias="fillTimeoutBars")

    model_config = {"populate_by_name": True}


def _backtest_payload(body: BacktestRequest) -> dict:
    return {
        "from": body.from_date,
        "to": body.to_date,
        "symbol": body.symbol,
        "direction": body.direction,
        "maxRisk": body.max_risk,
        "sizingMode": body.sizing_mode,
        "lots": body.lots,
        "chopLength": body.chop_length,
        "chopMax": body.chop_max,
        "targetR": body.target_r,
        "sessionStart": body.session_start,
        "sessionEnd": body.session_end,
        "fillTimeoutBars": body.fill_timeout_bars,
    }


@router.post("/backtest")
async def start_backtest(
    body: BacktestRequest,
    user=Depends(get_user),
    service: CascadeStarService = Depends(get_cascade_star_service),
):
    return {"job": await service.submit_backtest(user, _backtest_payload(body))}


@router.get("/backtest/job")
async def backtest_job(
    user=Depends(get_user),
    service: CascadeStarService = Depends(get_cascade_star_service),
):
    return {"job": service.get_backtest_job(user)}


@router.get("/backtest/runs")
async def backtest_runs(
    user=Depends(get_user),
    service: CascadeStarService = Depends(get_cascade_star_service),
):
    return {"runs": await service.list_backtest_runs(user)}


@router.get("/backtest/runs/{run_id}")
async def backtest_run(
    run_id: str,
    user=Depends(get_user),
    service: CascadeStarService = Depends(get_cascade_star_service),
):
    return {"run": await service.get_backtest_run(user, run_id)}
