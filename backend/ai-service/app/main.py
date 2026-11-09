"""AI service chẩn đoán lá (đặc tả §15.6). Chỉ nghe 127.0.0.1:8001, chỉ backend gọi.

Chạy (thư mục backend/ai-service):  uvicorn app.main:app --host 127.0.0.1 --port 8001
  AI_MODE=stub  → bộ chấm theo màu để kiểm thử (model_version = stub-v0), không cần TensorFlow/trọng số.

POST /v1/infer   multipart: image, crop_box? (JSON [x0,y0,x1,y1]), active_tiles? (JSON [[r,c],...])
GET  /v1/health  → {"status":"ok"|"no_model", "model_version", "mode"}
"""
from __future__ import annotations

import logging
import threading
import time
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse

from . import config, engine as engines
from .preprocess import BadInput, prepare

ABNORMAL = ("YELLOW", "SPOT")


def _setup_logging() -> None:
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    h = RotatingFileHandler(config.LOG_DIR / "ai-service.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not any(isinstance(x, RotatingFileHandler) for x in root.handlers):
        root.addHandler(h)
    for name in ("uvicorn", "uvicorn.access"):
        lg = logging.getLogger(name)
        if not any(isinstance(x, RotatingFileHandler) for x in lg.handlers):
            lg.addHandler(h)


_setup_logging()
log = logging.getLogger("ai")
ENGINE = None
_lock = threading.Lock()   # suy luận tuần tự: một mô hình, một luồng


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global ENGINE
    ENGINE = engines.create()
    try:
        ENGINE.load()   # nạp mô hình MỘT lần khi khởi động
    except Exception as e:  # noqa: BLE001
        ENGINE.ready, ENGINE.reason = False, f"lỗi nạp mô hình: {e}"
        log.exception("Không nạp được mô hình")
    log.info("AI service sẵn sàng: mode=%s model_version=%s ready=%s", ENGINE.kind, ENGINE.model_version, ENGINE.ready)
    yield


app = FastAPI(title="Vườn ươm — AI chẩn đoán lá", version="1.0.0", lifespan=lifespan)


def _err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"code": code, "message": message}, status_code=status)


@app.get("/v1/health")
def health():
    if not ENGINE or not ENGINE.ready:
        return {"status": "no_model", "model_version": getattr(ENGINE, "model_version", None),
                "mode": config.MODE, "reason": getattr(ENGINE, "reason", "")}
    return {"status": "ok", "model_version": ENGINE.model_version, "mode": ENGINE.kind,
            "conf_unknown": config.CONF_UNKNOWN, "min_tomato_mass": config.MIN_TOMATO_MASS}


def label_tile(probs: dict[str, float]) -> tuple[str, float]:
    lab = max(probs, key=probs.get)
    conf = probs[lab]
    return ("UNKNOWN" if conf < config.CONF_UNKNOWN else lab), conf


def pick_top(tiles: list[dict]) -> tuple[str, float]:
    """Ô bất thường (YELLOW/SPOT) có độ tin cậy cao nhất; không có thì HEALTHY cao nhất; không có nữa thì UNKNOWN."""
    for group in (ABNORMAL, ("HEALTHY",)):
        cand = [t for t in tiles if t["label"] in group]
        if cand:
            best = max(cand, key=lambda t: t["conf"])
            return best["label"], best["conf"]
    return "UNKNOWN", max((t["conf"] for t in tiles), default=0.0)


@app.post("/v1/infer")
def infer(image: UploadFile = File(...), crop_box: str | None = Form(None), active_tiles: str | None = Form(None)):
    t0 = time.perf_counter()
    if not ENGINE or not ENGINE.ready:
        return _err(503, "NO_MODEL", getattr(ENGINE, "reason", "") or "chưa nạp mô hình")
    data = image.file.read(config.MAX_IMAGE_BYTES + 1)
    if len(data) > config.MAX_IMAGE_BYTES:
        return _err(413, "TOO_LARGE", "ảnh quá lớn")
    try:
        cells, active = prepare(data, crop_box, active_tiles)
    except BadInput as e:
        return _err(400, "BAD_INPUT", str(e))
    run = [(r, c, t) for r, c, t in cells if active is None or (r, c) in active]
    results = {}
    if run:
        with _lock:
            preds = ENGINE.infer([t for _, _, t in run])
        results = {(r, c): p for (r, c, _), p in zip(run, preds)}
    tiles = []
    for r, c, _ in cells:
        p = results.get((r, c))
        if p is None:  # ô ngoài active_tiles: không có cây
            tiles.append({"r": r, "c": c, "label": "UNKNOWN", "conf": 0.0,
                          "probs": {k: 0.0 for k in engines.CLASSES}, "active": False})
            continue
        lab, conf = label_tile(p["probs"])
        if config.MIN_TOMATO_MASS > 0 and p.get("tomato_mass", 1.0) < config.MIN_TOMATO_MASS:
            lab = "UNKNOWN"
        t = {"r": r, "c": c, "label": lab, "conf": round(conf, 4),
             "probs": {k: round(v, 4) for k, v in p["probs"].items()}}
        if "tomato_mass" in p:
            t["tomato_mass"] = round(p["tomato_mass"], 4)   # tổng xác suất các lớp cà chua trước khi chuẩn hóa lại
        tiles.append(t)
    top_label, top_conf = pick_top([t for t in tiles if t.get("active", True)])
    ms = int((time.perf_counter() - t0) * 1000)
    log.info("infer: %d ô, top=%s %.2f, %d ms", len(run), top_label, top_conf, ms)
    return {"model_version": ENGINE.model_version, "tiles": tiles, "top_label": top_label,
            "top_confidence": round(top_conf, 4), "latency_ms": ms}
