"""Kiểm thử luồng AI service bằng ảnh khay giả + mô hình GIẢ.

LƯU Ý: leaf.onnx giả có trọng số ngẫu nhiên, điểm phân loại của nó VÔ NGHĨA. Test chỉ kiểm tra LUỒNG
(đủ 9 ô, nhãn hợp lệ, crop_box, active_tiles, mã lỗi...), không kiểm tra độ đúng của nhãn.
mobile_sam.pt lấy từ runtime/ai/models (chỉ đọc; liên kết/sao chép vào thư mục tạm), không đụng models thật.

Chạy:  .venv\\Scripts\\python.exe tests\\test_infer.py        (hoặc pytest nếu đã cài)
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np
import requests

SERVICE = Path(__file__).resolve().parents[1]
REPO = SERVICE.parents[1]
REAL_SAM = REPO / "runtime" / "ai" / "models" / "mobile_sam.pt"
LABELS = {"HEALTHY", "YELLOW", "SPOT", "UNKNOWN"}
_servers: dict[str, tuple] = {}
_tmp = Path(tempfile.mkdtemp(prefix="ai-test-"))


def make_tray(w=800, h=600, seed=3) -> np.ndarray:
    """Nền đất nâu, 9 lá elip xanh rời nhau (1 lá vàng, 2 lá có đốm nâu)."""
    rng = np.random.default_rng(seed)
    img = np.zeros((h, w, 3), np.uint8)
    img[:] = (35, 60, 95)  # BGR nâu
    img = np.clip(img.astype(int) + rng.integers(-8, 8, img.shape), 0, 255).astype(np.uint8)
    for i in range(9):
        r, c = divmod(i, 3)
        cx, cy = int((c + 0.5) * w / 3), int((r + 0.5) * h / 3)
        col = (40, 160, 50)
        if i == 4:
            col = (30, 210, 220)  # vàng
        cv2.ellipse(img, (cx, cy), (55, 38), 25 * (i % 4), 0, 360, col, -1)
        if i in (2, 7):
            for dx, dy in ((-15, -5), (10, 10), (0, -15)):
                cv2.circle(img, (cx + dx, cy + dy), 7, (20, 40, 90), -1)
    return img


def jpg(img) -> bytes:
    return cv2.imencode(".jpg", img)[1].tobytes()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(kind: str):
    """kind: 'dummy' (leaf.onnx giả) hoặc 'empty' (thiếu mô hình)."""
    if kind in _servers:
        return _servers[kind][1]
    mdir = _tmp / f"models-{kind}"
    mdir.mkdir(exist_ok=True)
    if kind == "dummy":
        subprocess.run([sys.executable, str(SERVICE / "scripts" / "make_dummy_model.py"), str(mdir)], check=True)
        try:
            os.link(REAL_SAM, mdir / "mobile_sam.pt")
        except OSError:
            shutil.copy2(REAL_SAM, mdir / "mobile_sam.pt")
    port = _free_port()
    env = dict(os.environ, AI_MODEL_DIR=str(mdir), LOG_DIR=str(_tmp / "logs"), AI_MODE="model")
    p = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
                         cwd=SERVICE, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    for _ in range(240):
        try:
            requests.get(url + "/v1/health", timeout=1)
            break
        except requests.RequestException:
            time.sleep(0.5)
    _servers[kind] = (p, url)
    return url


def stop_servers():
    for p, _ in _servers.values():
        p.terminate()
    shutil.rmtree(_tmp, ignore_errors=True)


def post(url, data, **form):
    return requests.post(url + "/v1/infer", files={"image": ("t.jpg", data, "image/jpeg")}, data=form, timeout=120)


def check_tiles(res):
    assert len(res["tiles"]) == 9
    assert {(t["r"], t["c"]) for t in res["tiles"]} == {(r, c) for r in range(3) for c in range(3)}
    for t in res["tiles"]:
        assert t["label"] in LABELS
        assert set(t["probs"]) == {"HEALTHY", "YELLOW", "SPOT"}
        assert "n_leaves" in t
    assert res["top_label"] in LABELS and "latency_ms" in res and res["model_version"]


def test_health_ok():
    h = requests.get(start_server("dummy") + "/v1/health").json()
    assert h["status"] == "ok" and h["model_version"]


def test_infer_9_tiles_and_polygons():
    res = post(start_server("dummy"), jpg(make_tray())).json()
    check_tiles(res)
    assert len(res["leaves"]) >= 1
    for lf in res["leaves"]:
        assert lf["label"] in LABELS and len(lf["bbox"]) == 4
        assert all(0 <= v <= 1 for pt in lf["polygon"] for v in pt)


def test_empty_background_all_unknown():
    bg = np.full((600, 800, 3), (35, 60, 95), np.uint8)
    res = post(start_server("dummy"), jpg(bg)).json()
    check_tiles(res)
    assert all(t["label"] == "UNKNOWN" and t["conf"] == 0 and t["n_leaves"] == 0 for t in res["tiles"])
    assert res["leaves"] == []


def test_crop_box_and_active_tiles():
    url = start_server("dummy")
    res = post(url, jpg(make_tray()), crop_box=json.dumps([0, 0, 400, 300])).json()
    check_tiles(res)
    for lf in res["leaves"]:
        x, y, w, h = lf["bbox"]
        assert x + w <= 410 and y + h <= 310  # bbox theo pixel ảnh gốc, nằm trong vùng cắt
    res = post(url, jpg(make_tray()), active_tiles=json.dumps([[0, 0], [0, 1]])).json()
    check_tiles(res)
    for t in res["tiles"]:
        if (t["r"], t["c"]) not in ((0, 0), (0, 1)):
            assert t["label"] == "UNKNOWN" and t["conf"] == 0 and t["n_leaves"] == 0
    assert all(lf["tile"] in ([0, 0], [0, 1]) for lf in res["leaves"])


def test_bad_inputs_400():
    url = start_server("dummy")
    assert post(url, b"khong phai anh").status_code == 400
    assert post(url, jpg(make_tray()), crop_box="khong json").status_code == 400
    assert post(url, jpg(make_tray()), crop_box=json.dumps([2000, 2000, 3000, 3000])).status_code == 400
    assert post(url, jpg(make_tray()), active_tiles=json.dumps([[5, 5]])).status_code == 400


def test_too_large_413():
    assert post(start_server("dummy"), b"\xff\xd8" + b"0" * 5_100_000).status_code == 413


def test_missing_model_503():
    url = start_server("empty")
    assert requests.get(url + "/v1/health").json() == {**requests.get(url + "/v1/health").json(), "status": "no_model",
                                                       "model_version": None}
    r = post(url, jpg(make_tray()))
    assert r.status_code == 503
    msg = r.json()["message"]
    assert "mobile_sam.pt" in msg and "leaf.onnx" in msg


if __name__ == "__main__":
    if not REAL_SAM.exists():
        print("Thiếu runtime/ai/models/mobile_sam.pt — cần để chạy test.")
        sys.exit(2)
    fails = 0
    try:
        for name, fn in list(globals().items()):
            if name.startswith("test_") and callable(fn):
                try:
                    fn()
                    print("PASS", name)
                except Exception as e:  # noqa: BLE001
                    fails += 1
                    print("FAIL", name, repr(e))
    finally:
        stop_servers()
    print("Tổng:", "OK" if not fails else f"{fails} lỗi")
    sys.exit(1 if fails else 0)
