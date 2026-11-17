"""Ảnh và chẩn đoán (đặc tả §10.9). Ảnh chỉ trả qua API có kiểm quyền mỗi lần, không có URL tĩnh công khai.

API web dùng id số nguyên (diagnoses.id); tiền tố img-/dg- chỉ dùng trong phản hồi cho thiết bị (§8.9).
"""
from __future__ import annotations

import io
import threading
import time
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from PIL import Image, ImageOps
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .. import diagnosis
from ..audit import audit
from ..config import settings
from ..db import get_db
from ..deps import client_ip, current_user, device_for_view, permission_of
from ..errors import ApiError, forbidden, not_found
from ..models import Diagnosis, User
from ..schemas import Api
from .device_api import _store

router = APIRouter(tags=["diagnoses"])
LABELS = ("HEALTHY", "YELLOW", "SPOT", "UNKNOWN")

# Tải ảnh lên để thử AI (trigger = 'test'): không tạo cảnh báo, không tính vào "chẩn đoán mới nhất" của dashboard.
TEST_MAX_BYTES = 12 * 1024 * 1024   # ảnh gốc người dùng chọn (điện thoại thường 2–6 MB)
TEST_MAX_SIDE = 1600                # thu nhỏ trước khi lưu: đủ cho AI (cạnh dài 800) và để xem ảnh
TEST_GAP_S = 3
_test_last: dict[int, float] = {}
_test_lock = threading.Lock()


class ReviewIn(Api):
    verdict: Literal["CONFIRMED", "REJECTED"]
    correct_label: Literal["HEALTHY", "YELLOW", "SPOT", "UNKNOWN"] | None = None
    note: str | None = Field(default=None, max_length=300)


def diagnosis_out(d: Diagnosis, with_leaves: bool = False) -> dict:
    """with_leaves: chỉ trang chi tiết cần polygon từng lá; danh sách thì bỏ để phản hồi nhẹ."""
    out = {"id": d.id, "deviceId": d.device_id, "capturedAt": d.captured_at, "status": d.status,
           "topLabel": d.top_label, "topConfidence": d.top_confidence, "abnormalTiles": d.abnormal_tiles or [],
           "tiles": [{"r": t.get("r"), "c": t.get("c"), "label": t.get("label"), "conf": t.get("conf"),
                      "probs": t.get("probs"), "nLeaves": t.get("n_leaves")} for t in (d.tiles or [])],
           "modelVersion": d.model_version, "trigger": d.trigger, "cmdId": d.cmd_id, "lampOn": d.lamp_on,
           "reviewVerdict": d.review_verdict, "correctLabel": d.correct_label, "reviewedBy": d.reviewed_by,
           "reviewedAt": d.reviewed_at, "createdAt": d.created_at}
    if with_leaves:
        out["leaves"] = d.leaves or []
    return out


def _get_view(db: Session, user: User, diag_id: int) -> tuple[Diagnosis, str]:
    d = db.get(Diagnosis, diag_id)
    perm = permission_of(db, user, d.device_id) if d else None
    if not d or not perm:
        raise not_found("Không tìm thấy chẩn đoán")
    return d, perm


@router.get("/devices/{device_id}/diagnoses")
def list_diagnoses(device_id: int, frm: datetime | None = Query(None, alias="from"), to: datetime | None = None,
                   label: Literal["HEALTHY", "YELLOW", "SPOT", "UNKNOWN"] | None = None,
                   status: Literal["QUEUED", "RUNNING", "DONE", "FAILED"] | None = None,
                   page: int = Query(0, ge=0), size: int = Query(20, ge=1, le=100),
                   user: User = Depends(current_user), db: Session = Depends(get_db)):
    device_for_view(db, user, device_id)
    q = select(Diagnosis).where(Diagnosis.device_id == device_id)
    if frm:
        q = q.where(Diagnosis.captured_at >= frm)
    if to:
        q = q.where(Diagnosis.captured_at <= to)
    if label:
        q = q.where(Diagnosis.top_label == label)
    if status:
        q = q.where(Diagnosis.status == status)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(q.order_by(Diagnosis.captured_at.desc(), Diagnosis.id.desc()).offset(page * size).limit(size))
    return {"items": [diagnosis_out(d) for d in rows], "page": page, "size": size, "total": total}


