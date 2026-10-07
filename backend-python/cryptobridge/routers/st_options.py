from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel, Field

from cryptobridge.dependencies import get_st_options_service, get_user
from cryptobridge.services.st_options_service import (
    HISTORY_DEFAULT_LIMIT,
    HISTORY_MAX_LIMIT,
    StOptionsService,
)

router = APIRouter(prefix="/api/st-options", tags=["st-options"])


class ConfigPatch(BaseModel):
    underlying: str | None = None
    max_risk: float | None = Field(default=None, alias="maxRisk")
    st_period: int | None = Field(default=None, alias="stPeriod")
    st_multiplier: float | None = Field(default=None, alias="stMultiplier")
    ema_length: int | None = Field(default=None, alias="emaLength")
    min_premium_pct: float | None = Field(default=None, alias="minPremiumPct")
    stop_loss_pct: float | None = Field(default=None, alias="stopLossPct")
    take_profit_pct: float | None = Field(default=None, alias="takeProfitPct")
    breakeven_decay_pct: float | None = Field(default=None, alias="breakevenDecayPct")
    pair_hedge_decay_pct: float | None = Field(default=None, alias="pairHedgeDecayPct")
    max_st_distance_pct: float | None = Field(default=None, alias="maxStDistancePct")

    model_config = {"populate_by_name": True}


class BacktestConfigPatch(BaseModel):
    underlying: str | None = None
    max_risk: float | None = Field(default=None, alias="maxRisk")
    st_period: int | None = Field(default=None, alias="stPeriod")
    st_multiplier: float | None = Field(default=None, alias="stMultiplier")
    ema_length: int | None = Field(default=None, alias="emaLength")
    min_premium_pct: float | None = Field(default=None, alias="minPremiumPct")
    stop_loss_pct: float | None = Field(default=None, alias="stopLossPct")
    take_profit_pct: float | None = Field(default=None, alias="takeProfitPct")
    breakeven_decay_pct: float | None = Field(default=None, alias="breakevenDecayPct")
    dynamic_sizing_enabled: bool | None = Field(default=None, alias="dynamicSizingEnabled")
    dyn_after_losses: int | None = Field(default=None, alias="dynAfterLosses")
    dyn_increase_pct: float | None = Field(default=None, alias="dynIncreasePct")
    dyn_max_risk_pct: float | None = Field(default=None, alias="dynMaxRiskPct")
    dyn_after_profits: int | None = Field(default=None, alias="dynAfterProfits")
    dyn_decrease_pct: float | None = Field(default=None, alias="dynDecreasePct")
    strike_select_mode: str | None = Field(default=None, alias="strikeSelectMode")
    strike_type: str | None = Field(default=None, alias="strikeType")
    min_premium_abs: float | None = Field(default=None, alias="minPremiumAbs")
    one_trade_per_formation: bool | None = Field(default=None, alias="oneTradePerFormation")
    skip_setups_after_target: int | None = Field(default=None, alias="skipSetupsAfterTarget")
    max_st_distance_pct: float | None = Field(default=None, alias="maxStDistancePct")
    pair_hedge_enabled: bool | None = Field(default=None, alias="pairHedgeEnabled")
    pair_hedge_mode: str | None = Field(default=None, alias="pairHedgeMode")
    pair_hedge_decay_pct: float | None = Field(default=None, alias="pairHedgeDecayPct")

    model_config = {"populate_by_name": True}


