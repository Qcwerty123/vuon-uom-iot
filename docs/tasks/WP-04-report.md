# Báo cáo WP-04 — Frontend (đợt 1, 06/11)

## Đã xong

Đủ 11 màn hình của WP-04 §4, chạy được với backend WP-02/WP-03 hiện có (theo code `backend/api`). Chi tiết: `frontend/README.md`.

Đã chạy thử bằng chế độ dữ liệu giả (`npm run dev:mock`) với trình duyệt tự động, đạt 22/22 kịch bản:

- Đăng nhập sai báo lỗi; 3 vai trò có menu khác nhau; viewer không thấy nút điều khiển, cấu hình chỉ đọc; admin thấy quản lý thiết bị.
- Dashboard đổi số không cần tải lại trang (bản tin WS 3 giây/lần).
- Bật bơm: Đang chờ → Đã thực hiện; trạng thái bơm cập nhật qua telemetry.
- Cấu hình: chặn `soil_low ≥ soil_high`; "Chờ thiết bị áp dụng" → "Đã áp dụng".
- Cảnh báo: nhận xử lý, đóng có ghi chú.
- Cấp phát: secret hiện một lần, có nút copy và khối `secrets.h`; Provisioned → Active realtime; tạm khóa; thu hồi phải nhập lại mã.
- Ngắt WebSocket: hiện banner, tự kết nối lại, banner biến mất.
- Tải lại trang vẫn giữ phiên (refresh token trong `sessionStorage`).
- Giao diện điện thoại (390 px) dùng được, có menu gập.

## Chưa kiểm được (cần máy chủ thật)

- Chạy với backend thật + PostgreSQL + Mosquitto: chưa thử (máy làm frontend chưa có `tools/`). Cần chạy `test-backend.ps1` song song rồi bấm thử từng màn.
- `npm run build` bằng Vite và mở `http://192.168.137.1:8000` từ điện thoại trong hotspot.

## API thiếu hoặc lệch đặc tả (ghi lại, không sửa backend)

1. **Chẩn đoán (WP-07)** chưa có. Frontend dùng dữ liệu giả theo §10.9 (cờ `MOCK.diagnoses` trong `src/config.js`). Đặc tả chưa chốt dạng trả về của `GET /devices/{id}/diagnoses`; frontend chấp nhận cả mảng lẫn `{items, page, size, total}`. Trường dùng: `id, capturedAt, status, topLabel, topConfidence, abnormalTiles, tiles[{r,c,label,conf}], modelVersion, trigger, reviewVerdict, correctLabel, reviewedAt`.
2. Backend phục vụ `frontend/dist` bằng `StaticFiles(html=True)`, không có fallback SPA. Vì vậy frontend dùng hash router (`#/...`), không cần sửa backend.
3. §10.11 ghi ví dụ `deviceIds: ["d-1"]` nhưng backend nhận số nguyên; frontend gửi số nguyên (đúng WP-04 §2).
4. Gardens/Zones (§10.4) chưa có API, nên form đăng ký thiết bị chỉ cho nhập mã khu vực dạng số (không bắt buộc).
