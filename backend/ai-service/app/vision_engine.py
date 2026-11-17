"""Engine 'vision-api' (AI_MODE=vision-api): gửi CẢ ẢNH cho mô hình ngôn ngữ nhìn ảnh qua API tương thích OpenAI
(POST {VISION_API_BASE}/chat/completions) và nhận nhãn cho từng ô 3x3. Trả về đúng hợp đồng /v1/infer như LeafEngine
nhưng không có `leaves` (không có viền từng lá). Lỗi API / hết hạn mức / JSON sai thì rơi về mô hình cục bộ (nếu nạp được).

Quyền riêng tư: chỉ gửi ảnh (đã cắt theo crop_box, thu nhỏ) và một câu lệnh chung; KHÔNG gửi mã thiết bị, đường dẫn,
tên người dùng hay bất kỳ siêu dữ liệu nào. Khóa API chỉ nằm trong header Authorization và không bao giờ được log.
"""
from __future__ import annotations

import base64
import json
import logging
import re
import time

import cv2
import numpy as np
import requests

from . import config

log = logging.getLogger("ai.vision")

GRID = 3
ABNORMAL = ("YELLOW", "SPOT")
OUT_CLASSES = ("HEALTHY", "YELLOW", "SPOT")
MODEL_LABELS = {"HEALTHY", "YELLOW", "SPOT", "NONE", "UNSURE"}

SYSTEM_PROMPT = (
    "You inspect ONE photo of a small nursery tray of Malabar spinach (mồng tơi, Basella alba) taken by a fixed, "
    "low-resolution camera. The photo carries an overlay: thin yellow lines split it into a 3x3 grid and each cell "
    "has a small label 'r,c' (row 0..2 from top to bottom, column 0..2 from left to right). The lines and labels are "
    "annotations, NOT part of the scene and NOT a symptom.\n\n"
    "For EACH of the 9 cells decide what is visible and give one label:\n"
    "- HEALTHY: plant leaves that look normal and green.\n"
    "- YELLOW: clear yellowing (chlorosis) on leaves.\n"
    "- SPOT: clear spots, brown or black lesions, holes or insect damage on leaves.\n"
    "- NONE: no plant leaves in that cell (soil, pot, wall, floor, clothes, furniture, other objects).\n"
    "- UNSURE: a plant is there but it is too blurry, dark, covered or cut off to judge.\n"
    "Give confidence from 0 to 1 for the label, based only on what is visible.\n\n"
    "Rules: shadows, dark or shaded areas, leaf veins, leaves cut by the image border, soil, water drops and "
    "reflections are NOT disease. Report YELLOW or SPOT only when the symptom is clearly visible on a leaf inside "
    "that cell; if a cell contains both healthy and diseased leaves, report the disease. If you cannot tell, use "
    "UNSURE instead of guessing a disease. Never invent plants that are not in the photo.\n\n"
    "Reply with JSON only (no markdown, no extra text) in exactly this shape, with all 9 cells:\n"
    '{"cells":[{"r":0,"c":0,"label":"HEALTHY","confidence":0.9,"reason":"max 8 words"}]}'
)


OUTLINE_PROMPT = (
    "You analyse ONE photo of a small tray of Malabar spinach (mồng tơi) from a fixed low-resolution camera.\n"
    "Find every distinct leaf of the plant that is clearly visible and return its outline.\n"
    "For each leaf give: label, confidence, complete and polygon. Return at most the 14 largest leaves.\n"
    "- label: HEALTHY (normal green), YELLOW (clear yellowing), SPOT (clear spots, brown lesions, holes or insect damage).\n"
    "- confidence: 0 to 1, based only on what is visible.\n"
    "- complete: true only if the whole leaf is visible; false if it is cut by the image border, mostly covered by other "
    "leaves, or too dark or blurry to judge. Do NOT call a leaf diseased just because it is shaded, cut off or covered.\n"
    "- polygon: 6 to 9 [x, y] points, integers 0..1000 (fraction of image width/height x1000), following the visible "
    "edge of the leaf in order.\n"
    "Skip tiny leaves (under about 1% of the image). If there is no plant in the photo return an empty list. "
    'Reply with JSON only: {"leaves":[{"label":"HEALTHY","confidence":0.9,"complete":true,"polygon":[[x,y],...]}]}'
)
MAX_LEAVES = 30
MIN_LEAF_AREA = 0.002          # phần diện tích ảnh; nhỏ hơn thì bỏ (polygon suy biến)