class BacktestRequest(BaseModel):
    from_date: str = Field(alias="from")
    to_date: str = Field(alias="to")
    underlying: str | None = None
    max_risk: float | None = Field(default=None, alias="maxRisk")
    st_period: int | None = Field(default=None, alias="stPeriod")
    st_multiplier: float | None = Field(default=None, alias="stMultiplier")
    ema_length: int | None = Field(default=None, alias="emaLength")
    min_premium_pct: float | None = Field(default=None, alias="minPremiumPct")
    stop_loss_pct: float | None = Field(default=None, alias="stopLossPct")
    take_profit_pct: float | None = Field(default=None, alias="takeProfitPct")
    breakeven_decay_pct: float | None = Field(default=None, alias="breakevenDecayPct")
    dynamic_sizing_enabled: bool | None = Field(default=None, alias="dynamicSizingEnabled")
    dyn_after_losses: int | None = Field(default=None, alias="dynAfterLosses")
    dyn_increase_pct: float | None = Field(default=None, alias="dynIncreasePct")
    dyn_max_risk_pct: float | None = Field(default=None, alias="dynMaxRiskPct")
    dyn_after_profits: int | None = Field(default=None, alias="dynAfterProfits")
    dyn_decrease_pct: float | None = Field(default=None, alias="dynDecreasePct")
    strike_select_mode: str | None = Field(default=None, alias="strikeSelectMode")
    strike_type: str | None = Field(default=None, alias="strikeType")
    min_premium_abs: float | None = Field(default=None, alias="minPremiumAbs")
    one_trade_per_formation: bool | None = Field(default=None, alias="oneTradePerFormation")
    skip_setups_after_target: int | None = Field(default=None, alias="skipSetupsAfterTarget")
    max_st_distance_pct: float | None = Field(default=None, alias="maxStDistancePct")
    pair_hedge_enabled: bool | None = Field(default=None, alias="pairHedgeEnabled")
    pair_hedge_mode: str | None = Field(default=None, alias="pairHedgeMode")
    pair_hedge_decay_pct: float | None = Field(default=None, alias="pairHedgeDecayPct")

    model_config = {"populate_by_name": True}


def _backtest_settings_payload(body: BacktestConfigPatch | BacktestRequest) -> dict:
    return {
        "underlying": body.underlying,
        "maxRisk": body.max_risk,
        "stPeriod": body.st_period,
        "stMultiplier": body.st_multiplier,
        "emaLength": body.ema_length,
        "minPremiumPct": body.min_premium_pct,
        "stopLossPct": body.stop_loss_pct,
        "takeProfitPct": body.take_profit_pct,
        "breakevenDecayPct": body.breakeven_decay_pct,
        "dynamicSizingEnabled": body.dynamic_sizing_enabled,
        "dynAfterLosses": body.dyn_after_losses,
        "dynIncreasePct": body.dyn_increase_pct,
        "dynMaxRiskPct": body.dyn_max_risk_pct,
        "dynAfterProfits": body.dyn_after_profits,
        "dynDecreasePct": body.dyn_decrease_pct,
        "strikeSelectMode": body.strike_select_mode,
        "strikeType": body.strike_type,
        "minPremiumAbs": body.min_premium_abs,
        "oneTradePerFormation": body.one_trade_per_formation,
        "skipSetupsAfterTarget": body.skip_setups_after_target,
        "maxStDistancePct": body.max_st_distance_pct,
        "pairHedgeEnabled": body.pair_hedge_enabled,
        "pairHedgeMode": body.pair_hedge_mode,
        "pairHedgeDecayPct": body.pair_hedge_decay_pct,
    }


@router.get("/meta")
async def meta(
    user=Depends(get_user),
    service: StOptionsService = Depends(get_st_options_service),
):
    return service.meta()


@router.get("/config")
async def get_config(
    user=Depends(get_user),
    service: StOptionsService = Depends(get_st_options_service),
):
    return {"config": await service.get_config(user)}


@router.patch("/config")
async def patch_config(
    body: ConfigPatch,
    user=Depends(get_user),
    service: StOptionsService = Depends(get_st_options_service),
):
    config = await service.patch_config(
        user,
        {
            "underlying": body.underlying,
            "maxRisk": body.max_risk,
            "stPeriod": body.st_period,
            "stMultiplier": body.st_multiplier,
            "emaLength": body.ema_length,
            "minPremiumPct": body.min_premium_pct,
            "stopLossPct": body.stop_loss_pct,
            "takeProfitPct": body.take_profit_pct,
            "breakevenDecayPct": body.breakeven_decay_pct,
            "pairHedgeDecayPct": body.pair_hedge_decay_pct,
            "maxStDistancePct": body.max_st_distance_pct,
        },
    )
    return {"config": config}


