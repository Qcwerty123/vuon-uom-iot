"""Gửi ảnh khay tới AI service rồi vẽ viền từng lá + nhãn lên ảnh.
Dùng: python viz_infer.py khay.jpg [ket_qua.jpg] [--url http://127.0.0.1:8001/v1/infer]"""
import argparse

import cv2
import numpy as np
import requests

COL = {"HEALTHY": (80, 190, 60), "YELLOW": (30, 200, 240), "SPOT": (50, 60, 230), "UNKNOWN": (170, 170, 170)}  # BGR
VN = {"HEALTHY": "Khoe", "YELLOW": "Vang la", "SPOT": "Dom la/Sau", "UNKNOWN": "?"}

ap = argparse.ArgumentParser()
ap.add_argument("src")
ap.add_argument("dst", nargs="?", default="ket_qua.jpg")
ap.add_argument("--url", default="http://127.0.0.1:8001/v1/infer")
a = ap.parse_args()
src, dst = a.src, a.dst
with open(src, "rb") as f:
    r = requests.post(a.url, files={"image": (src, f, "image/jpeg")}, timeout=120)
r.raise_for_status()
res = r.json()
img = cv2.imread(src); H, W = img.shape[:2]
out = img.copy(); ov = img.copy()
for lf in res["leaves"]:
    pts = np.array([[int(px * W), int(py * H)] for px, py in lf["polygon"]], np.int32)
    c = COL[lf["label"]]
    if lf["label"] in ("SPOT", "YELLOW"):
        cv2.fillPoly(ov, [pts], c)
    cv2.polylines(out, [pts], True, c, 3, cv2.LINE_AA)
out = cv2.addWeighted(ov, 0.35, out, 0.65, 0)
for lf in res["leaves"]:
    pts = np.array([[int(px * W), int(py * H)] for px, py in lf["polygon"]], np.int32)
    cx, cy = pts.mean(axis=0).astype(int)
    t = f'{VN[lf["label"]]} {int(lf["conf"] * 100)}%'
    (tw, th), _ = cv2.getTextSize(t, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
    cv2.rectangle(out, (cx - tw // 2 - 4, cy - th - 4), (cx + tw // 2 + 4, cy + 5), COL[lf["label"]], -1)
    cv2.putText(out, t, (cx - tw // 2, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
cv2.imwrite(dst, out)
print(f'{len(res["leaves"])} lá | {res["latency_ms"]} ms | top: {res["top_label"]} {res["top_confidence"]}')
print("Ô:", [(t["r"], t["c"], t["label"], t["n_leaves"]) for t in res["tiles"]])
print("Đã lưu", dst)
