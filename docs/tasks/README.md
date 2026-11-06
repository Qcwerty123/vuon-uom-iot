# Giao việc (gói việc WP)

Mỗi file `WP-xx-*.md` là một gói việc tự đủ để một agent hoặc một thành viên làm mà không cần đọc lại cả cuộc thảo luận: bối cảnh, luật, việc cần làm, tiêu chí xong, cách kiểm tra, cách báo cáo. Cuối mỗi file có **prompt** để dán cho agent.

| Gói | Nội dung | Trạng thái |
|---|---|---|
| WP-00 | Triển khai nền tảng trên Windows: công cụ portable, CSDL, broker, script vận hành | **Xong 06/11** — `logs/agent/WP-00-report.md` |
| WP-01 | Thiết bị mô phỏng Node 1 (`tests/load/simulator.py`, `scripts/windows/sim.ps1`) | **Xong 06/11** (đã chạy thử: lệnh, cấu hình, ack ~15 ms) |
| WP-02 | Backend lõi FastAPI (`backend/api`): auth, thiết bị + cấp phát dynsec, ingest, WebSocket | **Xong 06/11** — `test-backend.ps1` đạt 24/24 |
| WP-04 | Frontend React (`frontend/`) | Giao việc 06/11 — `WP-04-frontend.md` |
| WP-N1 | Nối Node 1, Node 2 thật vào hệ thống qua backend | 07/11 — `WP-N1-noi-thiet-bi.md` |

Danh sách đầy đủ các gói: `DINH-HUONG.md` mục 7 (bản riêng của nhóm, không commit).

Quy ước chung cho mọi gói:

- Đọc `docs/dac-ta-he-thong.md` (v1.3) — nguồn đúng duy nhất. Thấy đặc tả sai hoặc thiếu thì ghi vào báo cáo, không tự đổi thiết kế.
- Mọi thứ nằm trong thư mục repo; đường dẫn tương đối theo gốc repo; `tools/`, `runtime/`, `logs/`, `.env` không commit (đặc tả §17.2, C22).
- Báo cáo kết quả vào `logs/agent/<WP>-report.md`.
- Không commit, không push trừ khi người giao việc yêu cầu.
