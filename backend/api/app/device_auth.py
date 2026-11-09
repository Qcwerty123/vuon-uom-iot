"""Xác thực thiết bị qua HTTP Basic (đặc tả §8.9): bcrypt so với credential_hash, cache 5 phút.

Khóa cache: (device_code, sha256(secret)) — không giữ secret trong bộ nhớ. Cache bị xóa khi trạng thái thiết bị
đổi (lifecycle.transition) hoặc cấp lại khóa (rotate-secret). Module không phụ thuộc module khác để tránh vòng import.
"""
from __future__ import annotations

import hashlib
import threading
import time

TTL_S = 300
_cache: dict[tuple[str, str], tuple[float, int, str]] = {}   # key -> (hết hạn, device_id, credential_hash)
_lock = threading.Lock()


def _key(code: str, secret: str) -> tuple[str, str]:
    return code, hashlib.sha256(secret.encode()).hexdigest()


def cached(code: str, secret: str, credential_hash: str | None) -> bool:
    """True nếu cặp (code, secret) đã được bcrypt xác nhận trong 5 phút qua với đúng credential_hash hiện tại."""
    k = _key(code, secret)
    with _lock:
        v = _cache.get(k)
        if not v:
            return False
        if v[0] < time.time() or v[2] != credential_hash:
            _cache.pop(k, None)
            return False
        return True


def remember(code: str, secret: str, device_id: int, credential_hash: str) -> None:
    with _lock:
        _cache[_key(code, secret)] = (time.time() + TTL_S, device_id, credential_hash)


def invalidate(code: str) -> None:
    with _lock:
        for k in [k for k in _cache if k[0] == code]:
            _cache.pop(k, None)