class VisionError(RuntimeError):
    """Lỗi gọi API hoặc kết quả không dùng được (khiến engine rơi về mô hình cục bộ)."""


def annotate_grid(bgr: np.ndarray) -> np.ndarray:
    """Vẽ lưới 3x3 mảnh màu vàng và nhãn 'r,c' để mô hình xác định đúng ô (LLM kém chia ảnh theo lưới nếu không có mốc)."""
    h, w = bgr.shape[:2]
    out = bgr.copy()
    for i in (1, 2):
        x, y = round(w * i / GRID), round(h * i / GRID)
        cv2.line(out, (x, 0), (x, h - 1), (0, 255, 255), 1, cv2.LINE_AA)
        cv2.line(out, (0, y), (w - 1, y), (0, 255, 255), 1, cv2.LINE_AA)
    scale = max(0.5, min(w, h) / 900)
    for r in range(GRID):
        for c in range(GRID):
            org = (round(w * c / GRID) + 6, round(h * r / GRID) + int(22 * scale))
            text = f"{r},{c}"
            cv2.putText(out, text, org, cv2.FONT_HERSHEY_SIMPLEX, 0.7 * scale, (0, 0, 0), 3, cv2.LINE_AA)
            cv2.putText(out, text, org, cv2.FONT_HERSHEY_SIMPLEX, 0.7 * scale, (0, 255, 255), 1, cv2.LINE_AA)
    return out


def encode_image(bgr: np.ndarray, max_side: int, draw_grid: bool) -> str:
    h, w = bgr.shape[:2]
    s = min(1.0, max_side / max(h, w))
    if s < 1:
        bgr = cv2.resize(bgr, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    if draw_grid:
        bgr = annotate_grid(bgr)
    ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 88])
    if not ok:
        raise VisionError("không mã hóa được ảnh")
    return base64.b64encode(buf.tobytes()).decode("ascii")


def extract_json(text: str) -> dict:
    """Mô hình hay bọc JSON trong khối ```json ... ```; lấy phần JSON đầu tiên."""
    t = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if m:
        t = m.group(1).strip()
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j <= i:
        raise VisionError("phản hồi không có JSON")
    try:
        obj = json.loads(t[i:j + 1])
    except ValueError as e:
        raise VisionError(f"JSON sai định dạng: {e}") from e
    if not isinstance(obj, dict):
        raise VisionError("JSON không phải đối tượng")
    return obj


def parse_cells(obj: dict) -> dict[tuple[int, int], tuple[str, float, str]]:
    """{(r, c): (nhãn mô hình, độ tin cậy 0..1, lý do)}; bỏ ô sai định dạng. Cần ít nhất 5 ô hợp lệ."""
    cells = obj.get("cells")
    if not isinstance(cells, list):
        raise VisionError("thiếu mảng 'cells'")
    out: dict[tuple[int, int], tuple[str, float, str]] = {}
    for it in cells:
        if not isinstance(it, dict):
            continue
        try:
            r, c = int(it["r"]), int(it["c"])
            label = str(it["label"]).strip().upper()
        except (KeyError, TypeError, ValueError):
            continue
        if not (0 <= r < GRID and 0 <= c < GRID) or label not in MODEL_LABELS:
            continue
        try:
            conf = float(it.get("confidence", 0.5))
        except (TypeError, ValueError):
            conf = 0.5
        if conf > 1:                       # có mô hình trả phần trăm
            conf = conf / 100 if conf <= 100 else 1.0
        conf = min(1.0, max(0.0, conf))
        out[(r, c)] = (label, conf, str(it.get("reason", ""))[:80])
    if len(out) < 5:
        raise VisionError(f"chỉ có {len(out)}/9 ô hợp lệ")
    return out


