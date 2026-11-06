"""Rule engine cảnh báo (đặc tả §13): THRESHOLD, OFFLINE, EVENT (AI_LEAF do WP-07 gọi open_alert)."""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from . import realtime, telegram
from .db import session_scope
from .models import Alert, AlertRule, Device, DeviceAssignment, Garden, User, Zone

log = logging.getLogger("alerts")
LOCAL_TZ = timezone(timedelta(hours=7))  # giờ Việt Nam; không dùng zoneinfo vì Windows thiếu tzdata
ACTIVE = ("OPEN", "ACKNOWLEDGED")
CLEAR_EVENT = {"tank_ok": "tank_low", "sensor_ok": "sensor_fault"}
METRIC_LABEL = {"soil": "Độ ẩm đất", "soil1": "Đất 1", "soil2": "Đất 2", "air_temp": "Nhiệt độ", "air_hum": "Độ ẩm KK",
                "light": "Ánh sáng", "tank": "Mực nước bể"}
UNIT = {"soil": "%", "soil1": "%", "soil2": "%", "air_temp": "°C", "air_hum": "%", "light": " lux", "tank": "%"}

_breach: dict[tuple[int, int], float] = {}   # (rule_id, device_id) -> thời điểm bắt đầu vượt ngưỡng
_lock = threading.Lock()
_rules_cache: tuple[float, list] = (0.0, [])


def _utc() -> datetime:
    return datetime.now(timezone.utc)


def _rules(db: Session) -> list[AlertRule]:
    global _rules_cache
    if time.time() - _rules_cache[0] > 10:
        rules = list(db.scalars(select(AlertRule).where(AlertRule.enabled.is_(True))))
        for r in rules:
            db.expunge(r)
        _rules_cache = (time.time(), rules)
    return _rules_cache[1]


def invalidate_rules() -> None:
    global _rules_cache
    _rules_cache = (0.0, [])


def _applies(r: AlertRule, dev: Device) -> bool:
    return (r.scope_device_id in (None, dev.id)) and (r.scope_zone_id in (None, dev.zone_id))


def _place(db: Session, dev: Device) -> str:
    z = db.get(Zone, dev.zone_id) if dev.zone_id else None
    g = db.get(Garden, z.garden_id) if z else None
    return f"Vườn {g.code if g else '?'} · {z.name if z else '?'}"


def open_alert(db: Session, dev: Device, rule: AlertRule, message: str, context: dict) -> Alert | None:
    active = db.scalar(select(Alert).where(Alert.rule_id == rule.id, Alert.device_id == dev.id,
                                           Alert.status.in_(ACTIVE)).limit(1))
    if active:
        return None
    last = db.scalar(select(Alert.opened_at).where(Alert.rule_id == rule.id, Alert.device_id == dev.id)
                     .order_by(Alert.opened_at.desc()).limit(1))
    if last and _utc() - last < timedelta(minutes=rule.cooldown_min or 0):
        return None  # chống gửi lặp (§13.1)
    text = f"[{_place(db, dev)}] {message}. Thiết bị {dev.device_code}."
    a = Alert(rule_id=rule.id, device_id=dev.id, type=rule.type, severity=rule.severity, message=text[:300],
              context=context, status="OPEN", opened_at=_utc())
    db.add(a)
    db.flush()
    realtime.publish(dev.id, {"type": "alert", "id": a.id, "deviceId": dev.id, "alertType": a.type,
                              "severity": a.severity, "status": a.status, "message": a.message})
    if rule.notify_telegram and dev.status != "MAINTENANCE" and telegram.enabled():
        threading.Thread(target=_notify, args=(a.id,), daemon=True).start()
    log.info("Mở cảnh báo #%s: %s", a.id, a.message)
    return a


def _notify(alert_id: int) -> None:
    time.sleep(0.5)  # chờ giao dịch mở cảnh báo commit
    with session_scope() as db:
        a = db.get(Alert, alert_id)
        if not a:
            return
        q = (select(User).where(User.status == "ACTIVE", User.telegram_chat_id.isnot(None),
                                or_(User.role == "ADMIN",
                                    User.id.in_(select(DeviceAssignment.user_id)
                                                .where(DeviceAssignment.device_id == a.device_id)))))
        icon = "🔴" if a.severity == "CRITICAL" else ("⚠" if a.severity == "WARNING" else "ℹ")
        sent = False
        for u in db.scalars(q):
            sent = telegram.send(u.telegram_chat_id, f"{icon} {a.message}") or sent
        if sent:
            a.notified_at = _utc()


