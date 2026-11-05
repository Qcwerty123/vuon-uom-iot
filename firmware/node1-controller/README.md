# Node 1 — Firmware điều khiển

Đặc tả: `docs/dac-ta-he-thong.md` §6 (firmware), §8 (MQTT). Phiên bản `FW_VERSION` ở `app.h`.

## Nạp lần đầu

1. Đã qua nghiệm thu phần cứng (hướng dẫn lắp đặt §F2) bằng `../test-hardware`.
2. Mở `node1-controller.ino` trong Arduino IDE 2. Mọi file trong thư mục hiện thành tab.
3. Tạo tab `secrets.h` từ `secrets.example.h`, điền WiFi, IP server, `DEVICE_SECRET`, PIN.
4. Nếu jumper relay đặt ở L: sửa `RELAY_ACTIVE_HIGH 0` trong `app.h`.
5. Board **NodeMCU-32S**, Partition **Default**, Upload. Serial Monitor 115200, **New Line**.

Số hiệu chuẩn (DRY/WET cảm biến đất, `TANK_EMPTY_CM`/`TANK_FULL_CM`) **không** sửa trong code: gửi qua cấu hình (`config`, đặc tả §8.7), thiết bị lưu NVS.

## Các tab

| File | Việc |
|---|---|
| `node1-controller.ino` | `setup()`, `loop()` không chặn, lệnh Serial, log 10 s |
| `app.h` | `FW_VERSION`, gán chân, kiểu dữ liệu chung |
| `config_store.*` | Cấu hình mặc định + nhận qua MQTT (kiểm tra miền giá trị), `seq` không lặp sau reboot, lưu NVS |
| `sensors.*` | Đọc + trung vị 5 mẫu; cảm biến đất bật GPIO32 → 100 ms → đọc → tắt; phát hiện cảm biến lỗi; hợp nhất 2 cảm biến đất (§6.4) |
| `control.*` | Tưới, quạt có trễ, AUTO/MANUAL/LOCAL, khóa an toàn (§6.5, §6.6); timer phần cứng cắt bơm đúng hạn |
| `net.*` | WiFi + MQTT kết nối lại có backoff 1→30 s, NTP (server trước, `pool.ntp.org` sau), LWT |
| `protocol.*` | telemetry / status / event / ack; xử lý `command`, `config`; chống trùng `cmd_id`; hạn lệnh `ttl_s` |
| `buffer.*` | Hàng đợi 200 bản ghi khi mất mạng, gửi bù 5 bản tin/giây kèm `buffered:true` |
| `ui.*` | OLED SH1106 3 trang + keypad có PIN |

## Lệnh Serial

| Lệnh | Việc |
|---|---|
| `s` | In số đo hiện tại |
| `c` | In cấu hình đang dùng |
| `n` | Trạng thái WiFi / MQTT / NTP |
| `factory` | Xóa cấu hình về mặc định, khởi động lại |

## Keypad

`#` đổi trang OLED. `*` + PIN 4 số + `#` vào LOCAL 60 s (sai 3 lần khóa phím 60 s). Trong LOCAL: `1` bơm, `2` quạt, `3` AUTO/MANUAL, `0` thoát. Lệnh từ xa trong lúc LOCAL bị `blocked_local`.

## Thử nhanh không cần backend

Tạo tài khoản `ctl-0001` trên broker bằng tay (xem hướng dẫn trong chat/README deployment), rồi dùng MQTTX hoặc `mosquitto_pub`:

```bash
# Xem mọi bản tin của thiết bị (đăng nhập bằng tài khoản backend)
mosquitto_sub -h <IP> -u backend -P '<pw>' -t 'nursery/g01/ctl-0001/#' -v
# Bật bơm 5 giây
mosquitto_pub -h <IP> -u backend -P '<pw>' -q 1 -t nursery/g01/ctl-0001/command \
  -m '{"cmd_id":"t-1","action":"pump_on","params":{"duration_s":5},"ttl_s":30}'
# Gửi cấu hình (retain)
mosquitto_pub -h <IP> -u backend -P '<pw>' -q 1 -r -t nursery/g01/ctl-0001/config \
  -m '{"config_version":1,"params":{"soil_low":35,"soil_high":55,"soil_cal":{"s1":{"dry":3150,"wet":1320},"s2":{"dry":3210,"wet":1290}},"tank_cal":{"empty_cm":25,"full_cm":5}}}'
```

## Hành vi cần biết

- Lệnh quạt từ xa khi đang AUTO giữ hiệu lực 5 phút rồi trả về tự động.
- Không đọc được mực nước (HC-SR04 lỗi) thì **không bơm** (`blocked_sensor_fault`), kể cả lệnh tay.
- Nhận lại đúng `config_version` đang dùng (bản retain sau khi kết nối) thì gửi lại ack `executed`, không áp lại.
- Bản ghi tạo lúc chưa có giờ NTP được gán lại `ts` khi đã đồng bộ giờ, trước khi gửi.
