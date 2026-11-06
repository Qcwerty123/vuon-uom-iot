"""Kiểm thử đầu-cuối WP-03 (lệnh, cấu hình, offline, cảnh báo, người dùng, audit) với backend đang chạy.

Dùng thiết bị mô phỏng cấp phát qua API. Kết quả: logs/tests/smoke-wp03-<giờ>.txt
Chạy: scripts/windows/test-backend.ps1 -Wp 03
"""
from __future__ import annotations

import json
import sys
import threading
import time
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import smoke_wp02 as base  # noqa: E402  — dùng lại call/check/login/ws_listen

base.OUT = base.REPO / "logs" / "tests" / f"smoke-wp03-{time.strftime('%Y%m%d-%H%M%S')}.txt"
call, check, say, simulator = base.call, base.check, base.say, base.simulator


def wait_cmd(tok: str, cmd_id: str, want: set[str], timeout: float = 15) -> dict:
    end = time.time() + timeout
    c: dict = {}
    while time.time() < end:
        _, c = call("GET", f"/api/v1/commands/{cmd_id}", tok)
        if c.get("status") in want:
            return c
        time.sleep(0.5)
    return c


def main() -> int:
    base.OUT.parent.mkdir(parents=True, exist_ok=True)
    say(f"# Smoke WP-03 — {time.strftime('%Y-%m-%d %H:%M:%S')}")
    adm, op, vw = base.login("admin"), base.login("operator"), base.login("viewer")
    if not (adm and op and vw):
        return 1

    # Thiết bị thử, gán operator CONTROL, viewer VIEW
    st, dev = call("POST", "/api/v1/devices", adm, {"type": "CONTROLLER", "name": "Smoke test WP-03", "zoneId": 1})
    did, code = dev["id"], dev["deviceCode"]
    _, prov = call("POST", f"/api/v1/devices/{did}/provision", adm)
    _, users = call("GET", "/api/v1/users", adm)
    uid = {u["username"]: u["id"] for u in users}
    call("POST", f"/api/v1/devices/{did}/assignments", adm, {"userId": uid["operator"], "permission": "CONTROL"})
    call("POST", f"/api/v1/devices/{did}/assignments", adm, {"userId": uid["viewer"], "permission": "VIEW"})

    a = types.SimpleNamespace(soil=45, tank=80, drop_rate=0.0, duplicate_rate=0.0, offline_every=0, offline_for=30,
                              interval=2)
    sim = simulator.SimDevice(code, prov["secret"], prov["gardenCode"], a)
    stop = threading.Event()
    sim.start()
    threading.Thread(target=sim.loop, args=(stop,), daemon=True).start()
    time.sleep(6)

    # --- Lệnh (FT5, UC05) ---
    st, r = call("POST", f"/api/v1/devices/{did}/commands", op, {"action": "pump_on", "params": {"durationS": 3}})
    check("Tham số sai tên (durationS) → 400", st == 400, f"HTTP {st}")
    st, r = call("POST", f"/api/v1/devices/{did}/commands", op, {"action": "pump_on", "params": {"duration_s": 3}})
    ok = check("Operator gửi pump_on → 202 PENDING", st == 202 and r.get("status") == "PENDING", f"HTTP {st} {r}")
    if ok:
        c = wait_cmd(op, r["cmdId"], {"EXECUTED", "REJECTED", "FAILED", "TIMEOUT"})
        check("Lệnh → EXECUTED (ack)", c.get("status") == "EXECUTED", f"{c.get('status')} {c.get('result')}")
        if c.get("ackAt") and c.get("issuedAt"):
            say(f"INFO thời gian lệnh → ack: {c['issuedAt']} → {c['ackAt']}")
    time.sleep(4.5)  # chờ bơm chạy xong 3 s → bắt đầu thời gian nghỉ cooldown
    st, r = call("POST", f"/api/v1/devices/{did}/commands", op, {"action": "pump_on", "params": {"duration_s": 3}})
    c = wait_cmd(op, r.get("cmdId", ""), {"EXECUTED", "REJECTED", "FAILED", "TIMEOUT"}) if st == 202 else {}
    check("Bơm lại khi đang cooldown → REJECTED blocked_cooldown", c.get("result") == "blocked_cooldown",
          f"{c.get('status')} {c.get('result')}")
    st, r = call("POST", f"/api/v1/devices/{did}/commands", vw, {"action": "fan_on"})
    check("Viewer gửi lệnh → 403 (bước 9)", st == 403, f"HTTP {st}")
    st, r = call("POST", f"/api/v1/devices/{did}/commands", op, {"action": "capture"})
    check("Lệnh camera gửi tới bộ điều khiển → 400", st == 400, f"HTTP {st}")
    sim.ignore_commands = True
    st, r = call("POST", f"/api/v1/devices/{did}/commands", op, {"action": "fan_on"})
    c = wait_cmd(op, r.get("cmdId", ""), {"TIMEOUT"}, timeout=20) if st == 202 else {}
    check("Không có ack sau 10 s → TIMEOUT", c.get("status") == "TIMEOUT", c.get("status", ""))
    sim.ignore_commands = False

    # --- Cấu hình (FT6) ---
    st, r = call("PUT", f"/api/v1/devices/{did}/config", op, {"params": {"soil_low": 60, "soil_high": 50}})
    check("Cấu hình sai (soil_low ≥ soil_high) → 400", st == 400, f"HTTP {st}")
    st, r = call("PUT", f"/api/v1/devices/{did}/config", op, {"params": {"soil_low": 30, "soil_high": 60}})
    ver = r.get("configVersion")
    check("Đổi cấu hình → 202 PENDING", st == 202 and r.get("status") == "PENDING", f"HTTP {st} v{ver}")
    time.sleep(3)
    _, cfg = call("GET", f"/api/v1/devices/{did}/config", op)
    check("Thiết bị áp dụng → APPLIED", (cfg.get("latest") or {}).get("status") == "APPLIED",
          json.dumps(cfg.get("latest"))[:200])
    check("Thiết bị thật nhận soil_low=30", sim.cfg.get("soil_low") == 30, str(sim.cfg.get("soil_low")))

    # --- Cảnh báo THRESHOLD (FT8) ---
    st, rule = call("POST", "/api/v1/alert-rules", adm, {"name": "Smoke: đất dưới 99", "type": "THRESHOLD",
                                                         "scopeDeviceId": did, "metric": "soil", "operator": "<",
                                                         "threshold": 99, "durationS": 0, "cooldownMin": 0,
                                                         "notifyTelegram": False})
    check("Admin tạo luật cảnh báo", st == 201, f"HTTP {st} {rule.get('message', '')}")
    st, r = call("POST", "/api/v1/alert-rules", op, {"name": "x", "type": "OFFLINE"})
    check("Operator tạo luật → 403", st == 403, f"HTTP {st}")
    time.sleep(14)  # cache luật 10 s + một chu kỳ telemetry
    _, al = call("GET", f"/api/v1/alerts?deviceId={did}&status=OPEN", op)
    th = [x for x in al.get("items", []) if x["type"] == "THRESHOLD"]
    if check("Vượt ngưỡng → cảnh báo OPEN", bool(th), th[0]["message"] if th else str(al)[:200]):
        aid = th[0]["id"]
        st, _ = call("POST", f"/api/v1/alerts/{aid}/acknowledge", vw)
        check("Viewer xác nhận cảnh báo → 403", st == 403, f"HTTP {st}")
        st, x = call("POST", f"/api/v1/alerts/{aid}/acknowledge", op)
        check("Operator xác nhận → ACKNOWLEDGED", x.get("status") == "ACKNOWLEDGED", f"HTTP {st}")
        st, x = call("POST", f"/api/v1/alerts/{aid}/close", op, {"note": "smoke"})
        check("Đóng → CLOSED", x.get("status") == "CLOSED", f"HTTP {st}")
    if rule.get("id"):
        call("DELETE", f"/api/v1/alert-rules/{rule['id']}", adm)

    # --- Cảnh báo EVENT: bể cạn ---
    sim.tank = 5
    time.sleep(5)
    _, al = call("GET", f"/api/v1/alerts?deviceId={did}", op)
    check("Bể cạn (event tank_low) → cảnh báo", any(x["type"] == "EVENT" for x in al.get("items", [])),
          ",".join(x["message"][:40] for x in al.get("items", [])[:3]))
    st, r = call("POST", f"/api/v1/devices/{did}/commands", op, {"action": "pump_on", "params": {"duration_s": 2}})
    c = wait_cmd(op, r.get("cmdId", ""), {"EXECUTED", "REJECTED", "FAILED", "TIMEOUT"}) if st == 202 else {}
    check("Bơm khi bể cạn → REJECTED blocked_no_water (FT5)", c.get("result") == "blocked_no_water",
          f"{c.get('status')} {c.get('result')}")
    sim.tank = 80

    # --- Offline (FT7) ---
    sim.go_offline()
    time.sleep(4)
    _, d = call("GET", f"/api/v1/devices/{did}", op)
    check("Mất kết nối đột ngột → OFFLINE (LWT)", d.get("status") == "OFFLINE" and not d.get("online"),
          f"{d.get('status')} online={d.get('online')}")
    _, al = call("GET", f"/api/v1/alerts?deviceId={did}&status=OPEN", op)
    check("Cảnh báo OFFLINE mở", any(x["type"] == "OFFLINE" for x in al.get("items", [])))
    st, r = call("POST", f"/api/v1/devices/{did}/commands", op, {"action": "fan_on"})
    check("Gửi lệnh khi offline → 409 DEVICE_OFFLINE", st == 409, f"HTTP {st} {r.get('code')}")
    sim.go_online()
    time.sleep(6)
    _, d = call("GET", f"/api/v1/devices/{did}", op)
    check("Có lại kết nối → ACTIVE", d.get("status") == "ACTIVE", d.get("status", ""))
    _, al = call("GET", f"/api/v1/alerts?deviceId={did}&status=CLOSED", op)
    check("Cảnh báo OFFLINE tự đóng", any(x["type"] == "OFFLINE" and x.get("closeNote") == "auto"
                                          for x in al.get("items", [])))

    # --- Bảo trì ---
    st, r = call("POST", f"/api/v1/devices/{did}/maintenance", op, {"reason": "smoke"})
    check("Operator chuyển bảo trì → MAINTENANCE", r.get("status") == "MAINTENANCE", f"HTTP {st}")
    st, r = call("POST", f"/api/v1/devices/{did}/maintenance/end", op, {"reason": "smoke"})
    check("Kết thúc bảo trì → ACTIVE", r.get("status") == "ACTIVE", f"HTTP {st}")

    # --- Người dùng, audit, dashboard ---
    uname = f"smoke{int(time.time()) % 100000}"
    st, u = call("POST", "/api/v1/users", adm, {"username": uname, "role": "VIEWER", "password": "matkhau-tam-123"})
    check("Admin tạo người dùng", st == 201, f"HTTP {st}")
    st, _ = call("POST", "/api/v1/users", op, {"username": uname + "x", "role": "VIEWER", "password": "matkhau-tam-123"})
    check("Operator tạo người dùng → 403", st == 403, f"HTTP {st}")
    if u.get("id"):
        call("POST", f"/api/v1/users/{u['id']}/lock", adm)
        st, _ = call("POST", "/api/v1/auth/login", body={"username": uname, "password": "matkhau-tam-123"})
        check("Tài khoản bị khóa không đăng nhập được", st in (401, 403), f"HTTP {st}")
    _, au = call("GET", "/api/v1/audit-logs?size=200", adm)
    acts = {x["action"] for x in au.get("items", [])}
    check("Audit có COMMAND_SENT, COMMAND_DENIED, CONFIG_CHANGED, ALERT_CLOSED",
          {"COMMAND_SENT", "COMMAND_DENIED", "CONFIG_CHANGED", "ALERT_CLOSED"} <= acts, ",".join(sorted(acts))[:200])
    st, _ = call("GET", "/api/v1/audit-logs", op)
    check("Operator xem audit → 403", st == 403, f"HTTP {st}")
    st, sm = call("GET", "/api/v1/dashboard/summary", vw)
    check("Dashboard summary (viewer)", st == 200 and "devices" in sm, f"{len(sm.get('devices', []))} thiết bị")

    # Dọn dẹp
    stop.set()
    time.sleep(1)
    call("POST", f"/api/v1/devices/{did}/decommission", adm, {"reason": "smoke", "confirm": code})

    fails = sum(1 for ok_, *_ in base.results if not ok_)
    say(f"=== KẾT QUẢ: {'ĐẠT TẤT CẢ' if not fails else f'{fails} mục KHÔNG ĐẠT'} ({len(base.results)} mục) ===")
    say(f"Log: {base.OUT}")
    return fails


if __name__ == "__main__":
    sys.exit(main())
