# Hệ thống chăm sóc vườn ươm thông minh

Đồ án kết thúc học phần **IoT và ứng dụng** — Nhóm [__]

Hai node ESP32 đặt tại vườn ươm:

- **Node 1 (điều khiển)** đo độ ẩm đất, nhiệt độ, độ ẩm không khí, ánh sáng, mực nước bể. Tự tưới, thông gió và chiếu sáng bổ sung theo ngưỡng, có khóa an toàn ngay trên thiết bị.
- **Node 2 (ESP32-CAM)** chụp ảnh khay cây để AI phân loại tình trạng lá.

Dữ liệu và lệnh đi qua MQTT. Ảnh gửi qua HTTP. Backend tự xây quản lý người dùng (3 vai trò), vòng đời thiết bị (8 trạng thái), dữ liệu đo, lệnh, cấu hình, cảnh báo (Telegram) và chẩn đoán ảnh. Toàn bộ phía server chạy trực tiếp trên **một máy Windows**, gói trong thư mục repo; máy đó phát WiFi cho các node. Docker Compose để sau demo.

> **Bắt đầu từ đâu?** Đọc [`HUONG-DAN.md`](HUONG-DAN.md): cách đưa repo lên GitHub, và việc tiếp theo của từng thành viên.

## Kiến trúc

```
Node 1 (ESP32) ──MQTT──┐                       ┌──► Web dashboard (REST + WebSocket)
                       ├──► Mosquitto ──► Backend ──► PostgreSQL · kho ảnh
Node 2 (ESP32-CAM) ────┘        ▲          │    └──► Telegram
        └──────── HTTP ảnh ─────┼──────────┘    └──► AI service (Python)
```

Chi tiết: [`docs/dac-ta-he-thong.md`](docs/dac-ta-he-thong.md).

## Cấu trúc thư mục

| Thư mục | Nội dung |
|---|---|
| `firmware/` | Sketch Arduino IDE 2: chẩn đoán phần cứng, Node 1, Node 2 |
| `backend/` | API, xử lý telemetry, quản lý thiết bị (`api/`) và dịch vụ AI (`ai-service/`) |
| `frontend/` | Giao diện web |
| `database/` | Schema, dữ liệu mẫu |
| `scripts/windows/` | Script PowerShell: cài đặt, bật/tắt, kiểm tra, sao lưu (đang viết) |
| `deployment/` | Mẫu cấu hình Mosquitto; Docker Compose và Nginx (để sau) |
| `tools/`, `runtime/`, `logs/` | Công cụ portable, dữ liệu chạy, log — tạo khi cài đặt, **không commit** |
| `hardware/` | Danh sách linh kiện, sơ đồ nối dây, nhật ký lắp đặt, ảnh prototype |
| `tests/` | Kịch bản kiểm thử, mã kiểm thử, kết quả đo |
| `docs/` | Phân tích, đặc tả, hướng dẫn lắp đặt, sơ đồ, báo cáo, slide |
| `.env.example` | Danh sách biến môi trường (không chứa bí mật thật) |

## Trạng thái

| Hạng mục | Trạng thái |
|---|---|
| Tài liệu phân tích, đặc tả, hướng dẫn lắp đặt | ✅ |
| Sketch chẩn đoán phần cứng (`firmware/test-hardware`) | ✅ |
| Schema và seed CSDL | ✅ |
| Triển khai trên Windows (script, PostgreSQL, Mosquitto) | ⬜ giai đoạn N0 |
| Firmware Node 1 | ✅ đã viết `v1.1.0`, chưa thử trên mạch |
| Firmware Node 2 | ✅ đã viết `v1.0.0`, chưa thử trên mạch |
| Backend API (FastAPI) | ⬜ |
| AI service | ⬜ |
| Frontend | ⬜ |
| Kiểm thử và số liệu | ⬜ |
| Demo trên máy chủ Windows | ⬜ khoảng 18/11/2026 |
| Báo cáo, release `v1.0.0` | ⬜ (hạn 24/11/2026) |
| Docker Compose | để sau demo |

## Chạy hệ thống (Windows)

Đang xây dựng ở giai đoạn N0. Khi xong, các bước sẽ là (PowerShell, tại gốc repo):

```powershell
Copy-Item .env.example .env              # rồi sửa mọi giá trị change-me
.\scripts\windows\setup.ps1             # lần đầu: tạo runtime/, CSDL, môi trường Python
.\scripts\windows\init-broker.ps1       # lần đầu: tài khoản broker và ACL
.\scripts\windows\firewall.ps1          # lần đầu, quyền Administrator: mở cổng 1883, 8000
.\scripts\windows\start.ps1             # bật toàn hệ thống
.\scripts\windows\status.ps1            # kiểm tra
```

Chi tiết: [`deployment/README.md`](deployment/README.md) và đặc tả §17.

## Tài liệu

| Tài liệu | Nội dung |
|---|---|
| [`docs/phan-tich-he-thong.md`](docs/phan-tich-he-thong.md) | Phân tích ban đầu (v0.1, tài liệu lịch sử — đặc tả là nguồn đúng) |
| [`docs/dac-ta-he-thong.md`](docs/dac-ta-he-thong.md) | Đặc tả chi tiết: phần cứng, firmware, MQTT, API, CSDL, bảo mật, AI, kiểm thử |
| [`docs/huong-dan-lap-dat-phan-cung.md`](docs/huong-dan-lap-dat-phan-cung.md) | Lắp mạch từng công đoạn, cài Arduino IDE 2 và thư viện |

## Thành viên

| Thành viên | MSSV | GitHub | Phụ trách |
|---|---|---|---|
| Hà Mạnh Quân | | | Phần cứng, firmware |
| Lê Trung Kiên | | | Backend, CSDL |
| Nguyễn Văn Đức Anh | | | Frontend, kiểm thử |
| Cao Công Hoè | | | Bảo mật, DevOps, AI |

## Bảo mật

Không commit `.env`, `secrets.h`, khóa, chứng chỉ, ảnh có người, hay các thư mục `tools/`, `runtime/`, `logs/`. Danh sách chặn nằm trong `.gitignore`. Chỉ commit các file `*.example`.

## Thư viện và tài nguyên bên thứ ba

Liệt kê ở `firmware/LIBRARIES.md`, `backend/ai-service/README.md` (dataset, mô hình) và báo cáo, theo yêu cầu công khai nguồn của đề bài.

