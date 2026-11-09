"""Gửi cảnh báo qua Telegram (đặc tả §13.3). Bỏ qua yên lặng nếu chưa có TELEGRAM_BOT_TOKEN.

Người dùng lấy chat id: nhắn /start cho bot → bot trả lời chat id → dán vào Hồ sơ trên web.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.parse
import urllib.request

from .config import settings

log = logging.getLogger("telegram")
API = "https://api.telegram.org/bot{token}/{method}"


def enabled() -> bool:
    t = settings.telegram_token
    return bool(t) and t != "change-me" and ":" in t


def _call(method: str, params: dict, timeout: float = 10) -> dict:
    url = API.format(token=settings.telegram_token, method=method)
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=timeout) as r:
        return json.loads(r.read())


def send(chat_id: str, text: str) -> bool:
    """Thử 3 lần. Trả về True nếu gửi được."""
    if not enabled():
        return False
    for attempt in range(3):
        try:
            if _call("sendMessage", {"chat_id": chat_id, "text": text}).get("ok"):
                return True
        except Exception as e:  # noqa: BLE001
            log.warning("Gửi Telegram lỗi (lần %d): %s", attempt + 1, e)
        time.sleep(2 * (attempt + 1))
    return False


def _poll() -> None:
    offset = 0
    while True:
        try:
            res = _call("getUpdates", {"timeout": 25, "offset": offset}, timeout=35)
            for u in res.get("result", []):
                offset = u["update_id"] + 1
                msg = u.get("message") or {}
                chat = msg.get("chat", {}).get("id")
                if chat and str(msg.get("text", "")).startswith("/start"):
                    send(str(chat), f"Xin chào! Chat ID của bạn là: {chat}\n"
                                    "Dán số này vào mục Hồ sơ trên web vườn ươm để nhận cảnh báo.")
        except Exception as e:  # noqa: BLE001
            log.warning("Lỗi nhận tin Telegram: %s", e)
            time.sleep(10)


def start_bot() -> None:
    if enabled():
        threading.Thread(target=_poll, name="telegram-bot", daemon=True).start()
        log.info("Bot Telegram đang chạy")
    else:
        log.info("Chưa có TELEGRAM_BOT_TOKEN — tắt gửi Telegram")
