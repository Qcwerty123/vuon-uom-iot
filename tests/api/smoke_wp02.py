"""Kiểm thử đầu-cuối WP-02 (backend lõi) với backend đang chạy ở 127.0.0.1:BACKEND_PORT.

Luồng: đăng nhập 3 vai trò → phân quyền (FT1, ST1, C6) → admin đăng ký + cấp phát thiết bị (FT2) →
thiết bị mô phỏng kết nối bằng secret vừa cấp → backend lưu telemetry, thiết bị ACTIVE (FT3) →
WebSocket nhận telemetry realtime → khóa: thiết bị bị ngắt (FT9/ST3) → mở khóa → thu hồi.
Kết quả: logs/tests/smoke-wp02-<giờ>.txt. Chạy: scripts/windows/test-backend.ps1
"""
from __future__ import annotations

import json
import sys
import threading
import time
import types
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tests" / "load"))
import simulator  # noqa: E402

ENV = simulator.load_env()
simulator.ENV = ENV
BASE = f"http://127.0.0.1:{ENV.get('BACKEND_PORT', '8000')}"
OUT = REPO / "logs" / "tests" / f"smoke-wp02-{time.strftime('%Y%m%d-%H%M%S')}.txt"
results: list[tuple[bool, str, str]] = []


def say(s: str) -> None:
    print(s, flush=True)
    with OUT.open("a", encoding="utf-8") as f:
        f.write(s + "\n")


def check(name: str, cond: bool, detail: str = "") -> bool:
    results.append((cond, name, detail))
    say(f"{'PASS' if cond else 'FAIL'} {name} {detail}")
    return cond


def call(method: str, path: str, token: str | None = None, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"raw": raw.decode(errors="replace")}


def login(user: str) -> str | None:
    st, b = call("POST", "/api/v1/auth/login", body={"username": user, "password": ENV.get(f"SEED_{user.upper()}_PASSWORD")})
    check(f"Đăng nhập {user}", st == 200 and "accessToken" in b, f"HTTP {st}")
    return b.get("accessToken")


