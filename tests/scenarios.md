# Kịch bản và kết quả kiểm thử

Điền cột **Kết quả** (Đạt / Không đạt + ghi chú) và **Bằng chứng** (đường dẫn file trong `results/`).

## 1. Kiểm thử chức năng

| Mã | Ca | Các bước chính | Kỳ vọng | Ngày | Người test | Kết quả | Bằng chứng |
|---|---|---|---|---|---|---|---|
| FT1 | Đăng nhập, phân quyền | Đăng nhập 3 vai trò; VIEWER gọi `POST /commands` | Menu đúng vai trò; 403 | | | | |
| FT2 | Đăng ký, kích hoạt thiết bị | Tạo → cấp phát → nạp secret → bật nguồn | REGISTERED → PROVISIONED → ACTIVE, có lịch sử + audit | | | | |
| FT3 | Telemetry | Chạy Node 1 trong 5 phút | ~30 bản ghi mỗi metric, không trùng | | | | |
| FT4 | Dashboard realtime | Hà hơi vào DHT22; nhúng cảm biến đất vào nước | Giá trị đổi trên UI < 3 s | | | | |
| FT5 | Lệnh + xác nhận | Bật bơm 5 s khi bể đủ nước; rút nước rồi bật lại | EXECUTED; REJECTED `blocked_no_water` | | | | |
| FT6 | Đổi cấu hình | Đổi `soil_low` | Config APPLIED; hành vi tưới đổi theo | | | | |
| FT7 | Offline | Rút nguồn Node 1 | OFFLINE ≤ 90 s + cảnh báo + Telegram; cắm lại tự Active | | | | |
| FT8 | Cảnh báo | Hạ ngưỡng để kích hoạt; xác nhận; đóng | OPEN → ACKNOWLEDGED → CLOSED, có audit | | | | |
| FT9 | Khóa / thu hồi | Suspend Node 1 | Broker từ chối CONNECT; resume thì kết nối lại | | | | |
| FT10 | Chụp và chẩn đoán | Lệnh chụp; ảnh lá bệnh 3 lần | Diagnosis DONE; cảnh báo AI_LEAF | | | | |
| FT11 | Mất mạng | Tắt router 10 phút rồi bật lại | Node 1 vẫn tưới; gửi bù đủ, `seq` liên tục | | | | |
| FT12 | Keypad / LOCAL | Nhập PIN, bật bơm tại chỗ | Event `local_override`; lệnh từ xa bị `blocked_local` | | | | |

## 2. Kiểm thử phi chức năng

| Mã | Chỉ tiêu | Ngưỡng | Phương pháp | Số liệu đo | Đạt? | Nhận xét |
|---|---|---|---|---|---|---|
| NFR01 | Cảm biến → dashboard | < 3 s (p95) | So `ts` thiết bị với thời điểm UI nhận; 100 mẫu | | | |
| NFR02 | Lệnh → ack | < 2 s (p95) | `ack_at − issued_at`; 50 lệnh | | | |
| NFR03 | Phát hiện offline | ≤ 90 s | Rút nguồn, bấm giờ | | | |
| NFR04 | Chạy liên tục | 72 giờ | Đếm reboot và khoảng trống heartbeat | | | |
| NFR05 | Mất bản tin | < 1% | Khoảng trống `seq` / tổng | | | |
| NFR06 | Kết nối lại | < 30 s; không mất dữ liệu nếu mất mạng ≤ 15 phút | Tắt/bật router | | | |
| NFR07 | Đệm offline | ≥ 100 bản ghi | Ngắt mạng > 100 chu kỳ | | | |
| NFR08 | Bản tin trùng | 0 trùng, 0 lệnh chạy 2 lần | Phát lại cùng `seq` / `cmd_id` | | | |
| NFR09 | Khả năng tải | ≥ 20 thiết bị × 1 msg/s | Script `load/`; đo CPU, RAM, độ trễ | | | |

## 3. Kiểm thử bảo mật

| Mã | Ca | Kỳ vọng | Ngày | Kết quả | Bằng chứng |
|---|---|---|---|---|---|
| ST1 | OPERATOR A truy cập / gửi lệnh tới thiết bị không được gán | 404 (C6), audit `COMMAND_DENIED` | | | |
| ST2 | Token hết hạn; token sửa chữ ký | 401 | | | |
| ST3 | Suspend thiết bị đang kết nối; kết nối lại bằng secret cũ | Bị ngắt; CONNACK not authorized | | | |
| ST4 | `ctl-0001` publish lên topic của `cam-0001` | Broker chặn, backend không có bản ghi | | | |
| ST5 | Telemetry sai schema / `soil=250`; upload file không phải JPEG | Bị loại / 400, có log | | | |
| ST6 | Sai mật khẩu 6 lần | Khóa tạm 15 phút, audit `LOGIN_FAILED` | | | |
