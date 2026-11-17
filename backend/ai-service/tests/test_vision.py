"""Test OFFLINE cho engine vision-api (không gọi mạng, không cần mô hình): phân tích phản hồi, dựng 9 ô,
dự phòng cục bộ, và khóa API không bị lộ trong thông báo lỗi.

Chạy:  .venv\\Scripts\\python.exe tests\\test_vision.py      (hoặc pytest tests\\test_vision.py)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config  # noqa: E402
from app import vision_engine as v  # noqa: E402

FENCED = '''```json
{"cells": [
 {"r":0,"c":0,"label":"HEALTHY","confidence":0.92,"reason":"green"},
 {"r":0,"c":1,"label":"spot","confidence":85,"reason":"brown lesions"},
 {"r":0,"c":2,"label":"NONE","confidence":0.9,"reason":"wall"},
 {"r":1,"c":0,"label":"UNSURE","confidence":0.4,"reason":"blurry"},
 {"r":1,"c":1,"label":"YELLOW","confidence":0.5,"reason":"pale"},
 {"r":1,"c":2,"label":"BANANA","confidence":0.9,"reason":"label không hợp lệ"},
 {"r":2,"c":0,"label":"HEALTHY","confidence":0.8,"reason":"ok"},
 {"r":3,"c":0,"label":"HEALTHY","confidence":0.8,"reason":"ngoài lưới"}
]}
```'''


def test_extract_json_fenced_and_plain():
    assert len(v.extract_json(FENCED)["cells"]) == 8
    assert v.extract_json('Kết quả: {"cells": []} xong')["cells"] == []
    for bad in ("", "không có json", "{hỏng", "[1,2]"):
        try:
            v.extract_json(bad)
        except v.VisionError:
            continue
        raise AssertionError(f"phải lỗi với {bad!r}")


def test_parse_cells_normalizes_and_drops_invalid():
    p = v.parse_cells(v.extract_json(FENCED))
    assert (1, 2) not in p and (3, 0) not in p            # nhãn lạ và ô ngoài lưới bị bỏ
    assert p[(0, 1)][0] == "SPOT" and abs(p[(0, 1)][1] - 0.85) < 1e-9   # 85 (phần trăm) -> 0.85, chữ thường -> hoa
    assert len(p) == 6


def test_parse_cells_needs_at_least_five():
    try:
        v.parse_cells({"cells": [{"r": 0, "c": 0, "label": "HEALTHY", "confidence": 0.9}]})
    except v.VisionError:
        return
    raise AssertionError("phải lỗi khi quá ít ô")


def test_build_tiles_labels_threshold_and_active():
    parsed = v.parse_cells(v.extract_json(FENCED))
    tiles = {(t["r"], t["c"]): t for t in v.build_tiles(parsed, None, 0.6)}
    assert len(tiles) == 9
    assert tiles[(0, 0)]["label"] == "HEALTHY"
    assert tiles[(0, 1)]["label"] == "SPOT" and tiles[(0, 1)]["conf"] == 0.85
    assert tiles[(0, 2)]["label"] == "UNKNOWN" and tiles[(0, 2)]["conf"] == 0.0     # NONE = không có cây
    assert tiles[(1, 0)]["label"] == "UNKNOWN"                                      # UNSURE
    assert tiles[(1, 1)]["label"] == "UNKNOWN" and tiles[(1, 1)]["conf"] == 0.5     # YELLOW 0.5 < ngưỡng 0.6
    assert tiles[(1, 2)]["label"] == "UNKNOWN" and "thiếu" in tiles[(1, 2)]["note"]  # ô thiếu trong phản hồi
    assert abs(sum(tiles[(0, 1)]["probs"].values()) - 1) < 1e-3
    act = {t["r"] * 3 + t["c"]: t for t in v.build_tiles(parsed, {(0, 0)}, 0.6)}
    assert act[0]["label"] == "HEALTHY" and act[1]["label"] == "UNKNOWN" and act[1]["active"] is False


def test_pick_top_prefers_abnormal():
    parsed = v.parse_cells(v.extract_json(FENCED))
    tiles = v.build_tiles(parsed, None, 0.6)
    assert v.pick_top(tiles) == ("SPOT", 0.85)
    healthy_only = [t for t in tiles if t["label"] == "HEALTHY"]
    assert v.pick_top(healthy_only) == ("HEALTHY", 0.92)
    assert v.pick_top([{"label": "UNKNOWN", "conf": 0.0}]) == ("UNKNOWN", 0.0)


def test_encode_image_with_grid_is_valid_jpeg_and_resized():
    import base64
    import cv2
    img = np.full((1200, 1600, 3), 90, np.uint8)
    b64 = v.encode_image(img, 1024, True)
    out = cv2.imdecode(np.frombuffer(base64.b64decode(b64), np.uint8), cv2.IMREAD_COLOR)
    assert max(out.shape[:2]) == 1024 and (out != 90).any()                          # đã thu nhỏ và có nét vẽ lưới


class _Local:
    model_version = "convnext-t-leaf-v1"

    def infer_image(self, bgr, crop_box, active):
        return {"tiles": [], "leaves": [], "top_label": "UNKNOWN", "top_confidence": 0.0, "latency_ms": 1}


def _engine(local=None, outline=False):
    config.VISION_API_KEY, config.VISION_API_BASE = "khoa-gia-123456", "https://x.invalid/v1"
    config.VISION_OUTLINE = outline
    e = v.VisionEngine()
    e.local = local
    return e


def test_fallback_to_local_when_api_fails():
    e = _engine(_Local())
    e._post = lambda b64: (_ for _ in ()).throw(v.VisionError("API hỏng"))        # type: ignore[assignment]
    out = e.infer_image(np.zeros((60, 80, 3), np.uint8), None, None)
    assert out["source"] == "local-fallback" and out["model_version"] == "convnext-t-leaf-v1"
    assert e.stats["api_fail"] == 1 and e.stats["fallback_used"] == 1


def test_no_fallback_raises():
    e = _engine(None)
    e._post = lambda b64: "không phải json"                                          # type: ignore[assignment]
    try:
        e.infer_image(np.zeros((60, 80, 3), np.uint8), None, None)
    except v.VisionError:
        return
    raise AssertionError("phải lỗi khi API hỏng và không có dự phòng")


def test_api_success_path_and_crop_box():
    import json
    e = _engine(None)
    seen = {}

    def fake_post(b64):
        seen["called"] = True
        return json.dumps({"cells": [{"r": r, "c": c, "label": "HEALTHY", "confidence": 0.9} for r in range(3) for c in range(3)]})
    e._post = fake_post                                                              # type: ignore[assignment]
    out = e.infer_image(np.zeros((600, 800, 3), np.uint8), (100, 100, 700, 500), None)
    assert seen["called"] and out["source"] == "vision-api" and out["top_label"] == "HEALTHY" and out["leaves"] == []
    assert len(out["tiles"]) == 9 and e.stats["api_ok"] == 1


def test_api_key_never_appears_in_error():
    import requests as rq
    e = _engine(None)

    class R:
        status_code = 401
        text = '{"error":"invalid key khoa-gia-123456"}'

    orig = rq.post
    rq.post = lambda *a, **k: R()                                                    # type: ignore[assignment]
    try:
        e._post("AAAA")
    except v.VisionError as ex:
        assert "khoa-gia-123456" not in str(ex) and "401" in str(ex)
    else:
        raise AssertionError("phải lỗi với HTTP 401")
    finally:
        rq.post = orig


if __name__ == "__main__":
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for f in fns:
        f()
        print("ok  ", f.__name__)
    print(f"{len(fns)}/{len(fns)} test đạt")
