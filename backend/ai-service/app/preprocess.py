"""Tiền xử lý ảnh khay (đặc tả §15.4): cắt crop_box → lưới 3×3 → resize 224×224.

Chuẩn hóa: mô hình hiện tại (model.json) đã có sẵn lớp chuẩn hóa x/127.5 − 1 bên trong (kiểu MobileNetV2),
nên ô được trả về dạng float32 0..255. Nếu đổi sang mô hình cần chuẩn hóa ngoài thì sửa normalize().
"""
from __future__ import annotations

import io
import json

import numpy as np
from PIL import Image, ImageOps

GRID = 3
SIZE = (224, 224)


class BadInput(ValueError):
    pass


def open_image(data: bytes) -> Image.Image:
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as e:  # noqa: BLE001
        raise BadInput(f"không mở được ảnh: {e}") from e
    img = ImageOps.exif_transpose(img)
    return img.convert("RGB")


def parse_crop_box(raw: str | None, w: int, h: int) -> tuple[int, int, int, int] | None:
    """crop_box là JSON [x0, y0, x1, y1] theo pixel của ảnh gốc (quy ước hộp của PIL).
    Nếu cả 4 số trong [0, 1] thì hiểu là tỉ lệ theo kích thước ảnh."""
    if raw is None or str(raw).strip() in ("", "null", "None"):
        return None
    try:
        v = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(v, dict):
            v = [v["x0"], v["y0"], v["x1"], v["y1"]]
        x0, y0, x1, y1 = (float(t) for t in v)
    except Exception as e:  # noqa: BLE001
        raise BadInput("crop_box phải là JSON [x0, y0, x1, y1]") from e
    if all(0 <= t <= 1 for t in (x0, y0, x1, y1)):
        x0, x1, y0, y1 = x0 * w, x1 * w, y0 * h, y1 * h
    box = (max(0, int(round(x0))), max(0, int(round(y0))), min(w, int(round(x1))), min(h, int(round(y1))))
    if box[2] - box[0] < GRID * 8 or box[3] - box[1] < GRID * 8:
        raise BadInput("crop_box quá nhỏ hoặc nằm ngoài ảnh")
    return box


def parse_active_tiles(raw: str | None) -> set[tuple[int, int]] | None:
    """active_tiles là JSON [[r, c], ...] (giống abnormal_tiles) hoặc [chỉ số 0..8 theo hàng]. Không có = cả 9 ô."""
    if raw is None or str(raw).strip() in ("", "null", "None"):
        return None
    try:
        v = json.loads(raw) if isinstance(raw, str) else raw
        out: set[tuple[int, int]] = set()
        for t in v:
            r, c = (int(t[0]), int(t[1])) if isinstance(t, (list, tuple)) else divmod(int(t), GRID)
            if not (0 <= r < GRID and 0 <= c < GRID):
                raise ValueError
            out.add((r, c))
    except Exception as e:  # noqa: BLE001
        raise BadInput("active_tiles phải là JSON [[r, c], ...] với r, c trong 0..2") from e
    return out


def split_grid(img: Image.Image) -> list[tuple[int, int, Image.Image]]:
    w, h = img.size
    xs = [round(i * w / GRID) for i in range(GRID + 1)]
    ys = [round(i * h / GRID) for i in range(GRID + 1)]
    return [(r, c, img.crop((xs[c], ys[r], xs[c + 1], ys[r + 1]))) for r in range(GRID) for c in range(GRID)]


def normalize(tile: Image.Image) -> np.ndarray:
    return np.asarray(tile.resize(SIZE, Image.BILINEAR), dtype=np.float32)


def prepare(data: bytes, crop_box: str | None, active_tiles: str | None):
    """Trả về (danh sách (r, c, ô PIL đã resize), tập ô active hoặc None)."""
    img = open_image(data)
    box = parse_crop_box(crop_box, *img.size)
    if box:
        img = img.crop(box)
    active = parse_active_tiles(active_tiles)
    tiles = [(r, c, t.resize(SIZE, Image.BILINEAR)) for r, c, t in split_grid(img)]
    return tiles, active
