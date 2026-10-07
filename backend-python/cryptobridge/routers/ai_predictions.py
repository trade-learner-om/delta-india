from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from cryptobridge.dependencies import get_user
from cryptobridge.market_intel.service import AiPredictionService

router = APIRouter(prefix="/api/ai-predictions", tags=["ai-predictions"])


def get_ai_predictions(request: Request) -> AiPredictionService:
    return request.app.state.ai_predictions


@router.get("")
async def ai_predictions(
    symbol: str = Query(...),
    user=Depends(get_user),
    service: AiPredictionService = Depends(get_ai_predictions),
):
    del user
    return await service.predict(symbol)
