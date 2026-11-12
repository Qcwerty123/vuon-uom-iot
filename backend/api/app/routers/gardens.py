"""Vườn và khu vực (đặc tả §10.4): ADMIN ghi; người đã đăng nhập đọc các vườn/khu có thiết bị được gán (ADMIN thấy hết)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db
from ..deps import client_ip, current_user, require_admin
from ..errors import ApiError, not_found
from ..models import AlertRule, Device, DeviceAssignment, Garden, User, Zone
from ..schemas import Api

router = APIRouter(tags=["gardens"])


class GardenIn(Api):
    code: str = Field(min_length=1, max_length=20, pattern=r"^[a-z0-9-]+$")
    name: str = Field(min_length=1, max_length=120)
    address: str | None = Field(default=None, max_length=200)


class ZoneIn(Api):
    name: str = Field(min_length=1, max_length=120)
    crop_type: str | None = Field(default=None, max_length=60)


class ZonePatch(Api):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    crop_type: str | None = Field(default=None, max_length=60)


def _garden_out(g: Garden) -> dict:
    return {"id": g.id, "code": g.code, "name": g.name, "address": g.address}


def _zone_out(z: Zone, count: int | None = None) -> dict:
    return {"id": z.id, "gardenId": z.garden_id, "name": z.name, "cropType": z.crop_type, "deviceCount": count}


def _visible_zone_ids(db: Session, user: User):
    """Khu có thiết bị được gán cho user (câu truy vấn con)."""
    return (select(Device.zone_id).join(DeviceAssignment, DeviceAssignment.device_id == Device.id)
            .where(DeviceAssignment.user_id == user.id, Device.zone_id.isnot(None)))


def _device_counts(db: Session) -> dict[int, int]:
    rows = db.execute(select(Device.zone_id, func.count()).where(Device.zone_id.isnot(None),
                                                                Device.status != "DECOMMISSIONED")
                      .group_by(Device.zone_id)).all()
    return {z: n for z, n in rows}


@router.get("/gardens")
def list_gardens(user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(Garden).order_by(Garden.id)
    if user.role != "ADMIN":
        q = q.where(Garden.id.in_(select(Zone.garden_id).where(Zone.id.in_(_visible_zone_ids(db, user)))))
    return [_garden_out(g) for g in db.scalars(q)]


@router.post("/gardens", status_code=201)
def create_garden(body: GardenIn, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if db.scalar(select(Garden.id).where(Garden.code == body.code)):
        raise ApiError(409, "CONFLICT", "Mã vườn đã tồn tại")
    g = Garden(code=body.code, name=body.name, address=body.address)
    db.add(g)
    db.flush()
    audit(db, "GARDEN_CHANGED", actor=admin, target_type="garden", target_id=g.id,
          detail={"action": "create", "code": g.code, "name": g.name}, ip=client_ip(request))
    db.commit()
    return _garden_out(g)


@router.get("/gardens/{garden_id}/zones")
def list_zones(garden_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    g = db.get(Garden, garden_id)
    q = select(Zone).where(Zone.garden_id == garden_id).order_by(Zone.id)
    if user.role != "ADMIN":
        q = q.where(Zone.id.in_(_visible_zone_ids(db, user)))
    zones = list(db.scalars(q)) if g else []
    if not g or (user.role != "ADMIN" and not zones):
        raise not_found("Không tìm thấy vườn")
    counts = _device_counts(db)
    return [_zone_out(z, counts.get(z.id, 0)) for z in zones]


@router.post("/gardens/{garden_id}/zones", status_code=201)
def create_zone(garden_id: int, body: ZoneIn, request: Request, admin: User = Depends(require_admin),
                db: Session = Depends(get_db)):
    if not db.get(Garden, garden_id):
        raise not_found("Không tìm thấy vườn")
    if db.scalar(select(Zone.id).where(Zone.garden_id == garden_id, Zone.name == body.name)):
        raise ApiError(409, "CONFLICT", "Tên khu vực đã có trong vườn này")
    z = Zone(garden_id=garden_id, name=body.name, crop_type=body.crop_type)
    db.add(z)
    db.flush()
    audit(db, "ZONE_CHANGED", actor=admin, target_type="zone", target_id=z.id,
          detail={"action": "create", "garden_id": garden_id, "name": z.name}, ip=client_ip(request))
    db.commit()
    return _zone_out(z, 0)


def _zone(db: Session, zone_id: int) -> Zone:
    z = db.get(Zone, zone_id)
    if not z:
        raise not_found("Không tìm thấy khu vực")
    return z


@router.patch("/zones/{zone_id}")
def patch_zone(zone_id: int, body: ZonePatch, request: Request, admin: User = Depends(require_admin),
               db: Session = Depends(get_db)):
    z = _zone(db, zone_id)
    changes = body.model_dump(exclude_unset=True)
    if changes.get("name") and changes["name"] != z.name and db.scalar(
            select(Zone.id).where(Zone.garden_id == z.garden_id, Zone.name == changes["name"])):
        raise ApiError(409, "CONFLICT", "Tên khu vực đã có trong vườn này")
    for k, v in changes.items():
        setattr(z, k, v)
    audit(db, "ZONE_CHANGED", actor=admin, target_type="zone", target_id=z.id, detail={"action": "update", **changes},
          ip=client_ip(request))
    db.commit()
    return _zone_out(z, _device_counts(db).get(z.id, 0))


@router.delete("/zones/{zone_id}", status_code=204)
def delete_zone(zone_id: int, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    z = _zone(db, zone_id)
    # Mọi thiết bị (kể cả đã thu hồi) còn tham chiếu khu vực → không xóa được (§10.4)
    n = db.scalar(select(func.count()).select_from(Device).where(Device.zone_id == z.id))
    if n:
        raise ApiError(409, "CONFLICT", f"Khu vực còn {n} thiết bị, chuyển thiết bị sang khu khác trước",
                       {"deviceCount": n})
    if db.scalar(select(func.count()).select_from(AlertRule).where(AlertRule.scope_zone_id == z.id)):
        raise ApiError(409, "CONFLICT", "Khu vực đang được luật cảnh báo tham chiếu")
    db.delete(z)
    audit(db, "ZONE_CHANGED", actor=admin, target_type="zone", target_id=zone_id,
          detail={"action": "delete", "name": z.name}, ip=client_ip(request))
    db.commit()
