# Firmware

Công cụ: **Arduino IDE 2** + core **esp32 by Espressif Systems** 3.x. Cách cài và cấu hình menu Tools ở `docs/huong-dan-lap-dat-phan-cung.md` §A6.

| Thư mục | Board | Trạng thái | Nội dung |
|---|---|---|---|
| `test-hardware/` | NodeMCU-32S | ✅ | Sketch chẩn đoán: test từng linh kiện qua Serial Monitor (lệnh `h` để xem menu) |
| `node1-controller/` | NodeMCU-32S | ✅ v1.2.0 (chưa thử trên mạch) | Firmware chính Node 1 (đặc tả §6, §6.11) |
| `node2-camera/` | AI Thinker ESP32-CAM | ✅ v1.1.0 (chưa thử trên mạch) | Firmware chính Node 2 (đặc tả §7) |

## Quy ước

- Tên thư mục **trùng** tên file `.ino` (yêu cầu của Arduino IDE).
- Mỗi sketch có `secrets.example.h` (commit) và `secrets.h` (**không** commit). Tạo `secrets.h` bằng nút **…** → **New Tab** trong IDE.
- Cả nhóm cài đúng phiên bản trong [`LIBRARIES.md`](LIBRARIES.md).
- Khai báo phiên bản firmware ở đầu `.ino`: `#define FW_VERSION "1.0.0"`. Tăng số mỗi lần nạp bản mới lên thiết bị dùng cho demo.
- Firmware nạp bằng cáp. Cập nhật từ xa (OTA) tạm chưa làm (đặc tả C14).

## Danh tính thiết bị qua Serial (NVS)

Mặc định firmware dùng WiFi/MQTT/`DEVICE_CODE`/`DEVICE_SECRET` trong `secrets.h` như trước. Từ Node 1 v1.2.0 / Node 2 v1.1.0 có thể **ghi đè bằng lệnh Serial** (lưu NVS, giữ qua reset và qua lần nạp sketch sau) để đổi thiết bị mà không phải sửa `secrets.h` rồi nạp lại.

| Lệnh | Tác dụng |
|---|---|
| `id` | In danh tính đang dùng, mỗi trường kèm nguồn `[nvs]` hoặc `[secrets.h]` (secret và mật khẩu WiFi bị che) |
| `set code ctl-0002` | Đặt `device_code` (chữ, số, `-`, `_`) |
| `set secret <chuỗi>` | Đặt secret (không có dấu cách) |
| `set garden g01` · `set host 192.168.137.1` · `set port 1883` | Garden, địa chỉ và cổng MQTT |
| `set ssid <tên>` · `set pass <mật khẩu>` | WiFi (tên có dấu cách được) |
| `set upload <url>` | URL upload ảnh (chỉ Node 2) |
| `save` | Ghi các thay đổi vào NVS rồi khởi động lại (chỉ lúc này mới có hiệu lực) |
| `clear` | Xóa NVS danh tính → quay về giá trị `secrets.h`, khởi động lại |

Lệnh `set` chỉ sửa bản nháp trong RAM; chưa `save` thì thiết bị vẫn chạy bằng danh tính cũ. Dòng lệnh tối đa 158 ký tự. `factory` chỉ xóa cấu hình vận hành, **không** đụng danh tính.

## Cấu hình Tools (tóm tắt)

| | Node 1 | Node 2 |
|---|---|---|
| Board | NodeMCU-32S | AI Thinker ESP32-CAM |
| Upload Speed | 921600 | 460800 |
| Partition Scheme | Default | Huge APP (3MB No OTA/1MB SPIFFS) |
| Serial Monitor | 115200, New Line | 115200 |

## Thử Node 2 trước khi có firmware chính

Dùng ví dụ có sẵn: `File → Examples → ESP32 → Camera → CameraWebServer`, chọn `CAMERA_MODEL_AI_THINKER`, điền WiFi. Xem hướng dẫn lắp đặt §D2.
