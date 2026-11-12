"""Sinh ảnh khay cây giả (800×600, lưới 3×3) cho camera giả và smoke_wp07. Tất định (seed cố định).

  healthy.jpg  — 9 ô lá xanh trên nền đất xám
  sick.jpg     — như healthy nhưng ô (0,1) có đốm nâu, ô (1,2) vàng lá
  empty.jpg    — chỉ có đất (không lá)
Ảnh là đầu vào KIỂM THỬ (vẽ bằng PIL), không phải ảnh cây thật. Không commit (.gitignore).
Chạy: python tests/fixtures/make_images.py   (smoke_wp07 / cam_sim tự gọi nếu thiếu)
"""
from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

OUT = Path(__file__).resolve().parent / "images"
W, H = 800, 600
SOIL = (92, 84, 76)
GREEN = [(60, 140, 50), (70, 155, 60), (50, 125, 45)]
YELLOW = [(220, 200, 40), (230, 210, 60), (210, 185, 35)]
BROWN = (110, 60, 20)


def _tile_box(r: int, c: int) -> tuple[int, int, int, int]:
    return (c * W // 3, r * H // 3, (c + 1) * W // 3, (r + 1) * H // 3)


def _leaves(d: ImageDraw.ImageDraw, rnd: random.Random, box, colors, n: int = 7) -> list:
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    out = []
    for _ in range(n):
        lx, ly = cx + rnd.uniform(-60, 60), cy + rnd.uniform(-40, 40)
        rw, rh = rnd.uniform(35, 55), rnd.uniform(22, 34)
        e = (lx - rw, ly - rh, lx + rw, ly + rh)
        d.ellipse(e, fill=rnd.choice(colors))
        out.append(e)
    return out


def draw(sick: set[tuple[int, int, str]] | None = None, empty: bool = False, seed: int = 7) -> Image.Image:
    rnd = random.Random(seed)
    img = Image.new("RGB", (W, H), SOIL)
    d = ImageDraw.Draw(img)
    for _ in range(4000):  # hạt đất
        x, y = rnd.randrange(W), rnd.randrange(H)
        g = rnd.randint(-14, 14)
        d.point((x, y), fill=tuple(max(0, min(255, v + g)) for v in SOIL))
    for r in range(3):
        for c in range(3):
            box = _tile_box(r, c)
            d.rectangle(box, outline=(70, 66, 62), width=3)  # vách khay
            if empty:
                continue
            kind = next((k for (rr, cc, k) in (sick or set()) if (rr, cc) == (r, c)), None)
            leaves = _leaves(d, rnd, box, YELLOW if kind == "yellow" else GREEN)
            if kind == "spot":
                for e in leaves:
                    for _ in range(12):
                        sx = rnd.uniform(e[0] + 8, e[2] - 8)
                        sy = rnd.uniform(e[1] + 6, e[3] - 6)
                        s = rnd.uniform(5, 9)
                        d.ellipse((sx - s, sy - s, sx + s, sy + s), fill=BROWN)
    return img.filter(ImageFilter.GaussianBlur(0.8))


def ensure(force: bool = False) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = {
        "healthy.jpg": lambda: draw(),
        "sick.jpg": lambda: draw({(0, 1, "spot"), (1, 2, "yellow")}),
        "empty.jpg": lambda: draw(empty=True),
    }
    for name, fn in jobs.items():
        p = OUT / name
        if force or not p.exists():
            fn().save(p, "JPEG", quality=85)
    return OUT


if __name__ == "__main__":
    d = ensure(force=True)
    for p in sorted(d.glob("*.jpg")):
        print(f"{p.name}: {p.stat().st_size // 1024} KB")
