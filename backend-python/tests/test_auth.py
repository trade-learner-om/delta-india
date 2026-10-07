from __future__ import annotations

from cryptobridge.services.auth_service import pwd_context


def test_bcrypt_hash_and_verify():
    password = "secure-password-123"
    hashed = pwd_context.hash(password)
    assert pwd_context.verify(password, hashed)
    assert not pwd_context.verify("wrong-password", hashed)
