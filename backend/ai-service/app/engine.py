"""Bộ suy luận: luồng thật MobileSAM + ConvNeXt (LeafEngine) hoặc stub theo màu (AI_MODE=stub, chỉ để kiểm thử)."""
from __future__ import annotations

import logging
import time

import numpy as np
from PIL import Image

from . import config

log = logging.getLogger("ai.engine")
CLASSES = ("HEALTHY", "YELLOW", "SPOT")


class LeafEngine:
    """Luồng thật: MobileSAM tách lá -> ConvNeXt-Tiny (ONNX) phân loại -> gộp về lưới 3x3 (leaf_pipeline.py)."""

    kind = "model"

    def __init__(self) -> None:
        self.ready = False
        self.reason = ""
        self.model_version = config.MODEL_VERSION
        self.pipe = None

    def missing_files(self) -> list[str]:
        return [f for f in ("mobile_sam.pt", "leaf.onnx") if not (config.MODEL_DIR / f).exists()]

    def load(self) -> None:
        miss = self.missing_files()
        if miss:
            self.reason = (f"Thiếu file mô hình: {', '.join(miss)}. Đặt vào thư mục {config.MODEL_DIR} "
                           f"(xem backend/ai-service/README.md).")
            log.warning(self.reason)
            return
        from . import leaf_pipeline  # noqa: PLC0415 — nạp chậm (torch), stub không cần
        from .leaf_pipeline import LeafPipeline  # noqa: PLC0415

        leaf_pipeline.UNKNOWN_T = config.CONF_UNKNOWN   # .env cũng được đọc (config.py)

        t0 = time.time()
        self.pipe = LeafPipeline(config.MODEL_DIR / "mobile_sam.pt", config.MODEL_DIR / "leaf.onnx",
                                 config.MODEL_DIR / "model_meta.json")
        self.ready = True
        log.info("Đã nạp mô hình %s (lớp %s) trong %.1f s", self.model_version, self.pipe.classes, time.time() - t0)

    def infer_image(self, bgr, crop_box, active):
        return self.pipe.infer(bgr, crop_box, active)


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
    return LeafEngine()
