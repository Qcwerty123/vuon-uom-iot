"""Mật khẩu bcrypt, JWT HS256, refresh token (đặc tả §14.2)."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(pw: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except ValueError:
        return False


def make_access_token(user_id: int, role: str) -> tuple[str, int]:
    ttl = settings.access_ttl_min * 60
    now = utcnow()
    payload = {"sub": str(user_id), "role": role, "typ": "access", "iat": int(now.timestamp()),
               "exp": int((now + timedelta(seconds=ttl)).timestamp())}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256"), ttl


def decode_access_token(token: str) -> dict:
    """Ném jwt.PyJWTError nếu sai chữ ký, hết hạn, hoặc không phải access token."""
    data = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    if data.get("typ") != "access":
        raise jwt.InvalidTokenError("not an access token")
    return data


def new_refresh_token() -> tuple[str, str]:
    """Trả về (token gửi client, sha256 lưu CSDL)."""
    tok = secrets.token_urlsafe(48)
    return tok, sha256(tok)


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def new_device_secret() -> str:
    return secrets.token_urlsafe(32)
