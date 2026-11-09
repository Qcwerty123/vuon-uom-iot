# Phần cứng

| File | Nội dung |
|---|---|
| `bom.md` | Danh sách linh kiện, vai trò, chi phí |
| `nhat-ky-lap-dat.md` | Số liệu đo và hiệu chuẩn ghi trong lúc lắp |
| `photos/` | Ảnh từng công đoạn, ảnh prototype hoàn chỉnh, video bơm chạy |
| `wiring.md` | Sơ đồ nối dây chi tiết, phân nhánh nguồn, cầu chia áp, bảo vệ tải |
| `wiring.png` (cần thêm) | Ảnh sơ đồ nối dây xuất từ Mermaid / Fritzing / Wokwi |

Hướng dẫn lắp đặt đầy đủ: [`docs/huong-dan-lap-dat-phan-cung.md`](../docs/huong-dan-lap-dat-phan-cung.md).
Bảng gán chân: [`docs/dac-ta-he-thong.md`](../docs/dac-ta-he-thong.md) §5.2.

## Gán chân Node 1 (tóm tắt)

| Linh kiện | Chân ESP32 |
|---|---|
| Đất 1 / Đất 2 (AO) | GPIO34 / GPIO35 |
| Nguồn cảm biến đất (VCC cả 2, chỉ bật khi đo) | GPIO32 |
| DHT22 | GPIO4 |
| I2C SDA / SCL (BH1750 + OLED) | GPIO21 / GPIO22 |
| HC-SR04 TRIG / ECHO (qua chia áp 1k/2k) | GPIO5 / GPIO18 |
| Relay IN1 bơm / IN2 quạt (1 quạt duy nhất) / IN3 đèn LED | GPIO26 / GPIO27 / GPIO25 |
| Chân đo của sketch chẩn đoán (lệnh `a`) | VP / GPIO36 |
| Keypad hàng R1–R4 | GPIO13, 14, 16, 17 |
| Keypad cột C1–C3 | GPIO19, 23, 33 |

Node 2 (ESP32-CAM AI-Thinker): flash GPIO4. Không gắn DHT11 (C4).
