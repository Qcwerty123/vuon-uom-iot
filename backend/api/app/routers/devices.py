"""Thiết bị: đăng ký, cấp phát, gán, khóa, mở khóa, thu hồi (đặc tả §10.5, §12.1, UC11–UC13)."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import device_auth, dynsec
from ..audit import audit
from ..config import settings
from ..db import get_db
from ..deps import client_ip, current_user, device_for_view, permission_of, require_admin
from ..errors import ApiError, not_found
from ..lifecycle import transition
from ..models import Device, DeviceAssignment, DeviceStatusHistory, Garden, User, Zone
from ..schemas import (AssignmentIn, AssignmentOut, DecommissionIn, DeviceCreate, DeviceOut, DevicePatch,
                       HistoryOut, ProvisionOut, ReasonIn)
from ..security import hash_password, new_device_secret, utcnow

router = APIRouter(prefix="/devices", tags=["devices"])
PREFIX = {"CONTROLLER": "ctl", "CAMERA": "cam"}


def _out(dev: Device, perm: str | None) -> DeviceOut:
    o = DeviceOut.model_validate(dev)
    o.permission = perm
    return o


def _garden_code(db: Session, dev: Device) -> str:
    if dev.zone_id:
        z = db.get(Zone, dev.zone_id)
        g = db.get(Garden, z.garden_id) if z else None
        if g:
            return g.code
    return "g01"


def _get(db: Session, device_id: int) -> Device:
    dev = db.get(Device, device_id)
    if not dev:
        raise not_found("Không tìm thấy thiết bị")
    return dev


def _broker_call(fn, *args) -> None:
    try:
        fn(*args)
    except dynsec.DynsecError as e:
        raise ApiError(503, "BROKER_UNAVAILABLE", f"Không thực hiện được trên broker: {e}")


@router.get("", response_model=list[DeviceOut])
def list_devices(status: str | None = None, type: str | None = None, zoneId: int | None = None,  # noqa: A002, N803
                 user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(Device).order_by(Device.id)
    if user.role != "ADMIN":
        q = q.join(DeviceAssignment, DeviceAssignment.device_id == Device.id).where(DeviceAssignment.user_id == user.id)
    if status:
        q = q.where(Device.status == status)
    if type:
        q = q.where(Device.type == type)
    if zoneId:
        q = q.where(Device.zone_id == zoneId)
    return [_out(d, permission_of(db, user, d.id)) for d in db.scalars(q)]


@router.get("/{device_id}", response_model=DeviceOut)
def get_device(device_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    dev, perm = device_for_view(db, user, device_id)
    return _out(dev, perm)


@router.post("", response_model=DeviceOut, status_code=201)
def create_device(body: DeviceCreate, request: Request, admin: User = Depends(require_admin),
                  db: Session = Depends(get_db)):
    if body.zone_id and not db.get(Zone, body.zone_id):
        raise ApiError(400, "VALIDATION_ERROR", "Khu vực không tồn tại")
    prefix = PREFIX[body.type]
    nums = [int(m.group(1)) for c in db.scalars(select(Device.device_code).where(Device.device_code.like(f"{prefix}-%")))
            if (m := re.fullmatch(rf"{prefix}-(\d{{4}})", c)) and int(m.group(1)) < 9000]  # 9xxx dành cho mô phỏng
    code = f"{prefix}-{(max(nums) + 1) if nums else 1:04d}"
    dev = Device(device_code=code, type=body.type, name=body.name, zone_id=body.zone_id, status="REGISTERED",
                 hw_version=body.hw_version)
    db.add(dev)
    db.flush()
    db.add(DeviceStatusHistory(device_id=dev.id, from_status=None, to_status="REGISTERED", reason="Đăng ký",
                               actor_id=admin.id))
    audit(db, "DEVICE_REGISTERED", actor=admin, target_type="device", target_id=dev.id,
          detail={"device_code": code}, ip=client_ip(request))
    db.commit()
    return _out(dev, "CONTROL")


@router.patch("/{device_id}", response_model=DeviceOut)
def patch_device(device_id: int, body: DevicePatch, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    dev = _get(db, device_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(dev, k, v)
    audit(db, "DEVICE_UPDATED", actor=admin, target_type="device", target_id=dev.id)
    db.commit()
    return _out(dev, "CONTROL")


@router.post("/{device_id}/provision", response_model=ProvisionOut)
def provision(device_id: int, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    dev = _get(db, device_id)
    if dev.status != "REGISTERED":
        raise ApiError(409, "INVALID_STATE_TRANSITION", "Chỉ cấp phát được thiết bị ở trạng thái REGISTERED; "
                                                      "muốn đổi khóa hãy dùng rotate-secret")
    garden = _garden_code(db, dev)
    secret = new_device_secret()
    _broker_call(dynsec.create_device, dev.device_code, garden, secret)  # lỗi → 503, giữ REGISTERED (UC11 4a)
    dev.credential_hash = hash_password(secret)
    transition(db, dev, "PROVISIONED", "Cấp phát khóa", admin.id)
    audit(db, "DEVICE_PROVISIONED", actor=admin, target_type="device", target_id=dev.id, ip=client_ip(request))
    db.commit()
    return ProvisionOut(device_code=dev.device_code, secret=secret, garden_code=garden,
                        mqtt_host=settings.mqtt_public_host, mqtt_port=settings.mqtt_port,
                        upload_url=f"http://{settings.mqtt_public_host}:{settings.backend_port}/device-api/v1/images")


@router.post("/{device_id}/rotate-secret", response_model=ProvisionOut)
def rotate_secret(device_id: int, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    dev = _get(db, device_id)
    if dev.status in ("REGISTERED", "DECOMMISSIONED"):
        raise ApiError(409, "INVALID_STATE_TRANSITION", f"Không cấp lại khóa khi thiết bị đang {dev.status}")
    secret = new_device_secret()
    _broker_call(dynsec.set_password, dev.device_code, secret)
    dev.credential_hash = hash_password(secret)
    device_auth.invalidate(dev.device_code)
    audit(db, "DEVICE_SECRET_ROTATED", actor=admin, target_type="device", target_id=dev.id, ip=client_ip(request))
    db.commit()
    garden = _garden_code(db, dev)
    return ProvisionOut(device_code=dev.device_code, secret=secret, garden_code=garden,
                        mqtt_host=settings.mqtt_public_host, mqtt_port=settings.mqtt_port,
                        upload_url=f"http://{settings.mqtt_public_host}:{settings.backend_port}/device-api/v1/images")


@router.post("/{device_id}/suspend", response_model=DeviceOut)
def suspend(device_id: int, body: ReasonIn, request: Request, admin: User = Depends(require_admin),
            db: Session = Depends(get_db)):
    dev = _get(db, device_id)
    if dev.status == "SUSPENDED":
        return _out(dev, "CONTROL")
    transition(db, dev, "SUSPENDED", body.reason, admin.id)          # kiểm tra luật trước
    _broker_call(dynsec.disable, dev.device_code)                    # ngắt ngay phiên đang mở (C18)
    dev.online = False
    audit(db, "DEVICE_SUSPENDED", actor=admin, target_type="device", target_id=dev.id,
          detail={"reason": body.reason}, ip=client_ip(request))
    db.commit()
    return _out(dev, "CONTROL")


@router.post("/{device_id}/resume", response_model=DeviceOut)
def resume(device_id: int, body: ReasonIn, request: Request, admin: User = Depends(require_admin),
           db: Session = Depends(get_db)):
    dev = _get(db, device_id)
    transition(db, dev, "PROVISIONED", body.reason, admin.id)       # chờ thiết bị kết nối lại → ACTIVE
    _broker_call(dynsec.enable, dev.device_code)
    audit(db, "DEVICE_RESUMED", actor=admin, target_type="device", target_id=dev.id,
          detail={"reason": body.reason}, ip=client_ip(request))
    db.commit()
    return _out(dev, "CONTROL")


@router.post("/{device_id}/decommission", response_model=DeviceOut)
def decommission(device_id: int, body: DecommissionIn, request: Request, admin: User = Depends(require_admin),
                 db: Session = Depends(get_db)):
    dev = _get(db, device_id)
    if body.confirm != dev.device_code:
        raise ApiError(400, "VALIDATION_ERROR", "Nhập đúng mã thiết bị để xác nhận thu hồi")
    transition(db, dev, "DECOMMISSIONED", body.reason, admin.id)
    _broker_call(dynsec.delete, dev.device_code)
    dev.online, dev.credential_hash, dev.decommissioned_at = False, None, utcnow()
    audit(db, "DEVICE_DECOMMISSIONED", actor=admin, target_type="device", target_id=dev.id,
          detail={"reason": body.reason}, ip=client_ip(request))
    db.commit()
    return _out(dev, "CONTROL")


@router.get("/{device_id}/history", response_model=list[HistoryOut])
def history(device_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    device_for_view(db, user, device_id)
    q = select(DeviceStatusHistory).where(DeviceStatusHistory.device_id == device_id).order_by(DeviceStatusHistory.at.desc())
    return list(db.scalars(q.limit(200)))


@router.get("/{device_id}/assignments", response_model=list[AssignmentOut])
def list_assignments(device_id: int, _admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _get(db, device_id)
    rows = db.execute(select(DeviceAssignment, User).join(User, User.id == DeviceAssignment.user_id)
                      .where(DeviceAssignment.device_id == device_id)).all()
    return [AssignmentOut(user_id=u.id, username=u.username, role=u.role, permission=a.permission) for a, u in rows]


@router.post("/{device_id}/assignments", response_model=AssignmentOut)
def assign(device_id: int, body: AssignmentIn, request: Request, admin: User = Depends(require_admin),
           db: Session = Depends(get_db)):
    _get(db, device_id)
    u = db.get(User, body.user_id)
    if not u:
        raise ApiError(400, "VALIDATION_ERROR", "Người dùng không tồn tại")
    perm = "VIEW" if u.role == "VIEWER" else body.permission
    a = db.get(DeviceAssignment, (u.id, device_id))
    if a:
        a.permission = perm
    else:
        db.add(DeviceAssignment(user_id=u.id, device_id=device_id, permission=perm, assigned_by=admin.id))
    audit(db, "DEVICE_ASSIGNED", actor=admin, target_type="device", target_id=device_id,
          detail={"user_id": u.id, "permission": perm}, ip=client_ip(request))
    db.commit()
    return AssignmentOut(user_id=u.id, username=u.username, role=u.role, permission=perm)


@router.delete("/{device_id}/assignments/{user_id}", status_code=204)
def unassign(device_id: int, user_id: int, request: Request, admin: User = Depends(require_admin),
             db: Session = Depends(get_db)):
    a = db.get(DeviceAssignment, (user_id, device_id))
    if a:
        db.delete(a)
        audit(db, "DEVICE_UNASSIGNED", actor=admin, target_type="device", target_id=device_id,
              detail={"user_id": user_id}, ip=client_ip(request))
        db.commit()