def ws_listen(token: str, device_id: int, seconds: float, box: dict) -> None:
    """Client WebSocket tối giản bằng thư viện websockets (có sẵn trong uvicorn[standard])."""
    import asyncio

    import websockets

    async def run():
        url = BASE.replace("http", "ws") + "/ws"
        async with websockets.connect(url) as ws:
            await ws.send(json.dumps({"type": "auth", "token": token}))
            await ws.send(json.dumps({"type": "subscribe", "deviceIds": [device_id]}))
            end = time.time() + seconds
            while time.time() < end:
                try:
                    m = json.loads(await asyncio.wait_for(ws.recv(), timeout=end - time.time()))
                except asyncio.TimeoutError:
                    break
                box.setdefault("types", []).append(m.get("type"))
    try:
        asyncio.run(run())
    except Exception as e:  # noqa: BLE001
        box["error"] = repr(e)


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    say(f"# Smoke WP-02 — {time.strftime('%Y-%m-%d %H:%M:%S')} — {BASE}")
    st, h = call("GET", "/api/v1/health")
    if not check("Backend sống (/health)", st == 200, json.dumps(h)):
        return 1
    check("Backend đã kết nối broker", bool(h.get("mqtt")))

    adm, op, vw = login("admin"), login("operator"), login("viewer")
    if not (adm and op and vw):
        return 1
    st, b = call("POST", "/api/v1/auth/login", body={"username": "viewer", "password": "sai-mat-khau"})
    check("Sai mật khẩu → 401", st == 401, f"HTTP {st}")
    st, b = call("GET", "/api/v1/devices", "token-gia")
    check("Token giả → 401 (ST2)", st == 401, f"HTTP {st}")

    st, devs = call("GET", "/api/v1/devices", vw)
    check("Viewer thấy thiết bị được gán", st == 200 and len(devs) >= 2, f"{len(devs) if isinstance(devs, list) else devs}")
    st, b = call("POST", "/api/v1/devices", vw, {"type": "CONTROLLER", "name": "x"})
    check("Viewer đăng ký thiết bị → 403 (FT1)", st == 403, f"HTTP {st}")

    # FT2: đăng ký + cấp phát
    st, dev = call("POST", "/api/v1/devices", adm, {"type": "CONTROLLER", "name": "Smoke test WP-02", "zoneId": 1})
    if not check("Admin đăng ký thiết bị → REGISTERED", st == 201 and dev.get("status") == "REGISTERED", json.dumps(dev)):
        return 1
    did, code = dev["id"], dev["deviceCode"]
    st, b = call("GET", f"/api/v1/devices/{did}", op)
    check("Operator không được gán → 404 (C6/ST1)", st == 404, f"HTTP {st}")
    st, prov = call("POST", f"/api/v1/devices/{did}/provision", adm)
    if not check("Cấp phát → secret một lần", st == 200 and prov.get("secret"), f"HTTP {st} {prov.get('message', '')}"):
        return 1
    st, b = call("POST", f"/api/v1/devices/{did}/provision", adm)
    check("Cấp phát lần 2 → 409", st == 409, f"HTTP {st}")

    # Thiết bị mô phỏng dùng secret vừa cấp
    a = types.SimpleNamespace(soil=45, tank=80, drop_rate=0.0, duplicate_rate=0.0, offline_every=0, offline_for=30,
                              interval=2)
    sim = simulator.SimDevice(code, prov["secret"], prov["gardenCode"], a)
    stop = threading.Event()
    sim.start()
    threading.Thread(target=sim.loop, args=(stop,), daemon=True).start()
    box: dict = {}
    wst = threading.Thread(target=ws_listen, args=(adm, did, 10, box), daemon=True)
    wst.start()
    time.sleep(10)
    wst.join(3)

    st, dev = call("GET", f"/api/v1/devices/{did}", adm)
    check("Thiết bị kết nối → ACTIVE, online", dev.get("status") == "ACTIVE" and dev.get("online"), json.dumps(dev))
    st, lat = call("GET", f"/api/v1/devices/{did}/telemetry/latest", adm)
    check("Telemetry đã lưu (latest có soil, tank)", st == 200 and {"soil", "tank"} <= set(lat.get("metrics", {})),
          ",".join(lat.get("metrics", {}).keys()))
    check("WebSocket nhận telemetry realtime", "telemetry" in box.get("types", []),
          f"{box.get('types', [])[:8]} {box.get('error', '')}")
    st, ser = call("GET", f"/api/v1/devices/{did}/telemetry?metric=soil", adm)
    n = len(ser.get("series", {}).get("soil", [])) if st == 200 else 0
    check("Chuỗi thời gian soil có dữ liệu", n >= 2, f"{n} điểm")

    # FT9: khóa → broker ngắt thiết bị
    st, dev = call("POST", f"/api/v1/devices/{did}/suspend", adm, {"reason": "smoke test"})
    time.sleep(3)
    check("Khóa → SUSPENDED", st == 200 and dev.get("status") == "SUSPENDED", f"HTTP {st}")
    check("Khóa → thiết bị mô phỏng bị ngắt", not sim.connected)
    st, dev = call("POST", f"/api/v1/devices/{did}/resume", adm, {"reason": "smoke test"})
    check("Mở khóa → PROVISIONED (chờ kết nối lại)", st == 200 and dev.get("status") == "PROVISIONED", f"HTTP {st}")
    time.sleep(35)  # paho thử kết nối lại với backoff tối đa 30 s
    st, dev = call("GET", f"/api/v1/devices/{did}", adm)
    check("Kết nối lại sau mở khóa → ACTIVE", dev.get("status") == "ACTIVE", dev.get("status", ""))

    stop.set()
    time.sleep(1)
    st, b = call("POST", f"/api/v1/devices/{did}/decommission", adm, {"reason": "smoke test", "confirm": "sai"})
    check("Thu hồi sai mã xác nhận → 400", st == 400, f"HTTP {st}")
    st, dev = call("POST", f"/api/v1/devices/{did}/decommission", adm, {"reason": "smoke test", "confirm": code})
    check("Thu hồi → DECOMMISSIONED", st == 200 and dev.get("status") == "DECOMMISSIONED", f"HTTP {st}")
    st, hist = call("GET", f"/api/v1/devices/{did}/history", adm)
    check("Có lịch sử trạng thái", st == 200 and len(hist) >= 5, f"{len(hist) if isinstance(hist, list) else hist} bản ghi")

    fails = sum(1 for ok, *_ in results if not ok)
    say(f"=== KẾT QUẢ: {'ĐẠT TẤT CẢ' if not fails else f'{fails} mục KHÔNG ĐẠT'} ({len(results)} mục) ===")
    say(f"Log: {OUT}")
    return fails


if __name__ == "__main__":
    sys.exit(main())
