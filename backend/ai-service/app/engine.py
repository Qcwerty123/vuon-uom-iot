"""Bộ suy luận: mô hình thật (Keras, PlantVillage 38 lớp) hoặc stub theo màu (AI_MODE=stub).

Cả hai trả về, cho mỗi ô, xác suất đã gộp về 3 lớp {HEALTHY, YELLOW, SPOT} (tổng = 1) và thông tin phụ.
Việc gán UNKNOWN theo ngưỡng làm ở main.py để dùng chung cho hai chế độ.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time

import numpy as np
from PIL import Image

from . import config

log = logging.getLogger("ai.engine")
CLASSES = ("HEALTHY", "YELLOW", "SPOT")


def _sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class KerasEngine:
    """Mô hình tiền huấn luyện công khai (C24). Chỉ lấy các lớp Tomato___*, chuẩn hóa lại tổng = 1, gộp theo label_map."""

    kind = "model"

    def __init__(self) -> None:
        self.ready = False
        self.reason = ""
        man = json.loads(config.MANIFEST.read_text(encoding="utf-8"))
        self.model_version = man["model_version"]
        self.classes: list[str] = man["classes"]
        self.path = config.MODEL_DIR / man["file"]
        self.sha256 = man.get("sha256", "")
        lm = json.loads(config.LABEL_MAP.read_text(encoding="utf-8"))["plantvillage"]
        self.tomato_idx = [i for i, n in enumerate(self.classes) if n.startswith("Tomato___")]
        missing = [self.classes[i] for i in self.tomato_idx if self.classes[i] not in lm]
        if missing:
            raise RuntimeError(f"label_map.json thiếu lớp: {missing}")
        # Ma trận gộp: (số lớp Tomato) × 3
        self.merge = np.zeros((len(self.tomato_idx), len(CLASSES)), dtype=np.float32)
        for j, i in enumerate(self.tomato_idx):
            self.merge[j, CLASSES.index(lm[self.classes[i]])] = 1.0
        self.model = None

    def load(self) -> None:
        if not self.path.exists():
            self.reason = f"thiếu trọng số {self.path.name} trong {config.MODEL_DIR} (chạy scripts/windows/get-model.ps1)"
            log.warning(self.reason)
            return
        if self.sha256 and _sha256(self.path) != self.sha256:
            self.reason = f"SHA256 của {self.path.name} không khớp model.json"
            log.error(self.reason)
            return
        t0 = time.time()
        os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
        os.environ.setdefault("KERAS_BACKEND", "tensorflow")
        import keras  # noqa: PLC0415 — nạp chậm, stub không cần TensorFlow

        self.model = keras.saving.load_model(self.path, compile=False)
        out = int(self.model.output_shape[-1])
        if out != len(self.classes):
            self.reason = f"mô hình có {out} lớp, model.json ghi {len(self.classes)}"
            log.error(self.reason)
            self.model = None
            return
        self.predict(np.zeros((1, 224, 224, 3), dtype=np.float32))  # khởi động đồ thị
        self.ready = True
        log.info("Đã nạp mô hình %s trong %.1f s", self.model_version, time.time() - t0)

    def predict(self, batch: np.ndarray) -> np.ndarray:
        return np.asarray(self.model(batch, training=False))

    def infer(self, tiles: list[Image.Image]) -> list[dict]:
        batch = np.stack([np.asarray(t, dtype=np.float32) for t in tiles])
        p = self.predict(batch)                          # (n, 38) softmax
        tom = p[:, self.tomato_idx]
        mass = tom.sum(axis=1, keepdims=True)
        tom = tom / np.clip(mass, 1e-9, None)            # chỉ trong các lớp cà chua, tổng = 1
        agg = tom @ self.merge                           # (n, 3)
        out = []
        for k in range(len(tiles)):
            j = int(np.argmax(tom[k]))
            out.append({"probs": {c: float(agg[k, i]) for i, c in enumerate(CLASSES)},
                        "tomato_mass": float(mass[k, 0]),
                        "raw_top": self.classes[self.tomato_idx[j]]})
        return out


class StubEngine:
    """KHÔNG phải mô hình thật — chỉ để kiểm thử luồng khi chưa có trọng số.

    Tất định theo màu: đếm tỉ lệ pixel vàng / nâu (đốm) / xanh lá trong ô (HSV).
    Vàng ≥ 25 % → YELLOW, nâu ≥ 12 % → SPOT, xanh ≥ 20 % → HEALTHY, còn lại → không chắc (xác suất đều).
    """

    kind = "stub"
    model_version = "stub-v0"

    def __init__(self) -> None:
        self.ready = True
        self.reason = ""

    def load(self) -> None:
        log.warning("AI_MODE=stub: dùng bộ chấm theo màu, KHÔNG phải mô hình thật")

    @staticmethod
    def ratios(tile: Image.Image) -> dict[str, float]:
        hsv = np.asarray(tile.convert("HSV"), dtype=np.float32)
        h, s, v = hsv[..., 0] * 360 / 255, hsv[..., 1] / 255, hsv[..., 2] / 255
        n = h.size
        yellow = ((h >= 40) & (h < 70) & (s > 0.45) & (v > 0.45)).sum() / n
        brown = ((h >= 5) & (h < 40) & (s > 0.45) & (v > 0.12) & (v < 0.6)).sum() / n
        green = ((h >= 70) & (h < 170) & (s > 0.25) & (v > 0.15)).sum() / n
        return {"yellow": float(yellow), "brown": float(brown), "green": float(green)}

    def infer(self, tiles: list[Image.Image]) -> list[dict]:
        out = []
        for t in tiles:
            r = self.ratios(t)
            if r["yellow"] >= 0.25:
                lab, conf = "YELLOW", min(0.97, 0.80 + r["yellow"] * 0.4)
            elif r["brown"] >= 0.12:
                lab, conf = "SPOT", min(0.97, 0.80 + r["brown"] * 0.6)
            elif r["green"] >= 0.20:
                lab, conf = "HEALTHY", min(0.97, 0.75 + r["green"] * 0.3)
            else:
                lab, conf = None, 1 / 3
            if lab is None:
                probs = {c: 1 / 3 for c in CLASSES}
            else:
                rest = (1 - conf) / 2
                probs = {c: (conf if c == lab else rest) for c in CLASSES}
            out.append({"probs": probs, "color": {k: round(v, 3) for k, v in r.items()}})
        return out


def create():
    if config.MODE == "stub":
        return StubEngine()
    return KerasEngine()
