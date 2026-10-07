from __future__ import annotations
from cryptobridge.utils.signing import sign_delta


def test_sign_produces_hex_hmac():
    signature = sign_delta("secret-key", "GET1700000000/v2/profile")
    assert len(signature) == 64
    assert all(c in "0123456789abcdef" for c in signature)


def test_sign_is_deterministic():
    payload = "POST1700000000/v2/orders{}"
    assert sign_delta("my-secret", payload) == sign_delta("my-secret", payload)
