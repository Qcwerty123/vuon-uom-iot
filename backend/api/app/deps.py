"""Xác thực request và phân quyền canView / canControl (đặc tả §14.1)."""
from __future__ import annotations

import jwt
from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .db import get_db
from .errors import ApiError, forbidden, not_found
from .models import Device, DeviceAssignment, User
from .security import decode_access_token


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


# Swagger (/docs): nút Authorize mở form username/password, gọi /api/v1/auth/token
oauth2 = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)


def current_user(token: str | None = Depends(oauth2), db: Session = Depends(get_db)) -> User:
    if not token:
        raise ApiError(401, "UNAUTHORIZED", "Thiếu token")
    try:
        data = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise ApiError(401, "UNAUTHORIZED", "Token hết hạn")
    except jwt.PyJWTError:
        raise ApiError(401, "UNAUTHORIZED", "Token không hợp lệ")
    user = db.get(User, int(data["sub"]))
    if not user or user.status != "ACTIVE":
        raise ApiError(401, "UNAUTHORIZED", "Tài khoản không hoạt động")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "ADMIN":
        raise forbidden("Chỉ quản trị viên được thực hiện")
    return user


def permission_of(db: Session, user: User, device_id: int) -> str | None:
    """None = không được gán; VIEW; CONTROL. VIEWER luôn chỉ là VIEW."""
    if user.role == "ADMIN":
        return "CONTROL"
    a = db.get(DeviceAssignment, (user.id, device_id))
    if not a:
        return None
    if user.role == "VIEWER":
        return "VIEW"
    return a.permission


def device_for_view(db: Session, user: User, device_id: int) -> tuple[Device, str]:
    """Không được gán → 404 để không lộ sự tồn tại (C6)."""
    dev = db.get(Device, device_id)
    perm = permission_of(db, user, device_id) if dev else None
    if not dev or not perm:
        raise not_found("Không tìm thấy thiết bị")
    return dev, perm


def device_for_control(db: Session, user: User, device_id: int) -> Device:
    dev, perm = device_for_view(db, user, device_id)
    if perm != "CONTROL":
        raise forbidden("Cần quyền CONTROL trên thiết bị này")
    return dev
