"""HTTP cho thiết bị (đặc tả §8.9): Node 2 upload ảnh. Nằm ngoài /api/v1, không dùng JWT.

POST /device-api/v1/images
  Authorization: Basic base64(device_code:secret)   Content-Type: image/jpeg   Body: JPEG ≤ 300 KB
  X-Captured-At: epoch ms   X-Trigger: schedule|command   X-Cmd-Id: UUID (khi chụp theo lệnh)
→ 201 {"image_id":"img-<id>","diagnosis_id":"dg-<id>"}   (cùng một id: mỗi ảnh là một bản ghi diagnoses)
   400 không phải JPEG · 401 sai xác thực · 403 không phải CAMERA / bị khóa / thu hồi · 413 quá lớn · 429 > 1 ảnh/20 s

Thứ tự kiểm: Content-Length → xác thực → loại/trạng thái → tần suất → đọc body (giới hạn) → JPEG → lưu.
Lệnh capture có X-Cmd-Id hợp lệ (lệnh capture của chính thiết bị, phát trong 60 s, chưa dùng) được miễn giới hạn
tần suất, và ảnh đó không tính vào cửa sổ 20 s của ảnh chụp theo lịch.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import io
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from PIL import Image
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from .. import device_auth, diagnosis, ingest
from ..audit import audit
from ..config import settings
from ..db import SessionLocal
from ..errors import ApiError
from ..models import Command, Device, Diagnosis, Zone
from ..security import verify_password

router = APIRouter(prefix="/device-api/v1", tags=["device-api"])
log = logging.getLogger("device_api")
LOCAL_TZ = timezone(timedelta(hours=7))
RATE_WINDOW_S = 20
CMD_EXEMPT_S = 60
MAX_SKEW_S = 86400

_last_upload: dict[int, float] = {}        # device_id -> lúc nhận ảnh theo lịch gần nhất
_rate_lock = threading.Lock()


def _unauth(msg: str = "Sai thông tin xác thực thiết bị") -> ApiError:
    return ApiError(401, "UNAUTHORIZED", msg)


def _basic(header: str | None) -> tuple[str, str]:
    if not header or not header.lower().startswith("basic "):
        raise _unauth("Thiếu Authorization: Basic")
    try:
        raw = base64.b64decode(header[6:].strip(), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        raise _unauth("Authorization không hợp lệ")
    code, sep, secret = raw.partition(":")
    if not sep or not code or not secret or len(code) > 20 or len(secret) > 200:
        raise _unauth("Authorization không hợp lệ")
    return code, secret


def _authenticate(code: str, secret: str, ip: str | None) -> tuple[int, str]:
    """Trả về (device_id, device_code). bcrypt chỉ chạy khi cache trượt."""
    with SessionLocal() as db:
        dev = db.scalar(select(Device).where(Device.device_code == code))
        if not dev or not dev.credential_hash:
            raise _unauth()
        if not device_auth.cached(code, secret, dev.credential_hash):
            if not verify_password(secret, dev.credential_hash):
                log.warning("Upload ảnh: sai secret cho %s từ %s", code, ip)
                raise _unauth()
            device_auth.remember(code, secret, dev.id, dev.credential_hash)
        if dev.type != "CAMERA":
            raise ApiError(403, "FORBIDDEN", "Thiết bị không phải camera")
        if dev.status in ("SUSPENDED", "DECOMMISSIONED"):
            audit(db, "SECURITY_DEVICE_REJECTED", actor_label=code, target_type="device", target_id=dev.id,
                  detail={"channel": "http_upload", "status": dev.status}, ip=ip, success=False)
            db.commit()
            raise ApiError(403, "FORBIDDEN", f"Thiết bị đang {dev.status}")
        return dev.id, dev.device_code


def _cmd_exempt(device_id: int, cmd_id: str | None) -> bool:
    if not cmd_id:
        return False
    with SessionLocal() as db:
        cmd = db.get(Command, cmd_id)
        if not cmd or cmd.device_id != device_id or cmd.action != "capture":
            return False
        if datetime.now(timezone.utc) - cmd.issued_at > timedelta(seconds=CMD_EXEMPT_S):
            return False
        used = db.scalar(select(Diagnosis.id).where(Diagnosis.cmd_id == cmd_id).limit(1))
        return used is None


def _check_rate(device_id: int) -> None:
    with _rate_lock:
        last = _last_upload.get(device_id, 0.0)
        wait = RATE_WINDOW_S - (time.time() - last)
        if wait > 0:
            raise ApiError(429, "RATE_LIMITED", f"Tối đa 1 ảnh / {RATE_WINDOW_S} s", {"retryAfterS": int(wait) + 1})


def _captured_at(raw: str | None, code: str) -> datetime:
    now = datetime.now(timezone.utc)
    try:
        t = datetime.fromtimestamp(int(raw) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        log.info("Ảnh của %s: thiếu/sai X-Captured-At → dùng giờ server (captured_at_fallback)", code)
        return now
    if abs((t - now).total_seconds()) > MAX_SKEW_S:
        log.info("Ảnh của %s: X-Captured-At lệch > 24 h (%s) → dùng giờ server (captured_at_fallback)", code,
                 t.isoformat())
        return now
    return t


def _check_jpeg(body: bytes) -> None:
    if len(body) < 4 or body[:2] != b"\xff\xd8" or body.rstrip(b"\x00")[-2:] != b"\xff\xd9":
        raise ApiError(400, "VALIDATION_ERROR", "Không phải JPEG hợp lệ (thiếu FF D8 / FF D9)")
    try:
        with Image.open(io.BytesIO(body)) as im:
            if im.format != "JPEG":
                raise ValueError(im.format)
            im.verify()
    except Exception:  # noqa: BLE001
        raise ApiError(400, "VALIDATION_ERROR", "Không đọc được ảnh JPEG")


def _garden_of(db, dev: Device) -> int | None:
    z = db.get(Zone, dev.zone_id) if dev.zone_id else None
    return z.garden_id if z else None


def _lamp_state(db, cam: Device) -> bool | None:
    """Trạng thái đèn Node 1 cùng vườn lúc chụp (§6.11), lấy từ telemetry gần nhất (ingest.latest_state).
    Thiết bị chưa gán khu được coi là cùng vườn mặc định. Không có số liệu → None."""
    try:
        g = _garden_of(db, cam)
        ctrls = db.scalars(select(Device).where(Device.type == "CONTROLLER", Device.status != "DECOMMISSIONED")
                           .order_by(Device.last_seen_at.desc().nulls_last()))
        for c in ctrls:
            st = ingest.latest_state.get(c.id) or {}
            if "lamp" in st and _garden_of(db, c) == g:
                return bool(st["lamp"])
    except Exception:  # noqa: BLE001 — chỉ là dữ liệu phụ, không làm hỏng upload
        log.exception("Không lấy được trạng thái đèn")
    return None


def _store(device_id: int, code: str, body: bytes, captured: datetime, trigger: str, cmd_id: str | None,
           exempt: bool) -> int:
    """Ghi file tạm → sha256 → tạo diagnoses QUEUED → đổi tên file (atomic) → commit."""
    day = captured.astimezone(LOCAL_TZ).strftime("%Y-%m-%d")
    rel_dir = f"{code}/{day}"
    folder = settings.image_dir / code / day
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / f".upload-{uuid.uuid4().hex}.tmp"
    with open(tmp, "wb") as f:
        f.write(body)
        f.flush()
        os.fsync(f.fileno())
    sha = hashlib.sha256(body).hexdigest()
    final = None
    try:
        with SessionLocal() as db:
            dev = db.get(Device, device_id)
            if exempt and cmd_id:
                trigger = "command"
            d = Diagnosis(device_id=device_id, image_path=f"{rel_dir}/pending", image_sha256=sha, captured_at=captured,
                          trigger=trigger, cmd_id=cmd_id, status="QUEUED", lamp_on=_lamp_state(db, dev))
            db.add(d)
            db.flush()
            final = folder / f"{d.id}.jpg"
            os.replace(tmp, final)
            d.image_path = f"{rel_dir}/{d.id}.jpg"
            ingest.mark_seen(db, dev)   # last_seen_at; PROVISIONED/OFFLINE → ACTIVE (như ingest)
            db.commit()
            return d.id
    except Exception:
        for p in (tmp, final):
            if p is not None and p.exists():
                p.unlink(missing_ok=True)
        raise


@router.post("/images", status_code=201)
async def upload_image(request: Request):
    ip = request.client.host if request.client else None
    limit = settings.max_image_bytes
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > limit:
        raise ApiError(413, "PAYLOAD_TOO_LARGE", f"Ảnh tối đa {limit // 1024} KB")

    code, secret = _basic(request.headers.get("authorization"))
    device_id, code = await run_in_threadpool(_authenticate, code, secret, ip)

    cmd_id = request.headers.get("x-cmd-id") or None
    if cmd_id:
        try:
            cmd_id = str(uuid.UUID(cmd_id))
        except ValueError:
            log.info("Ảnh của %s: X-Cmd-Id không phải UUID, bỏ qua", code)
            cmd_id = None
    exempt = await run_in_threadpool(_cmd_exempt, device_id, cmd_id)
    if not exempt:
        _check_rate(device_id)

    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > limit:
            raise ApiError(413, "PAYLOAD_TOO_LARGE", f"Ảnh tối đa {limit // 1024} KB")
    body = bytes(body)
    _check_jpeg(body)

    trigger = (request.headers.get("x-trigger") or "").strip().lower()
    if trigger not in ("schedule", "command"):
        trigger = "command" if cmd_id else "schedule"
    captured = _captured_at(request.headers.get("x-captured-at"), code)
    if not exempt:
        with _rate_lock:   # kiểm lại ngay trước khi ghi để hai request đồng thời không cùng lọt
            if time.time() - _last_upload.get(device_id, 0.0) < RATE_WINDOW_S:
                raise ApiError(429, "RATE_LIMITED", f"Tối đa 1 ảnh / {RATE_WINDOW_S} s")
            _last_upload[device_id] = time.time()
    try:
        did = await run_in_threadpool(_store, device_id, code, body, captured, trigger, cmd_id, exempt)
    except Exception:
        if not exempt:
            with _rate_lock:
                _last_upload.pop(device_id, None)
        raise
    log.info("Nhận ảnh %s từ %s (%d byte, trigger=%s%s)", did, code, len(body), trigger,
             f", cmd {cmd_id}" if cmd_id else "")
    diagnosis.wake()
    return JSONResponse({"image_id": f"img-{did}", "diagnosis_id": f"dg-{did}"}, status_code=201)
