// Sao chép thành tab "secrets.h" rồi điền giá trị thật. KHÔNG commit secrets.h.
// DEVICE_CODE và DEVICE_SECRET lấy từ hộp thoại "Cấp phát thiết bị" trên web (chỉ hiện một lần).
#pragma once

#define WIFI_SSID      "ten-wifi-2.4GHz"
#define WIFI_PASS      "mat-khau-wifi"
#define MQTT_HOST      "192.168.1.10"   // = MQTT_PUBLIC_HOST trong .env
#define MQTT_PORT      1883
#define GARDEN_CODE    "g01"
#define DEVICE_CODE    "cam-0001"
#define DEVICE_SECRET  "dan-secret-nhan-khi-cap-phat"
#define UPLOAD_URL     "http://192.168.1.10/device-api/v1/images"   // cổng 80, Nginx proxy (C15)
#define NTP_SERVER     "192.168.1.10"   // máy server chạy chrony (C11)
