from __future__ import annotations
#!/usr/bin/env python3
"""HMAC-SHA256 signing reference for Delta REST."""

import hashlib
import hmac
import sys
import time


def sign(secret: str, payload: str) -> str:
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


if __name__ == "__main__":
    secret = sys.argv[1] if len(sys.argv) > 1 else "secret-key"
    method = sys.argv[2] if len(sys.argv) > 2 else "GET"
    path = sys.argv[3] if len(sys.argv) > 3 else "/v2/profile"
    ts = sys.argv[4] if len(sys.argv) > 4 else str(int(time.time()))
    payload = f"{method}{ts}{path}"
    print(sign(secret, payload))
