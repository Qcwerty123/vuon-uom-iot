"""Tạo 3 tài khoản mẫu lúc khởi động lần đầu, mật khẩu từ .env (đặc tả §11.5).
Gán sẵn operator = CONTROL, viewer = VIEW trên các thiết bị seed để demo phân quyền (bước 1, 9)."""
from __future__ import annotations

import logging

from sqlalchemy import select

from .config import settings
from .db import session_scope
from .models import Device, DeviceAssignment, User
from .security import hash_password

log = logging.getLogger("seed")
ACCOUNTS = [("admin", "ADMIN", "Quản trị viên"), ("operator", "OPERATOR", "Người vận hành"),
            ("viewer", "VIEWER", "Người xem")]


def run() -> None:
    with session_scope() as db:
        created = []
        for username, role, full_name in ACCOUNTS:
            if db.scalar(select(User).where(User.username == username)):
                continue
            pw = settings.seed_passwords.get(username)
            if not pw or pw == "change-me":
                log.warning("Bỏ qua tạo %s: thiếu SEED_%s_PASSWORD trong .env", username, username.upper())
                continue
            u = User(username=username, role=role, full_name=full_name, password_hash=hash_password(pw), status="ACTIVE")
            db.add(u)
            db.flush()
            created.append(u)
        if not created:
            return
        devices = list(db.scalars(select(Device).where(Device.device_code.in_(["ctl-0001", "cam-0001"]))))
        for u in created:
            if u.role == "ADMIN":
                continue
            for d in devices:
                db.add(DeviceAssignment(user_id=u.id, device_id=d.id,
                                        permission="CONTROL" if u.role == "OPERATOR" else "VIEW"))
        log.info("Đã tạo tài khoản: %s", ", ".join(u.username for u in created))
