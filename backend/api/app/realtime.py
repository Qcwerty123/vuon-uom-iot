"""WebSocket hub (đặc tả §10.11). Luồng MQTT gọi publish() từ thread khác; hub đẩy sang event loop."""
from __future__ import annotations

import asyncio
import json
import logging
import time

import jwt
from fastapi import WebSocket, WebSocketDisconnect

from .db import SessionLocal
from .deps import permission_of
from .models import User
from .security import decode_access_token

log = logging.getLogger("realtime")
_loop: asyncio.AbstractEventLoop | None = None
_clients: set["Conn"] = set()


def bind_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


def publish(device_id: int, message: dict) -> None:
    """Gọi được từ mọi thread."""
    if _loop is None:
        return
    _loop.call_soon_threadsafe(_fanout, device_id, message)


def _fanout(device_id: int, message: dict) -> None:
    for c in list(_clients):
        if c.wants(device_id):
            try:
                c.queue.put_nowait(message)
            except asyncio.QueueFull:
                log.warning("Hàng đợi WS của user %s đầy, bỏ bản tin", c.user_id)


class Conn:
    def __init__(self, ws: WebSocket):
        self.ws = ws
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        self.user_id: int | None = None
        self.role: str | None = None
        self.exp = 0
        self.devices: set[int] = set()

    def wants(self, device_id: int) -> bool:
        return self.user_id is not None and time.time() < self.exp and device_id in self.devices


async def endpoint(ws: WebSocket) -> None:
    await ws.accept()
    conn = Conn(ws)
    try:
        msg = await asyncio.wait_for(ws.receive_json(), timeout=5)
    except (asyncio.TimeoutError, WebSocketDisconnect, ValueError):
        await ws.close(code=4401)
        return
    if not await _auth(conn, msg):
        await ws.close(code=4401)
        return
    _clients.add(conn)
    sender = asyncio.create_task(_sender(conn))
    try:
        while True:
            m = await ws.receive_json()
            t = m.get("type")
            if t == "auth":
                await _auth(conn, m)
            elif t == "subscribe":
                await _subscribe(conn, m.get("deviceIds") or [])
            elif t == "ping":
                await conn.queue.put({"type": "pong"})
    except (WebSocketDisconnect, ValueError, RuntimeError):
        pass
    finally:
        _clients.discard(conn)
        sender.cancel()


async def _auth(conn: Conn, msg: dict) -> bool:
    if msg.get("type") != "auth":
        return False
    try:
        data = decode_access_token(str(msg.get("token", "")))
    except jwt.PyJWTError:
        await conn.ws.send_json({"type": "auth_error"})
        return False
    conn.user_id, conn.role, conn.exp = int(data["sub"]), data.get("role"), int(data["exp"])
    await conn.ws.send_json({"type": "auth_ok"})
    return True


async def _subscribe(conn: Conn, ids: list) -> None:
    allowed: set[int] = set()
    db = SessionLocal()
    try:
        user = db.get(User, conn.user_id)
        for raw in ids[:200]:
            try:
                did = int(raw)
            except (TypeError, ValueError):
                continue
            if user and permission_of(db, user, did):
                allowed.add(did)
    finally:
        db.close()
    conn.devices = allowed
    await conn.queue.put({"type": "subscribed", "deviceIds": sorted(allowed)})


async def _sender(conn: Conn) -> None:
    try:
        while True:
            m = await conn.queue.get()
            if conn.user_id is not None and time.time() >= conn.exp and m.get("type") not in ("pong", "subscribed"):
                await conn.ws.send_json({"type": "auth_expired"})
                continue
            await conn.ws.send_text(json.dumps(m, default=str))
    except Exception:  # noqa: BLE001 — kết nối đóng
        pass
