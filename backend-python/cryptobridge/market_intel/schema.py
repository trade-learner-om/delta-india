from __future__ import annotations

from pydantic import BaseModel, Field

DISCLAIMER = (
    "Caution: These probabilities are AI-generated market simulations for educational purposes only. "
    "Do not initiate trades based on these results."
)


class Horizon(BaseModel):
    bullish: int = Field(ge=0, le=100)
    bearish: int = Field(ge=0, le=100)


class AiForecast(BaseModel):
    horizon_1h: Horizon
    horizon_4h: Horizon
    horizon_24h: Horizon
    technical_rationale: str
    disclaimer: str
