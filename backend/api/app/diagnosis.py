"""DiagnosisWorker (đặc tả §9.1, §12.4, §15.6) và luật cảnh báo AI_LEAF (§13.1).

Một luồng nền:
  1. Lấy bản ghi QUEUED theo captured_at → RUNNING (commit).
  2. Gọi AI_URL/v1/infer (multipart, timeout 30 s), kèm crop_box / active_tiles từ cấu hình camera nếu có.
  3. Thành công: lưu kết quả, DONE (commit) → đẩy WS "diagnosis" → áp luật AI_LEAF.
     AI lỗi: thử lại tối đa 2 lần (tổng 3 lần gọi) rồi FAILED.
     AI không kết nối được / chưa có mô hình (503): trả về QUEUED, chờ, KHÔNG tính vào số lần thử.
Khi khởi động: RUNNING → QUEUED rồi quét lại. Số lần thử giữ trong RAM (khởi động lại backend thì đếm lại từ 0).
"""
from __future__ import annotations

import json
import logging
import threading
import urllib.error
import urllib.request
import uuid

from sqlalchemy import select, update

from . import alerts, commands, realtime
from .config import settings
from .db import session_scope
from .models import AlertRule, Device, Diagnosis

log = logging.getLogger("diagnosis")
LABELS = {"HEALTHY", "YELLOW", "SPOT", "UNKNOWN"}
ABNORMAL = ("YELLOW", "SPOT")
LEAF_VI = {"HEALTHY": "Khỏe", "YELLOW": "Vàng lá", "SPOT": "Đốm lá", "UNKNOWN": "Không rõ"}
MAX_RETRIES = 2
TIMEOUT_S = 30
WINDOW = 3            # số ảnh liên tiếp của luật AI_LEAF

_wake = threading.Event()
_stop = threading.Event()
_attempts: dict[int, int] = {}
state: dict = {"aiUp": None, "lastError": None, "modelVersion": None, "processed": 0, "failed": 0}


class AiUnavailable(Exception):
    """AI service tắt / chưa có mô hình — giữ QUEUED, không tính lần thử."""


class AiError(Exception):
    """AI trả lỗi hoặc kết quả sai định dạng — tính một lần thử."""


def wake() -> None:
    _wake.set()


# ---------------------------------------------------------------------------
# Gọi AI service
# ---------------------------------------------------------------------------

