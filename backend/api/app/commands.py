"""Lệnh điều khiển (đặc tả §3.3 UC05, §8.6, §12.2) và cấu hình thiết bị (§8.7, §9.3, §12.5)."""
from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import ingest, realtime
from .errors import ApiError
from .models import Command, Device, DeviceConfig, Garden, User, Zone

log = logging.getLogger("commands")

COMMAND_TTL_S = 10
TIMEOUT_S = 10
RATE_PER_MIN = 10
ONLINE_STATUSES = {"ACTIVE", "FAULT", "MAINTENANCE"}
RESULT_STATUS = {"executed": "EXECUTED", "duration_capped": "EXECUTED", "failed": "FAILED"}
REJECT_RESULTS = {"blocked_no_water", "blocked_cooldown", "blocked_sensor_fault", "blocked_local", "blocked_overheat",
                  "invalid",
                  "expired", "unsupported"}


def _utc() -> datetime:
    return datetime.now(timezone.utc)


def topic(db: Session, dev: Device, kind: str) -> str:
    garden = "g01"
    if dev.zone_id:
        z = db.get(Zone, dev.zone_id)
        g = db.get(Garden, z.garden_id) if z else None
        garden = g.code if g else garden
    return f"nursery/{garden}/{dev.device_code}/{kind}"


# ---------------------------------------------------------------------------
# Kiểm tra lệnh theo loại thiết bị
# ---------------------------------------------------------------------------

def validate_action(dev_type: str, action: str, params: dict) -> dict:
    def bad(field: str, msg: str):
        raise ApiError(400, "VALIDATION_ERROR", msg, {"field": field})

    common = {"reboot", "request_status"}
    if dev_type == "CONTROLLER":
        if action == "pump_on":
            d = params.get("duration_s")
            if not isinstance(d, int) or isinstance(d, bool) or not 1 <= d <= 60:
                bad("params.duration_s", "duration_s phải là số nguyên 1–60")
            return {"duration_s": d}
        if action in ("pump_off", "fan_on", "fan_off", "lamp_off") or action in common:
            return {}
        if action == "lamp_on":  # §6.11: duration_min tùy chọn, 1–lamp_override_min (tối đa 240)
            d = params.get("duration_min")
            if d is None:
                return {}
            if not isinstance(d, int) or isinstance(d, bool) or not 1 <= d <= 240:
                bad("params.duration_min", "duration_min phải là số nguyên 1–240")
            return {"duration_min": d}
        if action == "set_mode":
            if params.get("mode") not in ("AUTO", "MANUAL"):
                bad("params.mode", "mode phải là AUTO hoặc MANUAL")
            return {"mode": params["mode"]}
    elif dev_type == "CAMERA":
        if action == "capture":
            f = params.get("flash")
            if f not in (None, "on", "off"):
                bad("params.flash", "flash phải là on/off")
            return {"flash": f} if f else {}
        if action == "flash":
            if params.get("state") not in ("on", "off"):
                bad("params.state", "state phải là on/off")
            d = params.get("duration_s", 5)
            if not isinstance(d, int) or not 1 <= d <= 10:
                bad("params.duration_s", "duration_s phải là 1–10")
            return {"state": params["state"], "duration_s": d}
        if action in common:
            return {}
    bad("action", f"Lệnh '{action}' không hợp lệ với thiết bị {dev_type}")
    return {}


_rate: dict[int, deque] = defaultdict(deque)
_rate_lock = threading.Lock()


def _check_rate(device_id: int) -> None:
    now = time.time()
    with _rate_lock:
        q = _rate[device_id]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= RATE_PER_MIN:
            raise ApiError(429, "RATE_LIMITED", f"Tối đa {RATE_PER_MIN} lệnh/phút cho mỗi thiết bị")
        q.append(now)


def send_command(db: Session, dev: Device, user: User, action: str, params: dict) -> Command:
    if not dev.online or dev.status == "OFFLINE":
        raise ApiError(409, "DEVICE_OFFLINE", "Thiết bị đang offline")
    if dev.status not in ONLINE_STATUSES:
        raise ApiError(409, "INVALID_STATE", f"Thiết bị đang {dev.status}, không nhận lệnh")
    clean = validate_action(dev.type, action, params or {})
    _check_rate(dev.id)
    cmd = Command(cmd_id=str(uuid.uuid4()), device_id=dev.id, action=action, params=clean, status="PENDING",
                  issued_by=user.id, issued_at=_utc())
    db.add(cmd)
    db.flush()
    return cmd


