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


MODE = get("AI_MODE", "model").strip().lower()          # model | stub | vision-api
MODEL_DIR = repo_path(get("AI_MODEL_DIR", "runtime/ai/models"))
CONF_UNKNOWN = float(get("AI_CONF_UNKNOWN", "0.6"))
MODEL_VERSION = get("AI_MODEL_VERSION", "convnext-t-leaf-v1")
LOG_DIR = repo_path(get("LOG_DIR", "logs/services"))
LABEL_MAP = SERVICE_DIR / "label_map.json"
MAX_IMAGE_BYTES = 5_000_000   # chỉ backend gọi (ảnh ≤ 300 KB); chặn đầu vào bất thường

# ---- AI_MODE=vision-api: mô hình ngôn ngữ nhìn ảnh qua API tương thích OpenAI (xem app/vision_engine.py) ----
VISION_API_KEY = get("VISION_API_KEY")                               # bí mật: chỉ trong .env, không commit, không log
VISION_API_BASE = get("VISION_API_BASE").rstrip("/")                 # ví dụ https://host/v1 (có /chat/completions bên dưới)
VISION_MODEL = get("VISION_MODEL", "gemini-3.8-flash-high")
VISION_TIMEOUT_S = float(get("VISION_TIMEOUT_S", "45"))              # backend chờ AI tối đa 60 s (diagnosis.TIMEOUT_S), chừa chỗ cho dự phòng
VISION_OUTLINE = get("VISION_OUTLINE", "1") != "0"                   # 1: mô hình vẽ viền từng lá (chậm ~15-25 s); 0: chỉ nhãn 9 ô (~5-10 s)
VISION_MAX_SIDE = int(get("VISION_MAX_SIDE", "1024"))                # cạnh dài tối đa của ảnh gửi đi
VISION_DRAW_GRID = get("VISION_DRAW_GRID", "1") != "0"               # vẽ lưới 3x3 + nhãn ô lên ảnh gửi đi
VISION_FALLBACK = get("VISION_FALLBACK", "local").strip().lower()    # local | none
