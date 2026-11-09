# Phiên bản core và thư viện

Người cài đầu tiên điền số phiên bản thật (xem trong Boards Manager / Library Manager). Các thành viên khác cài **đúng** các phiên bản này. Đổi phiên bản thì cả nhóm đổi cùng lúc và cập nhật file này.

| Thành phần | Tác giả | Phiên bản | Dùng cho |
|---|---|---|---|
| Arduino IDE | Arduino | 2.3.10 | |
| Core esp32 | Espressif Systems | 3.3.12 | Node 1, Node 2 |
| PubSubClient | Nick O'Leary | 2.8.0 | MQTT |
| ArduinoJson | Benoit Blanchon | 7.4.3 | JSON |
| DHT sensor library | Adafruit | 1.4.7 | DHT22 |
| Adafruit Unified Sensor | Adafruit | 1.1.5 | phụ thuộc của DHT |
| BH1750 | Christopher Laws | 1.3.0 | ánh sáng |
| Keypad | Mark Stanley, Alexander Brevig | 3.1.1 | keypad 3×4 |
| U8g2 | oliver | 2.39.19 | OLED SH1106 (`U8G2_SH1106_128X64_NONAME_F_HW_I2C`) |

Có sẵn trong core, không cần cài: `WiFi`, `Wire`, `HTTPClient`, `Preferences`, `esp_camera.h`.
