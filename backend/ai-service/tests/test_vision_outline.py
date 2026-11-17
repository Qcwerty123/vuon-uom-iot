"""Test OFFLINE cho chế độ viền lá của engine vision-api (VISION_OUTLINE=1): phân tích polygon, gán lá vào ô 3x3,
loại mảnh lá khỏi chẩn đoán, và luồng infer_image đầu cuối với API giả.

Chạy:  .venv\\Scripts\\python.exe tests\\test_vision_outline.py      (hoặc pytest tests\\test_vision_outline.py)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config  # noqa: E402
from app import vision_engine as v  # noqa: E402


def sq(x0, y0, x1, y1):                       # hình chữ nhật 0..1000 làm "lá"
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


RESP = {"leaves": [
    {"label": "HEALTHY", "confidence": 0.9, "complete": True, "polygon": sq(50, 50, 250, 250)},     # ô (0,0)
    {"label": "SPOT", "confidence": 0.85, "complete": True, "polygon": sq(400, 60, 600, 260)},      # ô (0,1)
    {"label": "SPOT", "confidence": 0.9, "complete": False, "polygon": sq(700, 60, 950, 260)},      # ô (0,2): mảnh lá, không tính bệnh
    {"label": "YELLOW", "confidence": 0.4, "complete": True, "polygon": sq(50, 400, 250, 600)},    # ô (1,0): conf thấp -> UNKNOWN
    {"label": "HEALTHY", "confidence": 0.95, "complete": True, "polygon": sq(400, 400, 420, 410)}, # quá nhỏ -> bỏ
    {"label": "LẠ", "confidence": 0.9, "complete": True, "polygon": sq(50, 700, 250, 900)},         # nhãn lạ -> bỏ
    {"label": "HEALTHY", "confidence": 0.9, "polygon": [[1, 2]]},                                   # polygon thiếu điểm -> bỏ
]}


def test_parse_leaves_filters_invalid_and_tiny():
    lv = v.parse_leaves(RESP)
    assert [l["label"] for l in lv] == ["HEALTHY", "SPOT", "SPOT", "YELLOW"]
    assert lv[0]["polygon"][0] == [0.05, 0.05] and lv[2]["complete"] is False


def test_parse_leaves_accepts_unit_coordinates_and_percent_conf():
    lv = v.parse_leaves({"leaves": [{"label": "healthy", "confidence": 88,
                                     "polygon": [[0.1, 0.1], [0.4, 0.1], [0.4, 0.4], [0.1, 0.4]]}]})
    assert len(lv) == 1 and lv[0]["label"] == "HEALTHY" and abs(lv[0]["conf"] - 0.88) < 1e-9
    assert lv[0]["polygon"][2] == [0.4, 0.4]


def test_parse_leaves_missing_key_raises():
    try:
        v.parse_leaves({"cells": []})
    except v.VisionError:
        return
    raise AssertionError("phải lỗi khi thiếu 'leaves'")


def test_tiles_from_leaves():
    tiles, leaves = v.tiles_from_leaves(v.parse_leaves(RESP), None, 0.6, (0, 0), (800, 600))
    t = {(x["r"], x["c"]): x for x in tiles}
    assert len(tiles) == 9
    assert t[(0, 0)]["label"] == "HEALTHY" and t[(0, 0)]["n_leaves"] == 1
    assert t[(0, 1)]["label"] == "SPOT" and t[(0, 1)]["conf"] == 0.85
    assert t[(0, 2)]["label"] == "UNKNOWN"                       # chỉ có mảnh lá (không đủ) -> không kết luận bệnh
    assert t[(1, 0)]["label"] == "UNKNOWN"                       # YELLOW conf 0.4 < 0.6
    assert t[(2, 2)]["label"] == "UNKNOWN" and t[(2, 2)]["conf"] == 0.0 and t[(2, 2)]["n_leaves"] == 0
    assert len(leaves) == 4 and leaves[2]["label"] == "UNKNOWN" and leaves[2]["tile"] == [0, 2]
    assert leaves[0]["bbox"] == [40, 30, 160, 120]               # pixel: x=0.05*800, y=0.05*600, w=0.2*800, h=0.2*600


def test_tiles_from_leaves_bbox_uses_crop_origin_and_active_filter():
    lv = v.parse_leaves(RESP)
    tiles, leaves = v.tiles_from_leaves(lv, {(0, 0), (0, 1)}, 0.6, (100, 50), (600, 400))
    assert leaves[0]["bbox"][:2] == [130, 70]                    # 100+0.05*600, 50+0.05*400
    assert len(leaves) == 2                                      # lá ngoài ô active bị bỏ
    out_tile = [x for x in tiles if (x["r"], x["c"]) == (2, 2)][0]
    assert out_tile["active"] is False


def test_infer_image_outline_end_to_end():
    config.VISION_API_KEY, config.VISION_API_BASE, config.VISION_OUTLINE = "khoa-gia-123456", "https://x.invalid/v1", True
    e = v.VisionEngine()
    e._post = lambda b64, system=None, user_text=None: "```json\n" + json.dumps(RESP) + "\n```"   # type: ignore[assignment]
    out = e.infer_image(np.zeros((600, 800, 3), np.uint8), None, None)
    assert out["source"] == "vision-api" and out["top_label"] == "SPOT" and out["top_confidence"] == 0.85
    assert len(out["tiles"]) == 9 and len(out["leaves"]) == 4
    assert all(set(l) == {"tile", "label", "conf", "bbox", "polygon"} for l in out["leaves"])   # đúng hợp đồng /v1/infer


def test_no_plant_gives_all_unknown():
    config.VISION_API_KEY, config.VISION_API_BASE, config.VISION_OUTLINE = "khoa-gia-123456", "https://x.invalid/v1", True
    e = v.VisionEngine()
    e._post = lambda b64, system=None, user_text=None: '{"leaves": []}'                           # type: ignore[assignment]
    out = e.infer_image(np.zeros((600, 800, 3), np.uint8), None, None)
    assert out["top_label"] == "UNKNOWN" and out["top_confidence"] == 0.0 and out["leaves"] == []
    assert all(t["label"] == "UNKNOWN" and t["conf"] == 0.0 for t in out["tiles"])


if __name__ == "__main__":
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for f in fns:
        f()
        print("ok  ", f.__name__)
    print(f"{len(fns)}/{len(fns)} test đạt")
