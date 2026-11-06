"""Cảnh báo và luật cảnh báo (đặc tả §10.8, §12.3, §13)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import alerts as engine
from ..audit import audit
from ..db import get_db
from ..deps import client_ip, current_user, permission_of, require_admin
from ..errors import ApiError, forbidden, not_found
from ..models import Alert, AlertRule, Device, DeviceAssignment, User
from ..schemas import Api

router = APIRouter(tags=["alerts"])


class CloseIn(Api):
    note: str | None = Field(default=None, max_length=300)


class RuleIn(Api):
    name: str = Field(min_length=1, max_length=120)
    type: Literal["THRESHOLD", "OFFLINE", "EVENT", "AI_LEAF"]
    scope_zone_id: int | None = None
    scope_device_id: int | None = None
    metric: Literal["soil", "soil1", "soil2", "air_temp", "air_hum", "light", "tank"] | None = None
    operator: Literal["<", "<=", ">", ">="] | None = None
    threshold: float | None = None
    hysteresis: float = 0
    duration_s: int = Field(default=0, ge=0, le=86400)
    event_type: str | None = Field(default=None, max_length=30)
    severity: Literal["INFO", "WARNING", "CRITICAL"] = "WARNING"
    cooldown_min: int = Field(default=30, ge=0, le=1440)
    notify_telegram: bool = True
    enabled: bool = True


def _check_rule(r: RuleIn) -> None:
    if r.type == "THRESHOLD" and (r.metric is None or r.operator is None or r.threshold is None):
        raise ApiError(400, "VALIDATION_ERROR", "Luật THRESHOLD cần metric, operator, threshold")
    if r.type == "EVENT" and not r.event_type:
        raise ApiError(400, "VALIDATION_ERROR", "Luật EVENT cần eventType")


def rule_out(r: AlertRule) -> dict:
    return {"id": r.id, "name": r.name, "type": r.type, "scopeZoneId": r.scope_zone_id,
            "scopeDeviceId": r.scope_device_id, "metric": r.metric, "operator": r.operator, "threshold": r.threshold,
            "hysteresis": r.hysteresis, "durationS": r.duration_s, "eventType": r.event_type, "severity": r.severity,
            "cooldownMin": r.cooldown_min, "notifyTelegram": r.notify_telegram, "enabled": r.enabled}


@router.get("/alerts")
def list_alerts(status: str | None = None, severity: str | None = None, deviceId: int | None = None,  # noqa: N803
                frm: datetime | None = Query(None, alias="from"), to: datetime | None = None,
                page: int = Query(0, ge=0), size: int = Query(20, ge=1, le=200),
                user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(Alert, Device.device_code).join(Device, Device.id == Alert.device_id)
    if user.role != "ADMIN":
        q = q.where(Alert.device_id.in_(select(DeviceAssignment.device_id).where(DeviceAssignment.user_id == user.id)))
    if status:
        q = q.where(Alert.status.in_(status.split(",")))
    if severity:
        q = q.where(Alert.severity == severity)
    if deviceId:
        q = q.where(Alert.device_id == deviceId)
    if frm:
        q = q.where(Alert.opened_at >= frm)
    if to:
        q = q.where(Alert.opened_at <= to)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.execute(q.order_by(Alert.opened_at.desc()).offset(page * size).limit(size)).all()
    return {"items": [engine.alert_out(a, code) for a, code in rows], "page": page, "size": size, "total": total}


def _alert_for_control(db: Session, user: User, alert_id: int) -> Alert:
    a = db.get(Alert, alert_id)
    perm = permission_of(db, user, a.device_id) if a else None
    if not a or not perm:
        raise not_found("Không tìm thấy cảnh báo")
    if perm != "CONTROL":
        raise forbidden("Cần quyền CONTROL trên thiết bị này")
    return a


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge(alert_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = _alert_for_control(db, user, alert_id)
    if a.status != "OPEN":
        raise ApiError(409, "INVALID_STATE_TRANSITION", f"Cảnh báo đang {a.status}")
    a.status, a.ack_by, a.ack_at = "ACKNOWLEDGED", user.id, datetime.now(timezone.utc)
    audit(db, "ALERT_ACKNOWLEDGED", actor=user, target_type="alert", target_id=a.id, ip=client_ip(request))
    db.commit()
    engine.realtime.publish(a.device_id, {"type": "alert", "id": a.id, "deviceId": a.device_id, "alertType": a.type,
                                          "severity": a.severity, "status": a.status, "message": a.message})
    return engine.alert_out(a)


@router.post("/alerts/{alert_id}/close")
def close(alert_id: int, body: CloseIn, request: Request, user: User = Depends(current_user),
          db: Session = Depends(get_db)):
    a = _alert_for_control(db, user, alert_id)
    if a.status == "CLOSED":
        raise ApiError(409, "INVALID_STATE_TRANSITION", "Cảnh báo đã đóng")
    a.status, a.closed_by, a.closed_at, a.close_note = "CLOSED", user.id, datetime.now(timezone.utc), body.note
    audit(db, "ALERT_CLOSED", actor=user, target_type="alert", target_id=a.id, detail={"note": body.note},
          ip=client_ip(request))
    db.commit()
    engine.realtime.publish(a.device_id, {"type": "alert", "id": a.id, "deviceId": a.device_id, "alertType": a.type,
                                          "severity": a.severity, "status": a.status, "message": a.message})
    return engine.alert_out(a)


@router.get("/alert-rules")
def list_rules(_user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [rule_out(r) for r in db.scalars(select(AlertRule).order_by(AlertRule.id))]


@router.post("/alert-rules", status_code=201)
def create_rule(body: RuleIn, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _check_rule(body)
    r = AlertRule(**body.model_dump(), created_by=admin.id)
    db.add(r)
    db.flush()
    audit(db, "ALERT_RULE_CHANGED", actor=admin, target_type="alert_rule", target_id=r.id,
          detail={"action": "create", **body.model_dump()}, ip=client_ip(request))
    db.commit()
    engine.invalidate_rules()
    return rule_out(r)


@router.patch("/alert-rules/{rule_id}")
def update_rule(rule_id: int, body: RuleIn, request: Request, admin: User = Depends(require_admin),
                db: Session = Depends(get_db)):
    r = db.get(AlertRule, rule_id)
    if not r:
        raise not_found("Không tìm thấy luật")
    _check_rule(body)
    for k, v in body.model_dump().items():
        setattr(r, k, v)
    audit(db, "ALERT_RULE_CHANGED", actor=admin, target_type="alert_rule", target_id=r.id,
          detail={"action": "update", **body.model_dump()}, ip=client_ip(request))
    db.commit()
    engine.invalidate_rules()
    return rule_out(r)


@router.delete("/alert-rules/{rule_id}", status_code=204)
def delete_rule(rule_id: int, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Không xóa cứng (cảnh báo cũ còn tham chiếu): chỉ tắt luật."""
    r = db.get(AlertRule, rule_id)
    if not r:
        raise not_found("Không tìm thấy luật")
    r.enabled = False
    audit(db, "ALERT_RULE_CHANGED", actor=admin, target_type="alert_rule", target_id=r.id,
          detail={"action": "disable"}, ip=client_ip(request))
    db.commit()
    engine.invalidate_rules()
