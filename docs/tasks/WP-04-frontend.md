# WP-04 — Frontend (React)

**Mục tiêu:** web dashboard chạy trên máy chủ (backend phục vụ bản build ở `http://192.168.137.1:8000`), đủ các màn hình cho 10 bước demo (đặc tả §20.2). Hạn: các màn P0 xong **12/11**, ảnh/chẩn đoán xong **14/11**.

## 1. Đọc trước

| Nguồn | Nội dung |
|---|---|
| `docs/dac-ta-he-thong.md` §10 | REST API + WebSocket (quy ước, mã lỗi, camelCase) |
| `docs/dac-ta-he-thong.md` §16 | Danh sách màn hình, nguyên tắc giao diện |
| `docs/dac-ta-he-thong.md` §12, §14.1 | Trạng thái thiết bị/lệnh/cảnh báo; ma trận quyền |
| `http://127.0.0.1:8000/docs` | OpenAPI của backend đang chạy — nguồn đúng cho những API **đã có** |
| `frontend/README.md` | Thứ tự ưu tiên màn hình |

## 2. API hiện có và sắp có

**Đã có (WP-02, chạy được ngay):**
- `POST /api/v1/auth/login | refresh | logout`, `GET/PATCH /api/v1/users/me`, `POST /api/v1/users/me/password`
- `GET/POST /api/v1/devices`, `GET/PATCH /api/v1/devices/{id}`, `POST .../provision | rotate-secret | suspend | resume | decommission`, `GET .../history`, `GET/POST/DELETE .../assignments`
- `GET /api/v1/devices/{id}/telemetry/latest | telemetry?metric=&from=&to=&interval= | telemetry/stats | events`
- WebSocket `/ws`: gửi `{"type":"auth","token":...}` trong 5 giây, rồi `{"type":"subscribe","deviceIds":[1,2]}`; nhận `telemetry`, `device_status`, `device_event` (chi tiết đặc tả §10.11; `deviceIds` là số nguyên).

**Sắp có (WP-03, làm đúng theo đặc tả, tạm dùng dữ liệu giả nếu backend chưa xong):** commands (§10.7), config (§10.5 `PUT /devices/{id}/config`), alerts + alert-rules (§10.8), users cho admin (§10.3), audit (§10.10), dashboard summary (§10.10). WebSocket thêm `command_update`, `config_update`, `alert`.

**Sau đó (WP-07):** diagnoses (§10.9), WS `diagnosis`.

## 3. Luật

1. React 18 + Vite + Recharts (TypeScript nếu quen). Thư mục `frontend/`. Không đổi backend; cần API khác thì ghi vào báo cáo.
2. Node.js dùng bản trong `tools/node` (`tools\node\npm.cmd`), không cài Node ra ngoài. `node_modules/`, `dist/` không commit.
3. Gọi API bằng **đường dẫn tương đối** (`/api/v1`, `/ws`) để chạy với mọi IP máy chủ. Khi dev dùng proxy của Vite tới `http://127.0.0.1:8000` (cả `/ws`).
4. Access token chỉ giữ trong bộ nhớ; refresh token trong `sessionStorage`. Gặp 401 thì gọi `/auth/refresh` một lần rồi thử lại; vẫn 401 thì về trang đăng nhập.
5. Ẩn nút theo vai trò/quyền (`role` của user, `permission` VIEW/CONTROL của từng thiết bị) chỉ để tiện dùng — quyền thật do backend kiểm tra; hiển thị lỗi 403/404/409 theo `message` của backend.
6. Trạng thái luôn có **chữ**, không chỉ màu ("Online/Offline", "Đang chờ", "Bị từ chối: bể cạn"). Giao diện tiếng Việt.
7. Mất WebSocket: hiện banner, tự kết nối lại (lùi dần 1→30 s), tải lại `telemetry/latest`.
8. Bản build: `npm run build` ra `frontend/dist/`; backend tự phục vụ khi thư mục này tồn tại (khởi động lại backend sau khi build lần đầu).

## 4. Màn hình theo ưu tiên

