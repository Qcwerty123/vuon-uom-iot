# WP-N1 — Nối Node 1, Node 2 thật vào hệ thống (07/11)

Thay cho checklist ở WP-00 §7: từ 06/11 đã có backend, nên **cấp phát qua backend** (không dùng `dev-device.ps1` cho ctl-0001/cam-0001).

## Chuẩn bị trên máy chủ

1. Bật Mobile Hotspot 2,4 GHz. Ghi tên WiFi + mật khẩu.
2. `.\scripts\windows\start.ps1` → `.\scripts\windows\status.ps1`: PostgreSQL, Mosquitto, Backend, Hotspot, Firewall đều OK.
3. Mở `http://127.0.0.1:8000/docs`:
   - `POST /api/v1/auth/login` với `admin` (mật khẩu `SEED_ADMIN_PASSWORD` trong `.env`) → chép `accessToken`.
   - Bấm **Authorize**, dán token.
   - `GET /api/v1/devices` → `ctl-0001` (id 1), `cam-0001` (id 2) đang `REGISTERED`.
   - `POST /api/v1/devices/1/provision` → chép `secret` (chỉ hiện một lần). Làm tương tự với id 2 khi nối Node 2.

## Node 1

1. Người giữ node đã qua `firmware/test-hardware` (hướng dẫn lắp §F2). Hiệu chuẩn DRY/WET đất, `TANK_EMPTY_CM/FULL_CM` (ghi `hardware/nhat-ky-lap-dat.md`).
2. Arduino IDE 2 mở `firmware/node1-controller`, tạo tab `secrets.h` từ `secrets.example.h`:
   `WIFI_SSID`/`WIFI_PASS` = hotspot, `MQTT_HOST "192.168.137.1"`, `DEVICE_CODE "ctl-0001"`, `DEVICE_SECRET` = secret vừa cấp, `LOCAL_PIN`.
3. Nạp (NodeMCU-32S, Partition Default). Serial 115200: thấy `WiFi OK` → `MQTT OK`. **Không** chọn "Erase All Flash".
4. Kiểm tra trên máy chủ:
   - `GET /api/v1/devices/1` → `ACTIVE`, `online: true`, `fwVersion` 1.0.0.
   - `GET /api/v1/devices/1/telemetry/latest` → số đo thật; nhúng que đất vào nước, gọi lại thấy đổi.
   - Xem trực tiếp: `.\scripts\windows\sim.ps1 watch` (in mọi bản tin).
5. Bơm thử (chưa có API lệnh — WP-03): `.\scripts\windows\sim.ps1 cmd ctl-0001 pump_on --duration 5` → ack `executed`, bơm chạy 5 giây.
6. Gửi hiệu chuẩn: `.\scripts\windows\sim.ps1 config ctl-0001 --set tank_min=15` (thêm `soil_cal`, `tank_cal` theo số đo thật khi có API cấu hình).
7. Rút nguồn Node 1 → khoảng 45 giây sau `GET /devices/1` thấy `OFFLINE`, `online: false`. Cắm lại → `ACTIVE`.
8. Lưu log Serial vào `logs/firmware/node1-<ngày>.txt`, chụp ảnh/quay video bơm chạy.

## Node 2

Chưa có firmware chính (WP-05). Hôm nay: nạp ví dụ `CameraWebServer`, nguồn 5V/2A riêng, kiểm tra ảnh SVGA rõ, không brownout (hướng dẫn lắp §D2, §D3). Cấp phát `cam-0001` để dành khi có firmware.

## Gặp lỗi

| Hiện tượng | Kiểm tra |
|---|---|
| Serial `MQTT that bai, state=5` | Secret sai hoặc thiết bị đang bị khóa; cấp lại khóa `POST /devices/1/rotate-secret` |
| `state=-2` / không có WiFi | ESP32 chỉ bắt 2,4 GHz; tên/mật khẩu hotspot; máy chủ có `192.168.137.1` |
| Backend vẫn `PROVISIONED` dù Serial `MQTT OK` | Xem `logs/services/backend.log` (bản tin bị loại?) |
