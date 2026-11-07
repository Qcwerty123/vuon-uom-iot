# Frontend — web dashboard (WP-04)

React 18 + Vite + Recharts, viết bằng JavaScript (JSX). Đặc tả: `docs/dac-ta-he-thong.md` §10 (API), §10.11 (WebSocket), §16 (màn hình). Gói việc: `docs/tasks/WP-04-frontend.md`.

## Chạy

```powershell
cd frontend
..\tools\node\npm.cmd install          # lần đầu
..\tools\node\npm.cmd run dev          # http://localhost:5173, proxy /api và /ws sang backend 127.0.0.1:8000
..\tools\node\npm.cmd run build        # ra frontend\dist; backend tự phục vụ ở http://192.168.137.1:8000 (khởi động lại backend sau lần build đầu)
```

- **Cài dependency:** chỉ một lệnh `npm install` (gói lấy theo `package.json` + `package-lock.json`, ~100 gói, ~15 s), làm lần đầu
  hoặc khi `package.json` đổi. **Cần có mạng** — máy chủ demo không có internet thì cài + build trước, hoặc build ở máy khác rồi chép `frontend/dist` sang.
  Máy cá nhân có Node sẵn thì gõ `npm install` / `npm run ...` thay cho `..\tools\node\npm.cmd`.
- Lúc demo chỉ cần thư mục `dist/`; backend Python không cần gói nào của frontend.
- Bỏ qua cảnh báo `recharts deprecated` và `vulnerabilities` khi cài (thuộc dev server). **Không chạy `npm audit fix --force`** — lệnh này nâng Vite lên bản mới, hỏng build.
- **Làm trên máy khác** (đã vào hotspot của máy chủ): `$env:BACKEND_URL = "http://192.168.137.1:8000"; ..\tools\node\npm.cmd run dev`.
- **Không có backend:** `..\tools\node\npm.cmd run dev:mock` chạy toàn bộ API + WebSocket bằng dữ liệu giả trong trình duyệt
  (đăng nhập `admin` / `operator` / `viewer`, mật khẩu bất kỳ; gõ `sai` để thử lỗi). Trong console có `__mock.dropWs()`,
  `__mock.offline(1)`, `__mock.online(1)`, `__mock.tankLow()` để thử banner mất kết nối, offline, bể cạn.

## Cờ dữ liệu giả — `src/config.js`

| Cờ | Mặc định | Ý nghĩa |
|---|---|---|
| `MOCK.all` | bật khi `npm run dev:mock` | Toàn bộ API + WS giả |
| `MOCK.diagnoses` | `true` | Ảnh/chẩn đoán (`/devices/{id}/diagnoses`, `/diagnoses/{id}`, `/image`, `/review`) dùng dữ liệu giả vì WP-07 chưa có. **Backend xong WP-07 thì đổi thành `false`.** |

## Cấu trúc

| Đường dẫn | Việc |
|---|---|
| `src/api/client.js` | Gọi REST; access token trong bộ nhớ, refresh token trong `sessionStorage`; 401 → refresh một lần rồi thử lại; tự refresh trước khi hết hạn |
| `src/api/realtime.js` | WebSocket: `auth` → `subscribe`; `auth_expired` → refresh rồi gửi lại token; mất kết nối → banner, lùi dần 1 → 30 s, phát `reconnected` để các màn tải lại `telemetry/latest` |
| `src/auth.jsx`, `src/devices.jsx` | Phiên đăng nhập; danh sách thiết bị dùng chung, cập nhật trạng thái realtime |
| `src/labels.js` | Chữ tiếng Việt cho mọi mã trạng thái (trạng thái luôn có chữ, không chỉ màu) |
| `src/pages/` | Các màn hình (bảng dưới) |
| `src/components/` | Thành phần chung, bảng điều khiển, form cấu hình, biểu đồ |
| `src/mock/server.js` | Máy chủ giả (chỉ dùng khi bật cờ) |

Định tuyến bằng hash (`#/devices/1`) vì backend chỉ phục vụ tệp tĩnh của `dist/`: tải lại trang ở bất kỳ màn nào vẫn đúng mà không phải sửa backend.

## Màn hình

| # | Màn hình | Đường dẫn | Vai trò |
|---|---|---|---|
| 1 | Đăng nhập (sai mật khẩu, khóa tạm 423) | — | Tất cả |
| 2 | Tổng quan: thẻ thiết bị, số đo realtime có chữ theo ngưỡng, bơm/quạt/chế độ/khóa, ảnh mới nhất, cảnh báo đang mở | `#/` | Tất cả |
| 3 | Chi tiết thiết bị: thông tin, fw/hw, last seen, biểu đồ 1 giờ realtime, sự kiện, lịch sử lệnh và trạng thái, bảo trì | `#/devices/:id` | Theo gán |
| 4 | Điều khiển: bơm (chọn giây), quạt, AUTO/MANUAL, chụp ảnh, flash; nút hiện Đang chờ → kết quả | tab Điều khiển | CONTROL |
| 5 | Cấu hình: kiểm tra miền giá trị, `soil_low < soil_high`, hiệu chuẩn; "Chờ thiết bị áp dụng"; lịch sử phiên bản | tab Cấu hình | CONTROL (VIEW chỉ đọc) |
| 6 | Quản lý thiết bị: đăng ký, cấp phát (secret một lần + copy + khối `secrets.h`), cấp lại khóa, gán quyền, sửa, tạm khóa/mở khóa, thu hồi (nhập lại mã) | `#/admin/devices` | ADMIN |
| 7 | Cảnh báo: lọc trạng thái/mức/thiết bị, nhận xử lý, đóng có ghi chú | `#/alerts` | Theo gán |
| 8 | Lịch sử dữ liệu: metric, khoảng thời gian, biểu đồ, min/max/avg, bảng, xuất CSV | `#/history` | Theo gán |
| 9 | Hồ sơ: họ tên, email, Telegram chat id, đổi mật khẩu | `#/profile` | Tất cả |
| 10 | Ảnh + chẩn đoán: lưới 3×3 tô màu kèm chữ, độ tin cậy, xác nhận đúng/sai | `#/diagnoses` | Theo gán (xác nhận: CONTROL) |
| 11 | Người dùng, luật cảnh báo, audit log | `#/admin/users`, `#/rules`, `#/admin/audit` | ADMIN (luật: mọi vai trò xem) |

Ẩn nút theo vai trò/quyền chỉ để tiện dùng; quyền thật do backend kiểm tra, lỗi 403/404/409/429 hiện đúng `message` của backend.
