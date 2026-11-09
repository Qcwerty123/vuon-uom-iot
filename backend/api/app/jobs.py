"""Tác vụ nền (đặc tả §9.1): OfflineDetector, CommandTimeout, ConfigRetry, FaultDetector, HourlyRollup."""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text

from . import alerts, commands, realtime
from .db import session_scope
from .lifecycle import transition
from .models import Device

log = logging.getLogger("jobs")
OFFLINE_AFTER_S = 90
FAULT_AFTER_MIN = 5
_stop = threading.Event()


def offline_detector() -> None:
    limit = datetime.now(timezone.utc) - timedelta(seconds=OFFLINE_AFTER_S)
    with session_scope() as db:
        devs = db.scalars(select(Device).where(Device.online.is_(True),
                                               Device.status.in_(("ACTIVE", "FAULT", "MAINTENANCE", "PROVISIONED")),
                                               Device.last_seen_at < limit))
        for dev in devs:
            mark_offline(db, dev, f"Mất tín hiệu > {OFFLINE_AFTER_S} s")


def mark_offline(db, dev: Device, reason: str) -> None:
    """Dùng chung cho LWT (ingest) và OfflineDetector."""
    dev.online = False
    if dev.status == "ACTIVE":
        transition(db, dev, "OFFLINE", reason, strict=False)
    realtime.publish(dev.id, {"type": "device_status", "deviceId": dev.id, "status": dev.status, "online": False,
                              "lastSeenAt": dev.last_seen_at.isoformat() if dev.last_seen_at else None})
    alerts.on_offline(db, dev)


def fault_detector() -> None:
    """sensor_fault kéo dài > 5 phút chưa có sensor_ok → ACTIVE chuyển FAULT; hết lỗi → ACTIVE."""
    with session_scope() as db:
        for dev in db.scalars(select(Device).where(Device.status.in_(("ACTIVE", "FAULT")))):
            rows = db.execute(text(
                "SELECT DISTINCT ON (detail->>'sensor') type, ts FROM device_events "
                "WHERE device_id = :d AND type IN ('sensor_fault','sensor_ok') AND ts > now() - interval '1 day' "
                "ORDER BY detail->>'sensor', ts DESC"), {"d": dev.id}).all()
            limit = datetime.now(timezone.utc) - timedelta(minutes=FAULT_AFTER_MIN)
            faulty = [r for r in rows if r.type == "sensor_fault" and r.ts < limit]
            if faulty and dev.status == "ACTIVE":
                transition(db, dev, "FAULT", f"Cảm biến lỗi kéo dài > {FAULT_AFTER_MIN} phút", strict=False)
            elif not any(r.type == "sensor_fault" for r in rows) and dev.status == "FAULT":
                transition(db, dev, "ACTIVE", "Cảm biến hoạt động lại", strict=False)


def hourly_rollup() -> None:
    with session_scope() as db:
        db.execute(text(
            "INSERT INTO telemetry_hourly (device_id, metric, hour, min, max, avg, count) "
            "SELECT device_id, metric, date_trunc('hour', ts), min(value), max(value), avg(value), count(*) "
            "FROM telemetry WHERE ok AND ts >= date_trunc('hour', now()) - interval '2 hours' "
            "AND ts < date_trunc('hour', now()) GROUP BY 1, 2, 3 "
            "ON CONFLICT (device_id, metric, hour) DO UPDATE SET min = EXCLUDED.min, max = EXCLUDED.max, "
            "avg = EXCLUDED.avg, count = EXCLUDED.count"))


TASKS = [  # (tên, chu kỳ giây, hàm)
    ("CommandTimeout", 2, lambda: _with_db(commands.timeout_pending)),
    ("OfflineDetector", 15, offline_detector),
    ("ConfigRetry", 30, lambda: _with_db(commands.retry_configs)),
    ("FaultDetector", 60, fault_detector),
    ("HourlyRollup", 600, hourly_rollup),
]


def _with_db(fn) -> None:
    with session_scope() as db:
        fn(db)


def _run() -> None:
    nxt = {name: time.time() + 5 for name, _, _ in TASKS}
    while not _stop.is_set():
        now = time.time()
        for name, period, fn in TASKS:
            if now >= nxt[name]:
                nxt[name] = now + period
                try:
                    fn()
                except Exception:  # noqa: BLE001 — một tác vụ lỗi không làm dừng các tác vụ khác
                    log.exception("Tác vụ %s lỗi", name)
        _stop.wait(0.5)


def start() -> None:
    threading.Thread(target=_run, name="jobs", daemon=True).start()


def stop() -> None:
    _stop.set()
