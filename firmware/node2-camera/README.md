# Node 2 — Firmware camera (chưa viết)

Đặc tả: `docs/dac-ta-he-thong.md` §7 (firmware camera), §8.9 (HTTP upload ảnh).

## Điều kiện bắt đầu

- Ví dụ CameraWebServer chạy ổn với nguồn 5V/2A, không brownout (hướng dẫn lắp đặt §D2, §D3).
- Backend đã có endpoint `POST /device-api/v1/images` (hoặc dùng một server thử để nhận ảnh).

## Việc cần làm

1. Khởi tạo camera (AI Thinker), SVGA, chất lượng JPEG 12, PSRAM.
2. WiFi + NTP + MQTT: LWT, heartbeat 30 giây, subscribe `command` và `config`.
3. Chụp theo `capture_interval_min` và theo lệnh `capture`; bật flash GPIO4 khi cần.
4. Upload HTTP POST với Basic auth `device_code:secret`, header `X-Captured-At`, `X-Trigger`, `X-Cmd-Id`; thử lại 3 lần.
5. `ack` lệnh `capture` kèm `image_id`; `event: upload_failed` khi thất bại.
6. Không gắn DHT11 (C4), Node 2 không gửi telemetry.

## Cấu hình Tools

Board **AI Thinker ESP32-CAM**, Partition **Huge APP**, PSRAM bật. Nạp: giữ **IO0**, bấm **RST**, thả IO0.