def _since(ts: float) -> str:
    return datetime.fromtimestamp(ts, LOCAL_TZ).strftime("%H:%M")


def on_telemetry(db: Session, dev: Device, data: dict) -> None:
    now = time.time()
    for r in _rules(db):
        if r.type != "THRESHOLD" or not _applies(r, dev) or r.metric not in data:
            continue
        m = data[r.metric]
        v = m.get("v")
        if v is None or not m.get("ok", True) or r.threshold is None:
            continue
        thr, hyst, key = r.threshold, r.hysteresis or 0, (r.id, dev.id)
        breach = {"<": v < thr, "<=": v <= thr, ">": v > thr, ">=": v >= thr}.get(r.operator or "", False)
        with _lock:
            if breach:
                start = _breach.setdefault(key, now)
            else:
                cleared = (v >= thr + hyst) if (r.operator or "").startswith("<") else (v <= thr - hyst)
                if cleared:
                    _breach.pop(key, None)
                    for a in db.scalars(select(Alert).where(Alert.rule_id == r.id, Alert.device_id == dev.id,
                                                            Alert.status.in_(ACTIVE),
                                                            Alert.condition_cleared_at.is_(None))):
                        a.condition_cleared_at = _utc()
                continue
        if now - start >= (r.duration_s or 0):
            lbl, u = METRIC_LABEL.get(r.metric, r.metric), UNIT.get(r.metric, "")
            open_alert(db, dev, r, f"{r.name}: {lbl}={v:g}{u} ({r.operator} {thr:g}{u}) từ {_since(start)}",
                       {"metric": r.metric, "value": v, "threshold": thr, "operator": r.operator})


def on_event(db: Session, dev: Device, typ: str, detail: dict) -> None:
    if typ in CLEAR_EVENT:
        base = CLEAR_EVENT[typ]
        for a in db.scalars(select(Alert).join(AlertRule, AlertRule.id == Alert.rule_id)
                            .where(Alert.device_id == dev.id, Alert.status.in_(ACTIVE), AlertRule.event_type == base,
                                   Alert.condition_cleared_at.is_(None))):
            a.condition_cleared_at = _utc()
        return
    for r in _rules(db):
        if r.type == "EVENT" and r.event_type == typ and _applies(r, dev):
            extra = ""
            if typ == "sensor_fault" and detail.get("sensor"):
                extra = f" ({detail['sensor']})"
            elif typ == "tank_low" and detail.get("tank") is not None:
                extra = f" (bể còn {detail['tank']}%)"
            open_alert(db, dev, r, f"{r.name}{extra}", {"event": typ, "detail": detail})


def on_offline(db: Session, dev: Device) -> None:
    for r in _rules(db):
        if r.type == "OFFLINE" and _applies(r, dev):
            seen = dev.last_seen_at.astimezone(LOCAL_TZ).strftime("%H:%M") if dev.last_seen_at else "?"
            open_alert(db, dev, r, f"{r.name}: thiết bị offline, tín hiệu cuối {seen}", {"lastSeenAt": str(dev.last_seen_at)})


def on_online(db: Session, dev: Device) -> None:
    """OFFLINE tự đóng khi thiết bị online lại (§12.3)."""
    for a in db.scalars(select(Alert).where(Alert.device_id == dev.id, Alert.type == "OFFLINE",
                                            Alert.status.in_(ACTIVE))):
        a.status, a.closed_at, a.close_note, a.condition_cleared_at = "CLOSED", _utc(), "auto", _utc()
        realtime.publish(dev.id, {"type": "alert", "id": a.id, "deviceId": dev.id, "alertType": a.type,
                                  "severity": a.severity, "status": a.status, "message": a.message})


def alert_out(a: Alert, device_code: str | None = None) -> dict:
    return {"id": a.id, "ruleId": a.rule_id, "deviceId": a.device_id, "deviceCode": device_code, "type": a.type,
            "severity": a.severity, "message": a.message, "context": a.context, "status": a.status,
            "openedAt": a.opened_at, "conditionClearedAt": a.condition_cleared_at, "ackBy": a.ack_by,
            "ackAt": a.ack_at, "closedBy": a.closed_by, "closedAt": a.closed_at, "closeNote": a.close_note,
            "notifiedAt": a.notified_at}