@router.get("/diagnoses/{diag_id}")
def get_diagnosis(diag_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d, _ = _get_view(db, user, diag_id)
    return diagnosis_out(d, with_leaves=True)


def _normalize_test_image(raw: bytes) -> bytes:
    """JPEG/PNG/WEBP bất kỳ → JPEG RGB đã xoay theo EXIF, cạnh dài ≤ TEST_MAX_SIDE."""
    try:
        with Image.open(io.BytesIO(raw)) as im:
            if im.format not in ("JPEG", "PNG", "WEBP"):
                raise ValueError(im.format)
            im = ImageOps.exif_transpose(im).convert("RGB")
    except Exception:  # noqa: BLE001
        raise ApiError(400, "VALIDATION_ERROR", "Chỉ nhận ảnh JPEG, PNG hoặc WEBP hợp lệ")
    if max(im.size) > TEST_MAX_SIDE:
        im.thumbnail((TEST_MAX_SIDE, TEST_MAX_SIDE), Image.LANCZOS)
    out = io.BytesIO()
    im.save(out, "JPEG", quality=90)
    return out.getvalue()


@router.post("/devices/{device_id}/diagnoses/test-upload", status_code=201)
async def test_upload(device_id: int, request: Request, user: User = Depends(current_user),
                      db: Session = Depends(get_db)):
    """Body = nội dung ảnh (Content-Type image/*). Đi qua đúng hàng đợi AI như ảnh từ camera nhưng đánh dấu
    trigger='test': không áp luật cảnh báo AI_LEAF, không cập nhật trạng thái thiết bị."""
    dev, perm = device_for_view(db, user, device_id)
    if perm != "CONTROL":
        raise forbidden("Cần quyền CONTROL trên thiết bị này")
    if dev.type != "CAMERA" or dev.status == "DECOMMISSIONED":
        raise ApiError(409, "INVALID_STATE", "Chỉ tải ảnh thử lên camera chưa bị thu hồi")
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > TEST_MAX_BYTES:
        raise ApiError(413, "PAYLOAD_TOO_LARGE", f"Ảnh tối đa {TEST_MAX_BYTES // (1024 * 1024)} MB")
    with _test_lock:
        if time.time() - _test_last.get(device_id, 0.0) < TEST_GAP_S:
            raise ApiError(429, "RATE_LIMITED", f"Chờ {TEST_GAP_S} giây giữa hai lần tải ảnh")
        _test_last[device_id] = time.time()
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > TEST_MAX_BYTES:
            raise ApiError(413, "PAYLOAD_TOO_LARGE", f"Ảnh tối đa {TEST_MAX_BYTES // (1024 * 1024)} MB")
    jpeg = await run_in_threadpool(_normalize_test_image, bytes(body))
    # touch=False: không đánh dấu camera 'vừa có tín hiệu' (ảnh này không đến từ thiết bị)
    did = await run_in_threadpool(_store, dev.id, dev.device_code, jpeg, datetime.now(timezone.utc), "test", None,
                                  False, False)
    audit(db, "DIAGNOSIS_TEST_UPLOAD", actor=user, target_type="device", target_id=dev.id,
          detail={"diagnosis_id": did, "bytes": len(jpeg)}, ip=client_ip(request))
    db.commit()
    diagnosis.wake()
    return {"id": did, "status": "QUEUED"}


@router.get("/diagnoses/{diag_id}/image")
def get_image(diag_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d, _ = _get_view(db, user, diag_id)
    root = settings.image_dir.resolve()
    path = (settings.image_dir / d.image_path).resolve()
    if root not in path.parents or not path.is_file():
        raise not_found("Không tìm thấy ảnh")
    return FileResponse(path, media_type="image/jpeg",
                        headers={"Cache-Control": "private, max-age=300",
                                 "Content-Disposition": f'inline; filename="diagnosis-{d.id}.jpg"'})


@router.post("/diagnoses/{diag_id}/review")
def review(diag_id: int, body: ReviewIn, request: Request, user: User = Depends(current_user),
           db: Session = Depends(get_db)):
    d, perm = _get_view(db, user, diag_id)
    if perm != "CONTROL":
        raise forbidden("Cần quyền CONTROL trên thiết bị này")
    if d.status != "DONE":
        raise ApiError(409, "INVALID_STATE", "Chỉ đánh giá được chẩn đoán đã có kết quả")
    if body.verdict == "REJECTED" and not body.correct_label:
        raise ApiError(400, "VALIDATION_ERROR", "Báo sai cần correctLabel", {"field": "correctLabel"})
    d.review_verdict = body.verdict
    d.correct_label = body.correct_label if body.verdict == "REJECTED" else (body.correct_label or d.top_label)
    d.reviewed_by, d.reviewed_at = user.id, datetime.now(timezone.utc)
    audit(db, "DIAGNOSIS_REVIEWED", actor=user, target_type="diagnosis", target_id=d.id,
          detail={"verdict": body.verdict, "correct_label": d.correct_label, "top_label": d.top_label,
                  "note": body.note}, ip=client_ip(request))
    db.commit()
    return diagnosis_out(d)
