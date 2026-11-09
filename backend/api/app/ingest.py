"""Bộ nhận MQTT (đặc tả §8.10): kiểm tra, chống trùng, lưu, cập nhật last_seen, đẩy WebSocket.

Chạy trong thread của paho; mỗi bản tin một phiên CSDL.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from . import alerts, realtime
from .audit import audit
from .config import settings
from .db import session_scope
from .lifecycle import transition
from .models import Device, DeviceEvent, Telemetry

log = logging.getLogger("ingest")

RANGES = {"soil1": (0, 100), "soil2": (0, 100), "soil": (0, 100), "air_temp": (-40, 80), "air_hum": (0, 100),
          "light": (0, 65535), "tank": (0, 100)}
REJECT_STATUSES = {"REGISTERED", "SUSPENDED", "DECOMMISSIONED"}
MAX_PAYLOAD = 2048

stats = {"received": 0, "invalid": 0, "rejected": 0, "stored": 0}
latest_state: dict[int, dict] = {}          # device_id -> state (bơm, quạt, chế độ, khóa) mới nhất
_ack_handlers: list = []                    # WP-03 đăng ký xử lý ack lệnh/cấu hình
_client: mqtt.Client | None = None


def on_ack(fn) -> None:
    _ack_handlers.append(fn)


def _ts(ms, synced: bool = True) -> datetime:
    now = datetime.now(timezone.utc)
    try:
        ms = int(ms or 0)
    except (TypeError, ValueError):
        ms = 0
    if not synced or ms <= 0:
        return now
    t = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    # Giờ thiết bị lệch quá 1 ngày so với máy chủ → dùng giờ nhận
    return t if abs((t - now).total_seconds()) < 86400 else now


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


def _mark_seen(db, dev: Device, retained: bool = False) -> None:
    now = datetime.now(timezone.utc)
    if not retained:
        dev.last_seen_at = now
    if not dev.online:
        dev.online = True
        alerts.on_online(db, dev)
    if dev.status == "PROVISIONED":
        dev.first_seen_at = dev.first_seen_at or now
        transition(db, dev, "ACTIVE", "Kết nối lần đầu", strict=False)
    elif dev.status == "OFFLINE":
        transition(db, dev, "ACTIVE", "Có tín hiệu lại", strict=False)


def handle(topic: str, payload: bytes, retained: bool = False) -> None:
    stats["received"] += 1
    parts = topic.split("/")
    if len(parts) != 4 or parts[0] != "nursery":
        return
    _garden, code, kind = parts[1], parts[2], parts[3]
    if len(payload) > MAX_PAYLOAD:
        stats["invalid"] += 1
        log.warning("Bản tin quá lớn từ %s/%s (%d byte)", code, kind, len(payload))
        return
    try:
        body = json.loads(payload)
        if not isinstance(body, dict):
            raise ValueError("not an object")
    except ValueError:
        stats["invalid"] += 1
        log.warning("JSON lỗi từ %s/%s", code, kind)
        return

    with session_scope() as db:
        dev = db.scalar(select(Device).where(Device.device_code == code))
        if not dev or dev.status in REJECT_STATUSES:
            stats["rejected"] += 1
            log.warning("Bỏ bản tin của thiết bị không hợp lệ %s (%s)", code, dev.status if dev else "không tồn tại")
            return
        if body.get("device_id") not in (None, code):
            stats["rejected"] += 1
            audit(db, "SECURITY_TOPIC_MISMATCH", actor_label=code, target_type="device", target_id=dev.id,
                  detail={"topic": topic, "device_id": body.get("device_id")}, success=False)
            log.warning("device_id %s không khớp topic %s", body.get("device_id"), topic)
            return
        if kind == "telemetry":
            _telemetry(db, dev, body)
        elif kind == "status":
            _status(db, dev, body, retained)
        elif kind == "event":
            _event(db, dev, body)
        elif kind == "ack":
            _mark_seen(db, dev)
            for fn in _ack_handlers:
                fn(db, dev, body)


def _telemetry(db, dev: Device, b: dict) -> None:
    try:
        seq = int(b["seq"])
    except (KeyError, TypeError, ValueError):
        stats["invalid"] += 1
        return
    data = b.get("data")
    if not isinstance(data, dict):
        stats["invalid"] += 1
        return
    ts = _ts(b.get("ts"), bool(b.get("time_synced", True)))
    rows, out = [], {}
    for metric, m in data.items():
        if metric not in RANGES or not isinstance(m, dict):
            continue
        v, ok = m.get("v"), bool(m.get("ok", True))
        if v is not None:
            try:
                v = float(v)
            except (TypeError, ValueError):
                v, ok = None, False
        lo, hi = RANGES[metric]
        if v is not None and not lo <= v <= hi:
            ok = False  # ngoài miền: đánh dấu lỗi, vẫn lưu các đại lượng khác (§8.10 bước 5)
        rows.append({"device_id": dev.id, "seq": seq, "metric": metric, "value": v,
                     "unit": str(m.get("u", ""))[:8], "ok": ok, "ts": ts, "buffered": bool(b.get("buffered"))})
        out[metric] = {"v": v, "u": m.get("u"), "ok": ok}
    if rows:
        res = db.execute(insert(Telemetry).values(rows).on_conflict_do_nothing(
            index_elements=["device_id", "seq", "metric"]))
        stats["stored"] += res.rowcount or 0
    state = b.get("state") if isinstance(b.get("state"), dict) else {}
    latest_state[dev.id] = state
    _mark_seen(db, dev)
    alerts.on_telemetry(db, dev, out)
    realtime.publish(dev.id, {"type": "telemetry", "deviceId": dev.id, "ts": ts.isoformat(), "seq": seq,
                              "buffered": bool(b.get("buffered")), "data": out, "state": state})


def _status(db, dev: Device, b: dict, retained: bool) -> None:
    if b.get("online") is False:
        if dev.online:
            dev.online = False
            if dev.status == "ACTIVE":
                transition(db, dev, "OFFLINE", "Nhận LWT (mất kết nối)", strict=False)
            realtime.publish(dev.id, {"type": "device_status", "deviceId": dev.id, "status": dev.status,
                                      "online": False, "lastSeenAt": _iso(dev.last_seen_at)})
            alerts.on_offline(db, dev)
        return
    if isinstance(b.get("config_version"), int) and not retained:
        dev.current_config_version = max(dev.current_config_version or 0, b["config_version"])
    if b.get("fw"):
        dev.fw_version = str(b["fw"])[:30]
    if b.get("hw"):
        dev.hw_version = str(b["hw"])[:30]
    was_online = dev.online
    _mark_seen(db, dev, retained)
    if not was_online:
        realtime.publish(dev.id, {"type": "device_status", "deviceId": dev.id, "status": dev.status,
                                  "online": True, "lastSeenAt": _iso(dev.last_seen_at)})


def _event(db, dev: Device, b: dict) -> None:
    typ = str(b.get("type") or "")[:30]
    if not typ:
        stats["invalid"] += 1
        return
    detail = b.get("detail") if isinstance(b.get("detail"), dict) else {}
    seq = b.get("seq")
    ts = _ts(b.get("ts"))
    res = db.execute(insert(DeviceEvent).values(device_id=dev.id, seq=seq, type=typ, detail=detail, ts=ts)
                     .on_conflict_do_nothing(index_elements=["device_id", "seq"]))
    _mark_seen(db, dev)
    if res.rowcount:
        alerts.on_event(db, dev, typ, detail)
        realtime.publish(dev.id, {"type": "device_event", "deviceId": dev.id, "ts": ts.isoformat(),
                                  "eventType": typ, "detail": detail})


# ---------------------------------------------------------------------------

def _on_connect(cl, _u, _f, rc, _p=None):
    if getattr(rc, "is_failure", rc != 0):
        log.error("Backend không đăng nhập được broker: %s", rc)
        return
    cl.subscribe([(f"nursery/+/+/{k}", 1) for k in ("telemetry", "status", "event", "ack")])
    log.info("Bộ nhận MQTT đã kết nối broker %s:%s", settings.mqtt_host, settings.mqtt_port)


def _on_message(_c, _u, msg):
    try:
        handle(msg.topic, msg.payload, msg.retain)
    except Exception:  # noqa: BLE001 — một bản tin lỗi không được làm dừng bộ nhận
        log.exception("Lỗi xử lý bản tin %s", msg.topic)


def start() -> None:
    global _client
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"backend-ingest-{int(time.time())}",
                    protocol=mqtt.MQTTv311, clean_session=True)
    c.username_pw_set(settings.mqtt_backend_user, settings.mqtt_backend_password)
    c.on_connect, c.on_message = _on_connect, _on_message
    c.reconnect_delay_set(1, 30)
    c.connect_async(settings.mqtt_host, settings.mqtt_port, keepalive=30)
    c.loop_start()
    _client = c


def stop() -> None:
    if _client:
        _client.disconnect()
        _client.loop_stop()


def publish(topic: str, payload: dict, retain: bool = False) -> bool:
    """Backend gửi lệnh/cấu hình xuống thiết bị (QoS 1)."""
    if not _client or not _client.is_connected():
        return False
    return _client.publish(topic, json.dumps(payload, separators=(",", ":")), qos=1,
                           retain=retain).rc == mqtt.MQTT_ERR_SUCCESS


