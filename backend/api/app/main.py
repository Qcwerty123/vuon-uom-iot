"""Backend FastAPI — điểm vào. Chạy: uvicorn app.main:app --host 0.0.0.0 --port 8000 (thư mục backend/api).

Phục vụ trên cùng một cổng (đặc tả §17.1): /api/v1 (REST), /ws (WebSocket), /docs (OpenAPI),
và bản build frontend (frontend/dist) nếu có.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler

from fastapi import APIRouter, FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from . import errors, ingest, realtime, seed
from .config import REPO, settings
from .db import engine
from .routers import auth, devices, telemetry


def _setup_logging() -> None:
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    h = RotatingFileHandler(settings.log_dir / "backend.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not any(isinstance(x, RotatingFileHandler) for x in root.handlers):
        root.addHandler(h)
    for name in ("uvicorn", "uvicorn.access"):  # uvicorn.error đi lên "uvicorn", không gắn lại để khỏi ghi trùng
        lg = logging.getLogger(name)
        if not any(isinstance(x, RotatingFileHandler) for x in lg.handlers):
            lg.addHandler(h)


_setup_logging()
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if not settings.jwt_secret or len(settings.jwt_secret) < 32:
        raise RuntimeError("JWT_SECRET trong .env phải dài ít nhất 32 ký tự")
    realtime.bind_loop(asyncio.get_running_loop())
    with engine.connect() as c:
        c.execute(text("select 1"))
    seed.run()
    ingest.start()
    schemes = list(_app.openapi().get("components", {}).get("securitySchemes", {}))
    log.info("Backend đã khởi động (OpenAPI security: %s)", schemes)
    yield
    ingest.stop()
    log.info("Backend dừng")


app = FastAPI(title="Vườn ươm thông minh — API", version="0.2.0", lifespan=lifespan,
              docs_url="/docs", openapi_url="/api/v1/openapi.json")
errors.install(app)
app.add_middleware(CORSMiddleware, allow_origins=[settings.public_origin, "http://localhost:5173",
                                                  "http://127.0.0.1:5173"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def security_headers(request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    return resp


api = APIRouter(prefix="/api/v1")
api.include_router(auth.router)
api.include_router(devices.router)
api.include_router(telemetry.router)


@api.get("/health", tags=["system"])
def health():
    return {"status": "ok", "mqtt": bool(ingest._client and ingest._client.is_connected()), "ingest": ingest.stats}


app.include_router(api)


@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await realtime.endpoint(websocket)


_dist = REPO / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="web")
