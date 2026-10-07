from __future__ import annotations
#!/usr/bin/env python3
"""Subscribe to Delta India public WebSocket (ticker + ob_l1)."""

import asyncio
import json
import sys

import websockets

WS_URL = "wss://public-socket.india.delta.exchange"


async def main(symbols: list[str]) -> None:
    async with websockets.connect(WS_URL) as ws:
        await ws.send(json.dumps({"type": "enable_heartbeat"}))
        await ws.send(
            json.dumps(
                {
                    "type": "subscribe",
                    "payload": {
                        "channels": [
                            {"name": "ticker", "symbols": symbols},
                            {"name": "ob_l1", "symbols": symbols},
                            {"name": "mark_price", "symbols": [f"MARK:{s}" for s in symbols]},
                        ]
                    },
                }
            )
        )
        async for message in ws:
            print(message)


if __name__ == "__main__":
    syms = [s.upper() for s in sys.argv[1:]] or ["BTCUSD"]
    asyncio.run(main(syms))