def _multipart(image: bytes, fields: dict[str, str]) -> tuple[bytes, str]:
    b = uuid.uuid4().hex
    parts = [f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in fields.items()]
    parts.append(f'--{b}\r\nContent-Disposition: form-data; name="image"; filename="image.jpg"\r\n'
                 f"Content-Type: image/jpeg\r\n\r\n".encode() + image + b"\r\n")
    parts.append(f"--{b}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={b}"


def ai_health(timeout: float = 3) -> dict | None:
    try:
        with urllib.request.urlopen(settings.ai_url + "/v1/health", timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:  # noqa: BLE001
        return None


def call_ai(image: bytes, crop_box=None, active_tiles=None) -> dict:
    fields = {}
    if crop_box is not None:
        fields["crop_box"] = json.dumps(crop_box)
    if active_tiles is not None:
        fields["active_tiles"] = json.dumps(active_tiles)
    body, ctype = _multipart(image, fields)
    req = urllib.request.Request(settings.ai_url + "/v1/infer", data=body, headers={"Content-Type": ctype})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            res = json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read()[:200].decode(errors="replace")
        if e.code == 503:
            raise AiUnavailable(f"AI chưa sẵn sàng: {detail}")
        raise AiError(f"AI trả HTTP {e.code}: {detail}")
    except TimeoutError as e:
        raise AiError(f"AI quá {TIMEOUT_S} s: {e}")
    except urllib.error.URLError as e:
        if isinstance(e.reason, TimeoutError):
            raise AiError(f"AI quá {TIMEOUT_S} s")
        raise AiUnavailable(f"Không kết nối được AI service: {e.reason}")
    except (ConnectionError, OSError) as e:
        raise AiUnavailable(f"Mất kết nối AI service: {e}")
    except ValueError as e:
        raise AiError(f"AI trả JSON lỗi: {e}")
    tiles = res.get("tiles")
    if not isinstance(tiles, list) or len(tiles) != 9 or any(t.get("label") not in LABELS for t in tiles):
        raise AiError("Kết quả AI sai định dạng (cần 9 ô)")
    return res


# ---------------------------------------------------------------------------
# Xử lý một bản ghi
# ---------------------------------------------------------------------------

def _camera_params(db, dev: Device) -> tuple:
    p = commands.current_params(db, dev) if dev else {}
    return p.get("crop_box"), p.get("active_tiles")


def _claim() -> dict | None:
    with session_scope() as db:
        d = db.scalar(select(Diagnosis).where(Diagnosis.status == "QUEUED")
                      .order_by(Diagnosis.captured_at, Diagnosis.id).limit(1).with_for_update(skip_locked=True))
        if not d:
            return None
        d.status = "RUNNING"
        dev = db.get(Device, d.device_id)
        crop, active = _camera_params(db, dev)
        return {"id": d.id, "device_id": d.device_id, "path": settings.image_dir / d.image_path,
                "crop_box": crop, "active_tiles": active}


def _set_status(did: int, status: str) -> None:
    with session_scope() as db:
        d = db.get(Diagnosis, did)
        if d:
            d.status = status


def diagnosis_ws(d: Diagnosis) -> dict:
    """Bản tin WS (§10.11) + các trường frontend dùng (Dashboard, Diagnoses)."""
    return {"type": "diagnosis", "id": d.id, "deviceId": d.device_id, "status": d.status,
            "capturedAt": d.captured_at.isoformat() if d.captured_at else None, "topLabel": d.top_label,
            "confidence": d.top_confidence, "topConfidence": d.top_confidence, "abnormalTiles": d.abnormal_tiles or [],
            "modelVersion": d.model_version, "trigger": d.trigger}


def process_one() -> str:
    """Trả về: 'idle' (không có việc), 'done', 'error', 'down' (AI không sẵn sàng)."""
    job = _claim()
    if not job:
        return "idle"
    did = job["id"]
    try:
        image = job["path"].read_bytes()
    except OSError:
        log.error("Chẩn đoán %s: không đọc được file ảnh → FAILED", did)
        _set_status(did, "FAILED")
        state["failed"] += 1
        return "error"
    try:
        res = call_ai(image, job["crop_box"], job["active_tiles"])
    except AiUnavailable as e:
        _set_status(did, "QUEUED")
        if state["aiUp"] is not False:
            log.warning("AI service chưa sẵn sàng, giữ hàng đợi: %s", e)
        state["aiUp"], state["lastError"] = False, str(e)[:200]
        return "down"
    except AiError as e:
        n = _attempts.get(did, 0) + 1
        _attempts[did] = n
        final = n > MAX_RETRIES
        _set_status(did, "FAILED" if final else "QUEUED")
        state["lastError"] = str(e)[:200]
        log.warning("Chẩn đoán %s lỗi lần %d%s: %s", did, n, " → FAILED" if final else ", thử lại", e)
        if final:
            _attempts.pop(did, None)
            state["failed"] += 1
        return "error"

    if state["aiUp"] is False:
        log.info("AI service đã sẵn sàng lại")
    state["aiUp"], state["modelVersion"] = True, res.get("model_version")
    _attempts.pop(did, None)
    tiles = [{k: v for k, v in t.items()} for t in res["tiles"]]
    abnormal = [[t["r"], t["c"]] for t in tiles if t["label"] in ABNORMAL]
    with session_scope() as db:
        d = db.get(Diagnosis, did)
        d.tiles, d.abnormal_tiles = tiles, abnormal
        d.top_label = str(res.get("top_label") or "UNKNOWN")[:20]
        d.top_confidence = float(res.get("top_confidence") or 0)
        d.model_version = str(res.get("model_version") or "")[:30]
        d.status = "DONE"
        db.flush()
        msg = diagnosis_ws(d)
    # Đã commit → mới đẩy WS và áp luật (ghi trước, phát sau)
    realtime.publish(job["device_id"], msg)
    state["processed"] += 1
    log.info("Chẩn đoán %s DONE: %s %.2f, %d ô bất thường, %s ms", did, msg["topLabel"], msg["topConfidence"],
             len(abnormal), res.get("latency_ms"))
    try:
        apply_ai_leaf(job["device_id"])
    except Exception:  # noqa: BLE001 — lỗi luật không làm dừng worker
        log.exception("Áp luật AI_LEAF lỗi (thiết bị %s)", job["device_id"])
    return "done"


# ---------------------------------------------------------------------------
# Luật AI_LEAF: cùng một ô YELLOW/SPOT với conf ≥ ngưỡng ở cả 3 ảnh DONE gần nhất
# ---------------------------------------------------------------------------

def leaf_cells(diags: list[Diagnosis], thr: float) -> set[tuple[int, int]]:
    cells: set[tuple[int, int]] | None = None
    for d in diags:
        s = {(t["r"], t["c"]) for t in (d.tiles or []) if t.get("label") in ABNORMAL and (t.get("conf") or 0) >= thr}
        cells = s if cells is None else cells & s
    return cells or set()


def apply_ai_leaf(device_id: int) -> None:
    with session_scope() as db:
        dev = db.get(Device, device_id)
        if not dev:
            return
        rules = [r for r in alerts._rules(db) if r.type == "AI_LEAF" and alerts._applies(r, dev)]
        if not rules:
            return
        last = list(db.scalars(select(Diagnosis).where(Diagnosis.device_id == device_id, Diagnosis.status == "DONE")
                               .order_by(Diagnosis.captured_at.desc(), Diagnosis.id.desc()).limit(WINDOW)))
        if len(last) < WINDOW:
            return
        latest = last[0]
        tiles_now = {(t["r"], t["c"]): t for t in latest.tiles or []}
        for rule in rules:
            thr = rule.threshold if rule.threshold is not None else settings.ai_conf_alert
            cells = sorted(leaf_cells(last, thr))
            if not cells:
                continue
            desc = ", ".join(f"hàng {r + 1} cột {c + 1}: {LEAF_VI.get(tiles_now[(r, c)]['label'], '?')} "
                             f"{tiles_now[(r, c)]['conf']:.0%}" for r, c in cells)
            ctx = {"diagnosis_id": latest.id, "diagnosis_ids": [d.id for d in last],
                   "tiles": [[r, c] for r, c in cells],
                   "labels": {f"{r},{c}": tiles_now[(r, c)]["label"] for r, c in cells},
                   "threshold": thr, "model_version": latest.model_version}
            a = alerts.open_alert(db, dev, rule, f"{rule.name}: {desc} ({WINDOW} ảnh liên tiếp)", ctx, defer=True)
            if a:
                db.commit()  # ghi trước, rồi mới đẩy WS / Telegram (kèm ảnh mới nhất)
                alerts.announce(a, dev, rule, photo=settings.image_dir / latest.image_path)


def ensure_rule() -> None:
    """Chưa có luật AI_LEAF nào (kể cả đã tắt) thì seed luật mặc định §13.2."""
    with session_scope() as db:
        if db.scalar(select(AlertRule.id).where(AlertRule.type == "AI_LEAF").limit(1)) is None:
            db.add(AlertRule(name="Lá bất thường", type="AI_LEAF", threshold=settings.ai_conf_alert, duration_s=0,
                             severity="WARNING", cooldown_min=30, notify_telegram=True, enabled=True))
            log.info("Đã seed luật AI_LEAF mặc định")
    alerts.invalidate_rules()


# ---------------------------------------------------------------------------

def _run() -> None:
    while not _stop.is_set():
        try:
            if state["aiUp"] is False:
                h = ai_health()
                if not h or h.get("status") != "ok":
                    _wake.clear()
                    _wake.wait(5)
                    continue
            r = process_one()
        except Exception:  # noqa: BLE001
            log.exception("DiagnosisWorker lỗi")
            r = "error"
        if r == "done":
            continue
        _wake.clear()
        _wake.wait({"idle": 2, "error": 1, "down": 5}.get(r, 2))


def start() -> None:
    with session_scope() as db:
        n = db.execute(update(Diagnosis).where(Diagnosis.status == "RUNNING").values(status="QUEUED")).rowcount
    if n:
        log.info("Đưa %d chẩn đoán RUNNING về QUEUED sau khởi động", n)
    ensure_rule()
    h = ai_health()
    state["aiUp"] = bool(h and h.get("status") == "ok")
    state["modelVersion"] = (h or {}).get("model_version")
    log.info("DiagnosisWorker chạy, AI %s (%s)", "sẵn sàng" if state["aiUp"] else "chưa sẵn sàng",
             (h or {}).get("model_version") or (h or {}).get("status") or "không kết nối được")
    threading.Thread(target=_run, name="diagnosis", daemon=True).start()


def stop() -> None:
    _stop.set()
    _wake.set()
