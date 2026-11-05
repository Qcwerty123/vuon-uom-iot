# Database

PostgreSQL 16. Đặc tả: `docs/dac-ta-he-thong.md` §11.

| File | Nội dung |
|---|---|
| `init/01_schema.sql` | 16 bảng, kiểu enum, khóa, index (đã chạy thử trên PostgreSQL 16) |
| `init/02_seed.sql` | Vườn `g01`, 2 khu vực, 2 thiết bị REGISTERED (`ctl-0001`, `cam-0001`), 6 luật cảnh báo mặc định |
| `migrations/` | Thay đổi schema sau này, đánh số `V002__mo_ta.sql`, `V003__…` |

## Cách nạp

Docker Compose gắn `init/` vào `/docker-entrypoint-initdb.d`. PostgreSQL **chỉ chạy các file này ở lần khởi tạo đầu tiên**, khi volume dữ liệu còn trống.

Muốn chạy lại từ đầu (xóa sạch dữ liệu):

```bash
cd deployment
docker compose down -v      # -v xóa luôn volume dbdata
docker compose up -d db
```

## Tài khoản người dùng

Không tạo trong SQL vì mật khẩu phải băm bcrypt. Backend tạo `admin`, `operator`, `viewer` lúc khởi động lần đầu, lấy mật khẩu từ `SEED_*_PASSWORD` trong `.env`.

## Khi đổi schema

1. Sửa đặc tả §11.2 trước, để tài liệu và code khớp nhau.
2. Thêm file migration mới, **không sửa** file đã chạy trên máy người khác.
3. Backend dùng FastAPI + Alembic (đặc tả C1): khi dựng backend, tạo migration gốc từ 2 file này và quản lý thay đổi tiếp theo bằng Alembic.

## Ghi chú

- Telemetry lưu dạng dài, khóa chính `(device_id, seq, metric)` để chống trùng.
- Bảng `audit_logs` chỉ được INSERT. Khi triển khai thật nên tạo một tài khoản ứng dụng riêng (không phải chủ sở hữu bảng) và `REVOKE UPDATE, DELETE ON audit_logs`.
- Không dùng TimescaleDB (đặc tả §22, C12).