@router.get("/backtest/config")
async def get_backtest_config(
    user=Depends(get_user),
    service: StOptionsService = Depends(get_st_options_service),
):
    return {"config": await service.get_backtest_config(user)}


@router.patch("/backtest/config")
async def patch_backtest_config(
    body: BacktestConfigPatch,
    user=Depends(get_user),
    service: StOptionsService = Depends(get_st_options_service),
):
    config = await service.patch_backtest_config(user, _backtest_settings_payload(body))
    return {"config": config}


@router.get("/backtest/runs")
async def list_backtest_runs(
    user=Depends(get_user),
    service: StOptionsService = Depends(get_st_options_service),
):
    return {"runs": await service.list_backtest_runs(user)}


@router.get("/backtest/runs/{run_id}")
async def get_backtest_run(
    run_id: str,
    user=Depends(get_user),
    service: StOptionsService = Depends(get_st_options_service),
):
    return {"run": await service.get_backtest_run(user, run_id)}


@router.delete("/backtest/runs/{run_id}")
async def delete_backtest_run(
    run_id: str,
    user=Depends(get_user),
    service: StOptionsService = Depends(get_st_options_service),
):
    return await service.delete_backtest_run(user, run_id)


@router.post("/start")
async def start_live(
    body: ConfigPatch | None = Body(default=None),
    user=Depends(get_user),
    service: StOptionsService = Depends(get_st_options_service),
):
    patch = body or ConfigPatch()
    return await service.start_live(
        user,
        {
            "underlying": patch.underlying,
            "maxRisk": patch.max_risk,
            "stPeriod": patch.st_period,
            "stMultiplier": patch.st_multiplier,
            "emaLength": patch.ema_length,
            "minPremiumPct": patch.min_premium_pct,
            "stopLossPct": patch.stop_loss_pct,
            "takeProfitPct": patch.take_profit_pct,
            "breakevenDecayPct": patch.breakeven_decay_pct,
            "pairHedgeDecayPct": patch.pair_hedge_decay_pct,
            "maxStDistancePct": patch.max_st_distance_pct,
        },
    )


@router.post("/stop")
async def stop_live(
    user=Depends(get_user),
    service: StOptionsService = Depends(get_st_options_service),
):
    return await service.stop_live(user)


@router.post("/trades/{trade_id}/force-close")
async def force_close_trade(
    trade_id: str,
    user=Depends(get_user),
    service: StOptionsService = Depends(get_st_options_service),
):
    return await service.force_close_trade(user, trade_id)


@router.get("/live")
async def live(
    user=Depends(get_user),
    service: StOptionsService = Depends(get_st_options_service),
):
    return await service.live_snapshot(user)


@router.get("/history")
async def history(
    limit: int = Query(default=HISTORY_DEFAULT_LIMIT, ge=1, le=HISTORY_MAX_LIMIT),
    cursor: str | None = Query(default=None),
    user=Depends(get_user),
    service: StOptionsService = Depends(get_st_options_service),
):
    return await service.history(user, limit=limit, cursor=cursor)


@router.post("/backtest")
async def backtest(
    body: BacktestRequest,
    user=Depends(get_user),
    service: StOptionsService = Depends(get_st_options_service),
):
    payload = {
        **_backtest_settings_payload(body),
        "from": body.from_date,
        "to": body.to_date,
    }
    return await service.submit_backtest(user, payload)


@router.get("/backtest/job")
async def backtest_job(
    user=Depends(get_user),
    service: StOptionsService = Depends(get_st_options_service),
):
    return {"backtestJob": service.get_backtest_job(user)}
