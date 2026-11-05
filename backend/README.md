# Backend

| Thư mục | Nội dung | Trạng thái |
|---|---|---|
| `api/` | Backend chính: REST API, WebSocket, nhận MQTT, vòng đời thiết bị, lệnh, cấu hình, cảnh báo, Telegram, audit | ⬜ |
| `ai-service/` | Dịch vụ AI (Python): `POST /v1/infer` trả nhãn 9 ô | ⬜ |

## Công nghệ (đã chốt, đặc tả §1.3)

**FastAPI** (Python 3.11+). Thư viện đề xuất: SQLAlchemy 2 + Alembic, Pydantic v2, paho-mqtt, passlib/bcrypt, PyJWT.

Phần `auth`, `canView`/`canControl`, lọc WebSocket và rate limit do Hoè viết trong backend, Kiên review qua Pull Request (C16).

## Mô-đun (đặc tả §4.2)

`auth` · `users` · `gardens` · `devices` · `ingest` · `commands` · `configs` · `alerts` · `notify` · `images/diagnoses` · `telemetry query` · `audit` · `realtime` · `scheduler`

## Thứ tự làm đề xuất

1. Kết nối CSDL (schema có sẵn ở `database/init`), seed 3 tài khoản từ `.env`.
2. `auth` (đăng nhập, JWT, refresh) + `users`.
3. `devices`: đăng ký, cấp phát (gọi Mosquitto Dynamic Security, đặc tả §8.8), gán, khóa, thu hồi.
4. `ingest`: subscribe MQTT, kiểm tra, chống trùng, lưu, cập nhật `last_seen`.
5. `realtime` (WebSocket) + `telemetry query`.
6. `commands` + `configs` + `scheduler` (offline, timeout lệnh).
7. `alerts` + `notify` (Telegram).
8. `images/diagnoses` + gọi AI service.

Trong lúc chưa có phần cứng, dùng thiết bị mô phỏng ở `tests/load` để có dữ liệu.

## Tài liệu tham chiếu

- API: đặc tả §10.
- Luồng ingest: đặc tả §8.10.
- Máy trạng thái: đặc tả §12.
- Phân quyền: đặc tả §14.1.
