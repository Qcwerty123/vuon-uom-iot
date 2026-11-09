# Giao việc (gói việc WP)

Mỗi file `WP-xx-*.md` là một gói việc tự đủ để một agent hoặc một thành viên làm mà không cần đọc lại cả cuộc thảo luận: bối cảnh, luật, việc cần làm, tiêu chí xong, cách kiểm tra, cách báo cáo. Cuối mỗi file có **prompt** để dán cho agent.

| Gói | Nội dung | Trạng thái |
|---|---|---|
| WP-00 | Triển khai nền tảng trên Windows: công cụ portable, CSDL, broker, script vận hành | **Xong 06/11** — `logs/agent/WP-00-report.md` |
| WP-01 | Thiết bị mô phỏng Node 1 (`tests/load/simulator.py`, `scripts/windows/sim.ps1`) | **Xong 06/11** (đã chạy thử: lệnh, cấu hình, ack ~15 ms) |
| WP-02 | Backend lõi FastAPI (`backend/api`): auth, thiết bị + cấp phát dynsec, ingest, WebSocket | **Xong 06/11** — `test-backend.ps1` đạt 24/24 |
| WP-03 | Backend nghiệp vụ: lệnh, cấu hình, offline, cảnh báo + Telegram, người dùng, audit | **Xong 06/11** — `test-backend.ps1 -Wp 03` đạt 35/35 |
| WP-04 | Frontend React (`frontend/`) | **Đợt 1 xong 06/11** (đủ 11 màn, chạy thử bằng dữ liệu giả) — `WP-04-report.md` |
| WP-N1 | Nối Node 1, Node 2 thật vào hệ thống qua backend | Node 1 **đã nối 07/11**: ACTIVE, telemetry, lệnh bơm EXECUTED (ack 0,2 s). Còn: thử mất nguồn, hiệu chuẩn đất/bể, BH1750 báo lỗi. Node 2 chưa |
| WP-07 | Ảnh + AI chẩn đoán lá: upload `/device-api/v1/images`, AI service 8001, DiagnosisWorker, AI_LEAF + Telegram ảnh, API chẩn đoán, gardens/zones | **Giao 09/11** — `WP-07-anh-ai.md`, hạn 14/11 |

Danh sách đầy đủ các gói: `DINH-HUONG.md` mục 7 (bản riêng của nhóm, không commit).

Quy ước chung cho mọi gói:

- Đọc `docs/dac-ta-he-thong.md` (v1.3) — nguồn đúng duy nhất. Thấy đặc tả sai hoặc thiếu thì ghi vào báo cáo, không tự đổi thiết kế.
- Mọi thứ nằm trong thư mục repo; đường dẫn tương đối theo gốc repo; `tools/`, `runtime/`, `logs/`, `.env` không commit (đặc tả §17.2, C22).
- Báo cáo kết quả vào `logs/agent/<WP>-report.md`.
- Không commit, không push trừ khi người giao việc yêu cầu.
