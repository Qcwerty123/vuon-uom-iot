"""Kiểm thử đầu-cuối WP-08 — đèn chiếu sáng Node 1 (đặc tả v1.4 §6.11) + cấu hình camera khớp firmware Node 2.

Backend (và AI service, không bắt buộc) phải đang chạy. Dùng Node 1 giả (tests/load/simulator.py) cấp phát qua API.
Kết quả: logs/tests/smoke-wp08-<giờ>.txt
Chạy: scripts/windows/test-backend.ps1 -Wp 08
"""
from __future__ import annotations

import base64
import io
import sys
import threading
import time
import types
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import smoke_wp02 as base  # noqa: E402  — dùng lại call/check/login/simulator

base.OUT = base.REPO / "logs" / "tests" / f"smoke-wp08-{time.strftime('%Y%m%d-%H%M%S')}.txt"
call, check, say, simulator = base.call, base.check, base.say, base.simulator


def wait_cmd(tok: str, cmd_id: str, timeout: float = 15) -> dict:
    end, c = time.time() + timeout, {}
    while time.time() < end:
        _, c = call("GET", f"/api/v1/commands/{cmd_id}", tok)
        if c.get("status") not in (None, "PENDING"):
            return c
        time.sleep(0.4)
    return c


def command(tok: str, did: int, action: str, params: dict | None = None) -> tuple[int, dict]:
    st, r = call("POST", f"/api/v1/devices/{did}/commands", tok, {"action": action, "params": params or {}})
    if st == 202 and r.get("cmdId"):
        return st, wait_cmd(tok, r["cmdId"])
    return st, r


def config(tok: str, did: int, params: dict, timeout: float = 15) -> tuple[int, str]:
    st, r = call("PUT", f"/api/v1/devices/{did}/config", tok, {"params": params})
    if st != 202:
        return st, ""
    ver, end, status = r.get("configVersion"), time.time() + timeout, r.get("status", "")
    while time.time() < end and status == "PENDING":
        time.sleep(0.5)
        _, c = call("GET", f"/api/v1/devices/{did}/config", tok)
        lt = c.get("latest") or {}
        if lt.get("configVersion") == ver:
            status = lt.get("status", "")
    return st, status


def wait_state(tok: str, did: int, key: str, want, timeout: float = 12) -> dict:
    end, s = time.time() + timeout, {}
    while time.time() < end:
        _, lt = call("GET", f"/api/v1/devices/{did}/telemetry/latest", tok)
        s = lt.get("state") or {}
        if s.get(key) == want:
            return s
        time.sleep(0.5)
    return s


def wait_event(tok: str, did: int, typ: str, reason: str, after: float, timeout: float = 25) -> dict | None:
    end = time.time() + timeout
    while time.time() < end:
        _, evs = call("GET", f"/api/v1/devices/{did}/events?type={typ}&limit=20", tok)
        for e in evs if isinstance(evs, list) else []:
            ts = e.get("ts", "")
            if (e.get("detail") or {}).get("reason") == reason and ts and _epoch(ts) >= after - 1:
                return e
        time.sleep(0.5)
    return None


def _epoch(iso: str) -> float:
    from datetime import datetime
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def tiny_jpeg() -> bytes:
    try:
        from PIL import Image
    except ImportError:
        return b""
    buf = io.BytesIO()
    Image.new("RGB", (320, 240), (90, 140, 60)).save(buf, "JPEG", quality=80)
    return buf.getvalue()


def upload(code: str, secret: str, data: bytes) -> tuple[int, str]:
    h = {"Content-Type": "image/jpeg", "X-Trigger": "schedule", "X-Captured-At": str(int(time.time() * 1000)),
         "Authorization": "Basic " + base64.b64encode(f"{code}:{secret}".encode()).decode()}
    req = urllib.request.Request(base.BASE + "/device-api/v1/images", data=data, method="POST", headers=h)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            import json
            return r.status, json.loads(r.read() or b"{}").get("diagnosis_id", "")
    except urllib.error.HTTPError as e:
        return e.code, ""