def _norm_conf(raw) -> float:
    try:
        conf = float(raw)
    except (TypeError, ValueError):
        conf = 0.5
    if conf > 1:
        conf = conf / 100 if conf <= 100 else 1.0
    return min(1.0, max(0.0, conf))


def _area(pts: list[list[float]]) -> float:
    s = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2


def parse_leaves(obj: dict) -> list[dict]:
    """[{label, conf, complete, polygon[[x,y]...] chuẩn hóa 0..1 theo ảnh gửi đi}]; bỏ lá sai định dạng hoặc quá nhỏ."""
    lv = obj.get("leaves")
    if not isinstance(lv, list):
        raise VisionError("thiếu mảng 'leaves'")
    out = []
    for it in lv:
        if not isinstance(it, dict):
            continue
        label = str(it.get("label", "")).strip().upper()
        poly = it.get("polygon")
        if label not in OUT_CLASSES or not isinstance(poly, list) or len(poly) < 3:
            continue
        try:
            raw = [(float(p[0]), float(p[1])) for p in poly]
        except (TypeError, ValueError, IndexError):
            continue
        scale = 1.0 if max(max(x, y) for x, y in raw) <= 1.0 else 1000.0     # có model trả 0..1 thay vì 0..1000
        pts = [[min(1.0, max(0.0, x / scale)), min(1.0, max(0.0, y / scale))] for x, y in raw]
        if _area(pts) < MIN_LEAF_AREA:
            continue
        out.append({"label": label, "conf": _norm_conf(it.get("confidence", 0.5)),
                    "complete": it.get("complete", True) is not False, "polygon": pts})
    return out[:MAX_LEAVES]


def tiles_from_leaves(leaves: list[dict], active: set | None, conf_unknown: float,
                      origin: tuple[int, int], size: tuple[int, int]) -> tuple[list[dict], list[dict]]:
    """Gán lá vào ô 3x3 theo tâm lá (như mô hình cục bộ). Lá không đủ (bị cắt/che) hoặc conf thấp -> UNKNOWN, không tính bệnh.
    origin/size: góc trên-trái và kích thước (W, H) của vùng đã cắt theo pixel ảnh gốc, để tính bbox."""
    ox, oy = origin
    W, H = size
    per: dict[tuple[int, int], list[dict]] = {(r, c): [] for r in range(GRID) for c in range(GRID)}
    out_leaves = []
    for l in leaves:
        poly = l["polygon"]
        cx = sum(p[0] for p in poly) / len(poly)
        cy = sum(p[1] for p in poly) / len(poly)
        r, c = min(GRID - 1, int(cy * GRID)), min(GRID - 1, int(cx * GRID))
        if active is not None and (r, c) not in active:
            continue
        label = l["label"] if (l["complete"] and l["conf"] >= conf_unknown) else "UNKNOWN"
        xs, ys = [p[0] for p in poly], [p[1] for p in poly]
        out_leaves.append({"tile": [r, c], "label": label, "conf": round(l["conf"], 3),
                           "bbox": [round(ox + min(xs) * W), round(oy + min(ys) * H),
                                    round((max(xs) - min(xs)) * W), round((max(ys) - min(ys)) * H)],
                           "polygon": [[round(x, 4), round(y, 4)] for x, y in poly]})
        per[(r, c)].append({"label": label, "conf": l["conf"]})
    tiles = []
    for (r, c), ls in per.items():
        zero = {k: 0.0 for k in OUT_CLASSES}
        if active is not None and (r, c) not in active:
            tiles.append({"r": r, "c": c, "label": "UNKNOWN", "conf": 0.0, "probs": zero, "n_leaves": 0, "active": False})
            continue
        bad = [t for t in ls if t["label"] in ABNORMAL]
        good = [t for t in ls if t["label"] == "HEALTHY"]
        if bad:                                       # một lá bệnh đủ để ô bất thường
            t = max(bad, key=lambda t: t["conf"])
        elif good:
            t = min(good, key=lambda t: t["conf"])    # thận trọng: lấy lá kém chắc nhất
        elif ls:
            t = {"label": "UNKNOWN", "conf": max(x["conf"] for x in ls)}
        else:
            t = {"label": "UNKNOWN", "conf": 0.0}
        if t["label"] in OUT_CLASSES:
            rest = (1 - t["conf"]) / 2
            probs = {k: round(t["conf"] if k == t["label"] else rest, 4) for k in OUT_CLASSES}
        else:
            probs = zero
        tiles.append({"r": r, "c": c, "label": t["label"], "conf": round(t["conf"], 4), "probs": probs, "n_leaves": len(ls)})
    return tiles, out_leaves


