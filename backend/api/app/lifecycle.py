"""Máy trạng thái vòng đời thiết bị (đặc tả §12.1)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from . import realtime
from .errors import ApiError
from .models import Device, DeviceStatusHistory

ALLOWED: dict[str, set[str]] = {
    "REGISTERED": {"PROVISIONED"},
    "PROVISIONED": {"ACTIVE", "SUSPENDED", "DECOMMISSIONED"},
    "ACTIVE": {"OFFLINE", "FAULT", "MAINTENANCE", "SUSPENDED", "DECOMMISSIONED"},
    "OFFLINE": {"ACTIVE", "MAINTENANCE", "SUSPENDED", "DECOMMISSIONED"},
    "FAULT": {"ACTIVE", "MAINTENANCE", "SUSPENDED", "DECOMMISSIONED"},
    "MAINTENANCE": {"ACTIVE", "OFFLINE", "SUSPENDED", "DECOMMISSIONED"},
    "SUSPENDED": {"PROVISIONED", "DECOMMISSIONED"},
    "DECOMMISSIONED": set(),
}


def can_transition(cur: str, new: str) -> bool:
    return new in ALLOWED.get(cur, set())


def transition(db: Session, dev: Device, new: str, reason: str, actor_id: int | None = None,
               strict: bool = True) -> bool:
    """Đổi trạng thái + ghi lịch sử + đẩy WebSocket. strict: sai luật thì 409, không thì bỏ qua."""
    cur = dev.status
    if cur == new:
        return False
    if not can_transition(cur, new):
        if strict:
            raise ApiError(409, "INVALID_STATE_TRANSITION", f"Không chuyển được từ {cur} sang {new}")
        return False
    dev.status = new
    db.add(DeviceStatusHistory(device_id=dev.id, from_status=cur, to_status=new, reason=reason[:200],
                               actor_id=actor_id))
    realtime.publish(dev.id, {"type": "device_status", "deviceId": dev.id, "status": new, "online": dev.online,
                              "lastSeenAt": dev.last_seen_at.isoformat() if dev.last_seen_at else None})
    return True
