from __future__ import annotations
import hashlib
import hmac


def sign_delta(secret: str, payload: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest


def sign_delta_ws_auth(secret: str, timestamp: str) -> str:
    return sign_delta(secret, f"GET{timestamp}/live")
