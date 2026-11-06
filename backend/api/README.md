# backend/api — Backend FastAPI (WP-02: lõi)

Đặc tả: `docs/dac-ta-he-thong.md` §8.10 (ingest), §9, §10 (API), §12 (vòng đời), §14 (bảo mật).

## Chạy

- Nền (cùng các dịch vụ khác): `scripts\windows\start.ps1` — lần đầu tự tạo `.venv` và cài `requirements.txt`.
- Phát triển (log ra màn hình, tự nạp lại khi sửa code): `scripts\windows\start.ps1 -NoBackend` rồi `scripts\windows\backend.ps1`.
- API docs (OpenAPI/Swagger): `http://127.0.0.1:8000/docs`.
- Log: `logs/services/backend.log`, `logs/services/backend-console.log`.
- Kiểm thử đầu-cuối: `scripts\windows\test-backend.ps1` (đăng nhập, phân quyền, cấp phát, thiết bị mô phỏng gửi dữ liệu, WebSocket, khóa/mở/thu hồi).

## Cấu trúc

| File | Việc |
|---|---|
| `app/main.py` | Tạo app, logging, `/api/v1`, `/ws`, phục vụ `frontend/dist` nếu có |
| `app/config.py` | Đọc `.env` ở gốc repo |
| `app/db.py`, `app/models.py` | SQLAlchemy 2; ánh xạ bảng có sẵn (schema do `database/init` tạo) |
| `app/security.py`, `app/deps.py` | bcrypt, JWT, refresh token; `current_user`, `require_admin`, `canView`/`canControl` (404 khi không được gán — C6) |
| `app/lifecycle.py` | Máy trạng thái thiết bị §12.1 + lịch sử + đẩy WS |
| `app/dynsec.py` | Tạo/khóa/mở/xóa tài khoản thiết bị trên broker; đồng bộ file `.new` (đặc tả §17.5) |
| `app/ingest.py` | Bộ nhận MQTT: telemetry, status/LWT, event; chống trùng; Provisioned/Offline → Active |
| `app/realtime.py` | WebSocket hub: xác thực bằng bản tin `auth`, chỉ đẩy thiết bị được phép |
| `app/seed.py` | Tạo admin/operator/viewer từ `SEED_*_PASSWORD`; gán operator CONTROL, viewer VIEW cho ctl-0001, cam-0001 |
| `app/routers/` | `auth` (login/refresh/logout/me/password), `devices`, `telemetry` |

## Đã có (WP-02)

Auth + khóa tạm khi sai 5 lần, refresh rotation; `/users/me`; thiết bị: danh sách, chi tiết, đăng ký, sửa, cấp phát (secret một lần),
cấp lại khóa, khóa, mở khóa, thu hồi, lịch sử, gán quyền; telemetry latest/series/stats; events; WebSocket; audit.

## Chưa có (WP-03)

Lệnh + ack + timeout, cấu hình (quy tắc phiên bản §9.3), OfflineDetector/FaultDetector, bảo trì, cảnh báo + Telegram,
quản lý người dùng cho admin, đọc audit, xử lý `seq` bị tụt (§8.10), ảnh + chẩn đoán (WP-07). Alembic: chưa dùng, schema lấy từ `database/init`.
