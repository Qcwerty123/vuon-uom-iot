# Node 1 — Firmware điều khiển

Đặc tả: `docs/dac-ta-he-thong.md` §6 (firmware), §6.11 (đèn chiếu sáng), §8 (MQTT). Phiên bản `FW_VERSION` ở `app.h` (hiện 1.1.0).

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
| `control.*` | Tưới, quạt có trễ, đèn chiếu sáng (§6.11), AUTO/MANUAL/LOCAL, khóa an toàn và khóa nhiệt (§6.5, §6.6); mọi lần bật relay lệch nhau 400 ms; timer phần cứng cắt bơm đúng hạn |
| `net.*` | WiFi + MQTT kết nối lại có backoff 1→30 s, NTP `pool.ntp.org` qua Internet chia sẻ vào hotspot (C11), LWT |
| `protocol.*` | telemetry / status / event / ack; xử lý `command`, `config`; chống trùng `cmd_id`; hạn lệnh `ttl_s` |
| `buffer.*` | Hàng đợi 200 bản ghi khi mất mạng, gửi bù 5 bản tin/giây kèm `buffered:true` |
| `ui.*` | OLED SH1106 3 trang + keypad có PIN |

## Lệnh Serial

| Lệnh | Việc |
|---|---|
| `s` | In số đo hiện tại |
| `d` | Trạng thái đèn (giờ, khung, override, khóa nhiệt) và relay đang đóng |
| `c` | In cấu hình đang dùng |
| `n` | Trạng thái WiFi / MQTT / NTP |
| `factory` | Xóa cấu hình về mặc định, khởi động lại |

## Keypad

`#` đổi trang OLED. `*` + PIN 4 số + `#` vào LOCAL 60 s (sai 3 lần khóa phím 60 s). Trong LOCAL: `1` bơm, `2` quạt, `3` AUTO/MANUAL, `4` đèn, `0` thoát. Lệnh từ xa trong lúc LOCAL bị `blocked_local`.

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
# Demo đèn ở mọi giờ (nhớ đặt lại 6–20 sau demo)
mosquitto_pub -h <IP> -u backend -P '<pw>' -q 1 -r -t nursery/g01/ctl-0001/config \
  -m '{"config_version":2,"params":{"lamp_start_hour":0,"lamp_end_hour":24,"lamp_self_lux":300}}'
```

## Hành vi cần biết

- Lệnh quạt từ xa khi đang AUTO giữ hiệu lực 5 phút rồi trả về tự động.
- **Đèn (AUTO):** chỉ bật trong khung `lamp_start_hour`–`lamp_end_hour` (giờ Việt Nam, cần NTP). Bật khi lux < `lamp_lux_low` (800), tắt khi lux ≥ `lamp_lux_low` + `lamp_hyst` (1500). Điều kiện phải đúng liên tục `lamp_hold_s` (10 s), sau mỗi lần đổi giữ tối thiểu `lamp_min_on_s` / `lamp_min_off_s` (30 s). Ra khỏi khung giờ hoặc quá nóng thì tắt ngay. BH1750 lỗi thì bật theo lịch.
- **Lệnh đèn tay** (`lamp_on {duration_min?}`, `lamp_off`, phím `4`) khi đang AUTO giữ hiệu lực tối đa `lamp_override_min` (60 phút), kể cả ngoài khung giờ, rồi trả về tự động.
- **Khóa nhiệt:** `air_temp ≥ temp_high + 3` thì tắt đèn, lệnh bật đèn bị `blocked_overheat`; nhả khi nhiệt độ giảm thêm `temp_hyst`.
- **Lệch pha relay:** relay bơm, quạt, đèn đóng cách nhau ≥ 400 ms; tắt thì ngay. Thời gian bơm tính từ lúc relay thực sự đóng.
- Bản 1.1.0 đổi cấu trúc cấu hình trong NVS: nạp lần đầu thì cấu hình về mặc định (`config_version` = 0). Backend gửi lại cấu hình theo quy tắc §9.3.
- Không đọc được mực nước (HC-SR04 lỗi) thì **không bơm** (`blocked_sensor_fault`), kể cả lệnh tay.
- Nhận lại đúng `config_version` đang dùng (bản retain sau khi kết nối) thì gửi lại ack `executed`, không áp lại.
- Bản ghi tạo lúc chưa có giờ NTP được gán lại `ts` khi đã đồng bộ giờ, trước khi gửi.
