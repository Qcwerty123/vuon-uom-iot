# Triển khai

Đặc tả: `docs/dac-ta-he-thong.md` §17 (v1.3).

Từ 05/11 hệ thống chạy **trực tiếp trên một máy Windows**, không Docker (C21). Toàn bộ công cụ, dữ liệu, cấu hình và log nằm trong thư mục repo (C22). Các file Docker trong thư mục này giữ lại để đóng gói sau demo, hiện **không dùng**.

## Thành phần

| Dịch vụ | Chạy từ | Địa chỉ | Trạng thái |
|---|---|---|---|
| PostgreSQL 16 | `tools/pgsql`, dữ liệu `runtime/pgdata` | `127.0.0.1:5433` | ⬜ N0 |
| Mosquitto 2.x + Dynamic Security | `tools/mosquitto`, dữ liệu `runtime/mosquitto` | `0.0.0.0:1883` | ⬜ N0 |
| AI service | `backend/ai-service` | `127.0.0.1:8001` | ⬜ chờ code |
| Backend (API, WebSocket, web tĩnh, `/device-api`) | `backend/api` | `0.0.0.0:8000` | ⬜ chờ code |

## Phiên bản công cụ (`tools/VERSIONS.txt`)

| Công cụ | Phiên bản |
|---|---|
| uv | 0.5.11 |
| Python | 3.11.11 |
| PostgreSQL | 16.4 (cổng **5433**: cổng 5432 bị Windows từ chối trên máy demo) |
| Mosquitto | 2.0.18 (có `mosquitto_dynamic_security.dll`) |
| Node.js | 20.18.0 |

## Chạy lần đầu (PowerShell, tại gốc repo)

```powershell
.\scripts\windows\get-tools.ps1      # tải công cụ vào tools/
Copy-Item .env.example .env             # đổi mọi change-me
.\scripts\windows\setup.ps1          # CSDL + schema + seed
.\scripts\windows\init-broker.ps1    # cấu hình broker, tài khoản backend
.\scripts\windows\firewall.ps1       # quyền Administrator, một lần
.\scripts\windows\verify.ps1         # nghiệm thu: kết quả ở logs/tests/verify-*.txt
```

Hằng ngày: bật Mobile Hotspot → `start.ps1` → `status.ps1`; trước khi tắt máy: `stop.ps1`. Dịch vụ không tự chạy khi bật máy. Tài khoản thiết bị khi chưa có backend: `dev-device.ps1 create -Code ctl-0001`.

**Lưu ý dynsec trên Windows:** Mosquitto 2.0.18 không ghi đè được `dynamic-security.json` (log báo `File exists`). Các script tự chép bản `.new` về đúng tên; xem đặc tả §17.5.

## Mạng

Máy chủ bật **Mobile Hotspot** của Windows, băng tần 2,4 GHz; máy chủ luôn là `192.168.137.1` (C17). Hai node và điện thoại xem dashboard vào WiFi này. Internet của máy chủ (để gửi Telegram, NTP) lấy từ WiFi khác, cáp mạng hoặc điện thoại cắm USB. Chi tiết và phương án dự phòng: đặc tả §17.7.

## Script (`scripts/windows/`, đang viết)

| Script | Việc |
|---|---|
| `setup.ps1` | Kiểm tra `tools/`, tạo `runtime/`, `logs/`, khởi tạo CSDL + schema + seed, tạo môi trường Python |
| `init-broker.ps1` | Sinh cấu hình Mosquitto từ `mosquitto/mosquitto.windows.conf`, tạo tài khoản `dynsec-admin`, `backend` và ACL |
| `firewall.ps1` | (Administrator) mở TCP 1883, 8000 |
| `start.ps1` / `stop.ps1` / `status.ps1` | Bật, tắt, kiểm tra toàn hệ thống; log vào `logs/services/` |
| `backup.ps1` | Sao lưu CSDL, `dynamic-security.json`, ảnh vào `runtime/backups/` |
| `reset-db.ps1` | Tạo lại CSDL từ đầu |

## Kiểm tra thành công (sau N0)

| Kiểm tra | Cách làm | Kết quả đúng |
|---|---|---|
| CSDL có bảng và seed | `tools\pgsql\bin\psql -h 127.0.0.1 -U nursery_app -d nursery -c "select device_code, status from devices;"` | 2 dòng `ctl-0001`, `cam-0001` ở `REGISTERED` |
| Broker chạy | Xem `logs\services\mosquitto.log` | Có dòng `mosquitto version 2.x running` |
| Plugin dynsec có trên Windows | `tools\mosquitto` có `mosquitto_dynamic_security.dll`; `mosquitto_ctrl` tạo được client | Được. Không được thì dùng phương án passwd/acl (đặc tả §17.5) |
| Từ chối ẩn danh | MQTTX từ điện thoại/laptop khác kết nối `192.168.137.1:1883` không user | Bị từ chối (not authorized) |
| Tài khoản backend | MQTTX đăng nhập `backend`, subscribe `nursery/+/+/telemetry` | Kết nối và subscribe được |
| Chặn quyền | Tài khoản backend publish lên `nursery/g01/ctl-0001/telemetry` | Bị broker từ chối |
| Tường lửa | Từ điện thoại trong hotspot mở `http://192.168.137.1:8000` (khi backend đã chạy) | Mở được |

## Ghi chú bảo mật

- CSDL và AI service chỉ nghe `127.0.0.1`.
- `runtime/mosquitto/` chứa tài khoản broker; `runtime/`, `tools/`, `logs/`, `.env` đều nằm trong `.gitignore`.
- Demo chạy HTTP trong hotspot WPA2 riêng. HTTPS cho web (uvicorn + mkcert, cổng 8443) là tùy chọn sau demo (C5).

## Docker (để sau)

`docker-compose.yml`, `mosquitto/config/mosquitto.conf`, `mosquitto/init-dynsec.sh`, `nginx/` là bản thiết kế cho Docker. Khi đóng gói: xem đặc tả §17.9.
