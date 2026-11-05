# Thiết bị mô phỏng (chưa có code)

Đặc tả: `docs/dac-ta-he-thong.md` §18.3.

Script Python `simulator.py` (gợi ý dùng `paho-mqtt`):

- Cấp phát N thiết bị qua API bằng tài khoản admin test, lưu `device_code` + secret.
- Mỗi thiết bị publish `telemetry` theo chu kỳ (payload đúng đặc tả §8.3), `status` online + LWT, trả `ack` cho mọi lệnh nhận được.
- Tham số: `--devices 20 --interval 1 --duplicate-rate 0.05 --drop-rate 0.02`.

Dùng để:

1. Phát triển backend/frontend khi chưa có phần cứng.
2. Đo NFR09 (khả năng tải), NFR05 (mất bản tin), NFR08 (bản tin trùng).

Thiết bị mô phỏng **không thay thế** thiết bị thật trong demo (đề bài mục 4.2).
