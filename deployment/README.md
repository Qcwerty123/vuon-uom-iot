# Triển khai

Đặc tả: `docs/dac-ta-he-thong.md` §17.

## Thành phần

| Dịch vụ | Image / nguồn | Cổng | Trạng thái |
|---|---|---|---|
| `db` | `postgres:16` | `127.0.0.1:5432` (chỉ máy chủ) | ✅ |
| `mosquitto` | `eclipse-mosquitto:2` + Dynamic Security | `1883` (LAN) | ✅ |
| `ai` | `../backend/ai-service` | nội bộ | ⬜ chờ code |
| `backend` | `../backend/api` | nội bộ | ⬜ chờ code |
| `web` | `../frontend` (Nginx) | `80`, `443` | ⬜ chờ code |

## Yêu cầu

- Docker Desktop (Windows/macOS) hoặc Docker Engine + Compose plugin (Linux).
- Trên Windows: chạy các lệnh `.sh` trong **Git Bash** hoặc **WSL**.
- Máy chủ có IP cố định trong LAN (đặt IP tĩnh hoặc DHCP reservation trên router). Nhóm chốt `192.168.1.10` (C17). Điền IP đó vào `MQTT_PUBLIC_HOST` và `PUBLIC_ORIGIN` trong `.env`, và vào `MQTT_HOST` trong `secrets.h` của thiết bị.
- Cài `chrony` trên máy chủ làm máy chủ NTP cho thiết bị (C11).

## Chạy lần đầu

```bash
cp .env.example .env               # ở gốc repo; đổi MỌI giá trị change-me
cd deployment
chmod +x mosquitto/init-dynsec.sh
./mosquitto/init-dynsec.sh         # hỏi mật khẩu quản trị broker: nhập đúng MQTT_DYNSEC_PASSWORD
docker compose up -d db mosquitto
docker compose ps                  # cả hai ở trạng thái running / healthy
```

## Kiểm tra thành công

| Kiểm tra | Lệnh | Kết quả đúng |
|---|---|---|
| CSDL đã có bảng và seed | `docker compose exec db psql -U nursery_app -d nursery -c "select device_code, status from devices;"` | 2 dòng `ctl-0001`, `cam-0001` ở `REGISTERED` |
| Broker chạy | `docker compose logs mosquitto` | Có dòng `mosquitto version 2.x running` |
| Từ chối ẩn danh | MQTTX kết nối `<IP máy chủ>:1883` không user | Bị từ chối (not authorized) |
| Tài khoản backend | MQTTX đăng nhập `backend` / `MQTT_BACKEND_PASSWORD`, subscribe `nursery/+/+/telemetry` | Kết nối và subscribe được |
| Chặn quyền | Dùng tài khoản backend publish lên `nursery/g01/ctl-0001/telemetry` | Bị broker từ chối (chỉ được gửi `command`, `config`) |

## Lệnh thường dùng

```bash
docker compose logs -f mosquitto        # xem log broker trực tiếp
docker compose restart mosquitto
docker compose down                     # dừng, GIỮ dữ liệu
docker compose down -v                  # dừng và XÓA dữ liệu CSDL (seed chạy lại lần sau)
docker compose exec db pg_dump -U nursery_app nursery > backups/nursery-$(date +%F).sql   # sao lưu trước demo
```

## Khi đã có code backend, AI, frontend

Bỏ comment dịch vụ tương ứng trong `docker-compose.yml`, thêm `Dockerfile` vào thư mục đó, rồi `docker compose up -d --build`.

## Ghi chú bảo mật

- `mosquitto/data/` chứa tài khoản broker: đã nằm trong `.gitignore`.
- Không mở cổng 5432 ra LAN.
- TLS cho MQTT (cổng 8883) và HTTPS cho web: xem phần comment trong `mosquitto.conf` và `nginx/README.md`.
