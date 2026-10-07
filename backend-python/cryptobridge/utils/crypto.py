from __future__ import annotations
"""AES-256-GCM encryption compatible with Java SecretCryptoService."""

import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

IV_LENGTH = 12
TAG_BITS = 128


def _key(secret: str) -> bytes:
    return hashlib.sha256(secret.encode("utf-8")).digest()


def encrypt(plain_text: str, secret: str) -> str:
    key = _key(secret)
    iv = os.urandom(IV_LENGTH)
    aesgcm = AESGCM(key)
    encrypted = aesgcm.encrypt(iv, plain_text.encode("utf-8"), None)
    output = iv + encrypted
    return base64.b64encode(output).decode("ascii")


def decrypt(cipher_text: str, secret: str) -> str:
    key = _key(secret)
    decoded = base64.b64decode(cipher_text)
    iv = decoded[:IV_LENGTH]
    encrypted = decoded[IV_LENGTH:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(iv, encrypted, None).decode("utf-8")
