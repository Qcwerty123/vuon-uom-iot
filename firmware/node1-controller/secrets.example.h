// Sao chép thành tab "secrets.h" rồi điền giá trị thật. KHÔNG commit secrets.h.
// DEVICE_CODE và DEVICE_SECRET lấy từ hộp thoại "Cấp phát thiết bị" trên web (chỉ hiện một lần).
// Các giá trị này là MẶC ĐỊNH: có thể ghi đè lúc chạy bằng lệnh Serial (set ... / save), xem firmware/README.md.
#pragma once

#define WIFI_SSID      "ten-wifi-2.4GHz"
#define WIFI_PASS      "mat-khau-wifi"
#define MQTT_HOST      "192.168.137.1"  // = MQTT_PUBLIC_HOST trong .env (Mobile Hotspot của máy chủ, C17)
#define MQTT_PORT      1883
#define GARDEN_CODE    "g01"
#define DEVICE_CODE    "ctl-0001"
#define DEVICE_SECRET  "dan-secret-nhan-khi-cap-phat"
#define LOCAL_PIN      "0000"            // PIN keypad, đổi khi triển khai
#define NTP_SERVER     "pool.ntp.org"   // qua Internet chia sẻ vào hotspot (C11)