def dispatch_command(db: Session, dev: Device, cmd: Command) -> None:
    """Gọi SAU khi đã commit bản ghi lệnh: thiết bị có thể ack chỉ sau vài ms, bộ nhận ack phải thấy được lệnh."""
    payload = {"cmd_id": cmd.cmd_id, "action": cmd.action, "params": cmd.params or {},
               "issued_at": int(cmd.issued_at.timestamp() * 1000), "ttl_s": COMMAND_TTL_S,
               "issued_by": f"u-{cmd.issued_by}"}
    if not ingest.publish(topic(db, dev, "command"), payload):
        cmd.status, cmd.result = "FAILED", "broker_unavailable"
        db.commit()
        raise ApiError(503, "BROKER_UNAVAILABLE", "Backend chưa kết nối broker, thử lại sau")


def command_out(c: Command) -> dict:
    return {"cmdId": c.cmd_id, "deviceId": c.device_id, "action": c.action, "params": c.params, "status": c.status,
            "result": c.result, "detail": c.detail, "issuedBy": c.issued_by, "issuedAt": c.issued_at, "ackAt": c.ack_at}


def _push_cmd(c: Command) -> None:
    realtime.publish(c.device_id, {"type": "command_update", **{k: v for k, v in command_out(c).items()
                                                                if k in ("cmdId", "deviceId", "status", "result",
                                                                         "detail", "action")}})


# ---------------------------------------------------------------------------
# Cấu hình
# ---------------------------------------------------------------------------

CFG_RANGES = {"soil_low": (0, 100), "soil_high": (0, 100), "pump_max_s": (1, 60), "cooldown_s": (0, 3600),
              "tank_min": (0, 100), "temp_high": (-10, 60), "temp_hyst": (0.5, 10), "hum_high": (0, 100),
              "hum_hyst": (1, 20), "telemetry_interval_s": (2, 300), "capture_interval_min": (1, 1440),
              "jpeg_quality": (8, 30), "warmup_frames": (0, 5),
              # Chiếu sáng bổ sung Node 1 (§6.11)
              "lamp_start_hour": (0, 23), "lamp_end_hour": (1, 24), "lamp_lux_low": (0, 65535),
              "lamp_hyst": (1, 65535), "lamp_self_lux": (0, 5000), "lamp_hold_s": (2, 600),
              "lamp_min_on_s": (10, 3600), "lamp_min_off_s": (10, 3600), "lamp_override_min": (1, 240)}
LAMP_DEFAULTS = {"lamp_start_hour": 6, "lamp_end_hour": 20, "lamp_lux_low": 800, "lamp_hyst": 700,
                 "lamp_self_lux": 300, "lamp_hold_s": 10, "lamp_min_on_s": 30, "lamp_min_off_s": 30,
                 "lamp_override_min": 60}
CFG_INT = {"pump_max_s", "cooldown_s", "telemetry_interval_s", "capture_interval_min", "jpeg_quality",
           "warmup_frames", *LAMP_DEFAULTS}
FRAME_SIZES = ("VGA", "SVGA", "XGA", "HD", "SXGA", "UXGA")  # firmware Node 2 (config_store.cpp)
DEFAULTS = {"soil_low": 35, "soil_high": 55, "pump_max_s": 15, "cooldown_s": 120, "tank_min": 15, "temp_high": 32,
            "temp_hyst": 2, "hum_high": 90, "hum_hyst": 5, "telemetry_interval_s": 10, "manual_ignores_cooldown": False,
            **LAMP_DEFAULTS}


