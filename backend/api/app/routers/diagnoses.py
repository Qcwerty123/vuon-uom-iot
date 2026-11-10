"""Ảnh và chẩn đoán (đặc tả §10.9). Ảnh chỉ trả qua API có kiểm quyền mỗi lần, không có URL tĩnh công khai.

API web dùng id số nguyên (diagnoses.id); tiền tố img-/dg- chỉ dùng trong phản hồi cho thiết bị (§8.9).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import audit
from ..config import settings
from ..db import get_db
from ..deps import client_ip, current_user, device_for_view, permission_of
from ..errors import ApiError, forbidden, not_found
from ..models import Diagnosis, User
from ..schemas import Api

router = APIRouter(tags=["diagnoses"])
LABELS = ("HEALTHY", "YELLOW", "SPOT", "UNKNOWN")


class ReviewIn(Api):
    verdict: Literal["CONFIRMED", "REJECTED"]
    correct_label: Literal["HEALTHY", "YELLOW", "SPOT", "UNKNOWN"] | None = None
    note: str | None = Field(default=None, max_length=300)


def diagnosis_out(d: Diagnosis) -> dict:
    return {"id": d.id, "deviceId": d.device_id, "capturedAt": d.captured_at, "status": d.status,
            "topLabel": d.top_label, "topConfidence": d.top_confidence, "abnormalTiles": d.abnormal_tiles or [],
            "tiles": [{"r": t.get("r"), "c": t.get("c"), "label": t.get("label"), "conf": t.get("conf"),
                       "probs": t.get("probs")} for t in (d.tiles or [])],
            "modelVersion": d.model_version, "trigger": d.trigger, "cmdId": d.cmd_id, "lampOn": d.lamp_on,
            "reviewVerdict": d.review_verdict, "correctLabel": d.correct_label, "reviewedBy": d.reviewed_by,
            "reviewedAt": d.reviewed_at, "createdAt": d.created_at}


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
    return diagnosis_out(d)


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
