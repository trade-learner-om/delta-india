from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends

from cryptobridge.config import settings
from cryptobridge.db import get_db
from cryptobridge.delta.market_data import DeltaMarketDataService
from cryptobridge.dependencies import get_market_service, get_user

log = logging.getLogger(__name__)

router = APIRouter(tags=["meta"])

_IP_LOOKUP_URLS = (
    "https://api.ipify.org",
    "https://ifconfig.me/ip",
    "https://checkip.amazonaws.com",
)

_ip_cache: dict[str, object] = {"ip": None, "fetched_at": 0.0}
_ip_lock = asyncio.Lock()
_IP_CACHE_TTL_SECONDS = 6 * 60 * 60


async def _resolve_public_ip() -> str | None:
    if settings.server_public_ip:
        return settings.server_public_ip.strip()

    now = asyncio.get_event_loop().time()
    cached_ip = _ip_cache.get("ip")
    fetched_at = float(_ip_cache.get("fetched_at") or 0.0)
    if cached_ip and (now - fetched_at) < _IP_CACHE_TTL_SECONDS:
        return str(cached_ip)

    async with _ip_lock:
        now = asyncio.get_event_loop().time()
        cached_ip = _ip_cache.get("ip")
        fetched_at = float(_ip_cache.get("fetched_at") or 0.0)
        if cached_ip and (now - fetched_at) < _IP_CACHE_TTL_SECONDS:
            return str(cached_ip)

        async with httpx.AsyncClient(timeout=5.0) as client:
            for url in _IP_LOOKUP_URLS:
                try:
                    response = await client.get(url)
                    response.raise_for_status()
                    ip = response.text.strip()
                    if ip:
                        _ip_cache["ip"] = ip
                        _ip_cache["fetched_at"] = asyncio.get_event_loop().time()
                        return ip
                except Exception as exc:
                    log.warning("Public IP lookup failed via %s: %s", url, exc)
    return None


@router.get("/api/meta/public-ip")
async def public_ip(user=Depends(get_user)):
    ip = await _resolve_public_ip()
    if ip:
        return {"ip": ip}
    return {"ip": None, "error": "Could not determine the server's outbound IP. Set SERVER_PUBLIC_IP to override."}


@router.get("/api/health")
@router.get("/health")
async def health(market: DeltaMarketDataService = Depends(get_market_service)):
    mongo_status = "UP"
    try:
        await get_db().command("ping")
    except Exception as exc:
        mongo_status = f"DOWN: {exc}"

    overall = "UP" if mongo_status == "UP" else "DEGRADED"
    return {
        "status": overall,
        "service": "CryptoBridge",
        "publicApiBaseUrl": settings.public_api_base_url,
        "marketFeedStatus": market.status,
        "mongoStatus": mongo_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
