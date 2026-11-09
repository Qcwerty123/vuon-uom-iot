"""Lệnh, cấu hình, bảo trì thiết bị (đặc tả §10.5, §10.7)."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import commands as svc
from ..audit import audit
from ..db import get_db
from ..deps import client_ip, current_user, device_for_view, permission_of
from ..errors import ApiError, forbidden, not_found
from ..lifecycle import transition
from ..models import Command, DeviceConfig, User
from ..schemas import Api, ReasonIn

router = APIRouter(tags=["control"])


class CommandIn(Api):
    action: str = Field(min_length=1, max_length=30)
    params: dict = Field(default_factory=dict)


class ConfigIn(Api):
    params: dict


def _control(db: Session, user: User, device_id: int, request: Request, what: str):
    """Kiểm tra CONTROL; thiếu quyền thì ghi audit COMMAND_DENIED (§3.3 UC05 2a)."""
    dev, perm = device_for_view(db, user, device_id)
    if perm != "CONTROL":
        audit(db, "COMMAND_DENIED", actor=user, target_type="device", target_id=device_id, detail={"what": what},
              ip=client_ip(request), success=False)
        db.commit()
        raise forbidden("Cần quyền CONTROL trên thiết bị này")
    return dev


@router.post("/devices/{device_id}/commands", status_code=202)
def send_command(device_id: int, body: CommandIn, request: Request, user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    dev = _control(db, user, device_id, request, body.action)
    cmd = svc.send_command(db, dev, user, body.action, body.params)
    audit(db, "COMMAND_SENT", actor=user, target_type="device", target_id=dev.id,
          detail={"cmd_id": cmd.cmd_id, "action": cmd.action, "params": cmd.params}, ip=client_ip(request))
    db.commit()
    svc.dispatch_command(db, dev, cmd)
    return {"cmdId": cmd.cmd_id, "status": "PENDING"}


@router.get("/devices/{device_id}/commands")
def list_commands(device_id: int, status: str | None = None, frm: datetime | None = Query(None, alias="from"),
                  to: datetime | None = None, limit: int = Query(50, le=500), user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    device_for_view(db, user, device_id)
    q = select(Command).where(Command.device_id == device_id).order_by(Command.issued_at.desc()).limit(limit)
    if status:
        q = q.where(Command.status == status)
    if frm:
        q = q.where(Command.issued_at >= frm)
    if to:
        q = q.where(Command.issued_at <= to)
    return [svc.command_out(c) for c in db.scalars(q)]


@router.get("/commands/{cmd_id}")
def get_command(cmd_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        c = db.get(Command, cmd_id)
    except Exception:  # noqa: BLE001 — cmd_id không phải UUID
        db.rollback()
        c = None
    if not c or not permission_of(db, user, c.device_id):
        raise not_found("Không tìm thấy lệnh")
    return svc.command_out(c)


@router.get("/devices/{device_id}/config")
def get_config(device_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    dev, _ = device_for_view(db, user, device_id)
    last = db.scalar(select(DeviceConfig).where(DeviceConfig.device_id == device_id)
                     .order_by(DeviceConfig.config_version.desc()).limit(1))
    return {"deviceId": device_id, "deviceConfigVersion": dev.current_config_version,
            "params": svc.current_params(db, dev), "latest": svc.config_out(last) if last else None}


@router.put("/devices/{device_id}/config", status_code=202)
def put_config(device_id: int, body: ConfigIn, request: Request, user: User = Depends(current_user),
               db: Session = Depends(get_db)):
    dev = _control(db, user, device_id, request, "config")
    cfg = svc.put_config(db, dev, user, body.params)
    audit(db, "CONFIG_CHANGED", actor=user, target_type="device", target_id=dev.id,
          detail={"config_version": cfg.config_version, "changes": body.params}, ip=client_ip(request))
    db.commit()
    out = svc.config_out(cfg)
    svc.dispatch_config(db, dev, cfg)
    return out


@router.get("/devices/{device_id}/config/history")
def config_history(device_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    device_for_view(db, user, device_id)
    q = select(DeviceConfig).where(DeviceConfig.device_id == device_id).order_by(DeviceConfig.config_version.desc())
    return [svc.config_out(c) for c in db.scalars(q.limit(100))]


@router.post("/devices/{device_id}/maintenance")
def maintenance(device_id: int, body: ReasonIn, request: Request, user: User = Depends(current_user),
                db: Session = Depends(get_db)):
    dev = _control(db, user, device_id, request, "maintenance")
    transition(db, dev, "MAINTENANCE", body.reason, user.id)
    audit(db, "DEVICE_MAINTENANCE", actor=user, target_type="device", target_id=dev.id,
          detail={"reason": body.reason, "action": "start"}, ip=client_ip(request))
    db.commit()
    return {"id": dev.id, "status": dev.status}


@router.post("/devices/{device_id}/maintenance/end")
def maintenance_end(device_id: int, body: ReasonIn, request: Request, user: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    dev = _control(db, user, device_id, request, "maintenance_end")
    if dev.status != "MAINTENANCE":
        raise ApiError(409, "INVALID_STATE_TRANSITION", "Thiết bị không ở trạng thái bảo trì")
    transition(db, dev, "ACTIVE" if dev.online else "OFFLINE", body.reason, user.id)
    audit(db, "DEVICE_MAINTENANCE", actor=user, target_type="device", target_id=dev.id,
          detail={"reason": body.reason, "action": "end"}, ip=client_ip(request))
    db.commit()
    return {"id": dev.id, "status": dev.status}
