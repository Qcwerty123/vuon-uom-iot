"""
simulator.py — Thiết bị mô phỏng cho hệ thống vườn ươm (WP-01).

Đóng vai Node 1 (ESP32 điều khiển) đúng giao thức đặc tả §8: telemetry, status (+LWT), event,
command/ack (chống trùng cmd_id, hạn lệnh), config retain (config_version), khóa an toàn,
tưới/thông gió tự động như firmware §6.5–§6.6. Dùng để phát triển backend/web khi chưa có
phần cứng và để đo NFR05, NFR08, NFR09. KHÔNG thay thế thiết bị thật trong demo.

Lệnh (chạy qua scripts/windows/sim.ps1, tham số giống hệt):
  register --count 1                                   đăng ký + cấp phát qua backend API (thiết bị hiện trên web) — dùng cái này khi đã có backend
  provision --count 3 [--start 9001] [--garden g01]   chỉ tạo tài khoản broker ctl-9001.. (khi chưa có backend)
  deprovision                                          xóa các tài khoản đã tạo
  run [--codes ctl-9001,ctl-9002] [--interval 10] [--duplicate-rate 0.05] [--drop-rate 0.02]
      [--offline-every 0 --offline-for 30] [--soil 45 --tank 80]
  watch [--topic nursery/#]                            xem mọi bản tin (đăng nhập bằng tài khoản backend)
  cmd ctl-9001 pump_on --duration 5                    gửi lệnh như backend, chờ ack (--mode AUTO|MANUAL cho set_mode)
  config ctl-9001 --set soil_low=40 --set soil_high=60  gửi cấu hình retain như backend, chờ ack

Bí mật đọc từ .env ở gốc repo; secret thiết bị mô phỏng nằm trong runtime/sim/devices.json (không commit).
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import sys
import threading
import time
import uuid
from collections import deque
from pathlib import Path

import paho.mqtt.client as mqtt

REPO = Path(__file__).resolve().parents[2]
SIM_DIR = REPO / "runtime" / "sim"
DEVICES_FILE = SIM_DIR / "devices.json"
STATE_FILE = SIM_DIR / "state.json"
LOG_DIR = REPO / "logs" / "tests"
DYNSEC_JSON = REPO / "runtime" / "mosquitto" / "dynamic-security.json"

_print_lock = threading.Lock()
_log_file = None


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    with _print_lock:
        print(line, flush=True)
        if _log_file:
            _log_file.write(line + "\n")
            _log_file.flush()


def load_env() -> dict:
    env = {}
    p = REPO / ".env"
    if not p.exists():
        sys.exit("Thiếu .env ở gốc repo")
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


ENV: dict = {}


def broker_host() -> str:
    return os.environ.get("SIM_MQTT_HOST", "127.0.0.1")


def now_ms() -> int:
    return int(time.time() * 1000)


def sync_dynsec_file() -> None:
    """Mosquitto 2.0.18 trên Windows không đổi tên đè được file dynsec (đặc tả §17.5)."""
    new = Path(str(DYNSEC_JSON) + ".new")
    if new.exists():
        if not DYNSEC_JSON.exists() or new.stat().st_mtime >= DYNSEC_JSON.stat().st_mtime:
            shutil.copyfile(new, DYNSEC_JSON)
        new.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Quản trị broker (Dynamic Security qua $CONTROL) — giống việc backend sẽ làm khi cấp phát
# ---------------------------------------------------------------------------

def dynsec(commands: list[dict]) -> list[dict]:
    done = threading.Event()
    result: list[dict] = []
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"sim-admin-{uuid.uuid4().hex[:6]}",
                    protocol=mqtt.MQTTv311)
    c.username_pw_set(ENV["MQTT_DYNSEC_USER"], ENV["MQTT_DYNSEC_PASSWORD"])

    def on_connect(cl, _u, _f, rc, _p=None):
        if getattr(rc, "is_failure", rc != 0):
            log(f"Không đăng nhập được dynsec-admin: {rc}")
            done.set()
            return
        cl.subscribe("$CONTROL/dynamic-security/v1/response", qos=1)

    def on_subscribe(cl, *_a):
        cl.publish("$CONTROL/dynamic-security/v1", json.dumps({"commands": commands}), qos=1)

    def on_message(_cl, _u, msg):
        result.extend(json.loads(msg.payload).get("responses", []))
        done.set()

    c.on_connect, c.on_subscribe, c.on_message = on_connect, on_subscribe, on_message
    c.connect(broker_host(), int(ENV.get("MQTT_PORT", 1883)), 30)
    c.loop_start()
    done.wait(10)
    c.loop_stop()
    c.disconnect()
    time.sleep(0.3)
    sync_dynsec_file()
    return result


def acl_commands(code: str, garden: str) -> list[dict]:
    base = f"nursery/{garden}/{code}"
    cmds = [{"command": "createRole", "rolename": code}]
    for k in ("telemetry", "status", "event", "ack"):
        cmds.append({"command": "addRoleACL", "rolename": code, "acltype": "publishClientSend",
                     "topic": f"{base}/{k}", "allow": True})
    for k in ("command", "config"):
        for t in ("subscribeLiteral", "publishClientReceive"):
            cmds.append({"command": "addRoleACL", "rolename": code, "acltype": t, "topic": f"{base}/{k}", "allow": True})
    return cmds


def load_devices() -> dict:
    if DEVICES_FILE.exists():
        return json.loads(DEVICES_FILE.read_text(encoding="utf-8"))
    return {}


def save_devices(d: dict) -> None:
    SIM_DIR.mkdir(parents=True, exist_ok=True)
    DEVICES_FILE.write_text(json.dumps(d, indent=2), encoding="utf-8")


def cmd_provision(a) -> None:
    devs = load_devices()
    for i in range(a.count):
        code = f"ctl-{a.start + i:04d}"
        if code in devs:
            log(f"{code}: đã có, bỏ qua")
            continue
        secret = uuid.uuid4().hex + uuid.uuid4().hex[:8]
        cmds = [{"command": "createClient", "username": code, "password": secret}]
        cmds += acl_commands(code, a.garden)
        cmds.append({"command": "addClientRole", "username": code, "rolename": code})
        res = dynsec(cmds)
        errors = [r for r in res if r.get("error")]
        if errors or not res:
            log(f"{code}: LỖI {errors or 'không có phản hồi'}")
            continue
        devs[code] = {"secret": secret, "garden": a.garden}
        log(f"{code}: đã tạo tài khoản broker")
    save_devices(devs)


def cmd_register(a) -> None:
    import urllib.request
    base = f"http://127.0.0.1:{ENV.get('BACKEND_PORT', '8000')}/api/v1"

    def call(method, path, token=None, body=None):
        req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                     method=method, headers={"Content-Type": "application/json"})
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read() or b"{}")

    tok = call("POST", "/auth/login", body={"username": "admin", "password": ENV["SEED_ADMIN_PASSWORD"]})["accessToken"]
    devs = load_devices()
    for i in range(a.count):
        d = call("POST", "/devices", tok, {"type": "CONTROLLER", "name": f"Thiết bị mô phỏng {i + 1}", "zoneId": a.zone})
        p = call("POST", f"/devices/{d['id']}/provision", tok)
        devs[p["deviceCode"]] = {"secret": p["secret"], "garden": p["gardenCode"], "id": d["id"]}
        log(f"{p['deviceCode']} (id {d['id']}): đã đăng ký + cấp phát qua backend")
    save_devices(devs)
    log("Chạy: sim.ps1 run --codes " + ",".join(k for k, v in devs.items() if "id" in v))


def cmd_deprovision(_a) -> None:
    devs = load_devices()
    for code in list(devs):
        dynsec([{"command": "deleteClient", "username": code}, {"command": "deleteRole", "rolename": code}])
        devs.pop(code)
        log(f"{code}: đã xóa")
    save_devices(devs)


# ---------------------------------------------------------------------------
# Thiết bị mô phỏng Node 1
# ---------------------------------------------------------------------------

DEFAULT_CFG = {
    "soil_low": 35.0, "soil_high": 55.0, "pump_max_s": 15, "cooldown_s": 120, "tank_min": 15.0,
    "temp_high": 32.0, "temp_hyst": 2.0, "hum_high": 90.0, "hum_hyst": 5.0,
    "telemetry_interval_s": 10, "manual_ignores_cooldown": False,
    "soil_cal": {"s1": {"dry": 3150, "wet": 1320}, "s2": {"dry": 3210, "wet": 1290}},
    "tank_cal": {"empty_cm": 25.0, "full_cm": 5.0},
    # Chiếu sáng bổ sung (§6.11), mặc định như firmware v1.1.0
    "lamp_start_hour": 6, "lamp_end_hour": 20, "lamp_lux_low": 800, "lamp_hyst": 700, "lamp_self_lux": 300,
    "lamp_hold_s": 10, "lamp_min_on_s": 30, "lamp_min_off_s": 30, "lamp_override_min": 60,
}
RANGES = {  # giống firmware config_store.cpp
    "soil_low": (0, 100), "soil_high": (0, 100), "pump_max_s": (1, 60), "cooldown_s": (0, 3600),
    "tank_min": (0, 100), "temp_high": (-10, 60), "temp_hyst": (0.5, 10), "hum_high": (0, 100),
    "hum_hyst": (1, 20), "telemetry_interval_s": (2, 300),
    "lamp_start_hour": (0, 23), "lamp_end_hour": (1, 24), "lamp_lux_low": (0, 65535), "lamp_hyst": (1, 65535),
    "lamp_self_lux": (0, 5000), "lamp_hold_s": (2, 600), "lamp_min_on_s": (10, 3600), "lamp_min_off_s": (10, 3600),
    "lamp_override_min": (1, 240),
}
TZ_OFFSET_H = 7  # giờ Việt Nam cho khung chiếu sáng
TANK_HYST = 3.0


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


_state_lock = threading.Lock()


def persist_state(code: str, data: dict) -> None:
    with _state_lock:
        st = load_state()
        st[code] = data
        SIM_DIR.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(st, indent=2), encoding="utf-8")


class SimDevice:
    def __init__(self, code: str, secret: str, garden: str, a) -> None:
        self.code, self.secret, self.garden, self.a = code, secret, garden, a
        self.base = f"nursery/{garden}/{code}"
        saved = load_state().get(code, {})
        self.cfg = dict(DEFAULT_CFG)
        self.cfg.update(saved.get("cfg", {}))
        self.cfg_version = saved.get("cfg_version", 0)
        # seq không lặp sau khi khởi động lại (như firmware: +50)
        self.seq_t = saved.get("seq_t", 0) + 50
        self.seq_e = saved.get("seq_e", 0) + 50
        # môi trường vật lý
        self.soil = float(a.soil) + random.uniform(-2, 2)
        self.temp = 29.0 + random.uniform(-1, 1)
        self.hum = 75.0 + random.uniform(-3, 3)
        self.light = 1500.0
        self.tank = float(a.tank)
        # cơ cấu chấp hành
        self.pump = False
        self.pump_until = 0.0
        self.pump_src = "auto"
        self.pump_started = 0.0
        self.pump_off_at = 0.0
        self.pump_ever = False
        self.fan = False
        self.fan_override_until = 0.0
        self.lamp = False
        self.lamp_changed = 0.0         # lần đổi trạng thái gần nhất (thời gian giữ tối thiểu)
        self.lamp_want_since = 0.0      # debounce: thời điểm điều kiện đổi bắt đầu đúng liên tục
        self.lamp_override_until = 0.0  # lệnh tay khi AUTO
        self.overheat = False
        self.auto = saved.get("auto", True)
        self.tank_low = False
        # giao thức
        self.dedup: deque = deque(maxlen=20)
        self.buffer: deque = deque(maxlen=200)
        self.events: deque = deque(maxlen=30)
        self.dropped = 0
        self.connected = False
        self.forced_offline_until = 0.0
        self.started = time.time()
        self.lock = threading.RLock()
        self.client = self._make_client()
        self.emit("boot", {"reset_reason": "power_on", "fw": "sim-1.0.0"})

    # ---------- MQTT ----------
    def _make_client(self) -> mqtt.Client:
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=self.code, protocol=mqtt.MQTTv311,
                        clean_session=True)
        c.username_pw_set(self.code, self.secret)
        c.will_set(f"{self.base}/status", json.dumps({"v": 1, "device_id": self.code, "online": False}),
                   qos=1, retain=True)
        c.on_connect = self._on_connect
        c.on_disconnect = self._on_disconnect
        c.on_message = self._on_message
        c.reconnect_delay_set(1, 30)
        return c

    def start(self) -> None:
        self.client.connect_async(broker_host(), int(ENV.get("MQTT_PORT", 1883)), keepalive=30)
        self.client.loop_start()

    def go_offline(self) -> None:
        """Mất mạng đột ngột: đóng socket, không gửi DISCONNECT → broker phát LWT như khi rút nguồn."""
        self.client.loop_stop()
        sock = self.client.socket()
        if sock:
            try:
                sock.close()
            except OSError:
                pass
        self.connected = False

    def go_online(self) -> None:
        try:
            self.client.reconnect()
        except OSError as e:
            log(f"{self.code}: chưa kết nối lại được ({e}), paho sẽ thử tiếp")
        self.client.loop_start()

    def _on_connect(self, cl, _u, _f, rc, _p=None) -> None:
        if getattr(rc, "is_failure", rc != 0):
            log(f"{self.code}: kết nối bị từ chối ({rc}) — thiết bị bị khóa/thu hồi hoặc sai secret?")
            return
        self.connected = True
        log(f"{self.code}: MQTT OK")
        cl.subscribe([(f"{self.base}/command", 1), (f"{self.base}/config", 1)])
        self.publish_status()
        self.flush_events()

    def _on_disconnect(self, *_a) -> None:
        if self.connected:
            log(f"{self.code}: mất kết nối MQTT")
        self.connected = False

    def _pub(self, kind: str, payload: dict, retain: bool = False) -> bool:
        if not self.connected:
            return False
        info = self.client.publish(f"{self.base}/{kind}", json.dumps(payload, separators=(",", ":")), qos=0,
                                   retain=retain)
        return info.rc == mqtt.MQTT_ERR_SUCCESS

    def _on_message(self, _c, _u, msg) -> None:
        kind = msg.topic.rsplit("/", 1)[-1]
        try:
            body = json.loads(msg.payload)
        except ValueError:
            log(f"{self.code}: JSON lỗi trên {kind}, bỏ qua")
            return
        with self.lock:
            if kind == "command":
                self.handle_command(body)
            elif kind == "config":
                self.handle_config(body)

    # ---------- event / status / telemetry ----------
    def emit(self, typ: str, detail: dict | None = None) -> None:
        self.seq_e += 1
        self.events.append({"v": 1, "device_id": self.code, "ts": now_ms(), "seq": self.seq_e,
                            "type": typ, "detail": detail or {}})
        self.flush_events()

    def flush_events(self) -> None:
        while self.events and self.connected:
            if not self._pub("event", self.events[0]):
                break
            self.events.popleft()

    def publish_status(self) -> None:
        self._pub("status", {
            "v": 1, "device_id": self.code, "ts": now_ms(), "online": True, "fw": "sim-1.0.0",
            "hw": "node1-sim", "ip": "127.0.0.1", "rssi": -55, "uptime_s": int(time.time() - self.started),
            "heap": 180000, "config_version": self.cfg_version, "buffered": len(self.buffer),
            "dropped": self.dropped}, retain=True)

    def locks(self) -> list[str]:
        out = []
        if self.tank_low:
            out.append("no_water")
        if self.cooldown_active():
            out.append("cooldown")
        if self.overheat:
            out.append("overheat")
        return out

    def telemetry_payload(self) -> dict:
        self.seq_t += 1
        s1 = max(0, min(100, self.soil + random.uniform(-2, 2)))
        s2 = max(0, min(100, self.soil + random.uniform(-2, 2)))
        raw_cm = self.cfg["tank_cal"]["empty_cm"] - self.tank / 100 * (
            self.cfg["tank_cal"]["empty_cm"] - self.cfg["tank_cal"]["full_cm"])
        m = lambda v, u: {"v": round(v, 1), "u": u, "ok": True}  # noqa: E731
        tank = m(self.tank, "%")
        tank["raw_cm"] = round(raw_cm, 1)
        return {
            "v": 1, "device_id": self.code, "seq": self.seq_t, "ts": now_ms(), "time_synced": True,
            "buffered": False,
            "data": {"soil1": m(s1, "%"), "soil2": m(s2, "%"), "soil": m((s1 + s2) / 2, "%"),
                     "air_temp": m(self.temp, "C"), "air_hum": m(self.hum, "%RH"),
                     "light": m(self.measured_light(), "lux"), "tank": tank},
            "state": {"pump": int(self.pump), "fan": int(self.fan), "lamp": int(self.lamp), "mode": "AUTO" if self.auto else "MANUAL",
                      "locks": self.locks()},
        }

    def telemetry_tick(self) -> None:
        p = self.telemetry_payload()
        if random.random() < self.a.drop_rate:  # mô phỏng mất bản tin (NFR05)
            return
        if self.buffer or not self.connected:
            self.buffer.append(p)
            if len(self.buffer) == self.buffer.maxlen:
                self.dropped += 1
            return
        self._pub("telemetry", p)
        if random.random() < self.a.duplicate_rate:  # mô phỏng gửi trùng (NFR08)
            self._pub("telemetry", p)

    def drain_buffer(self) -> None:
        if self.buffer and self.connected:
            p = dict(self.buffer[0])
            p["buffered"] = True
            if self._pub("telemetry", p):
                self.buffer.popleft()

    # ---------- điều khiển (như firmware control.cpp) ----------
    def cooldown_active(self) -> bool:
        return self.pump_ever and (time.time() - self.pump_off_at) < self.cfg["cooldown_s"]

    def pump_block(self, src: str) -> str | None:
        if self.tank_low:
            return "blocked_no_water"
        if self.cooldown_active() and not (src != "auto" and self.cfg["manual_ignores_cooldown"]):
            return "blocked_cooldown"
        return None

    def pump_start(self, seconds: int, src: str) -> None:
        was = self.pump
        cap = min(seconds, self.cfg["pump_max_s"])
        self.pump, self.pump_src, self.pump_started = True, src, time.time()
        self.pump_until = self.pump_started + cap
        if not was:
            self.emit("pump_on", {"source": src, "duration_s": seconds})
        log(f"{self.code}: BƠM BẬT {cap}s ({src})")

    def pump_stop(self, reason: str, by: str) -> None:
        if not self.pump:
            return
        self.pump, self.pump_ever, self.pump_off_at = False, True, time.time()
        self.emit("pump_off", {"source": by, "duration_s": round(time.time() - self.pump_started, 1), "reason": reason})
        log(f"{self.code}: BƠM TẮT ({reason})")

    def fan_set(self, on: bool, src: str) -> None:
        if self.fan == on:
            return
        self.fan = on
        self.emit("fan_on" if on else "fan_off", {"source": src})

    # ---------- đèn (§6.11) ----------
    def measured_light(self) -> float:
        return self.light + (self.cfg["lamp_self_lux"] if self.lamp else 0)

    def lamp_set(self, on: bool, src: str, reason: str) -> None:
        if self.lamp == on:
            return
        self.lamp = on
        self.lamp_changed = time.time()
        self.lamp_want_since = 0.0
        self.emit("lamp_on" if on else "lamp_off", {"source": src, "reason": reason})

    def lamp_control(self) -> None:
        c, now = self.cfg, time.time()
        thr = c["temp_high"] + 3
        if not self.overheat and self.temp >= thr:
            self.overheat = True
        elif self.overheat and self.temp <= thr - c["temp_hyst"]:
            self.overheat = False
        if self.overheat:  # khóa nhiệt: mọi chế độ
            self.lamp_override_until = 0.0
            self.lamp_set(False, "auto", "overheat")
            return
        override_ended = False
        if self.lamp_override_until and now >= self.lamp_override_until:
            self.lamp_override_until, override_ended = 0.0, True
        if not self.auto or self.lamp_override_until:  # MANUAL, hoặc lệnh tay còn hiệu lực (như firmware)
            return
        hour = (time.gmtime(now).tm_hour + TZ_OFFSET_H) % 24
        if not c["lamp_start_hour"] <= hour < c["lamp_end_hour"]:
            self.lamp_set(False, "auto", "override_end" if override_ended else "window_end")
            self.lamp_want_since = 0.0
            return
        lux = self.measured_light()
        if not self.lamp and lux < c["lamp_lux_low"]:
            want, reason, hold_min = True, "low_light", c["lamp_min_off_s"]
        elif self.lamp and lux >= c["lamp_lux_low"] + c["lamp_hyst"]:
            want, reason, hold_min = False, "bright", c["lamp_min_on_s"]
        else:
            self.lamp_want_since = 0.0
            return
        if not self.lamp_want_since:
            self.lamp_want_since = now
        if now - self.lamp_want_since >= c["lamp_hold_s"] and (not self.lamp_changed
                                                              or now - self.lamp_changed >= hold_min):
            self.lamp_set(want, "auto", reason)

    def physics(self, dt: float) -> None:
        self.soil -= 0.02 * dt                                  # đất khô dần
        if self.pump:
            self.soil += 1.5 * dt
            self.tank -= 0.4 * dt
        self.temp += (0.01 if not self.fan else -0.05) * dt + random.uniform(-0.02, 0.02)
        self.hum += random.uniform(-0.1, 0.1) - (0.03 * dt if self.fan else 0)
        self.light = max(0.0, self.light + random.uniform(-20, 20))
        self.soil, self.tank = max(0, min(100, self.soil)), max(0, min(100, self.tank))
        self.temp, self.hum = max(15, min(45, self.temp)), max(30, min(99, self.hum))

    def control(self) -> None:
        if not self.tank_low and self.tank < self.cfg["tank_min"]:
            self.tank_low = True
            self.emit("tank_low", {"tank": round(self.tank, 1)})
        elif self.tank_low and self.tank >= self.cfg["tank_min"] + TANK_HYST:
            self.tank_low = False
            self.emit("tank_ok", {"tank": round(self.tank, 1)})
        if self.pump:
            if time.time() >= self.pump_until:
                self.pump_stop("done", self.pump_src)
            elif self.tank_low:
                self.pump_stop("no_water", "auto")
            elif self.pump_src == "auto" and self.soil >= self.cfg["soil_high"]:
                self.pump_stop("soil_high", "auto")
        self.lamp_control()
        if not self.auto:
            return
        if not self.pump and self.soil < self.cfg["soil_low"] and self.pump_block("auto") is None:
            self.pump_start(self.cfg["pump_max_s"], "auto")
        if time.time() < self.fan_override_until:
            return
        if self.temp >= self.cfg["temp_high"] or self.hum >= self.cfg["hum_high"]:
            self.fan_set(True, "auto")
        elif (self.temp <= self.cfg["temp_high"] - self.cfg["temp_hyst"]
              and self.hum <= self.cfg["hum_high"] - self.cfg["hum_hyst"]):
            self.fan_set(False, "auto")

    # ---------- lệnh và cấu hình (như firmware protocol.cpp) ----------
    def ack(self, cmd_id: str, kind: str, result: str, detail: dict | None = None) -> None:
        self._pub("ack", {"v": 1, "device_id": self.code, "ts": now_ms(), "cmd_id": cmd_id, "kind": kind,
                          "result": result, "detail": detail or {}})
        log(f"{self.code}: ack {kind} {cmd_id} -> {result}")

    def handle_command(self, b: dict) -> None:
        if getattr(self, "ignore_commands", False):  # kiểm thử TIMEOUT
            return
        cid, action = str(b.get("cmd_id") or ""), b.get("action") or ""
        if not cid or len(cid) >= 40:
            return
        for old_id, old_res in self.dedup:
            if old_id == cid:
                self.ack(cid, "command", old_res, {"duplicate": True})
                return
        detail: dict = {}
        issued, ttl = int(b.get("issued_at") or 0), int(b.get("ttl_s") or 0)
        params = b.get("params") or {}
        if not action:
            res = "invalid"
        elif issued and ttl and now_ms() > issued + ttl * 1000:
            res = "expired"
        elif action == "request_status":
            res = "executed"
            self.publish_status()
        elif action == "reboot":
            res = "executed"
        elif action == "pump_on":
            d = params.get("duration_s")
            if not isinstance(d, int) or d < 1:
                res, detail = "invalid", {"field": "duration_s"}
            else:
                blocked = self.pump_block("remote")
                if blocked:
                    res = blocked
                else:
                    cap = min(d, self.cfg["pump_max_s"])
                    self.pump_start(cap, "remote")
                    res, detail = ("duration_capped" if d > cap else "executed"), {"duration_s": cap}
        elif action == "pump_off":
            self.pump_stop("command", "remote")
            res = "executed"
        elif action in ("fan_on", "fan_off"):
            self.fan_set(action == "fan_on", "remote")
            if self.auto:
                self.fan_override_until = time.time() + 300
                detail = {"override_s": 300}
            res = "executed"
        elif action in ("lamp_on", "lamp_off"):
            on = action == "lamp_on"
            dmin = params.get("duration_min", self.cfg["lamp_override_min"])
            if on and (not isinstance(dmin, int) or isinstance(dmin, bool)
                       or not 1 <= dmin <= self.cfg["lamp_override_min"]):
                res, detail = "invalid", {"field": "duration_min"}
            elif on and self.overheat:
                res = "blocked_overheat"
            else:
                self.lamp_set(on, "remote", "command")
                if self.auto:
                    self.lamp_override_until = time.time() + dmin * 60
                    detail = {"override_min": dmin}
                res = "executed"
        elif action == "set_mode":
            m = params.get("mode")
            if m not in ("AUTO", "MANUAL"):
                res, detail = "invalid", {"field": "mode"}
            else:
                self.auto = m == "AUTO"
                if self.auto:  # như firmware: về AUTO thì bỏ lệnh tay quạt/đèn
                    self.fan_override_until = 0.0
                    self.lamp_override_until = 0.0
                if not self.auto and self.pump and self.pump_src == "auto":
                    self.pump_stop("mode_manual", "remote")
                res, detail = "executed", {"mode": m}
        else:
            res = "unsupported"
        self.dedup.append((cid, res))
        self.ack(cid, "command", res, detail)
        if action == "reboot" and res == "executed":
            threading.Thread(target=self.simulate_reboot, daemon=True).start()

    def handle_config(self, b: dict) -> None:
        ver = int(b.get("config_version") or 0)
        if ver == 0:
            return
        cid = f"cfg-{ver}"
        if ver < self.cfg_version:
            log(f"{self.code}: bỏ qua cấu hình cũ {ver} (đang dùng {self.cfg_version})")
            return
        if ver == self.cfg_version:
            self.ack(cid, "config", "executed")
            return
        new = json.loads(json.dumps(self.cfg))
        params = b.get("params") or {}
        for k, (lo, hi) in RANGES.items():
            if k in params:
                v = params[k]
                if not isinstance(v, (int, float)) or isinstance(v, bool) or not lo <= v <= hi:
                    self.ack(cid, "config", "invalid", {"field": k})
                    return
                new[k] = v
        for k in ("manual_ignores_cooldown",):
            if k in params:
                if not isinstance(params[k], bool):
                    self.ack(cid, "config", "invalid", {"field": k})
                    return
                new[k] = params[k]
        for k in ("soil_cal", "tank_cal"):
            if k in params:
                new[k] = params[k]
        if new["soil_low"] >= new["soil_high"]:
            self.ack(cid, "config", "invalid", {"field": "soil_low"})
            return
        if new["lamp_end_hour"] <= new["lamp_start_hour"]:
            self.ack(cid, "config", "invalid", {"field": "lamp_end_hour"})
            return
        if new["lamp_hyst"] <= new["lamp_self_lux"] + 200:
            self.ack(cid, "config", "invalid", {"field": "lamp_hyst"})
            return
        self.cfg, self.cfg_version = new, ver
        self.save()
        self.ack(cid, "config", "executed")
        self.publish_status()

    def simulate_reboot(self) -> None:
        time.sleep(0.5)
        log(f"{self.code}: khởi động lại (mô phỏng)")
        with self.lock:
            self.pump_stop("shutdown", "auto")
            self.fan_set(False, "auto")
            self.lamp_set(False, "auto", "shutdown")
            self.flush_events()
        self.client.disconnect()
        self.client.loop_stop()
        self.connected = False
        time.sleep(3)
        self.emit("boot", {"reset_reason": "software", "fw": "sim-1.0.0"})
        self.go_online()

    def save(self) -> None:
        persist_state(self.code, {"seq_t": self.seq_t, "seq_e": self.seq_e, "cfg": self.cfg,
                                  "cfg_version": self.cfg_version, "auto": self.auto})

    # ---------- vòng lặp ----------
    def loop(self, stop: threading.Event) -> None:
        last = time.time()
        next_tel = last + 3
        next_status = last + 30
        next_save = last + 30
        next_offline = last + self.a.offline_every if self.a.offline_every else None
        while not stop.is_set():
            now = time.time()
            with self.lock:
                self.physics(now - last)
                last = now
                self.control()
                if next_offline and now >= next_offline:
                    log(f"{self.code}: mô phỏng mất mạng {self.a.offline_for}s")
                    self.go_offline()
                    self.forced_offline_until = now + self.a.offline_for
                    next_offline = now + self.a.offline_every + self.a.offline_for
                if self.forced_offline_until and now >= self.forced_offline_until:
                    self.forced_offline_until = 0
                    self.go_online()
                if now >= next_tel:
                    next_tel = now + self.cfg["telemetry_interval_s"] if self.a.interval is None else now + self.a.interval
                    self.telemetry_tick()
                if now >= next_status:
                    next_status = now + 30
                    self.publish_status()
                if now >= next_save:
                    next_save = now + 30
                    self.save()
                self.flush_events()
                self.drain_buffer()
            stop.wait(0.2)  # ~5 bản tin bù / giây như firmware
        self.save()
        self.client.disconnect()
        self.client.loop_stop()


def cmd_run(a) -> None:
    devs = load_devices()
    codes = a.codes.split(",") if a.codes else list(devs)
    if not codes:
        sys.exit("Chưa có thiết bị mô phỏng. Chạy: sim.ps1 provision --count 1")
    sims = []
    for code in codes:
        if code not in devs:
            sys.exit(f"{code} không có trong runtime/sim/devices.json")
        sims.append(SimDevice(code, devs[code]["secret"], devs[code]["garden"], a))
    stop = threading.Event()
    threads = []
    for s in sims:
        s.start()
        t = threading.Thread(target=s.loop, args=(stop,), daemon=True)
        t.start()
        threads.append(t)
    log(f"Đang chạy {len(sims)} thiết bị: {', '.join(codes)}. Ctrl+C để dừng.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log("Dừng...")
        stop.set()
        for t in threads:
            t.join(3)


# ---------------------------------------------------------------------------
# Công cụ phía backend (để thử khi chưa có backend)
# ---------------------------------------------------------------------------

def backend_client(cid: str) -> mqtt.Client:
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cid, protocol=mqtt.MQTTv311)
    c.username_pw_set(ENV["MQTT_BACKEND_USER"], ENV["MQTT_BACKEND_PASSWORD"])
    return c


def cmd_watch(a) -> None:
    c = backend_client(f"sim-watch-{uuid.uuid4().hex[:6]}")
    topics = [a.topic] if a.topic else [f"nursery/+/+/{k}" for k in ("telemetry", "status", "event", "ack")]
    c.on_connect = lambda cl, *_: [cl.subscribe(t, 1) for t in topics]
    c.on_message = lambda _c, _u, m: log(f"{m.topic}{' (retain)' if m.retain else ''} {m.payload.decode(errors='replace')}")
    c.connect(broker_host(), int(ENV.get("MQTT_PORT", 1883)), 30)
    log(f"Đang xem {topics}. Ctrl+C để dừng.")
    try:
        c.loop_forever()
    except KeyboardInterrupt:
        pass


def _send_and_wait(code: str, garden: str, kind: str, payload: dict, ack_id: str, retain: bool) -> None:
    got = threading.Event()
    t0 = time.time()
    c = backend_client(f"sim-cmd-{uuid.uuid4().hex[:6]}")

    def on_connect(cl, *_a):
        cl.subscribe(f"nursery/{garden}/{code}/ack", 1)

    def on_subscribe(cl, *_a):
        cl.publish(f"nursery/{garden}/{code}/{kind}", json.dumps(payload), qos=1, retain=retain)
        log(f"Đã gửi {kind}: {json.dumps(payload)}")

    def on_message(_c, _u, m):
        b = json.loads(m.payload)
        if b.get("cmd_id") == ack_id:
            log(f"ACK sau {int((time.time() - t0) * 1000)} ms: {json.dumps(b)}")
            got.set()

    c.on_connect, c.on_subscribe, c.on_message = on_connect, on_subscribe, on_message
    c.connect(broker_host(), int(ENV.get("MQTT_PORT", 1883)), 30)
    c.loop_start()
    if not got.wait(10):
        log("Không có ack sau 10 s → lệnh sẽ là TIMEOUT")
    c.loop_stop()
    c.disconnect()


def cmd_cmd(a) -> None:
    cid = str(uuid.uuid4())
    params = json.loads(a.params)
    if a.duration is not None:
        params["duration_s"] = a.duration
    if a.mode:
        params["mode"] = a.mode
    payload = {"cmd_id": cid, "action": a.action, "params": params, "issued_at": now_ms(),
               "ttl_s": a.ttl, "issued_by": "sim-cli"}
    _send_and_wait(a.code, a.garden, "command", payload, cid, False)


def cmd_config(a) -> None:
    ver = a.version or int(time.time())  # đủ lớn để không bị bỏ qua (đặc tả §9.3)
    params = json.loads(a.params)
    for kv in a.set or []:
        k, _, v = kv.partition("=")
        if v.lower() in ("true", "false"):
            params[k] = v.lower() == "true"
        else:
            try:
                params[k] = int(v)
            except ValueError:
                params[k] = float(v)
    payload = {"config_version": ver, "issued_at": now_ms(), "params": params}
    _send_and_wait(a.code, a.garden, "config", payload, f"cfg-{ver}", True)


def main() -> None:
    global ENV, _log_file
    ENV = load_env()
    ap = argparse.ArgumentParser(description="Thiết bị mô phỏng vườn ươm (WP-01)")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("provision"); p.add_argument("--count", type=int, default=1)
    p.add_argument("--start", type=int, default=9001); p.add_argument("--garden", default="g01")
    sp.add_parser("deprovision")
    p = sp.add_parser("register"); p.add_argument("--count", type=int, default=1); p.add_argument("--zone", type=int, default=1)
    p = sp.add_parser("run"); p.add_argument("--codes", default="")
    p.add_argument("--interval", type=float, default=None, help="ghi đè telemetry_interval_s")
    p.add_argument("--duplicate-rate", type=float, default=0.0); p.add_argument("--drop-rate", type=float, default=0.0)
    p.add_argument("--offline-every", type=float, default=0); p.add_argument("--offline-for", type=float, default=30)
    p.add_argument("--soil", type=float, default=45); p.add_argument("--tank", type=float, default=80)
    p = sp.add_parser("watch"); p.add_argument("--topic", default="")
    p = sp.add_parser("cmd"); p.add_argument("code"); p.add_argument("action")
    p.add_argument("--params", default="{}"); p.add_argument("--ttl", type=int, default=10); p.add_argument("--garden", default="g01")
    p.add_argument("--duration", type=int, default=None); p.add_argument("--mode", default="")
    p = sp.add_parser("config"); p.add_argument("code"); p.add_argument("--params", default="{}")
    p.add_argument("--set", action="append", help="khóa=giá trị, lặp lại được")
    p.add_argument("--version", type=int, default=0); p.add_argument("--garden", default="g01")
    a = ap.parse_args()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _log_file = open(LOG_DIR / f"simulator-{time.strftime('%Y%m%d')}.log", "a", encoding="utf-8")
    {"provision": cmd_provision, "register": cmd_register, "deprovision": cmd_deprovision, "run": cmd_run, "watch": cmd_watch,
     "cmd": cmd_cmd, "config": cmd_config}[a.cmd](a)


if __name__ == "__main__":
    main()