def main() -> int:
    base.OUT.parent.mkdir(parents=True, exist_ok=True)
    say(f"# Smoke WP-08 (đèn chiếu sáng) — {time.strftime('%Y-%m-%d %H:%M:%S')}")
    adm, op, vw = base.login("admin"), base.login("operator"), base.login("viewer")
    if not (adm and op and vw):
        return 1
    _, users = call("GET", "/api/v1/users", adm)
    uid = {u["username"]: u["id"] for u in users}

    # Node 1 giả trong khu 1, operator CONTROL, viewer VIEW
    _, dev = call("POST", "/api/v1/devices", adm, {"type": "CONTROLLER", "name": "Smoke test WP-08", "zoneId": 1})
    did, code = dev["id"], dev["deviceCode"]
    _, prov = call("POST", f"/api/v1/devices/{did}/provision", adm)
    call("POST", f"/api/v1/devices/{did}/assignments", adm, {"userId": uid["operator"], "permission": "CONTROL"})
    call("POST", f"/api/v1/devices/{did}/assignments", adm, {"userId": uid["viewer"], "permission": "VIEW"})
    a = types.SimpleNamespace(soil=45, tank=80, drop_rate=0.0, duplicate_rate=0.0, offline_every=0, offline_for=30,
                              interval=2)
    sim = simulator.SimDevice(code, prov["secret"], prov["gardenCode"], a)
    sim.cfg["temp_high"], sim.temp = 40.0, 28.0          # tránh khóa nhiệt ngoài ý muốn ở phần đầu
    stop = threading.Event()
    sim.start()
    threading.Thread(target=sim.loop, args=(stop,), daemon=True).start()
    time.sleep(6)
    s = wait_state(op, did, "lamp", 0)
    check("Telemetry có state.lamp", "lamp" in s, str(s))

    # 1. Lệnh tay
    st, c = command(op, did, "lamp_on", {"duration_min": 1})
    check("lamp_on {duration_min:1} → EXECUTED", c.get("status") == "EXECUTED", f"HTTP {st} {c.get('status')} {c.get('result')}")
    s = wait_state(op, did, "lamp", 1)
    check("state.lamp = 1 sau lamp_on", s.get("lamp") == 1, str(s))
    t_cmd = time.time() - 15
    e = wait_event(op, did, "lamp_on", "command", t_cmd, timeout=8)
    check("Event lamp_on {source:remote, reason:command}", bool(e) and e["detail"].get("source") == "remote", str(e))
    st, _ = command(op, did, "lamp_on")
    check("lamp_on không tham số → chấp nhận (202)", st == 202, f"HTTP {st}")
    for bad in (0, 241, "5", True):
        st, _ = call("POST", f"/api/v1/devices/{did}/commands", op, {"action": "lamp_on", "params": {"duration_min": bad}})
        check(f"lamp_on duration_min={bad!r} → 400", st == 400, f"HTTP {st}")
    st, _ = call("POST", f"/api/v1/devices/{did}/commands", vw, {"action": "lamp_on", "params": {}})
    check("Viewer bật đèn → 403", st == 403, f"HTTP {st}")
    st, c = command(op, did, "lamp_off")
    check("lamp_off → EXECUTED", c.get("status") == "EXECUTED", f"HTTP {st} {c.get('status')}")
    s = wait_state(op, did, "lamp", 0)
    check("state.lamp = 0 sau lamp_off", s.get("lamp") == 0, str(s))
    # Ở AUTO, lệnh tay (cả lamp_off) giữ lamp_override_min; set_mode AUTO bỏ lệnh tay để AUTO chạy lại (§6.11)
    st, c = command(op, did, "set_mode", {"mode": "AUTO"})
    check("set_mode AUTO (bỏ lệnh tay đèn) → EXECUTED", c.get("status") == "EXECUTED", f"{c.get('status')}")

    # 2. Cấu hình lamp_* ở backend
    st, _ = call("PUT", f"/api/v1/devices/{did}/config", op, {"params": {"lamp_start_hour": 10, "lamp_end_hour": 8}})
    check("lamp_end_hour ≤ lamp_start_hour → 400", st == 400, f"HTTP {st}")
    st, _ = call("PUT", f"/api/v1/devices/{did}/config", op, {"params": {"lamp_hyst": 400, "lamp_self_lux": 300}})
    check("lamp_hyst ≤ lamp_self_lux + 200 → 400", st == 400, f"HTTP {st}")
    st, _ = call("PUT", f"/api/v1/devices/{did}/config", op, {"params": {"lamp_hold_s": 1}})
    check("lamp_hold_s ngoài miền → 400", st == 400, f"HTTP {st}")
    st, _ = call("PUT", f"/api/v1/devices/{did}/config", op, {"params": {"lamp_lux_low": 1.5}})
    check("lamp_lux_low không nguyên → 400", st == 400, f"HTTP {st}")
    st, _ = call("PUT", f"/api/v1/devices/{did}/config", op, {"params": {"lamp_color": 1}})
    check("Khóa lạ vẫn → 400", st == 400, f"HTTP {st}")

    # 3. AUTO: khung 0–24, ngưỡng bật rất cao → thiếu sáng → bật sau lamp_hold_s (debounce)
    t_cfg = time.time()
    st, cst = config(op, did, {"lamp_start_hour": 0, "lamp_end_hour": 24, "lamp_lux_low": 60000, "lamp_hyst": 1000,
                               "lamp_hold_s": 2, "lamp_min_on_s": 10, "lamp_min_off_s": 10, "temp_high": 40})
    check("Cấu hình demo đèn 0–24h → APPLIED", st == 202 and cst == "APPLIED", f"HTTP {st} {cst}")
    _, cur = call("GET", f"/api/v1/devices/{did}/config", op)
    check("GET config có lamp_* đã lưu", (cur.get("params") or {}).get("lamp_end_hour") == 24,
          str({k: v for k, v in (cur.get("params") or {}).items() if k.startswith("lamp")}))
    e = wait_event(op, did, "lamp_on", "low_light", t_cfg, timeout=25)
    check("AUTO: thiếu sáng → event lamp_on {reason:low_light}", bool(e) and e["detail"].get("source") == "auto", str(e))

    # 4. Khóa nhiệt: temp_high thấp → tắt đèn (overheat), lệnh bật bị REJECTED blocked_overheat
    t_hot = time.time()
    st, cst = config(op, did, {"temp_high": 20})
    check("Hạ temp_high = 20 → APPLIED", cst == "APPLIED", f"HTTP {st} {cst}")
    e = wait_event(op, did, "lamp_off", "overheat", t_hot, timeout=10)
    check("Quá nóng → event lamp_off {reason:overheat}", bool(e), str(e))
    s = wait_state(op, did, "locks", ["overheat"])
    check("state.locks có overheat", "overheat" in (s.get("locks") or []), str(s))
    st, c = command(op, did, "lamp_on", {"duration_min": 1})
    check("lamp_on khi quá nóng → REJECTED blocked_overheat",
          c.get("status") == "REJECTED" and c.get("result") == "blocked_overheat", f"{c.get('status')} {c.get('result')}")

    # 5. Lọc event nhiều loại (phục vụ "số giờ chiếu sáng hôm nay")
    _, evs = call("GET", f"/api/v1/devices/{did}/events?type=lamp_on,lamp_off&limit=100", vw)
    types_ = {e["type"] for e in evs} if isinstance(evs, list) else set()
    check("events?type=lamp_on,lamp_off chỉ trả event đèn", types_ and types_ <= {"lamp_on", "lamp_off"}, str(types_))
    st, cst = config(op, did, {"temp_high": 40, "lamp_start_hour": 6, "lamp_end_hour": 20, "lamp_lux_low": 800,
                               "lamp_hyst": 700})
    check("Trả cấu hình đèn về 6–20h → APPLIED", cst == "APPLIED", f"HTTP {st} {cst}")
    command(op, did, "set_mode", {"mode": "MANUAL"})   # MANUAL: đèn chỉ theo lệnh, không phụ thuộc giờ chạy test
    st, c = command(op, did, "lamp_on")
    check("MANUAL: lamp_on → EXECUTED (hết khóa nhiệt)", c.get("status") == "EXECUTED", f"{c.get('status')} {c.get('result')}")

    # 6. Camera: miền giá trị khớp firmware Node 2, diagnoses.lamp_on
    _, cam = call("POST", "/api/v1/devices", adm, {"type": "CAMERA", "name": "Smoke test WP-08 cam", "zoneId": 1})
    cid, ccode = cam["id"], cam["deviceCode"]
    _, cprov = call("POST", f"/api/v1/devices/{cid}/provision", adm)
    for params, want, name in (({"jpeg_quality": 40}, 400, "jpeg_quality=40 → 400 (firmware 8–30)"),
                               ({"jpeg_quality": 12}, 202, "jpeg_quality=12 → 202"),
                               ({"frame_size": "SVGA"}, 202, "frame_size=SVGA → 202"),
                               ({"frame_size": "4K"}, 400, "frame_size=4K → 400"),
                               ({"warmup_frames": 2}, 202, "warmup_frames=2 → 202"),
                               ({"warmup_frames": 9}, 400, "warmup_frames=9 → 400")):
        st, _ = call("PUT", f"/api/v1/devices/{cid}/config", adm, {"params": params})
        check(f"Camera {name}", st == want, f"HTTP {st}")
    wait_state(op, did, "lamp", 1)  # telemetry Node 1 cùng vườn đã báo đèn bật
    img = tiny_jpeg()
    if img:
        st, dg = upload(ccode, cprov["secret"], img)
        did_ = int(dg.split("-")[-1]) if dg else 0
        _, d = call("GET", f"/api/v1/diagnoses/{did_}", adm) if did_ else (0, {})
        check("Upload ảnh → diagnoses.lamp_on lấy từ Node 1 cùng vườn", st == 201 and d.get("lampOn") is True,
              f"HTTP {st} lampOn={d.get('lampOn')!r}")
    else:
        check("Upload ảnh (cần Pillow trong venv backend)", False, "thiếu Pillow")

    # Dọn dẹp
    stop.set()
    time.sleep(1)
    call("POST", f"/api/v1/devices/{did}/decommission", adm, {"reason": "smoke wp08", "confirm": code})
    call("POST", f"/api/v1/devices/{cid}/decommission", adm, {"reason": "smoke wp08", "confirm": ccode})

    fails = sum(1 for ok_, *_ in base.results if not ok_)
    say(f"=== KẾT QUẢ: {'ĐẠT TẤT CẢ' if not fails else f'{fails} mục KHÔNG ĐẠT'} ({len(base.results)} mục) ===")
    say(f"Log: {base.OUT}")
    return fails


if __name__ == "__main__":
    sys.exit(main())
