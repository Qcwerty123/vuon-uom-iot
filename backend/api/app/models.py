"""Ánh xạ ORM cho các bảng đã có trong database/init/01_schema.sql (đặc tả §11.2).
Schema do file SQL tạo; ORM không tự tạo bảng."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ENUM, INET, JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def pg_enum(name: str, *values: str) -> ENUM:
    return ENUM(*values, name=name, create_type=False)


UserRole = pg_enum("user_role", "ADMIN", "OPERATOR", "VIEWER")
UserStatus = pg_enum("user_status", "PENDING", "ACTIVE", "LOCKED")
DeviceType = pg_enum("device_type", "CONTROLLER", "CAMERA")
DeviceStatus = pg_enum("device_status", "REGISTERED", "PROVISIONED", "ACTIVE", "OFFLINE", "FAULT",
                       "MAINTENANCE", "SUSPENDED", "DECOMMISSIONED")
AssignPerm = pg_enum("assign_perm", "VIEW", "CONTROL")
CmdStatus = pg_enum("cmd_status", "PENDING", "EXECUTED", "REJECTED", "FAILED", "TIMEOUT")
CfgStatus = pg_enum("cfg_status", "PENDING", "APPLIED", "REJECTED")
TS = TIMESTAMP(timezone=True)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    email: Mapped[str | None] = mapped_column(String(120))
    full_name: Mapped[str | None] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(UserRole, default="VIEWER")
    status: Mapped[str] = mapped_column(UserStatus, default="ACTIVE")
    telegram_chat_id: Mapped[str | None] = mapped_column(String(40))
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(TS)
    created_at: Mapped[datetime] = mapped_column(TS, server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(TS, server_default="now()")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(TS)
    revoked_at: Mapped[datetime | None] = mapped_column(TS)
    created_at: Mapped[datetime] = mapped_column(TS, server_default="now()")
    user_agent: Mapped[str | None] = mapped_column(String(200))
    ip: Mapped[str | None] = mapped_column(INET)


class Garden(Base):
    __tablename__ = "gardens"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    address: Mapped[str | None] = mapped_column(String(200))


class Zone(Base):
    __tablename__ = "zones"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    garden_id: Mapped[int] = mapped_column(ForeignKey("gardens.id"))
    name: Mapped[str] = mapped_column(String(120))
    crop_type: Mapped[str | None] = mapped_column(String(60))


class Device(Base):
    __tablename__ = "devices"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    device_code: Mapped[str] = mapped_column(String(20), unique=True)
    type: Mapped[str] = mapped_column(DeviceType)
    name: Mapped[str] = mapped_column(String(120))
    zone_id: Mapped[int | None] = mapped_column(ForeignKey("zones.id"))
    status: Mapped[str] = mapped_column(DeviceStatus, default="REGISTERED")
    online: Mapped[bool] = mapped_column(Boolean, default=False)
    credential_hash: Mapped[str | None] = mapped_column(String(100))
    hw_version: Mapped[str | None] = mapped_column(String(30))
    fw_version: Mapped[str | None] = mapped_column(String(30))
    last_seen_at: Mapped[datetime | None] = mapped_column(TS)
    first_seen_at: Mapped[datetime | None] = mapped_column(TS)
    current_config_version: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TS, server_default="now()")
    decommissioned_at: Mapped[datetime | None] = mapped_column(TS)


class DeviceAssignment(Base):
    __tablename__ = "device_assignments"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), primary_key=True)
    permission: Mapped[str] = mapped_column(AssignPerm, default="VIEW")
    assigned_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    assigned_at: Mapped[datetime] = mapped_column(TS, server_default="now()")


class DeviceStatusHistory(Base):
    __tablename__ = "device_status_history"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"))
    from_status: Mapped[str | None] = mapped_column(DeviceStatus)
    to_status: Mapped[str] = mapped_column(DeviceStatus)
    reason: Mapped[str | None] = mapped_column(String(200))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    at: Mapped[datetime] = mapped_column(TS, server_default="now()")


class DeviceConfig(Base):
    __tablename__ = "device_configs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"))
    config_version: Mapped[int] = mapped_column(Integer)
    params: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(CfgStatus, default="PENDING")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(TS, server_default="now()")
    applied_at: Mapped[datetime | None] = mapped_column(TS)
    reject_detail: Mapped[dict | None] = mapped_column(JSONB)


class Command(Base):
    __tablename__ = "commands"
    cmd_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"))
    action: Mapped[str] = mapped_column(String(30))
    params: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(CmdStatus, default="PENDING")
    result: Mapped[str | None] = mapped_column(String(40))
    detail: Mapped[dict | None] = mapped_column(JSONB)
    issued_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    issued_at: Mapped[datetime] = mapped_column(TS, server_default="now()")
    ack_at: Mapped[datetime | None] = mapped_column(TS)


class Telemetry(Base):
    __tablename__ = "telemetry"
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), primary_key=True)
    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    metric: Mapped[str] = mapped_column(String(20), primary_key=True)
    value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(8))
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    ts: Mapped[datetime] = mapped_column(TS)
    received_at: Mapped[datetime] = mapped_column(TS, server_default="now()")
    buffered: Mapped[bool] = mapped_column(Boolean, default=False)


class DeviceEvent(Base):
    __tablename__ = "device_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"))
    seq: Mapped[int | None] = mapped_column(BigInteger)
    type: Mapped[str] = mapped_column(String(30))
    detail: Mapped[dict | None] = mapped_column(JSONB)
    ts: Mapped[datetime] = mapped_column(TS)
    received_at: Mapped[datetime] = mapped_column(TS, server_default="now()")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    actor_label: Mapped[str | None] = mapped_column(String(60))
    action: Mapped[str] = mapped_column(String(40))
    target_type: Mapped[str | None] = mapped_column(String(20))
    target_id: Mapped[str | None] = mapped_column(String(40))
    detail: Mapped[dict | None] = mapped_column(JSONB)
    ip: Mapped[str | None] = mapped_column(INET)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    at: Mapped[datetime] = mapped_column(TS, server_default="now()")


AlertSev = pg_enum("alert_sev", "INFO", "WARNING", "CRITICAL")
AlertStatus = pg_enum("alert_status", "OPEN", "ACKNOWLEDGED", "CLOSED")


class AlertRule(Base):
    __tablename__ = "alert_rules"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    type: Mapped[str] = mapped_column(String(20))
    scope_zone_id: Mapped[int | None] = mapped_column(ForeignKey("zones.id"))
    scope_device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id"))
    metric: Mapped[str | None] = mapped_column(String(20))
    operator: Mapped[str | None] = mapped_column(String(2))
    threshold: Mapped[float | None] = mapped_column(Float)
    hysteresis: Mapped[float | None] = mapped_column(Float, default=0)
    duration_s: Mapped[int] = mapped_column(Integer, default=0)
    event_type: Mapped[str | None] = mapped_column(String(30))
    severity: Mapped[str] = mapped_column(AlertSev, default="WARNING")
    cooldown_min: Mapped[int] = mapped_column(Integer, default=30)
    notify_telegram: Mapped[bool] = mapped_column(Boolean, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(TS, server_default="now()")


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("alert_rules.id"))
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"))
    type: Mapped[str] = mapped_column(String(20))
    severity: Mapped[str] = mapped_column(AlertSev)
    message: Mapped[str] = mapped_column(String(300))
    context: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(AlertStatus, default="OPEN")
    opened_at: Mapped[datetime] = mapped_column(TS, server_default="now()")
    condition_cleared_at: Mapped[datetime | None] = mapped_column(TS)
    ack_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    ack_at: Mapped[datetime | None] = mapped_column(TS)
    closed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    closed_at: Mapped[datetime | None] = mapped_column(TS)
    close_note: Mapped[str | None] = mapped_column(String(300))
    notified_at: Mapped[datetime | None] = mapped_column(TS)


DiagStatus = pg_enum("diag_status", "QUEUED", "RUNNING", "DONE", "FAILED")


class Diagnosis(Base):
    """Một ảnh Node 2 + kết quả AI (đặc tả §11.2, §12.4). image_path tương đối theo IMAGE_DIR, không public."""
    __tablename__ = "diagnoses"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"))
    image_path: Mapped[str] = mapped_column(String(200))
    image_sha256: Mapped[str] = mapped_column(String(64))
    captured_at: Mapped[datetime] = mapped_column(TS)
    trigger: Mapped[str] = mapped_column(String(10))
    cmd_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False))
    lamp_on: Mapped[bool | None] = mapped_column(Boolean)   # đèn Node 1 cùng vườn lúc chụp (§6.11)
    status: Mapped[str] = mapped_column(DiagStatus, default="QUEUED")
    model_version: Mapped[str | None] = mapped_column(String(30))
    tiles: Mapped[list | None] = mapped_column(JSONB)
    top_label: Mapped[str | None] = mapped_column(String(20))
    top_confidence: Mapped[float | None] = mapped_column(Float)
    abnormal_tiles: Mapped[list | None] = mapped_column(JSONB)
    review_verdict: Mapped[str | None] = mapped_column(String(10))
    correct_label: Mapped[str | None] = mapped_column(String(20))
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(TS)
    created_at: Mapped[datetime] = mapped_column(TS, server_default="now()")
