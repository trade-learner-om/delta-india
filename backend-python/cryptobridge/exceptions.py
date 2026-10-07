from __future__ import annotations
from fastapi import HTTPException


def http_error(status_code: int, detail: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error": detail, "detail": detail, "status": status_code},
    )
