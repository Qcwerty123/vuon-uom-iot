# Firmware

Công cụ: **Arduino IDE 2** + core **esp32 by Espressif Systems** 3.x. Cách cài và cấu hình menu Tools ở `docs/huong-dan-lap-dat-phan-cung.md` §A6.

| Thư mục | Board | Trạng thái | Nội dung |
|---|---|---|---|
| `test-hardware/` | NodeMCU-32S | ✅ | Sketch chẩn đoán: test từng linh kiện qua Serial Monitor (lệnh `h` để xem menu) |
| `node1-controller/` | NodeMCU-32S | ✅ v1.1.0 (chưa thử trên mạch) | Firmware chính Node 1 (đặc tả §6, §6.11) |
| `node2-camera/` | AI Thinker ESP32-CAM | ✅ v1.0.0 (chưa thử trên mạch) | Firmware chính Node 2 (đặc tả §7) |

## Quy ước

- Tên thư mục **trùng** tên file `.ino` (yêu cầu của Arduino IDE).
- Mỗi sketch có `secrets.example.h` (commit) và `secrets.h` (**không** commit). Tạo `secrets.h` bằng nút **…** → **New Tab** trong IDE.
- Cả nhóm cài đúng phiên bản trong [`LIBRARIES.md`](LIBRARIES.md).
- Khai báo phiên bản firmware ở đầu `.ino`: `#define FW_VERSION "1.0.0"`. Tăng số mỗi lần nạp bản mới lên thiết bị dùng cho demo.
- Firmware nạp bằng cáp. Cập nhật từ xa (OTA) tạm chưa làm (đặc tả C14).

## Cấu hình Tools (tóm tắt)

| | Node 1 | Node 2 |
|---|---|---|
| Board | NodeMCU-32S | AI Thinker ESP32-CAM |
| Upload Speed | 921600 | 460800 |
| Partition Scheme | Default | Huge APP (3MB No OTA/1MB SPIFFS) |
| Serial Monitor | 115200, New Line | 115200 |

## Thử Node 2 trước khi có firmware chính

Dùng ví dụ có sẵn: `File → Examples → ESP32 → Camera → CameraWebServer`, chọn `CAMERA_MODEL_AI_THINKER`, điền WiFi. Xem hướng dẫn lắp đặt §D2.
