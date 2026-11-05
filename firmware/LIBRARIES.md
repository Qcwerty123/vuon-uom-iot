# Phiên bản core và thư viện

Người cài đầu tiên điền số phiên bản thật (xem trong Boards Manager / Library Manager). Các thành viên khác cài **đúng** các phiên bản này. Đổi phiên bản thì cả nhóm đổi cùng lúc và cập nhật file này.

| Thành phần | Tác giả | Phiên bản | Dùng cho |
|---|---|---|---|
| Arduino IDE | Arduino | 2.__.__ | |
| Core esp32 | Espressif Systems | 3.__.__ | Node 1, Node 2 |
| PubSubClient | Nick O'Leary | __.__.__ | MQTT |
| ArduinoJson | Benoit Blanchon | 7.__.__ | JSON |
| DHT sensor library | Adafruit | __.__.__ | DHT22 |
| Adafruit Unified Sensor | Adafruit | __.__.__ | phụ thuộc của DHT |
| BH1750 | Christopher Laws | __.__.__ | ánh sáng |
| Keypad | Mark Stanley, Alexander Brevig | __.__.__ | keypad 3×4 |
| U8g2 | oliver | __.__.__ | OLED SH1106 (`U8G2_SH1106_128X64_NONAME_F_HW_I2C`) |

Có sẵn trong core, không cần cài: `WiFi`, `Wire`, `HTTPClient`, `Preferences`, `esp_camera.h`.
