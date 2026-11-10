"""Dữ liệu đo và sự kiện thiết bị (đặc tả §10.6)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .. import ingest
from ..db import get_db
from ..deps import current_user, device_for_view
from ..errors import ApiError
from ..models import DeviceEvent, Telemetry, User

router = APIRouter(prefix="/devices/{device_id}", tags=["telemetry"])
METRICS = ("soil1", "soil2", "soil", "air_temp", "air_hum", "light", "tank")


def _range(frm: datetime | None, to: datetime | None, default_hours: float = 1) -> tuple[datetime, datetime]:
    to = to or datetime.now(timezone.utc)
    frm = frm or to - timedelta(hours=default_hours)
    if frm >= to:
        raise ApiError(400, "VALIDATION_ERROR", "from phải trước to")
    return frm, to


@router.get("/telemetry/latest")
def latest(device_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    device_for_view(db, user, device_id)
    rows = db.execute(text(
        "SELECT DISTINCT ON (metric) metric, value, unit, ok, ts, seq FROM telemetry "
        "WHERE device_id = :d ORDER BY metric, ts DESC, seq DESC"), {"d": device_id}).mappings().all()
    return {"deviceId": device_id,
            "metrics": {r["metric"]: {"value": r["value"], "unit": r["unit"], "ok": r["ok"], "ts": r["ts"],
                                      "seq": r["seq"]} for r in rows},
            "state": ingest.latest_state.get(device_id)}


@router.get("/telemetry")
def series(device_id: int, metric: str = Query("soil,air_temp,air_hum,light,tank"),
           frm: datetime | None = Query(None, alias="from"), to: datetime | None = None,
           interval: str = Query("auto", pattern="^(auto|raw|1h|1d)$"),
           user: User = Depends(current_user), db: Session = Depends(get_db)):
    device_for_view(db, user, device_id)
    metrics = [m for m in metric.split(",") if m in METRICS]
    if not metrics:
        raise ApiError(400, "VALIDATION_ERROR", f"metric phải thuộc {', '.join(METRICS)}")
    frm, to = _range(frm, to)
    if interval == "auto":
        interval = "raw" if to - frm <= timedelta(days=2) else "1h"
    out: dict[str, list] = {m: [] for m in metrics}
    if interval == "raw":
        q = (select(Telemetry.metric, Telemetry.ts, Telemetry.value, Telemetry.ok)
             .where(Telemetry.device_id == device_id, Telemetry.metric.in_(metrics), Telemetry.ts >= frm,
                    Telemetry.ts <= to).order_by(Telemetry.ts).limit(20000))
        for m, ts, v, ok in db.execute(q):
            out[m].append({"ts": ts, "v": v, "ok": ok})
    else:
        unit = "hour" if interval == "1h" else "day"
        bucket = func.date_trunc(unit, Telemetry.ts).label("b")
        q = (select(Telemetry.metric, bucket, func.min(Telemetry.value), func.max(Telemetry.value),
                    func.avg(Telemetry.value), func.count())
             .where(Telemetry.device_id == device_id, Telemetry.metric.in_(metrics), Telemetry.ok.is_(True),
                    Telemetry.ts >= frm, Telemetry.ts <= to)
             .group_by(Telemetry.metric, bucket).order_by(bucket))
        for m, b, mn, mx, avg, cnt in db.execute(q):
            out[m].append({"ts": b, "min": mn, "max": mx, "avg": avg, "count": cnt})
    return {"deviceId": device_id, "from": frm, "to": to, "interval": interval, "series": out}


@router.get("/telemetry/stats")
def stats(device_id: int, metric: str = "soil", frm: datetime | None = Query(None, alias="from"),
          to: datetime | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    device_for_view(db, user, device_id)
    if metric not in METRICS:
        raise ApiError(400, "VALIDATION_ERROR", "metric không hợp lệ")
    frm, to = _range(frm, to, 24)
    mn, mx, avg, cnt = db.execute(
        select(func.min(Telemetry.value), func.max(Telemetry.value), func.avg(Telemetry.value), func.count())
        .where(Telemetry.device_id == device_id, Telemetry.metric == metric, Telemetry.ok.is_(True),
               Telemetry.ts >= frm, Telemetry.ts <= to)).one()
    return {"metric": metric, "from": frm, "to": to, "min": mn, "max": mx, "avg": avg, "count": cnt}


@router.get("/events")
def events(device_id: int, type: str | None = None, frm: datetime | None = Query(None, alias="from"),  # noqa: A002
           to: datetime | None = None, limit: int = Query(100, le=1000),
           user: User = Depends(current_user), db: Session = Depends(get_db)):
    device_for_view(db, user, device_id)
    frm, to = _range(frm, to, 24)
    q = (select(DeviceEvent).where(DeviceEvent.device_id == device_id, DeviceEvent.ts >= frm, DeviceEvent.ts <= to)
         .order_by(DeviceEvent.ts.desc()).limit(limit))
    if type:  # một loại hoặc nhiều loại cách nhau dấu phẩy, ví dụ lamp_on,lamp_off
        q = q.where(DeviceEvent.type.in_([t.strip() for t in type.split(",") if t.strip()]))
    return [{"id": e.id, "seq": e.seq, "type": e.type, "detail": e.detail, "ts": e.ts} for e in db.scalars(q)]


@router.get("/telemetry/export.csv")
def export_csv(device_id: int, frm: datetime | None = Query(None, alias="from"), to: datetime | None = None,
               user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Xuất CSV dạng dài (ts, metric, value, unit, ok, seq); tối đa 31 ngày (§10.6)."""
    import csv
    import io

    from fastapi.responses import StreamingResponse

    dev, _ = device_for_view(db, user, device_id)
    frm, to = _range(frm, to, 24)
    if to - frm > timedelta(days=31):
        raise ApiError(400, "VALIDATION_ERROR", "Khoảng xuất tối đa 31 ngày")
    rows = db.execute(select(Telemetry.ts, Telemetry.metric, Telemetry.value, Telemetry.unit, Telemetry.ok, Telemetry.seq)
                      .where(Telemetry.device_id == device_id, Telemetry.ts >= frm, Telemetry.ts <= to)
                      .order_by(Telemetry.ts, Telemetry.metric)).all()
    buf = io.StringIO()
    buf.write("﻿")  # BOM để Excel đọc đúng tiếng Việt
    w = csv.writer(buf)
    w.writerow(["ts", "metric", "value", "unit", "ok", "seq"])
    for r in rows:
        w.writerow([r.ts.isoformat(), r.metric, r.value, r.unit, r.ok, r.seq])
    name = f"{dev.device_code}_{frm:%Y%m%d%H%M}_{to:%Y%m%d%H%M}.csv"
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})
