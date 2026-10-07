from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable

import httpx

from cryptobridge.utils.signing import sign_delta

log = logging.getLogger(__name__)

DELTA_SIGN_EXTENSION = "delta_sign"


@dataclass(frozen=True)
class DeltaSignContext:
    api_key: str
    api_secret: str


def signed_path_from_request(request: httpx.Request) -> str:
    path = request.url.path or ""
    query = request.url.query.decode("utf-8") if request.url.query else ""
    return f"{path}?{query}" if query else path


def request_body_text(request: httpx.Request) -> str:
    content = request.content
    if not content:
        return ""
    if isinstance(content, bytes):
        return content.decode("utf-8")
    return str(content)


def build_signature_payload(method: str, timestamp: str, path: str, body: str) -> str:
    return f"{method.upper()}{timestamp}{path}{body}"


def apply_delta_signature(
    request: httpx.Request,
    *,
    api_key: str,
    api_secret: str,
    clock_offset: float = 0.0,
) -> None:
    """Stamp api-key, timestamp, and signature immediately before wire send."""
    timestamp = str(int(time.time() + clock_offset))
    path = signed_path_from_request(request)
    body = request_body_text(request) if request.method.upper() in {"POST", "PUT", "DELETE"} else ""
    signature = sign_delta(api_secret, build_signature_payload(request.method, timestamp, path, body))
    request.headers["api-key"] = api_key
    request.headers["timestamp"] = timestamp
    request.headers["signature"] = signature


def make_delta_sign_hook(
    clock_offset: Callable[[], float],
) -> Callable[[httpx.Request], Any]:
    async def _hook(request: httpx.Request) -> None:
        context = request.extensions.get(DELTA_SIGN_EXTENSION)
        if not isinstance(context, DeltaSignContext):
            return
        apply_delta_signature(
            request,
            api_key=context.api_key,
            api_secret=context.api_secret,
            clock_offset=clock_offset(),
        )

    return _hook


def parse_delta_error_body(text: str) -> dict[str, Any]:
    try:
        node = json.loads(text)
    except json.JSONDecodeError:
        return {}
    if not isinstance(node, dict):
        return {}
    error = node.get("error")
    if isinstance(error, dict):
        return error
    return {}


def is_expired_signature_response(response: httpx.Response) -> bool:
    if response.status_code not in (401, 403):
        return False
    error = parse_delta_error_body(response.text or "")
    return str(error.get("code") or "").lower() == "expired_signature"


def expired_signature_context(response: httpx.Response) -> tuple[int | None, int | None]:
    error = parse_delta_error_body(response.text or "")
    context = error.get("context")
    if not isinstance(context, dict):
        return None, None
    request_time = context.get("request_time")
    server_time = context.get("server_time")
    try:
        req = int(request_time) if request_time is not None else None
    except (TypeError, ValueError):
        req = None
    try:
        srv = int(server_time) if server_time is not None else None
    except (TypeError, ValueError):
        srv = None
    return req, srv


def clock_offset_from_expired_signature(response: httpx.Response) -> float | None:
    request_time, server_time = expired_signature_context(response)
    if request_time is None or server_time is None:
        return None
    return float(server_time - request_time)
