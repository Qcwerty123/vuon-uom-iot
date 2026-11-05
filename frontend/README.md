# Frontend (chưa có code)

Đặc tả: `docs/dac-ta-he-thong.md` §16 (màn hình), §10 (API), §10.11 (WebSocket).

Đề xuất: React + Vite + Recharts (hoặc framework nhóm quen). Build ra file tĩnh, phục vụ bằng Nginx trong image `web` (xem `deployment/nginx/README.md`).

## Màn hình theo thứ tự ưu tiên

1. Đăng nhập (lưu access token trong bộ nhớ, refresh token theo cách backend quy định).
2. Dashboard: thẻ thiết bị, giá trị mới nhất, cảnh báo đang mở. Cập nhật qua WebSocket.
3. Chi tiết thiết bị + điều khiển (nút hiển thị trạng thái lệnh PENDING → kết quả).
4. Lịch sử dữ liệu: biểu đồ, bảng, xuất CSV.
5. Cảnh báo: lọc, xác nhận, đóng.
6. Quản lý thiết bị (admin): đăng ký, cấp phát (hiện secret một lần), gán, khóa, thu hồi.
7. Quản lý người dùng, luật cảnh báo, audit log (admin).
8. Ảnh và chẩn đoán: lưới 3×3 tô màu kèm chữ, nút xác nhận đúng/sai.
9. Cấu hình ngưỡng, hồ sơ cá nhân.

## Nguyên tắc

- Ẩn nút theo vai trò chỉ để tiện dùng. Quyền thật kiểm tra ở backend.
- Trạng thái luôn có chữ, không chỉ màu ("Online", "Đang chờ", "Bị từ chối: bể cạn").
- Mất WebSocket: hiện banner, tự kết nối lại, tải lại dữ liệu mới nhất.
- Có `Dockerfile` (build + Nginx) để bật dịch vụ `web` trong Docker Compose.