| # | Màn hình | Vai trò | API |
|---|---|---|---|
| 1 | Đăng nhập (thông báo sai mật khẩu, tài khoản tạm khóa 423) | Tất cả | auth |
| 2 | Dashboard: thẻ thiết bị (trạng thái + online), số đo mới nhất cập nhật realtime, cảnh báo đang mở | Tất cả | devices, latest, WS |
| 3 | Chi tiết thiết bị: thông tin, fw/hw, last seen, biểu đồ 1 giờ realtime, sự kiện, lịch sử trạng thái | Theo gán | devices, telemetry, events, history, WS |
| 4 | Điều khiển: bơm (chọn giây), quạt, chế độ AUTO/MANUAL; nút hiện PENDING → kết quả | CONTROL | commands (WP-03) |
| 5 | Cấu hình ngưỡng có kiểm tra (`soil_low < soil_high`...), "chờ thiết bị áp dụng" | CONTROL | config (WP-03) |
| 6 | Quản lý thiết bị (admin): đăng ký, **cấp phát hiển thị secret một lần + nút copy** (kèm khối `secrets.h` mẫu), cấp lại khóa, gán quyền, khóa/mở, thu hồi (nhập lại mã) | ADMIN | devices |
| 7 | Cảnh báo: lọc, xác nhận, đóng có ghi chú | Theo gán | alerts (WP-03) |
| 8 | Lịch sử dữ liệu: chọn metric + khoảng thời gian, biểu đồ, min/max/avg, xuất CSV | Theo gán | telemetry |
| 9 | Hồ sơ: đổi mật khẩu, Telegram chat id | Tất cả | users/me |
| 10 | Ảnh + chẩn đoán: lưới 3×3 tô màu + chữ, độ tin cậy, xác nhận đúng/sai | Theo gán | diagnoses (WP-07) |
| 11 | Admin: người dùng, luật cảnh báo, audit log | ADMIN | WP-03 |

## 5. Cách chạy khi phát triển

```powershell
# Máy chủ (người giữ máy): PostgreSQL + broker + backend
.\scripts\windows\start.ps1
# Tạo dữ liệu: thiết bị mô phỏng cần được cấp phát qua API (Swagger /docs → POST /devices, /provision),
# hoặc dùng Node 1 thật. Tài khoản: admin / operator / viewer (mật khẩu trong .env của máy chủ).
cd frontend
..\tools\node\npm.cmd install
..\tools\node\npm.cmd run dev        # http://localhost:5173, proxy sang backend
```

Làm trên máy khác: đổi đích proxy của Vite sang `http://192.168.137.1:8000` (máy đó vào WiFi hotspot của máy chủ).

## 6. Tiêu chí xong

- [ ] Đăng nhập 3 vai trò, menu đúng vai trò; viewer không thấy nút điều khiển; admin thấy quản lý thiết bị.
- [ ] Dashboard đổi số trong < 3 giây khi thiết bị gửi dữ liệu (không tải lại trang).
- [ ] Cấp phát thiết bị từ giao diện, secret hiện một lần, copy được.
- [ ] Khóa/mở/thu hồi từ giao diện, trạng thái đổi realtime.
- [ ] Rút mạng backend: có banner, tự kết nối lại.
- [ ] `npm run build` thành công; mở `http://192.168.137.1:8000` từ điện thoại trong hotspot thấy web.
- [ ] Không có token/mật khẩu trong mã nguồn, không commit `node_modules/`, `dist/`.

## 7. Báo cáo và Git

- Làm trên nhánh `feat/frontend`, commit nhỏ bằng tài khoản của mình, mở Pull Request vào `dev`.
- Báo cáo ngắn vào mô tả PR (hoặc `logs/agent/WP-04-report.md` nếu là agent làm trên máy chủ): màn hình đã xong, API còn thiếu/chưa khớp, ảnh chụp màn hình.

---

## Prompt cho agent

```
Bạn là agent frontend làm việc trong repo vuon-uom-iot. Nhiệm vụ: gói việc WP-04 — xây web dashboard React + Vite trong thư mục frontend/.

Đọc kỹ docs/tasks/WP-04-frontend.md rồi làm đúng theo: mục 1 (đọc trước), 3 (luật), 4 (màn hình theo thứ tự ưu tiên), 6 (tiêu chí xong). API đã có xem trực tiếp ở http://127.0.0.1:8000/docs (nếu chạy trên máy chủ) và docs/dac-ta-he-thong.md §10; API chưa có (lệnh, cấu hình, cảnh báo, người dùng, audit, chẩn đoán) làm theo đúng đặc tả §10 và tạm dùng dữ liệu giả có cờ bật/tắt, để khi backend xong chỉ cần tắt cờ.

Yêu cầu:
- Dùng Node trong tools/node (tools\node\npm.cmd). Không sửa backend, firmware, database, scripts.
- Gọi API bằng đường dẫn tương đối; dev dùng proxy Vite tới backend; build ra frontend/dist.
- Giao diện tiếng Việt, trạng thái luôn có chữ, quyền thật do backend kiểm tra.
- Làm theo từng màn hình, chạy thử sau mỗi màn hình; ưu tiên màn 1, 2, 3, 6 trước.
- Không commit/push trừ khi người giao việc yêu cầu; nếu được yêu cầu thì dùng nhánh feat/frontend.

Khi xong một đợt, báo cáo: màn hình nào đã chạy, API nào thiếu hoặc lệch đặc tả, cách chạy thử.
```
