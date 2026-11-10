"""Kiểm thử đầu-cuối WP-07 (ảnh Node 2, AI chẩn đoán, AI_LEAF, API chẩn đoán, gardens/zones) với backend đang chạy.

Chạy: scripts/windows/test-backend.ps1 -Wp 07
  Script tạm dừng AI service thật; test này tự bật AI service ở chế độ AI_MODE=stub (bộ chấm theo màu, KHÔNG phải
  mô hình thật) tại 127.0.0.1:8001 để kết quả tất định, rồi tắt khi xong; script bật lại AI thật.
Dùng camera giả tests/load/cam_sim.py (MQTT + HTTP như Node 2). Kết quả: logs/tests/smoke-wp07-<giờ>.txt
"""
from __future__ import annotations

import base64
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import smoke_wp02 as base  # noqa: E402  — dùng lại call/check/login/ws_listen

base.OUT = base.REPO / "logs" / "tests" / f"smoke-wp07-{time.strftime('%Y%m%d-%H%M%S')}.txt"
call, check, say = base.call, base.check, base.say
REPO = base.REPO
sys.path.insert(0, str(REPO / "tests" / "load"))
import cam_sim  # noqa: E402

cam_sim.ENV = base.ENV
AI_DIR = REPO / "backend" / "ai-service"
AI_PY = os.environ.get("WP07_AI_PY") or str(AI_DIR / ".venv" / "Scripts" / "python.exe")
AI_PORT = 8001
_ai_proc: subprocess.Popen | None = None


# ---------------------------------------------------------------------------
# AI service stub do test điều khiển
# ---------------------------------------------------------------------------

def port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def ai_health() -> dict:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{AI_PORT}/v1/health", timeout=3) as r:
            return json.loads(r.read())
    except Exception:  # noqa: BLE001
        return {}


def ai_start() -> bool:
    global _ai_proc
    for _ in range(40):
        if not port_open(AI_PORT):
            break
        if ai_health().get("mode") == "stub":
            return True
        time.sleep(0.25)
    else:
        say("FAIL cổng 8001 đang bận bởi AI service thật — chạy qua test-backend.ps1 -Wp 07 (tự dừng AI thật)")
        return False
    logf = open(REPO / "logs" / "tests" / "ai-stub-wp07.log", "ab")
    env = dict(os.environ, AI_MODE="stub", PYTHONIOENCODING="utf-8")
    _ai_proc = subprocess.Popen([AI_PY, "-m", "uvicorn", "app.main:app", "--app-dir", str(AI_DIR), "--host", "127.0.0.1",
                                 "--port", str(AI_PORT)], env=env, stdout=logf, stderr=subprocess.STDOUT,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    for _ in range(120):
        if ai_health().get("status") == "ok":
            return True
        time.sleep(0.25)
    return False


def ai_stop() -> None:
    global _ai_proc
    if _ai_proc:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(_ai_proc.pid)], capture_output=True)
        _ai_proc = None
    for _ in range(40):
        if not port_open(AI_PORT):
            return
        time.sleep(0.25)


# ---------------------------------------------------------------------------

def raw(method: str, path: str, token: str | None = None, data: bytes | None = None,
        headers: dict | None = None) -> tuple[int, dict, bytes]:
    req = urllib.request.Request(base.BASE + path, data=data, method=method, headers=headers or {})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()
    except (ConnectionError, urllib.error.URLError) as e:
        # Server từ chối sớm theo Content-Length (413) rồi đóng kết nối khi client còn đang gửi body:
        # trên Windows client nhận ConnectionReset thay vì đọc được mã 413.
        return -1, {"error": str(e)}, b""


def upload_raw(auth: str | None, data: bytes, extra: dict | None = None) -> tuple[int, dict]:
    h = {"Content-Type": "image/jpeg", "X-Trigger": "schedule", "X-Captured-At": str(int(time.time() * 1000))}
    if auth:
        h["Authorization"] = "Basic " + base64.b64encode(auth.encode()).decode()
    h.update(extra or {})
    st, _, body = raw("POST", "/device-api/v1/images", data=data, headers=h)
    try:
        return st, json.loads(body or b"{}")
    except ValueError:
        return st, {}


