"""cam_sim.py — Camera giả (Node 2, ESP32-CAM) cho WP-07. KHÔNG thay thế thiết bị thật trong demo.

Đúng giao thức đặc tả §7, §8: đăng nhập MQTT bằng device_code/secret, LWT + status (heartbeat 30 s),
subscribe command/config; lệnh `capture` → upload JPEG qua HTTP (§8.9, Basic auth, X-Captured-At, X-Trigger,
X-Cmd-Id) → ack `executed {image_id}` hoặc `failed {reason}`; chụp theo chu kỳ `capture_interval_min`.
Ảnh lấy trong tests/fixtures/images/ (healthy | sick | empty | đường dẫn .jpg), tự sinh nếu thiếu.

Lệnh (qua scripts/windows/cam-sim.ps1):
  register [--zone 1]                                  đăng ký + cấp phát một camera qua API (admin) → runtime/sim/cameras.json
  run [--code cam-0002] [--image sick] [--interval-min 1]   chạy camera giả (Ctrl+C để dừng)
  upload [--code cam-0002] [--image sick]              upload một ảnh (trigger=schedule) rồi thoát
Bí mật đọc từ .env và runtime/sim/cameras.json (không commit).
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import paho.mqtt.client as mqtt

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tests" / "fixtures"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_images  # noqa: E402
import simulator  # noqa: E402  — dùng lại load_env, log

CAMS_FILE = REPO / "runtime" / "sim" / "cameras.json"
log = simulator.log
ENV: dict = {}


def now_ms() -> int:
    return int(time.time() * 1000)


def backend_url() -> str:
    return os.environ.get("SIM_BACKEND_URL", f"http://127.0.0.1:{ENV.get('BACKEND_PORT', '8000')}")


def image_bytes(name: str) -> bytes:
    p = Path(name)
    if p.suffix.lower() != ".jpg":
        p = make_images.ensure() / f"{name}.jpg"
    return p.read_bytes()


def upload(code: str, secret: str, data: bytes, trigger: str = "schedule", cmd_id: str | None = None,
           captured_ms: int | None = None, base: str | None = None, timeout: float = 15) -> tuple[int, dict]:
    """POST /device-api/v1/images như firmware Node 2. Trả về (HTTP status, JSON)."""
    auth = base64.b64encode(f"{code}:{secret}".encode()).decode()
    h = {"Authorization": f"Basic {auth}", "Content-Type": "image/jpeg", "X-Trigger": trigger,
         "X-Captured-At": str(captured_ms if captured_ms is not None else now_ms())}
    if cmd_id:
        h["X-Cmd-Id"] = cmd_id
    req = urllib.request.Request((base or backend_url()) + "/device-api/v1/images", data=data, method="POST", headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"raw": raw[:200].decode(errors="replace")}
    except (urllib.error.URLError, OSError) as e:
        return 0, {"error": str(e)}


class CamDevice:
    def __init__(self, code: str, secret: str, garden: str, image: str = "healthy") -> None:
        self.code, self.secret, self.garden, self.image = code, secret, garden, image
        self.base = f"nursery/{garden}/{code}"
        self.connected = False
        self.ignore_commands = False
        self.cfg: dict = {"capture_interval_min": 30}
        self.cfg_version = 0
        self.started = time.time()
        self.uploads: list[tuple[int, dict]] = []
        self.seq_e = int(time.time()) % 100000
        self.dedup: list[str] = []
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=code, protocol=mqtt.MQTTv311, clean_session=True)
        c.username_pw_set(code, secret)
        c.will_set(f"{self.base}/status", json.dumps({"v": 1, "device_id": code, "online": False}), qos=1, retain=True)
        c.on_connect, c.on_disconnect, c.on_message = self._on_connect, self._on_disconnect, self._on_message
        c.reconnect_delay_set(1, 30)
        self.client = c

    # ---------- MQTT ----------
    def start(self) -> None:
        self.client.connect_async(simulator.broker_host(), int(ENV.get("MQTT_PORT", 1883)), keepalive=30)
        self.client.loop_start()

    def stop(self) -> None:
        self._pub("status", {"v": 1, "device_id": self.code, "online": False}, retain=True)
        self.client.disconnect()
        self.client.loop_stop()

    def _on_connect(self, cl, _u, _f, rc, _p=None) -> None:
        if getattr(rc, "is_failure", rc != 0):
            log(f"{self.code}: MQTT bị từ chối ({rc})")
            return
        self.connected = True
        log(f"{self.code}: MQTT OK")
        cl.subscribe([(f"{self.base}/command", 1), (f"{self.base}/config", 1)])
        self.publish_status()

    def _on_disconnect(self, *_a) -> None:
        self.connected = False

    def _pub(self, kind: str, payload: dict, retain: bool = False) -> None:
        if self.connected:
            self.client.publish(f"{self.base}/{kind}", json.dumps(payload, separators=(",", ":")), qos=1, retain=retain)

    def publish_status(self) -> None:
        self._pub("status", {"v": 1, "device_id": self.code, "ts": now_ms(), "online": True, "fw": "cam-sim-1.0.0",
                             "hw": "node2-sim", "ip": "127.0.0.1", "rssi": -60, "uptime_s": int(time.time() - self.started),
                             "heap": 120000, "psram": 4000000, "config_version": self.cfg_version}, retain=True)

    def ack(self, cmd_id: str, result: str, detail: dict | None = None, kind: str = "command") -> None:
        self._pub("ack", {"v": 1, "device_id": self.code, "ts": now_ms(), "cmd_id": cmd_id, "kind": kind,
                          "result": result, "detail": detail or {}})

    def event(self, typ: str, detail: dict) -> None:
        self.seq_e += 1
        self._pub("event", {"v": 1, "device_id": self.code, "ts": now_ms(), "seq": self.seq_e, "type": typ,
                            "detail": detail})

    def _on_message(self, _c, _u, msg) -> None:
        try:
            body = json.loads(msg.payload)
        except ValueError:
            return
        kind = msg.topic.rsplit("/", 1)[-1]
        if kind == "config":
            ver = int(body.get("config_version") or 0)
            if ver > self.cfg_version:
                self.cfg.update(body.get("params") or {})
                self.cfg_version = ver
                self.ack(f"cfg-{ver}", "executed", kind="config")
            return
        if kind == "command" and not self.ignore_commands:
            # Upload chạy trong luồng riêng để không chặn vòng lặp mạng của paho (giống firmware: chụp → upload → ack)
            threading.Thread(target=self.handle_command, args=(body,), daemon=True).start()

    def handle_command(self, b: dict) -> None:
        cid, action = str(b.get("cmd_id") or ""), b.get("action")
        if cid in self.dedup:
            return
        self.dedup = (self.dedup + [cid])[-20:]
        if b.get("issued_at") and b.get("ttl_s") and now_ms() - int(b["issued_at"]) > int(b["ttl_s"]) * 1000:
            self.ack(cid, "expired")
            return
        if action == "capture":
            img_id, reason = self.capture("command", cid)
            if img_id:
                self.ack(cid, "executed", {"image_id": img_id})
            else:
                self.ack(cid, "failed", {"reason": reason})
        elif action in ("flash", "reboot"):
            self.ack(cid, "executed")
        elif action == "request_status":
            self.ack(cid, "executed")
            self.publish_status()
        else:
            self.ack(cid, "unsupported")

    # ---------- chụp + upload ----------
    def capture(self, trigger: str, cmd_id: str | None = None) -> tuple[str | None, str]:
        """Upload, thử lại 3 lần cách 5 s (§7.1); thất bại → event upload_failed."""
        data = image_bytes(self.image)
        last = ""
        for attempt in range(3):
            st, body = upload(self.code, self.secret, data, trigger, cmd_id)
            self.uploads.append((st, body))
            if st == 201:
                log(f"{self.code}: upload {trigger} → {body.get('image_id')}")
                return body.get("image_id"), ""
            last = f"http_{st}"
            log(f"{self.code}: upload lỗi HTTP {st} {body}")
            if st in (400, 401, 403, 413):
                break  # lỗi không sửa được bằng thử lại
            if attempt < 2:
                time.sleep(5)
        self.event("upload_failed", {"reason": last, "trigger": trigger})
        return None, last

    def loop(self, stop: threading.Event, interval_min: float | None = None) -> None:
        nxt_status = time.time() + 30
        nxt_cap = time.time() + 5 if interval_min else float("inf")
        while not stop.is_set():
            now = time.time()
            if now >= nxt_status:
                self.publish_status()
                nxt_status = now + 30
            if now >= nxt_cap:
                self.capture("schedule")
                period = interval_min or float(self.cfg.get("capture_interval_min") or 30)
                nxt_cap = now + period * 60
            stop.wait(0.5)


# ---------------------------------------------------------------------------

def _load() -> dict:
    return json.loads(CAMS_FILE.read_text(encoding="utf-8")) if CAMS_FILE.exists() else {}


def _creds(code: str | None) -> tuple[str, dict]:
    cams = _load()
    if not cams:
        sys.exit("Chưa có camera giả. Chạy: cam-sim.ps1 register")
    code = code or list(cams)[-1]
    if code not in cams:
        sys.exit(f"Không có {code} trong {CAMS_FILE}")
    return code, cams[code]


def cmd_register(a) -> None:
    base = backend_url() + "/api/v1"

    def call(method, path, token=None, body=None):
        req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                     method=method, headers={"Content-Type": "application/json"})
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read() or b"{}")

    tok = call("POST", "/auth/login", body={"username": "admin", "password": ENV["SEED_ADMIN_PASSWORD"]})["accessToken"]
    d = call("POST", "/devices", tok, {"type": "CAMERA", "name": "Camera giả (cam_sim)", "zoneId": a.zone})
    p = call("POST", f"/devices/{d['id']}/provision", tok)
    users = {u["username"]: u["id"] for u in call("GET", "/users", tok)}
    for name, perm in (("operator", "CONTROL"), ("viewer", "VIEW")):
        if name in users:
            call("POST", f"/devices/{d['id']}/assignments", tok, {"userId": users[name], "permission": perm})
    cams = _load()
    cams[p["deviceCode"]] = {"secret": p["secret"], "garden": p["gardenCode"], "id": d["id"]}
    CAMS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CAMS_FILE.write_text(json.dumps(cams, indent=2), encoding="utf-8")
    log(f"{p['deviceCode']} (id {d['id']}): đã đăng ký + cấp phát, gán operator=CONTROL, viewer=VIEW")
    log(f"Chạy: cam-sim.ps1 run --code {p['deviceCode']} --image sick")


def cmd_run(a) -> None:
    code, c = _creds(a.code)
    cam = CamDevice(code, c["secret"], c["garden"], a.image)
    cam.start()
    stop = threading.Event()
    log(f"{code}: camera giả chạy (ảnh={a.image}, chu kỳ={a.interval_min or 'theo cấu hình'} phút). Ctrl+C để dừng")
    try:
        cam.loop(stop, a.interval_min)
    except KeyboardInterrupt:
        pass
    finally:
        cam.stop()


def cmd_upload(a) -> None:
    code, c = _creds(a.code)
    st, body = upload(code, c["secret"], image_bytes(a.image), "schedule")
    log(f"{code}: HTTP {st} {body}")
    sys.exit(0 if st == 201 else 1)


def main() -> None:
    global ENV
    ENV = simulator.load_env()
    simulator.ENV = ENV
    ap = argparse.ArgumentParser(description="Camera giả Node 2 (WP-07)")
    sp = ap.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("register")
    r.add_argument("--zone", type=int, default=1)
    r = sp.add_parser("run")
    r.add_argument("--code")
    r.add_argument("--image", default="healthy", help="healthy | sick | empty | đường dẫn .jpg")
    r.add_argument("--interval-min", type=float, default=None, help="chụp theo chu kỳ (phút); mặc định theo cấu hình")
    r = sp.add_parser("upload")
    r.add_argument("--code")
    r.add_argument("--image", default="healthy")
    a = ap.parse_args()
    {"register": cmd_register, "run": cmd_run, "upload": cmd_upload}[a.cmd](a)


if __name__ == "__main__":
    main()
