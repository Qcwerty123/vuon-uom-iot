"""Cấu hình đọc từ .env ở gốc repo (đặc tả §17.6). Biến môi trường của tiến trình được ưu tiên."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote_plus

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
            v = v[1 : v.index(v[0], 1)]
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


@dataclass(frozen=True)
class Settings:
    db_url: str
    jwt_secret: str
    access_ttl_min: int
    refresh_ttl_days: int
    mqtt_host: str
    mqtt_port: int
    mqtt_backend_user: str
    mqtt_backend_password: str
    mqtt_dynsec_user: str
    mqtt_dynsec_password: str
    mqtt_public_host: str
    backend_port: int
    public_origin: str
    image_dir: Path
    log_dir: Path
    dynsec_file: Path
    seed_passwords: dict
    telegram_token: str
    ai_url: str
    ai_conf_alert: float
    max_image_bytes: int


def load() -> Settings:
    user, pw = get("POSTGRES_USER", "nursery_app"), get("POSTGRES_PASSWORD")
    host, port, db = get("DB_HOST", "127.0.0.1"), get("DB_PORT", "5433"), get("POSTGRES_DB", "nursery")
    return Settings(
        db_url=f"postgresql+psycopg://{quote_plus(user)}:{quote_plus(pw)}@{host}:{port}/{db}",
        jwt_secret=get("JWT_SECRET"),
        access_ttl_min=int(get("JWT_ACCESS_TTL_MIN", "15")),
        refresh_ttl_days=int(get("JWT_REFRESH_TTL_DAYS", "7")),
        mqtt_host=get("MQTT_HOST", "127.0.0.1"),
        mqtt_port=int(get("MQTT_PORT", "1883")),
        mqtt_backend_user=get("MQTT_BACKEND_USER", "backend"),
        mqtt_backend_password=get("MQTT_BACKEND_PASSWORD"),
        mqtt_dynsec_user=get("MQTT_DYNSEC_USER", "dynsec-admin"),
        mqtt_dynsec_password=get("MQTT_DYNSEC_PASSWORD"),
        mqtt_public_host=get("MQTT_PUBLIC_HOST", "192.168.137.1"),
        backend_port=int(get("BACKEND_PORT", "8000")),
        public_origin=get("PUBLIC_ORIGIN", "http://192.168.137.1:8000"),
        image_dir=repo_path(get("IMAGE_DIR", "runtime/images")),
        log_dir=repo_path(get("LOG_DIR", "logs/services")),
        dynsec_file=repo_path(get("DYNSEC_FILE", "runtime/mosquitto/dynamic-security.json")),
        seed_passwords={
            "admin": get("SEED_ADMIN_PASSWORD"),
            "operator": get("SEED_OPERATOR_PASSWORD"),
            "viewer": get("SEED_VIEWER_PASSWORD"),
        },
        telegram_token=get("TELEGRAM_BOT_TOKEN"),
        ai_url=get("AI_URL", "http://127.0.0.1:8001").rstrip("/"),
        ai_conf_alert=float(get("AI_CONF_ALERT", "0.8")),
        max_image_bytes=300 * 1024,  # §8.9: JPEG ≤ 300 KB
    )


settings = load()
