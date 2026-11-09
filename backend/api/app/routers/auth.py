"""Đăng nhập, làm mới phiên, đăng xuất, hồ sơ cá nhân (đặc tả §10.2)."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..audit import audit
from ..config import settings
from ..db import get_db
from ..deps import client_ip, current_user
from ..errors import ApiError
from ..models import RefreshToken, User
from ..schemas import LoginIn, MePatch, PasswordIn, RefreshIn, TokenOut, UserOut
from ..security import hash_password, make_access_token, new_refresh_token, sha256, utcnow, verify_password

router = APIRouter(tags=["auth"])
MAX_FAILS, LOCK_MIN = 5, 15


def _issue(db: Session, user: User, request: Request) -> TokenOut:
    access, ttl = make_access_token(user.id, user.role)
    token, h = new_refresh_token()
    db.add(RefreshToken(user_id=user.id, token_hash=h, expires_at=utcnow() + timedelta(days=settings.refresh_ttl_days),
                        user_agent=(request.headers.get("user-agent") or "")[:200], ip=client_ip(request)))
    return TokenOut(access_token=access, refresh_token=token, expires_in=ttl, user=UserOut.model_validate(user))


def _authenticate(db: Session, username: str, password: str, request: Request) -> User:
    """Kiểm tra mật khẩu, khóa tạm khi sai nhiều lần, ghi audit. Trả về user hợp lệ."""
    ip = client_ip(request)
    body = LoginIn(username=username, password=password)
    user = db.scalar(select(User).where(User.username == body.username))
    now = utcnow()
    if user and user.locked_until and user.locked_until > now:
        audit(db, "LOGIN_FAILED", actor=user, ip=ip, success=False, detail={"reason": "locked"})
        db.commit()
        raise ApiError(423, "ACCOUNT_LOCKED", "Tài khoản tạm khóa do đăng nhập sai nhiều lần",
                       {"lockedUntil": user.locked_until.isoformat()})
    if not user or not verify_password(body.password, user.password_hash):
        if user:
            user.failed_logins = (user.failed_logins or 0) + 1
            if user.failed_logins >= MAX_FAILS:
                user.locked_until, user.failed_logins = now + timedelta(minutes=LOCK_MIN), 0
        audit(db, "LOGIN_FAILED", actor=user, actor_label=body.username[:60], ip=ip, success=False)
        db.commit()
        raise ApiError(401, "UNAUTHORIZED", "Sai tên đăng nhập hoặc mật khẩu")
    if user.status != "ACTIVE":
        raise ApiError(403, "FORBIDDEN", "Tài khoản không hoạt động")
    user.failed_logins, user.locked_until = 0, None
    audit(db, "LOGIN_SUCCESS", actor=user, ip=ip)
    return user


@router.post("/auth/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    user = _authenticate(db, body.username, body.password, request)
    out = _issue(db, user, request)
    db.commit()
    return out


@router.post("/auth/token", include_in_schema=True, summary="Đăng nhập cho nút Authorize của Swagger (form)")
def token_form(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = _authenticate(db, form.username, form.password, request)
    out = _issue(db, user, request)
    db.commit()
    return {"access_token": out.access_token, "token_type": "bearer", "expires_in": out.expires_in}


@router.post("/auth/refresh", response_model=TokenOut)
def refresh(body: RefreshIn, request: Request, db: Session = Depends(get_db)):
    rt = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == sha256(body.refresh_token)))
    if not rt or rt.revoked_at or rt.expires_at <= utcnow():
        raise ApiError(401, "UNAUTHORIZED", "Phiên đã hết hạn, đăng nhập lại")
    user = db.get(User, rt.user_id)
    if not user or user.status != "ACTIVE":
        raise ApiError(401, "UNAUTHORIZED", "Tài khoản không hoạt động")
    rt.revoked_at = utcnow()  # rotation: token cũ hết hiệu lực
    out = _issue(db, user, request)
    db.commit()
    return out


@router.post("/auth/logout", status_code=204)
def logout(body: RefreshIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.execute(update(RefreshToken).where(RefreshToken.token_hash == sha256(body.refresh_token),
                                          RefreshToken.user_id == user.id).values(revoked_at=utcnow()))
    audit(db, "LOGOUT", actor=user, ip=client_ip(request))
    db.commit()


@router.get("/users/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


@router.patch("/users/me", response_model=UserOut)
def update_me(body: MePatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(user, k, v)
    user.updated_at = utcnow()
    audit(db, "USER_UPDATED", actor=user, target_type="user", target_id=user.id)
    db.commit()
    return user


@router.post("/users/me/password", status_code=204)
def change_password(body: PasswordIn, request: Request, user: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    if not verify_password(body.current_password, user.password_hash):
        raise ApiError(400, "VALIDATION_ERROR", "Mật khẩu hiện tại không đúng")
    user.password_hash = hash_password(body.new_password)
    user.updated_at = utcnow()
    db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
               .values(revoked_at=utcnow()))
    audit(db, "PASSWORD_CHANGED", actor=user, ip=client_ip(request))
    db.commit()
