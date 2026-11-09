"""Cấu hình AI service, đọc .env ở gốc repo (đặc tả §17.6). Biến môi trường của tiến trình được ưu tiên.

Tiến trình do start.ps1 khởi động qua WMI không thừa hưởng biến môi trường của cửa sổ PowerShell,
nên dịch vụ tự đọc .env giống backend.
"""
from __future__ import annotations

import os
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[3]


def _read_env_file() -> dict[str, str]:
    env: dict[str, str] = {}
    p = REPO / ".env"
    if not p.exists():
        return env
    for raw in p.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip()
        if v[:1] in "\"'" and v[:1] in v[1:]:
            v = v[1: v.index(v[0], 1)]
        else:
            v = v.split()[0] if v else ""
        env[k.strip()] = v
    return env


_FILE = _read_env_file()


def get(key: str, default: str = "") -> str:
    return os.environ.get(key) or _FILE.get(key) or default


def repo_path(rel: str) -> Path:
    p = Path(rel)
    return p if p.is_absolute() else REPO / p


MODE = get("AI_MODE", "model").strip().lower()          # model | stub
MODEL_DIR = repo_path(get("AI_MODEL_DIR", "runtime/ai/models"))
CONF_UNKNOWN = float(get("AI_CONF_UNKNOWN", "0.6"))
# Tùy chọn NGOÀI đặc tả, mặc định tắt (0): nếu tổng xác suất các lớp Tomato___* của mô hình gốc < ngưỡng này
# thì gán UNKNOWN (ô đất/khay bị mô hình coi là cây khác). Xem báo cáo WP-07 mục "Lệch đặc tả".
MIN_TOMATO_MASS = float(get("AI_MIN_TOMATO_MASS", "0"))
LOG_DIR = repo_path(get("LOG_DIR", "logs/services"))
MANIFEST = SERVICE_DIR / "model.json"
LABEL_MAP = SERVICE_DIR / "label_map.json"
MAX_IMAGE_BYTES = 2_000_000   # chỉ backend gọi (ảnh ≤ 300 KB); chặn đầu vào bất thường