def wait_diag(tok: str, did: int, want: set[str], timeout: float = 10) -> tuple[dict, float]:
    t0 = time.time()
    d: dict = {}
    while time.time() - t0 < timeout:
        _, d = call("GET", f"/api/v1/diagnoses/{did}", tok)
        if d.get("status") in want:
            break
        time.sleep(0.25)
    return d, time.time() - t0


def wait_cmd(tok: str, cmd_id: str, timeout: float = 15) -> dict:
    end = time.time() + timeout
    c: dict = {}
    while time.time() < end:
        _, c = call("GET", f"/api/v1/commands/{cmd_id}", tok)
        if c.get("status") not in (None, "PENDING"):
            return c
        time.sleep(0.3)
    return c


def capture(op: str, dev_id: int) -> tuple[dict, int | None]:
    st, r = call("POST", f"/api/v1/devices/{dev_id}/commands", op, {"action": "capture"})
    if st != 202:
        return {"status": f"HTTP {st}", "result": r.get("message")}, None
    c = wait_cmd(op, r["cmdId"])
    return c, (c.get("detail") or {}).get("diagnosis_id")


def ai_leaf_alerts(tok: str, dev_id: int) -> list[dict]:
    _, al = call("GET", f"/api/v1/alerts?deviceId={dev_id}&size=50", tok)
    return [a for a in al.get("items", []) if a["type"] == "AI_LEAF"]


def main() -> int:
    base.OUT.parent.mkdir(parents=True, exist_ok=True)
    say(f"# Smoke WP-07 — {time.strftime('%Y-%m-%d %H:%M:%S')} — {base.BASE}")
    if not check("Bật AI service chế độ stub (AI_MODE=stub, KHÔNG phải mô hình thật)", ai_start(), json.dumps(ai_health())):
        return 1
    try:
        return run()
    finally:
        ai_stop()


