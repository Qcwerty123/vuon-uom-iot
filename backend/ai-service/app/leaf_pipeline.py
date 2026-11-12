"""Tách từng lá bằng MobileSAM, phân loại bằng ConvNeXt-Tiny (ONNX), gộp về lưới 3x3."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

GRID = 3
DEFAULT_CLASSES = ["HEALTHY", "SPOT", "YELLOW", "PEST"]   # thứ tự LABELS lúc train; model_meta.json (nếu có) được ưu tiên
LABEL_MAP = {"HEALTHY": "HEALTHY", "SPOT": "SPOT", "YELLOW": "YELLOW",
             "PEST": "SPOT"}                       # hợp đồng có 3 nhãn: gộp PEST vào SPOT
OUT_CLASSES = ("HEALTHY", "YELLOW", "SPOT")
ABNORMAL = {"SPOT", "YELLOW"}
UNKNOWN_T = float(os.environ.get("AI_CONF_UNKNOWN") or 0.6)
MAX_LEAVES = 30
MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)


class ModelError(RuntimeError):
    pass


def crop_leaf(bgr, mask, size=224, bg=128):
    """Cắt một lá: nền ngoài lá = xám, đệm vuông, resize. DÙNG CHUNG cho train và suy luận."""
    ys, xs = np.where(mask)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    crop = bgr[y0:y1, x0:x1].copy()
    crop[~mask[y0:y1, x0:x1]] = bg
    h, w = crop.shape[:2]
    s = max(h, w)
    sq = np.full((s, s, 3), bg, np.uint8)
    sq[(s - h) // 2:(s - h) // 2 + h, (s - w) // 2:(s - w) // 2 + w] = crop
    return cv2.resize(sq, (size, size), interpolation=cv2.INTER_AREA), (int(x0), int(y0), int(x1 - x0), int(y1 - y0))


def load_classes(meta_path, n_out: int) -> list[str]:
    classes = list(DEFAULT_CLASSES)
    if meta_path and Path(meta_path).exists():
        try:
            classes = list(json.loads(Path(meta_path).read_text(encoding="utf-8-sig"))["classes"])
        except Exception as e:  # noqa: BLE001
            raise ModelError(f"model_meta.json không đọc được hoặc thiếu khóa 'classes': {e}") from e
    if len(classes) != n_out:
        raise ModelError(f"Số lớp không khớp: model_meta.json/mặc định có {len(classes)} lớp {classes}, "
                         f"nhưng leaf.onnx xuất {n_out} lớp.")
    unknown = [c for c in classes if c not in LABEL_MAP]
    if unknown:
        raise ModelError(f"Lớp {unknown} không có trong LABEL_MAP {sorted(LABEL_MAP)}.")
    return classes


class LeafPipeline:
    def __init__(self, sam_ckpt, onnx_path, meta_path=None, device="cpu",
                 min_frac=0.004, max_frac=0.12, work_long_side=800):
        from mobile_sam import sam_model_registry, SamPredictor
        sam = sam_model_registry["vit_t"](checkpoint=str(sam_ckpt)).to(device).eval()
        self.pred = SamPredictor(sam)
        self.sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
        inp, out = self.sess.get_inputs()[0], self.sess.get_outputs()[0]
        self.input_name = inp.name
        n_out = out.shape[-1]
        if not isinstance(n_out, int):
            raise ModelError(f"leaf.onnx có đầu ra không xác định số lớp: {out.shape}")
        self.classes = load_classes(meta_path, n_out)
        self.min_frac, self.max_frac, self.long = min_frac, max_frac, work_long_side

    @staticmethod
    def _seeds(bgr):
        """Mỗi lá một điểm gợi ý: đỉnh của distance transform trên mặt nạ màu lá.
        Lá dính nhau vẫn có đỉnh riêng (giống watershed)."""
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        leafy = ((hsv[..., 0] > 15) & (hsv[..., 0] < 95) & (hsv[..., 1] > 35)).astype(np.uint8) * 255
        leafy = cv2.morphologyEx(leafy, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))   # lấp đốm bệnh
        leafy = cv2.morphologyEx(leafy, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        dist = cv2.distanceTransform(leafy, cv2.DIST_L2, 5)
        k = max(12, int(0.03 * max(bgr.shape[:2])))
        peaks = (dist == cv2.dilate(dist, np.ones((2 * k + 1, 2 * k + 1), np.uint8))) & (dist > 0.012 * max(bgr.shape[:2]))
        n, _, _, cent = cv2.connectedComponentsWithStats(peaks.astype(np.uint8), connectivity=8)
        seeds = [(int(round(cx)), int(round(cy))) for cx, cy in cent[1:]]     # bỏ nền (nhãn 0)
        return leafy > 0, seeds

    def extract(self, bgr):
        H, W = bgr.shape[:2]
        leafy, seeds = self._seeds(bgr)
        if not seeds:
            return []
        self.pred.set_image(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))      # bộ mã hóa chạy 1 lần
        cands = []
        for i, (x, y) in enumerate(seeds):
            near = sorted((float(np.hypot(p[0] - x, p[1] - y)), p) for j, p in enumerate(seeds) if j != i)
            others = [p for d, p in near if near and d <= 1.6 * near[0][0]][:3]   # tối đa 3 điểm âm gần nhất
            pts = np.array([[x, y]] + others, dtype=np.float32)
            lbl = np.array([1] + [0] * len(others))
            masks, scores, _ = self.pred.predict(point_coords=pts, point_labels=lbl, multimask_output=True)
            best = None
            for m, sc in zip(masks, scores):
                a = int(m.sum())
                if not (self.min_frac * H * W < a < self.max_frac * H * W):
                    continue
                if (m & leafy).sum() < 0.7 * a or sc < 0.8:          # phải chủ yếu là màu lá
                    continue
                if best is None or sc > best[2]:                     # lấy mask SAM tự tin nhất
                    best = (a, m, sc)
            if best is not None:
                m = best[1].astype(np.uint8)                          # bỏ mảnh rời: giữ vùng liền lớn nhất
                n, cc, st, _ = cv2.connectedComponentsWithStats(m)
                if n > 2:
                    m = (cc == 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))).astype(np.uint8)
                cands.append((int(m.sum()), m.astype(bool), best[2]))
        out = []
        for a, seg, _ in sorted(cands, key=lambda t: -t[0]):
            if len(out) >= MAX_LEAVES:                                # giữ tối đa 30 lá lớn nhất
                break
            # bỏ mask trùng một lá đã nhận (hai điểm gợi ý rơi vào cùng một lá)
            if any(np.logical_and(seg, o["mask"]).sum() > 0.6 * a for o in out):
                continue
            img, bbox = crop_leaf(bgr, seg)
            out.append({"mask": seg, "img": img, "bbox": bbox})
        return out

    def classify(self, crops):
        if not crops:
            return np.zeros((0, len(self.classes)), np.float32)
        x = np.stack([(cv2.cvtColor(c, cv2.COLOR_BGR2RGB).astype(np.float32) / 255 - MEAN) / STD for c in crops])
        logits = self.sess.run(None, {self.input_name: x.transpose(0, 3, 1, 2).astype(np.float32)})[0]
        e = np.exp(logits - logits.max(1, keepdims=True))
        return e / e.sum(1, keepdims=True)

    def infer(self, bgr, crop_box=None, active_tiles=None):
        """crop_box: (x0, y0, x1, y1) pixel ảnh gốc, đã kiểm tra; active_tiles: tập {(r, c)} hoặc None."""
        t0 = time.time()
        ox = oy = 0
        if crop_box:
            x0, y0, x1, y1 = crop_box
            bgr, ox, oy = bgr[y0:y1, x0:x1], x0, y0
        H, W = bgr.shape[:2]
        s = min(1.0, self.long / max(H, W))
        small = cv2.resize(bgr, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) if s < 1 else bgr
        leaves = self.extract(small)
        probs = self.classify([l["img"] for l in leaves])
        h2, w2 = small.shape[:2]
        tiles = {(r, c): [] for r in range(GRID) for c in range(GRID)}
        out_leaves = []
        for l, p in zip(leaves, probs):
            x, y, w, h = l["bbox"]
            r = min(GRID - 1, int((y + h / 2) / h2 * GRID))
            c = min(GRID - 1, int((x + w / 2) / w2 * GRID))
            if active_tiles is not None and (r, c) not in active_tiles:
                continue                                              # ô không có cây: bỏ lá
            merged = {k: 0.0 for k in OUT_CLASSES}
            for ci, cn in enumerate(self.classes):
                merged[LABEL_MAP[cn]] += float(p[ci])                 # gộp xác suất PEST vào SPOT
            lab = max(merged, key=merged.get)
            conf = merged[lab]
            if conf < UNKNOWN_T:
                lab = "UNKNOWN"
            tiles[(r, c)].append({"label": lab, "conf": conf, "probs": merged})
            cs, _ = cv2.findContours(l["mask"].astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cnt = max(cs, key=cv2.contourArea)
            cnt = cv2.approxPolyDP(cnt, 0.01 * cv2.arcLength(cnt, True), True)
            poly = [[round(min(1.0, max(0.0, float(px) / w2)), 4), round(min(1.0, max(0.0, float(py) / h2)), 4)]
                    for px, py in cnt[:, 0]]
            out_leaves.append({"tile": [r, c], "label": lab, "conf": round(conf, 3),
                               "bbox": [int(x / s) + ox, int(y / s) + oy, int(w / s), int(h / s)],
                               "polygon": poly})
        res = []
        for (r, c), ls in tiles.items():
            active = active_tiles is None or (r, c) in active_tiles
            bad = [t for t in ls if t["label"] in ABNORMAL]
            good = [t for t in ls if t["label"] == "HEALTHY"]
            if bad:                                    # một lá bệnh là đủ để ô bất thường
                t = max(bad, key=lambda t: t["conf"])
            elif good:
                t = min(good, key=lambda t: t["conf"])  # thận trọng: lấy lá kém chắc nhất
            elif ls:                                   # chỉ có lá không chắc chắn
                t = {"label": "UNKNOWN", "conf": max(t["conf"] for t in ls), "probs": ls[0]["probs"]}
            else:
                t = {"label": "UNKNOWN", "conf": 0.0, "probs": {k: 0.0 for k in OUT_CLASSES}}
            res.append({"r": r, "c": c, "label": t["label"], "conf": round(t["conf"], 3),
                        "probs": {k: round(v, 3) for k, v in t["probs"].items()},
                        "n_leaves": len(ls), "active": active})
        cand = [t for t in res if t["active"]]
        ab = [t for t in cand if t["label"] in ABNORMAL]
        top = max(ab or cand, key=lambda t: t["conf"]) if cand else None
        for t in res:
            del t["active"]
        return {"tiles": res, "leaves": out_leaves,
                "top_label": top["label"] if top else "UNKNOWN",
                "top_confidence": top["conf"] if top else 0.0,
                "latency_ms": int((time.time() - t0) * 1000)}
