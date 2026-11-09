"""Ghi audit log — chỉ INSERT (đặc tả §14.3)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from .models import AuditLog


def audit(db: Session, action: str, *, actor=None, actor_label: str | None = None, target_type: str | None = None,
          target_id=None, detail: dict | None = None, ip: str | None = None, success: bool = True) -> None:
    db.add(AuditLog(
        actor_id=getattr(actor, "id", None),
        actor_label=actor_label or getattr(actor, "username", None),
        action=action, target_type=target_type,
        target_id=None if target_id is None else str(target_id),
        detail=detail, ip=ip, success=success,
    ))