def build_tiles(parsed: dict, active: set | None, conf_unknown: float) -> list[dict]:
    tiles = []
    for r in range(GRID):
        for c in range(GRID):
            zero = {k: 0.0 for k in OUT_CLASSES}
            if active is not None and (r, c) not in active:     # ô không có cây theo cấu hình camera
                tiles.append({"r": r, "c": c, "label": "UNKNOWN", "conf": 0.0, "probs": zero, "active": False})
                continue
            if (r, c) not in parsed:
                tiles.append({"r": r, "c": c, "label": "UNKNOWN", "conf": 0.0, "probs": zero,
                              "note": "thiếu trong phản hồi"})
                continue
            label, conf, note = parsed[(r, c)]
            if label == "NONE":
                tiles.append({"r": r, "c": c, "label": "UNKNOWN", "conf": 0.0, "probs": zero, "note": note or "không có cây"})
            elif label == "UNSURE":
                tiles.append({"r": r, "c": c, "label": "UNKNOWN", "conf": round(conf, 4),
                              "probs": {k: round(1 / 3, 4) for k in OUT_CLASSES}, "note": note or "không rõ"})
            else:
                rest = (1 - conf) / 2
                probs = {k: round(conf if k == label else rest, 4) for k in OUT_CLASSES}
                lab = "UNKNOWN" if conf < conf_unknown else label
                tiles.append({"r": r, "c": c, "label": lab, "conf": round(conf, 4), "probs": probs, "note": note})
    return tiles


def pick_top(tiles: list[dict]) -> tuple[str, float]:
    """Ô bất thường (YELLOW/SPOT) tin cậy cao nhất; không có thì HEALTHY cao nhất; không có nữa thì UNKNOWN."""
    live = [t for t in tiles if t.get("active", True)]
    for group in (ABNORMAL, ("HEALTHY",)):
        cand = [t for t in live if t["label"] in group]
        if cand:
            best = max(cand, key=lambda t: t["conf"])
            return best["label"], best["conf"]
    return "UNKNOWN", max((t["conf"] for t in live), default=0.0)


