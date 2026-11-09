# Node 2 — Firmware camera (ESP32-CAM)

Đặc tả: `docs/dac-ta-he-thong.md` §7 (firmware camera), §8 (MQTT), §8.9 (upload ảnh). Phiên bản `FW_VERSION` ở `app.h`.

## Nạp lần đầu

1. CameraWebServer đã chạy ổn với nguồn 5V/2A, không brownout (hướng dẫn lắp đặt §D2, §D3).
2. Mở `node2-camera.ino` trong Arduino IDE 2. Mọi file trong thư mục hiện thành tab.
3. Tạo tab `secrets.h` từ `secrets.example.h`: WiFi, IP server, `DEVICE_CODE` = `cam-0001`, `DEVICE_SECRET`, `UPLOAD_URL`.
4. Tools: Board **AI Thinker ESP32-CAM**, Partition **Huge APP (3MB No OTA/1MB SPIFFS)**, **PSRAM: Enabled**.
5. Nạp qua đế ESP32-CAM-MB. Serial Monitor 115200, **New Line**.

Thư viện cài thêm: PubSubClient, ArduinoJson 7. `esp_camera.h`, `HTTPClient` có sẵn trong core.

## Các tab

| File | Việc |
|---|---|
| `node2-camera.ino` | `setup()`, `loop()`, lệnh Serial, LED đỏ báo trạng thái |
| `app.h` | `FW_VERSION`, chân flash GPIO4, LED đỏ GPIO33, múi giờ cho flash `auto` |
| `config_store.*` | Cấu hình camera (mặc định + nhận qua MQTT), `seq` event không lặp, lưu NVS |
| `camera.*` | Khởi tạo OV2640 (buffer theo UXGA trong PSRAM rồi hạ theo cấu hình), chụp, bỏ khung khởi động, flash, tự khởi tạo lại khi lỗi |
| `capture.*` | Lịch chụp, chụp theo lệnh, upload HTTP: Basic auth, header `X-Captured-At`/`X-Trigger`/`X-Cmd-Id`, thử lại 3 lần cách 5 s, giữ khoảng cách 20 s giữa 2 ảnh |
| `net.*` | WiFi, NTP, MQTT — **giống hệt Node 1**, sửa một nơi thì chép sang nơi kia |
| `protocol.*` | status / event / ack; xử lý `command`, `config`; chống trùng `cmd_id`; ack `capture` sau khi upload xong |

## Lệnh MQTT (`…/command`)

| `action` | `params` | Ack |
|---|---|---|
| `capture` | `{flash?: "on"/"off"}` | Sau khi upload xong: `executed {image_id, diagnosis_id, bytes, attempts}` hoặc `failed {reason, http}`. Đang bận: `failed {reason:"busy"}` ngay |
| `flash` | `{state: "on"/"off", duration_s: 1–10}` (mặc định 3 s) | `executed` |
| `reboot` | — | `executed` rồi khởi động lại (đang upload thì `failed busy`) |
| `request_status` | — | `executed` + gửi `status` |

`reason` khi upload thất bại: `network`, `unauthorized` (401), `forbidden` (403 — thiết bị bị khóa/thu hồi), `too_large`, `rate_limited`, `bad_image`, `http_error`, `camera`.

## Cấu hình (`…/config`, retain)

```json
{"config_version": 1, "params": {"frame_size": "SVGA", "jpeg_quality": 12, "flash": "auto",
  "capture_interval_min": 30, "warmup_frames": 2}}
```

`frame_size`: VGA, SVGA, XGA, HD, SXGA, UXGA. `jpeg_quality` 8–30 (nhỏ = nét hơn). `flash`: on / off / auto (bật 19h–6h giờ Việt Nam). Khi demo đặt `capture_interval_min` = 1.

## Lệnh Serial

`p` chụp + gửi thử · `f` nháy flash 1 s · `c` cấu hình · `n` mạng · `factory` xóa cấu hình · `h` trợ giúp.

## LED đỏ (GPIO33)

Sáng = chưa kết nối được broker. Tắt = đã kết nối.

## Lưu ý cho backend

- Lệnh `capture` được ack **sau khi upload xong**: chờ khoảng cách 20 s + tối đa 3 lần thử, nên có thể mất 20–40 s. `CommandTimeout` (đặc tả §9.1) với `capture` nên đặt khoảng **60 s** thay vì 10 s, nếu không lệnh sẽ bị đánh TIMEOUT rồi mới nhận ack muộn.
- Node 2 không gửi telemetry (C4). Sức khỏe thiết bị nằm trong `status`: `camera_ok`, `images_ok`, `images_failed`, `next_capture_s`, `psram`.
