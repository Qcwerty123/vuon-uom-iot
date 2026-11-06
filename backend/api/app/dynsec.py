"""Điều khiển Mosquitto Dynamic Security qua topic $CONTROL (đặc tả §8.8).

Lưu ý Windows (đặc tả §17.5): Mosquitto 2.0.18 không đổi tên đè được dynamic-security.json,
nên sau MỖI lệnh phải chép bản .new về đúng tên, nếu không thay đổi mất khi khởi động lại broker.
"""
from __future__ import annotations

import json
import logging
import shutil
import threading
import time
import uuid

import paho.mqtt.client as mqtt

from .config import settings

log = logging.getLogger("dynsec")
REQ = "$CONTROL/dynamic-security/v1"
RESP = REQ + "/response"


class DynsecError(Exception):
    pass


_lock = threading.Lock()


def sync_file() -> None:
    f = settings.dynsec_file
    new = f.with_name(f.name + ".new")
    try:
        if new.exists():
            if not f.exists() or new.stat().st_mtime >= f.stat().st_mtime:
                shutil.copyfile(new, f)
            new.unlink(missing_ok=True)
    except OSError as e:
        log.error("Không đồng bộ được %s: %s", new, e)


def run(commands: list[dict], timeout: float = 8.0) -> list[dict]:
    """Gửi một lô lệnh, chờ phản hồi. Ném DynsecError nếu broker không trả lời."""
    with _lock:
        done = threading.Event()
        out: list[dict] = []
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"backend-dynsec-{uuid.uuid4().hex[:6]}",
                        protocol=mqtt.MQTTv311)
        c.username_pw_set(settings.mqtt_dynsec_user, settings.mqtt_dynsec_password)

        def on_connect(cl, _u, _f, rc, _p=None):
            if getattr(rc, "is_failure", rc != 0):
                log.error("dynsec-admin không đăng nhập được: %s", rc)
                done.set()
                return
            cl.subscribe(RESP, qos=1)

        def on_subscribe(cl, *_a):
            cl.publish(REQ, json.dumps({"commands": commands}), qos=1)

        def on_message(_c, _u, msg):
            out.extend(json.loads(msg.payload).get("responses", []))
            done.set()

        c.on_connect, c.on_subscribe, c.on_message = on_connect, on_subscribe, on_message
        try:
            c.connect(settings.mqtt_host, settings.mqtt_port, 30)
        except OSError as e:
            raise DynsecError(f"Không kết nối được broker: {e}") from e
        c.loop_start()
        ok = done.wait(timeout)
        c.loop_stop()
        c.disconnect()
        time.sleep(0.3)
        sync_file()
        if not ok or not out:
            raise DynsecError("Broker không phản hồi lệnh dynsec")
        return out


def _errors(res: list[dict], ignore: tuple[str, ...] = ()) -> list[str]:
    errs = []
    for r in res:
        e = r.get("error")
        if e and not any(i.lower() in e.lower() for i in ignore):
            errs.append(f"{r.get('command')}: {e}")
    return errs


def create_device(code: str, garden: str, secret: str) -> None:
    # Xóa tài khoản cũ cùng tên nếu có (ví dụ tạo tay bằng dev-device.ps1 trước khi có backend)
    run([{"command": "deleteClient", "username": code}, {"command": "deleteRole", "rolename": code}])
    base = f"nursery/{garden}/{code}"
    cmds = [{"command": "createClient", "username": code, "password": secret},
            {"command": "createRole", "rolename": code}]
    for k in ("telemetry", "status", "event", "ack"):
        cmds.append({"command": "addRoleACL", "rolename": code, "acltype": "publishClientSend",
                     "topic": f"{base}/{k}", "allow": True})
    for k in ("command", "config"):
        for t in ("subscribeLiteral", "publishClientReceive"):
            cmds.append({"command": "addRoleACL", "rolename": code, "acltype": t, "topic": f"{base}/{k}", "allow": True})
    cmds.append({"command": "addClientRole", "username": code, "rolename": code})
    errs = _errors(run(cmds))
    if errs:
        raise DynsecError("; ".join(errs))


def set_password(code: str, secret: str) -> None:
    errs = _errors(run([{"command": "setClientPassword", "username": code, "password": secret},
                        {"command": "disableClient", "username": code},
                        {"command": "enableClient", "username": code}]))
    if errs:
        raise DynsecError("; ".join(errs))


def disable(code: str) -> None:
    errs = _errors(run([{"command": "disableClient", "username": code}]))
    if errs:
        raise DynsecError("; ".join(errs))


def enable(code: str) -> None:
    errs = _errors(run([{"command": "enableClient", "username": code}]))
    if errs:
        raise DynsecError("; ".join(errs))


def delete(code: str) -> None:
    errs = _errors(run([{"command": "deleteClient", "username": code}, {"command": "deleteRole", "rolename": code}]),
                   ignore=("not found",))
    if errs:
        raise DynsecError("; ".join(errs))