class VisionEngine:
    kind = "vision-api"

    def __init__(self) -> None:
        self.ready = False
        self.reason = ""
        self.model_version = ("vlm-" + config.VISION_MODEL)[:30]      # cột DB model_version tối đa 30 ký tự
        self.local = None                                             # mô hình cục bộ làm dự phòng
        self.stats = {"api_ok": 0, "api_fail": 0, "fallback_used": 0}

    # ---- khởi động ----
    def load(self) -> None:
        if not config.VISION_API_KEY or not config.VISION_API_BASE:
            self.reason = "Thiếu VISION_API_KEY hoặc VISION_API_BASE trong .env"
            log.warning(self.reason)
        elif not config.VISION_API_BASE.startswith("https://"):
            log.warning("VISION_API_BASE không dùng https:// (khóa API và ảnh sẽ đi không mã hóa)")
        if config.VISION_FALLBACK == "local":
            try:
                from .engine import LeafEngine  # noqa: PLC0415 — nạp chậm (torch)
                eng = LeafEngine()
                eng.load()
                if eng.ready:
                    self.local = eng
                else:
                    log.warning("Mô hình cục bộ dự phòng không sẵn sàng: %s", eng.reason)
            except Exception:  # noqa: BLE001
                log.exception("Không nạp được mô hình cục bộ dự phòng")
        self.ready = bool(config.VISION_API_KEY and config.VISION_API_BASE) or self.local is not None
        if not self.ready and not self.reason:
            self.reason = "API vision và mô hình cục bộ đều không sẵn sàng"
        log.info("Vision engine: model=%s base=%s fallback=%s ready=%s", config.VISION_MODEL,
                 config.VISION_API_BASE.split("//")[-1].split("/")[0], "local" if self.local else "không", self.ready)

    def health_extra(self) -> dict:
        return {"vision_model": config.VISION_MODEL, "fallback": "local" if self.local else "none", **self.stats}

    # ---- gọi API ----
    def _post(self, b64: str, system: str = SYSTEM_PROMPT,
              user_text: str = "Analyze this tray photo and return the JSON for all 9 cells.") -> str:
        url = config.VISION_API_BASE + "/chat/completions"
        headers = {"Authorization": f"Bearer {config.VISION_API_KEY}", "Content-Type": "application/json"}
        base = {
            "model": config.VISION_MODEL,
            "max_tokens": 8000,        # gồm cả token suy luận của mô hình
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}},
                ]},
            ],
        }
        extras = {"response_format": {"type": "json_object"}, "temperature": 0}
        timeout = (5, config.VISION_TIMEOUT_S)
        r = None
        for payload in ({**base, **extras}, base):     # lần 2: bỏ tham số tùy chọn nếu gateway từ chối
            try:
                r = requests.post(url, headers=headers, json=payload, timeout=timeout)
            except requests.RequestException as e:
                raise VisionError(f"không gọi được API: {type(e).__name__}") from e
            if r.status_code not in (400, 422) or payload is base:
                break
        assert r is not None
        if r.status_code != 200:
            body = r.text.replace(config.VISION_API_KEY, "***")[:200]
            raise VisionError(f"API trả HTTP {r.status_code}: {body}")
        try:
            data = r.json()
            ch = data["choices"][0]
            content = ch["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as e:
            raise VisionError("API trả JSON không đúng cấu trúc chat/completions") from e
        if not isinstance(content, str) or not content.strip():
            raise VisionError(f"phản hồi rỗng (finish_reason={ch.get('finish_reason')})")
        return content

    def _via_api(self, bgr, active, origin: tuple[int, int] = (0, 0)) -> dict:
        t0 = time.perf_counter()
        leaves_out: list[dict] = []
        if config.VISION_OUTLINE:     # mô hình vẽ viền từng lá; nhãn ô suy ra từ các lá
            b64 = encode_image(bgr, config.VISION_MAX_SIDE, False)
            leaves = parse_leaves(extract_json(self._post(b64, OUTLINE_PROMPT, "Return the JSON.")))
            h, w = bgr.shape[:2]
            tiles, leaves_out = tiles_from_leaves(leaves, active, config.CONF_UNKNOWN, origin, (w, h))
        else:                         # chỉ nhãn 9 ô (nhanh hơn)
            b64 = encode_image(bgr, config.VISION_MAX_SIDE, config.VISION_DRAW_GRID)
            tiles = build_tiles(parse_cells(extract_json(self._post(b64))), active, config.CONF_UNKNOWN)
        top_label, top_conf = pick_top(tiles)
        return {"tiles": tiles, "leaves": leaves_out, "top_label": top_label, "top_confidence": round(top_conf, 4),
                "latency_ms": int((time.perf_counter() - t0) * 1000), "source": "vision-api"}

    # ---- giao diện chung với LeafEngine ----
    def infer_image(self, bgr, crop_box, active):
        region, origin = bgr, (0, 0)
        if crop_box:
            x0, y0, x1, y1 = crop_box
            region, origin = bgr[y0:y1, x0:x1], (x0, y0)
        if config.VISION_API_KEY and config.VISION_API_BASE:
            try:
                out = self._via_api(region, active, origin)
                self.stats["api_ok"] += 1
                return out
            except VisionError as e:
                self.stats["api_fail"] += 1
                log.warning("Vision API lỗi: %s", e)
        if self.local is not None:
            self.stats["fallback_used"] += 1
            out = self.local.infer_image(bgr, crop_box, active)
            out["model_version"] = self.local.model_version     # ghi đúng mô hình đã chạy, không gán nhầm là vision
            out["source"] = "local-fallback"
            return out
        raise VisionError("API vision lỗi và không có mô hình cục bộ dự phòng")
