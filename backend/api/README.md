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

## Đã có (WP-03)

- Lệnh: `POST/GET /devices/{id}/commands`, `GET /commands/{cmdId}` — kiểm tra quyền CONTROL (thiếu quyền ghi audit `COMMAND_DENIED`),
  trạng thái + online (409), tham số theo loại thiết bị (400), 10 lệnh/phút (429); ack → EXECUTED/REJECTED/FAILED; 10 s không ack → TIMEOUT.
- Cấu hình: `GET/PUT /devices/{id}/config`, `/config/history` — kiểm tra miền giá trị, phiên bản = max(CSDL, thiết bị báo) + 1 (§9.3),
  gửi retain, ack `cfg-N` → APPLIED/REJECTED, chưa ack sau 60 s thì gửi lại.
- Bảo trì: `POST /devices/{id}/maintenance`, `/maintenance/end`.
- Tác vụ nền (`app/jobs.py`): CommandTimeout 2 s, OfflineDetector 15 s (> 90 s), ConfigRetry 30 s, FaultDetector 60 s, HourlyRollup.
- Cảnh báo (`app/alerts.py`): THRESHOLD (duy trì `durationS`, trễ `hysteresis`), OFFLINE (tự đóng khi online lại), EVENT (tank_low, sensor_fault…),
  chống gửi lặp `cooldownMin`; `GET /alerts`, `acknowledge`, `close`; `/alert-rules` (ADMIN ghi; xóa = tắt).
- Telegram (`app/telegram.py`): gửi cho admin và người được gán có `telegramChatId`; thiết bị đang bảo trì không gửi. Nhắn `/start` cho bot để lấy chat id.
- Người dùng (ADMIN): `GET/POST /users`, `PATCH /users/{id}`, `lock`, `unlock`, `activate`, `reset-password`. Audit: `GET /audit-logs`. `GET /dashboard/summary`.
- Xuất CSV: `GET /devices/{id}/telemetry/export.csv`.
- Kiểm thử: `scripts\windows\test-backend.ps1 -Wp 03`.

## Chưa có

Ảnh + chẩn đoán + luật AI_LEAF (WP-07), xử lý `seq` bị tụt (§8.10), Retention, Alembic (schema lấy từ `database/init`).