def validate_config(params: dict, base: dict) -> dict:
    def bad(field: str, msg: str):
        raise ApiError(400, "VALIDATION_ERROR", msg, {"field": field})

    out = dict(base)
    for k, v in params.items():
        if k in CFG_RANGES:
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                bad(k, f"{k} phải là số")
            lo, hi = CFG_RANGES[k]
            if not lo <= v <= hi:
                bad(k, f"{k} phải trong khoảng {lo}–{hi}")
            if k in CFG_INT and int(v) != v:
                bad(k, f"{k} phải là số nguyên")
            out[k] = int(v) if k in CFG_INT else v
        elif k == "manual_ignores_cooldown":
            if not isinstance(v, bool):
                bad(k, "manual_ignores_cooldown phải là true/false")
            out[k] = v
        elif k == "soil_cal":
            if not isinstance(v, dict):
                bad(k, "soil_cal không hợp lệ")
            for s in ("s1", "s2"):
                c = v.get(s)
                if c is None:
                    continue
                if not (isinstance(c, dict) and isinstance(c.get("dry"), int) and isinstance(c.get("wet"), int)
                        and 0 <= c["wet"] <= 4095 and 0 <= c["dry"] <= 4095 and c["dry"] - c["wet"] >= 200):
                    bad(f"soil_cal.{s}", "dry/wet là ADC 0–4095, dry lớn hơn wet ít nhất 200")
            out[k] = {**base.get(k, {}), **v}
        elif k == "tank_cal":
            if not (isinstance(v, dict) and all(isinstance(v.get(x), (int, float)) for x in ("empty_cm", "full_cm"))
                    and 2 <= v["full_cm"] <= 400 and 2 <= v["empty_cm"] <= 400 and v["empty_cm"] - v["full_cm"] >= 2):
                bad(k, "tank_cal cần empty_cm, full_cm (2–400 cm), empty lớn hơn full ít nhất 2")
            out[k] = v
        elif k == "frame_size":
            if v not in FRAME_SIZES:
                bad(k, f"frame_size phải thuộc {', '.join(FRAME_SIZES)}")
            out[k] = v
        elif k == "flash":
            if v not in ("on", "off", "auto"):
                bad(k, "flash phải là on/off/auto")
            out[k] = v
        elif k == "crop_box":  # camera: vùng khay [x0, y0, x1, y1] (pixel, hoặc tỉ lệ 0..1) — §15.4
            if v is not None and not (isinstance(v, list) and len(v) == 4
                                      and all(isinstance(t, (int, float)) and not isinstance(t, bool) and t >= 0
                                              for t in v) and v[2] > v[0] and v[3] > v[1]):
                bad(k, "crop_box phải là [x0, y0, x1, y1] với x1 > x0, y1 > y0")
            out[k] = v
        elif k == "active_tiles":  # camera: các ô có cây [[r, c], ...] — §15.6
            if v is not None and not (isinstance(v, list) and all(
                    isinstance(t, list) and len(t) == 2 and all(isinstance(x, int) and 0 <= x <= 2 for x in t)
                    for t in v)):
                bad(k, "active_tiles phải là [[r, c], ...] với r, c trong 0..2")
            out[k] = v
        else:
            bad(k, f"Khóa cấu hình '{k}' không được hỗ trợ")
    if out.get("soil_low", 0) >= out.get("soil_high", 100):
        bad("soil_low", "soil_low phải nhỏ hơn soil_high")
    if any(k in out for k in LAMP_DEFAULTS):  # ràng buộc chéo §6.11, giống firmware Node 1
        lv = {k: out.get(k, d) for k, d in LAMP_DEFAULTS.items()}
        if lv["lamp_end_hour"] <= lv["lamp_start_hour"]:
            bad("lamp_end_hour", "lamp_end_hour phải lớn hơn lamp_start_hour")
        if lv["lamp_hyst"] <= lv["lamp_self_lux"] + 200:
            bad("lamp_hyst", "lamp_hyst phải lớn hơn lamp_self_lux + 200 (tránh đèn tự bật/tắt liên tục)")
    return out


def current_params(db: Session, dev: Device) -> dict:
    last = db.scalar(select(DeviceConfig).where(DeviceConfig.device_id == dev.id, DeviceConfig.status != "REJECTED")
                     .order_by(DeviceConfig.config_version.desc()).limit(1))
    if last:
        return dict(last.params)
    return dict(DEFAULTS) if dev.type == "CONTROLLER" else {}


def next_version(db: Session, dev: Device) -> int:
    """Quy tắc §9.3: lớn hơn cả bản trong CSDL lẫn bản thiết bị đang báo (tránh bị bỏ qua sau khi reset CSDL)."""
    db_max = db.scalar(select(func.max(DeviceConfig.config_version)).where(DeviceConfig.device_id == dev.id)) or 0
    return max(db_max, dev.current_config_version or 0) + 1


def publish_config(db: Session, dev: Device, cfg: DeviceConfig) -> bool:
    payload = {"config_version": cfg.config_version, "issued_at": int(time.time() * 1000), "params": cfg.params}
    ok = ingest.publish(topic(db, dev, "config"), payload, retain=True)
    _cfg_sent[cfg.id] = time.time()
    return ok


_cfg_sent: dict[int, float] = {}


