from __future__ import annotations

import hashlib
import hmac
import time


def create_view_token(secret: str, source_id: str, ttl_seconds: int) -> str:
    expires_at = int(time.time()) + ttl_seconds
    payload = f"{source_id}:{expires_at}"
    signature = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256)
    return f"{expires_at}.{signature.hexdigest()}"


def verify_view_token(secret: str, source_id: str, token: str) -> bool:
    try:
        expires_raw, signature = token.split(".", 1)
        expires_at = int(expires_raw)
    except (TypeError, ValueError):
        return False
    if expires_at < int(time.time()):
        return False
    payload = f"{source_id}:{expires_at}"
    expected = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)
