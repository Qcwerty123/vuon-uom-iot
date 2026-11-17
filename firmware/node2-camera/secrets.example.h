// Sao chép thành tab "secrets.h" rồi điền giá trị thật. KHÔNG commit secrets.h.
// DEVICE_CODE và DEVICE_SECRET lấy từ hộp thoại "Cấp phát thiết bị" trên web (chỉ hiện một lần).
// Các giá trị này là MẶC ĐỊNH: có thể ghi đè lúc chạy bằng lệnh Serial (set ... / save), xem firmware/README.md.
#pragma once

// WiFi để TRỐNG = không cố định trong code: thiết bị tự phát WiFi "VuonUom-<code>" để nhập mạng bằng điện thoại
// (portal, xem portal.h). Điền vào đây chỉ khi muốn có mạng mặc định.
#define WIFI_SSID      ""
#define WIFI_PASS      ""
// #define PORTAL_AP_PASS "vuonuom1"       // mật khẩu WiFi do thiết bị phát khi cài đặt (>= 8 ký tự)
#define MQTT_HOST      "192.168.137.1"  // = MQTT_PUBLIC_HOST trong .env (Mobile Hotspot của máy chủ, C17)
#define MQTT_PORT      1883
#define GARDEN_CODE    "g01"
#define DEVICE_CODE    "cam-0001"
#define DEVICE_SECRET  "dan-secret-nhan-khi-cap-phat"
#define UPLOAD_URL     "http://192.168.137.1:8000/device-api/v1/images"   // backend phục vụ thẳng (C15)
#define NTP_SERVER     "pool.ntp.org"   // qua Internet chia sẻ vào hotspot (C11)
