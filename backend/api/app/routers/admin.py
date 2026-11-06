"""Quản lý người dùng (§10.3), audit log và tổng quan dashboard (§10.10)."""
from __future__ import annotations

import secrets
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from .. import alerts as engine
from .. import ingest
from ..audit import audit
from ..db import get_db
from ..deps import client_ip, current_user, permission_of, require_admin
from ..errors import ApiError, not_found
from ..models import Alert, AuditLog, Device, DeviceAssignment, RefreshToken, User
from ..schemas import Api, UserOut
from ..security import hash_password, utcnow

router = APIRouter(tags=["admin"])


class UserCreate(Api):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_.-]+$")
    full_name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=120)
    role: Literal["ADMIN", "OPERATOR", "VIEWER"] = "VIEWER"
    password: str = Field(min_length=8, max_length=200)


class UserPatch(Api):
    full_name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=120)
    role: Literal["ADMIN", "OPERATOR", "VIEWER"] | None = None
    telegram_chat_id: str | None = Field(default=None, max_length=40)


def _user(db: Session, user_id: int) -> User:
    u = db.get(User, user_id)
    if not u:
        raise not_found("Không tìm thấy người dùng")
    return u


@router.get("/users", response_model=list[UserOut])
def list_users(role: str | None = None, status: str | None = None, q: str | None = None,
               _a: User = Depends(require_admin), db: Session = Depends(get_db)):
    s = select(User).order_by(User.id)
    if role:
        s = s.where(User.role == role)
    if status:
        s = s.where(User.status == status)
    if q:
        s = s.where(or_(User.username.ilike(f"%{q}%"), User.full_name.ilike(f"%{q}%")))
    return list(db.scalars(s))


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.username == body.username)):
        raise ApiError(409, "CONFLICT", "Tên đăng nhập đã tồn tại")
    u = User(username=body.username, full_name=body.full_name, email=body.email, role=body.role,
             password_hash=hash_password(body.password), status="ACTIVE")
    db.add(u)
    db.flush()
    audit(db, "USER_CREATED", actor=admin, target_type="user", target_id=u.id,
          detail={"username": u.username, "role": u.role}, ip=client_ip(request))
    db.commit()
    return u


@router.patch("/users/{user_id}", response_model=UserOut)
def patch_user(user_id: int, body: UserPatch, request: Request, admin: User = Depends(require_admin),
               db: Session = Depends(get_db)):
    u = _user(db, user_id)
    changes = body.model_dump(exclude_unset=True)
    if "role" in changes and changes["role"] != u.role:
        if u.id == admin.id:
            raise ApiError(409, "CONFLICT", "Không tự đổi vai trò của chính mình")
        audit(db, "ROLE_CHANGED", actor=admin, target_type="user", target_id=u.id,
              detail={"from": u.role, "to": changes["role"]}, ip=client_ip(request))
    for k, v in changes.items():
        setattr(u, k, v)
    u.updated_at = utcnow()
    audit(db, "USER_UPDATED", actor=admin, target_type="user", target_id=u.id, detail=changes, ip=client_ip(request))
    db.commit()
    return u


def _set_status(db: Session, admin: User, user_id: int, status: str, action: str, request: Request) -> User:
    u = _user(db, user_id)
    if u.id == admin.id and status != "ACTIVE":
        raise ApiError(409, "CONFLICT", "Không tự khóa chính mình")
    u.status, u.updated_at = status, utcnow()
    if status == "ACTIVE":
        u.failed_logins, u.locked_until = 0, None
    else:
        db.execute(update(RefreshToken).where(RefreshToken.user_id == u.id, RefreshToken.revoked_at.is_(None))
                   .values(revoked_at=utcnow()))
    audit(db, action, actor=admin, target_type="user", target_id=u.id, ip=client_ip(request))
    db.commit()
    return u


@router.post("/users/{user_id}/lock", response_model=UserOut)
def lock(user_id: int, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return _set_status(db, admin, user_id, "LOCKED", "USER_LOCKED", request)


@router.post("/users/{user_id}/unlock", response_model=UserOut)
def unlock(user_id: int, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return _set_status(db, admin, user_id, "ACTIVE", "USER_UNLOCKED", request)


@router.post("/users/{user_id}/activate", response_model=UserOut)
def activate(user_id: int, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return _set_status(db, admin, user_id, "ACTIVE", "USER_UPDATED", request)


@router.post("/users/{user_id}/reset-password")
def reset_password(user_id: int, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    u = _user(db, user_id)
    temp = secrets.token_urlsafe(9)
    u.password_hash, u.updated_at = hash_password(temp), utcnow()
    db.execute(update(RefreshToken).where(RefreshToken.user_id == u.id, RefreshToken.revoked_at.is_(None))
               .values(revoked_at=utcnow()))
    audit(db, "PASSWORD_CHANGED", actor=admin, target_type="user", target_id=u.id, detail={"by": "admin_reset"},
          ip=client_ip(request))
    db.commit()
    return {"userId": u.id, "temporaryPassword": temp, "note": "Mật khẩu tạm chỉ hiển thị một lần"}


@router.get("/audit-logs")
def audit_logs(actorId: int | None = None, action: str | None = None,  # noqa: N803
               frm: datetime | None = Query(None, alias="from"), to: datetime | None = None,
               page: int = Query(0, ge=0), size: int = Query(50, ge=1, le=500),
               _a: User = Depends(require_admin), db: Session = Depends(get_db)):
    q = select(AuditLog)
    if actorId:
        q = q.where(AuditLog.actor_id == actorId)
    if action:
        q = q.where(AuditLog.action == action)
    if frm:
        q = q.where(AuditLog.at >= frm)
    if to:
        q = q.where(AuditLog.at <= to)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(q.order_by(AuditLog.at.desc()).offset(page * size).limit(size))
    return {"items": [{"id": r.id, "actorId": r.actor_id, "actorLabel": r.actor_label, "action": r.action,
                       "targetType": r.target_type, "targetId": r.target_id, "detail": r.detail, "ip": str(r.ip) if r.ip else None,
                       "success": r.success, "at": r.at} for r in rows],
            "page": page, "size": size, "total": total}


@router.get("/dashboard/summary")
def summary(user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(Device).where(Device.status != "DECOMMISSIONED").order_by(Device.id)
    if user.role != "ADMIN":
        q = q.join(DeviceAssignment, DeviceAssignment.device_id == Device.id).where(DeviceAssignment.user_id == user.id)
    devices = list(db.scalars(q))
    ids = [d.id for d in devices]
    by_status: dict[str, int] = {}
    for d in devices:
        by_status[d.status] = by_status.get(d.status, 0) + 1
    open_alerts = []
    if ids:
        rows = db.execute(select(Alert, Device.device_code).join(Device, Device.id == Alert.device_id)
                          .where(Alert.device_id.in_(ids), Alert.status.in_(("OPEN", "ACKNOWLEDGED")))
                          .order_by(Alert.opened_at.desc()).limit(20)).all()
        open_alerts = [engine.alert_out(a, c) for a, c in rows]
    return {
        "devices": [{"id": d.id, "deviceCode": d.device_code, "name": d.name, "type": d.type, "status": d.status,
                     "online": d.online, "lastSeenAt": d.last_seen_at, "permission": permission_of(db, user, d.id),
                     "state": ingest.latest_state.get(d.id)} for d in devices],
        "countByStatus": by_status,
        "onlineCount": sum(1 for d in devices if d.online),
        "openAlerts": open_alerts,
    }