def run() -> int:
    images = cam_sim.make_images.ensure()
    healthy, sick = (images / "healthy.jpg").read_bytes(), (images / "sick.jpg").read_bytes()
    check("Ảnh mẫu < 300 KB", max(len(healthy), len(sick)) < 300 * 1024, f"{len(healthy)} / {len(sick)} byte")
    adm, op, vw = base.login("admin"), base.login("operator"), base.login("viewer")
    if not (adm and op and vw):
        return 1
    _, users = call("GET", "/api/v1/users", adm)
    uid = {u["username"]: u["id"] for u in users}

    # Camera thử + bộ điều khiển thử (để kiểm 403 "không phải camera")
    st, cam = call("POST", "/api/v1/devices", adm, {"type": "CAMERA", "name": "Smoke test WP-07 camera", "zoneId": 1})
    if not check("Admin đăng ký camera → REGISTERED", st == 201 and cam.get("type") == "CAMERA", f"HTTP {st}"):
        return 1
    cid, code = cam["id"], cam["deviceCode"]
    _, prov = call("POST", f"/api/v1/devices/{cid}/provision", adm)
    secret, garden = prov["secret"], prov["gardenCode"]
    check("Cấp phát trả uploadUrl /device-api/v1/images", prov.get("uploadUrl", "").endswith("/device-api/v1/images"),
          prov.get("uploadUrl", ""))
    call("POST", f"/api/v1/devices/{cid}/assignments", adm, {"userId": uid["operator"], "permission": "CONTROL"})
    call("POST", f"/api/v1/devices/{cid}/assignments", adm, {"userId": uid["viewer"], "permission": "VIEW"})
    _, ctl = call("POST", "/api/v1/devices", adm, {"type": "CONTROLLER", "name": "Smoke WP-07 controller", "zoneId": 1})
    _, ctl_prov = call("POST", f"/api/v1/devices/{ctl['id']}/provision", adm)

    # --- Upload: mã lỗi (§8.9) ---
    st, _ = upload_raw(f"{code}:sai-mat-khau", healthy)
    check("Upload sai mật khẩu → 401", st == 401, f"HTTP {st}")
    st, _ = upload_raw(None, healthy)
    check("Upload thiếu Authorization → 401", st == 401, f"HTTP {st}")
    st, _ = upload_raw(f"{ctl['deviceCode']}:{ctl_prov['secret']}", healthy)
    check("Thiết bị không phải camera → 403", st == 403, f"HTTP {st}")
    st, _ = upload_raw(f"{code}:{secret}", b"day khong phai anh jpeg" * 10)
    check("Body không phải JPEG → 400", st == 400, f"HTTP {st}")
    st, _ = upload_raw(f"{code}:{secret}", healthy[: len(healthy) // 2])
    check("JPEG cụt (thiếu FF D9) → 400", st == 400, f"HTTP {st}")
    big = healthy[:-2] + os.urandom(310 * 1024) + b"\xff\xd9"
    st, _ = upload_raw(f"{code}:{secret}", big)
    check("Ảnh > 300 KB → 413 (hoặc server cắt kết nối sớm)", st in (413, -1), f"HTTP {st} ({len(big) // 1024} KB)")

    t_up = time.time()
    st, up = upload_raw(f"{code}:{secret}", healthy)
    ok = check("Upload hợp lệ → 201 {image_id, diagnosis_id}", st == 201 and str(up.get("image_id", "")).startswith("img-")
               and str(up.get("diagnosis_id", "")).startswith("dg-"), f"HTTP {st} {up}")
    if not ok:
        return 1
    did = int(up["diagnosis_id"][3:])
    st, _ = upload_raw(f"{code}:{secret}", healthy)
    check("Ảnh thứ 2 trong 20 s → 429", st == 429, f"HTTP {st}")
    _, dev = call("GET", f"/api/v1/devices/{cid}", adm)
    check("Upload cập nhật lastSeenAt, PROVISIONED → ACTIVE", dev.get("status") == "ACTIVE" and dev.get("lastSeenAt"),
          f"{dev.get('status')} {dev.get('lastSeenAt')}")

    # --- QUEUED → DONE ---
    d, _ = wait_diag(op, did, {"DONE", "FAILED"})
    dt = time.time() - t_up
    check("Chẩn đoán QUEUED → DONE ≤ 10 s", d.get("status") == "DONE" and dt <= 10, f"{d.get('status')} sau {dt:.1f} s")
    check("Kết quả có 9 ô {r,c,label,conf}", len(d.get("tiles") or []) == 9
          and all({"r", "c", "label", "conf"} <= set(t) for t in d["tiles"]), str(len(d.get("tiles") or [])))
    check("Ảnh khỏe → HEALTHY, không ô bất thường, modelVersion stub-v0",
          d.get("topLabel") == "HEALTHY" and d.get("abnormalTiles") == [] and d.get("modelVersion") == "stub-v0",
          f"{d.get('topLabel')} {d.get('abnormalTiles')} {d.get('modelVersion')}")
    fields = {"id", "deviceId", "capturedAt", "status", "topLabel", "topConfidence", "abnormalTiles", "tiles",
              "modelVersion", "trigger", "cmdId", "reviewVerdict", "correctLabel", "reviewedAt"}
    check("Bản ghi đủ trường frontend dùng", fields <= set(d), ",".join(sorted(fields - set(d))))

    # --- Quyền (C6, §10.9) ---
    st, lst = call("GET", f"/api/v1/devices/{cid}/diagnoses?size=5", vw)
    check("Viewer GET danh sách → {items,page,size,total}", st == 200 and {"items", "page", "size", "total"} <= set(lst)
          and lst["total"] >= 1, f"HTTP {st} total={lst.get('total')}")
    st, h, img = raw("GET", f"/api/v1/diagnoses/{did}/image", vw)
    check("Viewer GET ảnh → image/jpeg, Cache-Control private, đúng file",
          st == 200 and h.get("content-type", "").startswith("image/jpeg") and "private" in h.get("cache-control", "")
          and img == healthy, f"HTTP {st} {h.get('content-type')} {h.get('cache-control')}")
    st, _, _ = raw("GET", f"/api/v1/diagnoses/{did}/image")
    check("Ảnh không có token → 401", st == 401, f"HTTP {st}")
    st, _ = call("POST", f"/api/v1/diagnoses/{did}/review", vw, {"verdict": "CONFIRMED"})
    check("Viewer review → 403", st == 403, f"HTTP {st}")
    stranger = f"smoke07{int(time.time()) % 100000}"
    pw = "Smoke-wp07-" + base64.b16encode(os.urandom(4)).decode()
    call("POST", "/api/v1/users", adm, {"username": stranger, "role": "OPERATOR", "password": pw})
    st, b = call("POST", "/api/v1/auth/login", body={"username": stranger, "password": pw})
    stok = b.get("accessToken")
    st1, _ = call("GET", f"/api/v1/diagnoses/{did}", stok)
    st2, _, _ = raw("GET", f"/api/v1/diagnoses/{did}/image", stok)
    st3, _ = call("GET", f"/api/v1/devices/{cid}/diagnoses", stok)
    check("User không được gán → 404 (chi tiết, ảnh, danh sách)", (st1, st2, st3) == (404, 404, 404), f"{st1} {st2} {st3}")

    # --- Review ---
    st, _ = call("POST", f"/api/v1/diagnoses/{did}/review", op, {"verdict": "REJECTED"})
    check("Báo sai thiếu correctLabel → 400", st == 400, f"HTTP {st}")
    st, r = call("POST", f"/api/v1/diagnoses/{did}/review", op, {"verdict": "CONFIRMED", "note": "smoke wp07"})
    check("Operator review CONFIRMED → reviewedAt", st == 200 and r.get("reviewVerdict") == "CONFIRMED"
          and r.get("reviewedAt"), f"HTTP {st} {r.get('reviewVerdict')} {r.get('reviewedAt')}")
    _, au = call("GET", "/api/v1/audit-logs?action=DIAGNOSIS_REVIEWED&size=20", adm)
    check("Có audit DIAGNOSIS_REVIEWED", any(x.get("targetId") == str(did) for x in au.get("items", [])),
          f"{au.get('total')} dòng")

    # --- Camera giả qua MQTT: lệnh capture → upload → ack ---
    cam_dev = cam_sim.CamDevice(code, secret, garden, image="sick")
    cam_dev.start()
    stop = threading.Event()
    threading.Thread(target=cam_dev.loop, args=(stop,), daemon=True).start()
    for _ in range(20):
        _, dev = call("GET", f"/api/v1/devices/{cid}", op)
        if dev.get("online") and cam_dev.connected:
            break
        time.sleep(0.5)
    check("Camera giả kết nối MQTT → online", bool(dev.get("online")), f"{dev.get('status')} online={dev.get('online')}")
    box: dict = {}
    wst = threading.Thread(target=base.ws_listen, args=(op, cid, 25, box), daemon=True)
    wst.start()
    time.sleep(1)
    sick_ids = []
    for i in range(3):
        c, sid = capture(op, cid)
        if i == 0:
            check("Lệnh capture → EXECUTED, ack có image_id", c.get("status") == "EXECUTED"
                  and str((c.get("detail") or {}).get("image_id", "")).startswith("img-"), f"{c.get('status')} {c.get('detail')}")
        if sid:
            d, _ = wait_diag(op, sid, {"DONE", "FAILED"})
            sick_ids.append((sid, d))
    check("3 ảnh capture (miễn giới hạn 20 s nhờ X-Cmd-Id) đều DONE", len(sick_ids) == 3
          and all(d.get("status") == "DONE" for _, d in sick_ids), str([(i, d.get("status")) for i, d in sick_ids]))
    if sick_ids:
        d = sick_ids[0][1]
        check("Ảnh bệnh: ô (0,1) SPOT và (1,2) YELLOW, trigger=command, có cmdId",
              {(0, 1), (1, 2)} <= {tuple(x) for x in d.get("abnormalTiles", [])} and d.get("trigger") == "command"
              and d.get("cmdId"), f"{d.get('abnormalTiles')} {d.get('trigger')} {d.get('topLabel')}")
    time.sleep(1.5)
    leaf = ai_leaf_alerts(op, cid)
    ctx = (leaf[0].get("context") or {}) if leaf else {}
    check("3 ảnh bất thường cùng ô → đúng 1 cảnh báo AI_LEAF (WARNING)", len(leaf) == 1 and leaf[0]["severity"] == "WARNING",
          leaf[0]["message"] if leaf else "không có")
    check("Context AI_LEAF có diagnosis_id, danh sách ô, nhãn",
          ctx.get("diagnosis_id") == (sick_ids[-1][0] if sick_ids else None) and [0, 1] in ctx.get("tiles", [])
          and ctx.get("labels"), json.dumps(ctx, ensure_ascii=False)[:200])
    c, sid4 = capture(op, cid)
    if sid4:
        wait_diag(op, sid4, {"DONE", "FAILED"})
    time.sleep(1.5)
    check("Ảnh bất thường thứ 4 → không mở thêm cảnh báo (cooldown)", len(ai_leaf_alerts(op, cid)) == 1,
          f"{len(ai_leaf_alerts(op, cid))} cảnh báo")
    wst.join(30)
    types = box.get("types", [])
    check("WebSocket nhận 'diagnosis' và 'alert'", "diagnosis" in types and "alert" in types,
          f"{sorted(set(types))} {box.get('error', '')}")

    # --- AI service tắt → QUEUED; bật lại → DONE ---
    ai_stop()
    c, qid = capture(op, cid)
    check("AI tắt: upload vẫn 201, ack executed", c.get("status") == "EXECUTED" and qid, f"{c.get('status')}")
    time.sleep(6)
    d, _ = wait_diag(op, qid, {"DONE", "FAILED"}, timeout=0.5) if qid else ({}, 0)
    check("AI tắt → bản ghi giữ QUEUED", d.get("status") == "QUEUED", d.get("status", ""))
    _, h = call("GET", "/api/v1/health")
    check("/health báo ai.aiUp=false", (h.get("ai") or {}).get("aiUp") is False, json.dumps(h.get("ai")))
    ai_start()
    d, waited = wait_diag(op, qid, {"DONE", "FAILED"}, timeout=25) if qid else ({}, 0)
    check("Bật AI lại → tự xử lý → DONE", d.get("status") == "DONE", f"{d.get('status')} sau {waited:.1f} s")

    # --- Dashboard ---
    _, sm = call("GET", "/api/v1/dashboard/summary", op)
    mine = next((x for x in sm.get("devices", []) if x["id"] == cid), {})
    check("dashboard/summary có chẩn đoán mới nhất của camera", (mine.get("latestDiagnosis") or {}).get("id") == qid,
          str((mine.get("latestDiagnosis") or {}).get("id")))

    # --- Cấu hình camera: crop_box / active_tiles truyền sang AI ---
    st, _ = call("PUT", f"/api/v1/devices/{cid}/config", op, {"params": {"active_tiles": [[0, 1], [1, 1]]}})
    check("Cấu hình active_tiles → 202", st == 202, f"HTTP {st}")
    st, _ = call("PUT", f"/api/v1/devices/{cid}/config", op, {"params": {"crop_box": [10, 10]}})
    check("crop_box sai → 400", st == 400, f"HTTP {st}")
    time.sleep(1)
    c, aid = capture(op, cid)
    d, _ = wait_diag(op, aid, {"DONE", "FAILED"}) if aid else ({}, 0)
    inactive = [t for t in d.get("tiles", []) if (t["r"], t["c"]) not in ((0, 1), (1, 1))]
    check("Ô ngoài active_tiles → UNKNOWN, conf 0", d.get("status") == "DONE" and len(inactive) == 7
          and all(t["label"] == "UNKNOWN" and t["conf"] == 0 for t in inactive), str([(t['r'], t['c'], t['label']) for t in d.get('tiles', [])][:4]))
    call("PUT", f"/api/v1/devices/{cid}/config", op, {"params": {"active_tiles": None}})

    # --- Gardens / Zones (§10.4) ---
    st, g = call("POST", "/api/v1/gardens", adm, {"code": "smoke-wp07", "name": "Vườn thử WP-07"})
    if st == 409:
        _, gl = call("GET", "/api/v1/gardens", adm)
        g = next(x for x in gl if x["code"] == "smoke-wp07")
        st = 201
    check("Admin tạo vườn (hoặc đã có) → 201", st == 201 and g.get("id"), f"HTTP {st}")
    st, _ = call("POST", "/api/v1/gardens", adm, {"code": "smoke-wp07", "name": "Trùng"})
    check("Trùng mã vườn → 409", st == 409, f"HTTP {st}")
    st, _ = call("POST", "/api/v1/gardens", op, {"code": "op-garden", "name": "x"})
    check("Operator tạo vườn → 403", st == 403, f"HTTP {st}")
    zname = f"Khay thử {int(time.time()) % 100000}"
    st, z = call("POST", f"/api/v1/gardens/{g['id']}/zones", adm, {"name": zname, "cropType": "Cà chua"})
    check("Admin tạo khu vực → 201", st == 201 and z.get("gardenId") == g["id"], f"HTTP {st}")
    st, z2 = call("PATCH", f"/api/v1/zones/{z.get('id')}", adm, {"cropType": "Ớt"})
    check("Sửa khu vực → 200", st == 200 and z2.get("cropType") == "Ớt", f"HTTP {st}")
    st, gl = call("GET", "/api/v1/gardens", vw)
    check("Viewer đọc vườn có thiết bị được gán (g01), không thấy vườn thử",
          st == 200 and any(x["code"] == "g01" for x in gl) and not any(x["code"] == "smoke-wp07" for x in gl),
          f"HTTP {st} {[x['code'] for x in gl] if isinstance(gl, list) else gl}")
    st, zl = call("GET", f"/api/v1/gardens/{g['id']}/zones", vw)
    check("Viewer đọc khu của vườn không được gán → 404", st == 404, f"HTTP {st}")
    st, zl = call("GET", "/api/v1/gardens/1/zones", vw)
    check("Viewer đọc khu vực của g01", st == 200 and any(x["id"] == 1 for x in zl), f"HTTP {st}")
    st, _ = call("DELETE", "/api/v1/zones/1", adm)
    check("Xóa khu vực còn thiết bị → 409", st == 409, f"HTTP {st}")
    st, _ = call("DELETE", f"/api/v1/zones/{z.get('id')}", adm)
    check("Xóa khu vực trống → 204", st == 204, f"HTTP {st}")

    # --- Khóa / đổi khóa: cache xác thực bị xóa ---
    stop.set()
    cam_dev.stop()
    time.sleep(21)  # qua cửa sổ 20 s của ảnh theo lịch
    st, _ = call("POST", f"/api/v1/devices/{cid}/suspend", adm, {"reason": "smoke wp07"})
    st2, _ = upload_raw(f"{code}:{secret}", healthy)
    check("Camera bị suspend → upload 403", st == 200 and st2 == 403, f"suspend HTTP {st}, upload HTTP {st2}")
    call("POST", f"/api/v1/devices/{cid}/resume", adm, {"reason": "smoke wp07"})
    st, rot = call("POST", f"/api/v1/devices/{cid}/rotate-secret", adm)
    st2, _ = upload_raw(f"{code}:{secret}", healthy)
    st3, _ = upload_raw(f"{code}:{rot.get('secret')}", healthy)
    check("Cấp lại khóa → secret cũ 401, secret mới 201", (st2, st3) == (401, 201), f"{st2} {st3}")

    # Dọn dẹp
    for d_id, c_code in ((cid, code), (ctl["id"], ctl["deviceCode"])):
        call("POST", f"/api/v1/devices/{d_id}/decommission", adm, {"reason": "smoke wp07", "confirm": c_code})
    st2, _ = upload_raw(f"{code}:{rot.get('secret')}", healthy)
    check("Camera đã thu hồi → upload 401/403", st2 in (401, 403), f"HTTP {st2}")
    if uid.get(stranger) is None:
        _, us = call("GET", f"/api/v1/users?q={stranger}", adm)
        for u in us if isinstance(us, list) else []:
            call("POST", f"/api/v1/users/{u['id']}/lock", adm)

    fails = sum(1 for ok, *_ in base.results if not ok)
    say(f"=== KẾT QUẢ: {'ĐẠT TẤT CẢ' if not fails else f'{fails} mục KHÔNG ĐẠT'} ({len(base.results)} mục) ===")
    say(f"Log: {base.OUT}")
    return fails


if __name__ == "__main__":
    sys.exit(main())
