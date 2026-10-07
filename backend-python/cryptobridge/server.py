"""Uvicorn entrypoint with WebSocket settings that avoid keepalive ping races."""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8080"))
    reload = os.environ.get("UVICORN_RELOAD", "").lower() in {"1", "true", "yes"}
    uvicorn.run(
        "cryptobridge.main:app",
        host=host,
        port=port,
        reload=reload,
        # App-level ping/pong on /ws/live; disable protocol keepalive to avoid
        # websockets legacy "keepalive ping failed" AssertionError on Windows.
        ws_ping_interval=None,
        ws_ping_timeout=None,
    )


if __name__ == "__main__":
    main()
