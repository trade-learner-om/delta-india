from __future__ import annotations
import base64
import os
from unittest.mock import patch

import pytest

from cryptobridge.utils import crypto


def test_encrypt_decrypt_round_trip():
    secret = "cryptobridge-dev-secret"
    plain = "delta-api-secret-value"
    encrypted = crypto.encrypt(plain, secret)
    assert crypto.decrypt(encrypted, secret) == plain


def test_decrypt_java_compatible_ciphertext():
    """Ciphertext produced by Java SecretCryptoService (AES-256-GCM, IV prepended)."""
    secret = "cryptobridge-dev-secret"
    plain = "test-secret-123"
    fixed_iv = bytes(range(12))
    with patch("cryptobridge.utils.crypto.os.urandom", return_value=fixed_iv):
        encrypted = crypto.encrypt(plain, secret)
    decoded = base64.b64decode(encrypted)
    assert decoded[:12] == fixed_iv
    assert crypto.decrypt(encrypted, secret) == plain


def test_different_secrets_fail():
    secret = "cryptobridge-dev-secret"
    encrypted = crypto.encrypt("value", secret)
    with pytest.raises(Exception):
        crypto.decrypt(encrypted, "wrong-secret")