def put_config(db: Session, dev: Device, user: User, params: dict) -> DeviceConfig:
    if dev.status in ("REGISTERED", "SUSPENDED", "DECOMMISSIONED"):
        raise ApiError(409, "INVALID_STATE", f"Thiết bị đang {dev.status}")
    merged = validate_config(params or {}, current_params(db, dev))
    cfg = DeviceConfig(device_id=dev.id, config_version=next_version(db, dev), params=merged, status="PENDING",
                       created_by=user.id)
    db.add(cfg)
    db.flush()
    return cfg


def dispatch_config(db: Session, dev: Device, cfg: DeviceConfig) -> None:
    """Gọi SAU khi commit (lý do như dispatch_command). Broker lỗi thì ConfigRetry gửi lại sau."""
    if not publish_config(db, dev, cfg):
        raise ApiError(503, "BROKER_UNAVAILABLE", "Đã lưu cấu hình nhưng chưa gửi được tới broker; hệ thống sẽ thử lại")


def config_out(c: DeviceConfig) -> dict:
    return {"id": c.id, "deviceId": c.device_id, "configVersion": c.config_version, "params": c.params,
            "status": c.status, "createdBy": c.created_by, "createdAt": c.created_at, "appliedAt": c.applied_at,
            "rejectDetail": c.reject_detail}


# ---------------------------------------------------------------------------
# Ack từ thiết bị (gọi trong luồng ingest)
# ---------------------------------------------------------------------------

def on_ack(db: Session, dev: Device, b: dict) -> None:
    cid, kind, result = str(b.get("cmd_id") or ""), b.get("kind"), str(b.get("result") or "")
    detail = b.get("detail") if isinstance(b.get("detail"), dict) else {}
    if kind == "config" or cid.startswith("cfg-"):
        try:
            ver = int(cid[4:])
        except ValueError:
            return
        cfg = db.scalar(select(DeviceConfig).where(DeviceConfig.device_id == dev.id, DeviceConfig.config_version == ver))
        if not cfg:
            return
        if result == "executed":
            if cfg.status != "APPLIED":
                cfg.status, cfg.applied_at = "APPLIED", _utc()
            dev.current_config_version = max(dev.current_config_version or 0, ver)
        else:
            cfg.status, cfg.reject_detail = "REJECTED", {"result": result, **detail}
        _cfg_sent.pop(cfg.id, None)
        realtime.publish(dev.id, {"type": "config_update", "deviceId": dev.id, "configVersion": ver,
                                  "status": cfg.status, "detail": cfg.reject_detail})
        return
    try:
        uuid.UUID(cid)
    except ValueError:
        return  # lệnh gửi tay (không qua backend)
    cmd = db.get(Command, cid)
    if not cmd or cmd.device_id != dev.id:
        return
    if cmd.status != "PENDING":
        cmd.detail = {**(cmd.detail or {}), "late_ack": result}
        return
    cmd.status = RESULT_STATUS.get(result, "REJECTED" if result in REJECT_RESULTS else "FAILED")
    if cmd.action == "capture" and result == "executed":
        # §7.4: ack executed {image_id:"img-<id>"} → lưu cả diagnosis_id dạng số để web mở thẳng bản ghi
        img = str(detail.get("image_id") or "")
        if img.startswith("img-") and img[4:].isdigit():
            detail = {**detail, "diagnosis_id": int(img[4:])}
    cmd.result, cmd.detail, cmd.ack_at = result[:40], detail, _utc()
    _push_cmd(cmd)


ingest.on_ack(on_ack)


# ---------------------------------------------------------------------------
# Tác vụ nền (jobs.py gọi)
# ---------------------------------------------------------------------------

def timeout_pending(db: Session) -> None:
    limit = _utc() - timedelta(seconds=TIMEOUT_S)
    for c in db.scalars(select(Command).where(Command.status == "PENDING", Command.issued_at < limit)):
        c.status, c.result = "TIMEOUT", None
        _push_cmd(c)


def retry_configs(db: Session) -> None:
    """Cấu hình chưa có ack sau 60 s mà thiết bị đang online → gửi lại (§9.1 ConfigRetry)."""
    now = time.time()
    pend = db.scalars(select(DeviceConfig).where(DeviceConfig.status == "PENDING")).all()
    for cfg in pend:
        newer = db.scalar(select(func.max(DeviceConfig.config_version)).where(DeviceConfig.device_id == cfg.device_id))
        if newer and newer > cfg.config_version:
            continue  # đã có bản mới hơn
        if now - _cfg_sent.get(cfg.id, 0) < 60:
            continue
        dev = db.get(Device, cfg.device_id)
        if dev and dev.online:
            log.info("Gửi lại cấu hình v%s cho %s", cfg.config_version, dev.device_code)
            publish_config(db, dev, cfg)
