# WP-07 — Ảnh, AI chẩn đoán lá, cảnh báo AI_LEAF

**Mục tiêu:** Node 2 (ESP32-CAM) gửi ảnh lên backend, AI service chấm 9 ô lá, kết quả hiện trên web. Cùng một ô bất thường 3 ảnh liên tiếp thì sinh cảnh báo AI_LEAF và gửi Telegram kèm ảnh. Đây là bước 8–9 của kịch bản demo (đặc tả §15.7, FT10).

**Hạn:** chạy được đầu–cuối bằng thiết bị giả **14/11**. Ráp với Node 2 thật **15–16/11**. Demo khoảng 18/11.

Node 2 thật do người khác viết firmware, có thể chưa sẵn. Vì vậy gói này phải tự kiểm tra được bằng **camera giả** (mục 4.6).

## 1. Đọc trước

| Nguồn | Nội dung |
|---|---|
| `docs/dac-ta-he-thong.md` §8.9 | Hợp đồng upload ảnh: header, mã lỗi 201/400/401/403/413/429, cache bcrypt |
| §7 (dòng ~635–661) | Node 2: lệnh `capture` → ack `executed {image_id}` / `failed {reason}`; `capture_interval_min` |
| §10.9, §10.11 (WS `diagnosis`), §10.4 | API chẩn đoán, WebSocket, Gardens/Zones |
| §12.4 | Trạng thái QUEUED → RUNNING → DONE/FAILED, thử lại tối đa 2 lần |
| §13.1, §15.6 | Luật AI_LEAF, hợp đồng `/v1/infer` và `/v1/health` |
| §15.2, §15.4, §15.5 (C24) | Gộp nhãn 3 lớp, tiền xử lý 3×3, dùng mô hình tiền huấn luyện PlantVillage |
| §17 | Vận hành Windows: một thư mục, công cụ portable, cổng |
| `database/init/01_schema.sql` | Bảng `diagnoses` (đã có), enum `diag_status`, `alert_rules.type = AI_LEAF` |
| `backend/ai-service/` | `README.md`, `label_map.json`, `requirements.txt` — chưa có code |
| `backend/api/app/` | Mẫu đã có: `ingest.py`, `commands.py` (`on_ack`), `alerts.py` (`open_alert`, Telegram), `jobs.py`, `realtime.py`, `deps.py` (`device_for_view`, `device_for_control`), `errors.py` |
| `docs/tasks/WP-04-report.md`, `frontend/src/` (tìm `diagnos`) | Trường mà frontend đang chờ. `frontend/src/config.js` có cờ `MOCK.diagnoses` |
| `.env.example` | `AI_URL`, `AI_MODEL_DIR`, `AI_CONF_UNKNOWN`, `AI_CONF_ALERT`, `IMAGE_DIR`, `RETENTION_IMAGES_DAYS` |

## 2. Bối cảnh máy chủ

- Windows, chạy trực tiếp, không Docker (C21). Mọi thứ nằm trong thư mục repo (C22).
- Python lấy qua `uv` portable trong `tools/`. Mỗi dịch vụ có `.venv` riêng, tạo bằng `Ensure-Venv` trong `scripts/windows/common.ps1`.
- PostgreSQL chạy cổng **5433**. Backend chạy `0.0.0.0:8000`. AI service chạy **127.0.0.1:8001**, chỉ backend gọi.
- Node 2 gọi `http://192.168.137.1:8000/device-api/v1/images` qua mạng hotspot của máy chủ.
- Script vận hành nằm ở `scripts/windows/`:
  - `start.ps1`, `stop.ps1`, `status.ps1`
  - `test-backend.ps1 -Wp 02|03`
  - `sim.ps1` (Node 1 giả)
  - `reset-db.ps1`

## 2b. Làm trên máy khác (clone mới)

Gói này làm trên máy của một thành viên, không cần phần cứng. Dựng môi trường một lần (PowerShell, Windows 10/11, tại gốc repo, nhánh `dev`):

```powershell
git clone <repo> vuon-uom-iot; cd vuon-uom-iot; git checkout dev
git checkout -b feat/wp07-ai
.\scripts\windows\get-tools.ps1     # tải uv, Python, PostgreSQL, Mosquitto, Node vào tools/ (vài trăm MB)
Copy-Item .env.example .env          # sửa mọi giá trị change-me bằng giá trị tự đặt
.\scripts\windows\setup.ps1         # runtime/, CSDL (cổng 5433), .venv
.\scripts\windows\init-broker.ps1   # tài khoản broker + ACL
.\scripts\windows\start.ps1
.\scripts\windows\verify.ps1        # phải đạt hết
.\scripts\windows\test-backend.ps1 -Wp 02; .\scripts\windows\test-backend.ps1 -Wp 03   # mốc ban đầu: 24/24, 35/35
```

- Không cần `firewall.ps1`, không cần hotspot: mọi thứ chạy ở `127.0.0.1`.
- `.env` là của riêng máy này, không gửi lên đâu. `TELEGRAM_BOT_TOKEN`: để `change-me` (backend tự tắt Telegram), hoặc tự tạo một bot thử qua @BotFather. Không dùng bot chung của nhóm.
- Lỗi khi dựng môi trường (script, cổng, quyền) ghi vào báo cáo kèm cách đã xử lý; không sửa logic trong `scripts/windows/` ngoài phần mục 4.2 yêu cầu.
- Bàn giao: commit lên nhánh `feat/wp07-ai`, push, người giữ máy chủ sẽ merge vào `dev`. Trước khi commit chạy `git status`, bảo đảm không có `.env`, `tools/`, `runtime/`, `logs/`, `.venv`, ảnh, trọng số. Báo cáo `logs/agent/WP-07-report.md` nằm trong `logs/` (không commit) — bản sao chép vào `docs/tasks/WP-07-report.md` để commit cùng.

## 3. Luật

1. **Không đổi thiết kế.** Làm theo đặc tả. Nếu thấy đặc tả sai hoặc thiếu, ghi vào báo cáo mục "Lệch đặc tả" và chọn cách ít thay đổi nhất.
2. **Không làm hỏng cái đang chạy.** `test-backend.ps1 -Wp 02` (24/24) và `-Wp 03` (35/35) phải vẫn đạt.
3. **Ghi trước, phát sau.** Mọi bản ghi phải commit vào CSDL TRƯỚC khi publish MQTT hoặc đẩy WS. Thiết bị ack trong khoảng 15 ms, nên làm ngược sẽ gây race (lỗi đã gặp ở WP-03).
4. **Đường dẫn tương đối theo gốc repo:**
   - Ảnh lưu ở `runtime/images/<device_code>/<yyyy-mm-dd>/<id>.jpg`.
   - Trọng số mô hình ở `runtime/ai/models/`.
   - Log ở `logs/services/` (`ai-service.log`).
   - Không ghi file ra ngoài thư mục repo.
5. **Không commit:** `runtime/`, `logs/`, `tools/`, `.env`, `.venv`, trọng số, ảnh. Ghi link tải trọng số vào `backend/ai-service/README.md`.
6. **Bảo mật:**
   - Ảnh chỉ trả qua API có kiểm tra quyền, không có URL tĩnh công khai.
   - Không log secret hoặc header Authorization.
   - Token Telegram chỉ đọc từ `.env`.
7. **Script PowerShell:** UTF-8 **có BOM**, CRLF. Tiến trình nền khởi động bằng `Start-StandaloneProcess` (WMI), không dùng `Start-Process` trực tiếp.
8. **Tên trường API** theo camelCase (`to_camel` trong `schemas.py`). Lỗi trả `{code, message, details, traceId}` qua `ApiError`.
9. Chỉ commit trên nhánh `feat/wp07-ai`; push khi người giao việc đồng ý; không merge vào `dev`/`main`.

## 4. Việc cần làm

### 4.1. AI service (`backend/ai-service/`)

- `app/main.py` (FastAPI) với hai endpoint:
  - `POST /v1/infer` nhận multipart `image`, `crop_box?`, `active_tiles?`.
  - `GET /v1/health`.
  - Kết quả trả về đúng như §15.6.
- `app/preprocess.py`: cắt `crop_box` nếu có → lưới 3×3 → resize 224×224 → chuẩn hóa theo mô hình.
- **Mô hình (C24):** tự chọn một mô hình tiền huấn luyện công khai trên PlantVillage (38 lớp, có các lớp Tomato).
  - Ưu tiên chạy CPU nhẹ trên Windows: PyTorch CPU, ONNX Runtime hoặc TensorFlow CPU đều được.
  - Được sửa `requirements.txt`, miễn cài được bằng `uv` trên Python 3.11 Windows.
  - Ghi vào báo cáo và README: tên mô hình, nguồn, giấy phép, `model_version`.
- **Gộp nhãn:** chỉ lấy xác suất các lớp `Tomato___*`, chuẩn hóa lại tổng = 1, rồi gộp về HEALTHY/YELLOW/SPOT theo `label_map.json`.
  - Sửa khóa trong `label_map.json` cho khớp tên lớp thật của mô hình.
  - Nếu xác suất lớn nhất < `AI_CONF_UNKNOWN` (0,6) thì gán `UNKNOWN`.
  - Ô nằm ngoài `active_tiles` cũng gán `UNKNOWN`, với `conf` = 0.
- `top_label`, `top_confidence`: lấy ô bất thường (YELLOW/SPOT) có độ tin cậy cao nhất. Nếu không có ô bất thường thì lấy HEALTHY có độ tin cậy cao nhất.
- Tải mô hình **một lần** khi khởi động. Nếu thiếu trọng số, `/v1/health` trả `{"status":"no_model"}`.
- **Chế độ `stub`** (biến môi trường `AI_MODE=stub`) để kiểm thử khi chưa có mô hình:
  - Kết quả tất định theo màu: ô có tỉ lệ pixel vàng hoặc nâu cao thì là YELLOW hoặc SPOT, ngược lại là HEALTHY.
  - `model_version` = `stub-v0`.
  - Ghi rõ trong báo cáo rằng đây không phải mô hình thật.
- `scripts/windows/get-model.ps1` (hoặc `.py`): tải trọng số về `runtime/ai/models/`, có kiểm tra SHA256 nếu nguồn cung cấp.
- Mục tiêu độ trễ: một ảnh 9 ô < 3 s trên CPU.

### 4.2. Vận hành AI service

- `start.ps1`: thêm bước khởi động AI service.
  - Dùng `Ensure-Venv backend/ai-service`, `uvicorn app.main:app --host 127.0.0.1 --port 8001`, log ra `logs/services/ai-service.log`.
  - Khởi động sau broker, trước backend.
  - Thêm cờ `-NoAi` để bỏ qua bước này.
- `stop.ps1`: dừng AI service, tìm tiến trình theo dòng lệnh.
- `status.ps1`: hiện trạng thái AI service (gọi `/v1/health`).
- Backend phải chạy được khi AI service tắt: diagnosis ở lại QUEUED, khi AI lên lại thì tự xử lý.

### 4.3. Backend — nhận ảnh (`/device-api/v1/images`, §8.9)

Router mới, ví dụ `app/routers/device_api.py`. Endpoint nằm ngoài `/api/v1` và không dùng JWT.

- **Xác thực:** Basic `device_code:secret`, so bcrypt với `credential_hash`.
  - Cache kết quả 5 phút theo `(device_code, sha256(secret))`.
  - Xóa cache khi thiết bị đổi trạng thái (suspend, resume, decommission, rotate-secret).
- **Mã lỗi:**

  | Tình huống | Mã |
  |---|---|
  | Sai thông tin xác thực | 401 |
  | Không phải loại CAMERA, hoặc đang SUSPENDED/DECOMMISSIONED | 403 |
  | Body > 300 KB (kiểm `Content-Length` trước, rồi kiểm kích thước thật) | 413 |
  | Không bắt đầu bằng `FF D8` hoặc không kết thúc bằng `FF D9`, hoặc PIL không mở được | 400 |
  | Quá 1 ảnh / 20 s / thiết bị | 429 |

  Lệnh `capture` có `X-Cmd-Id` hợp lệ thì được miễn giới hạn tần suất. Ghi lựa chọn này vào báo cáo.
- **Header:**
  - `X-Captured-At` tính bằng ms epoch. Nếu thiếu hoặc lệch quá 24 h thì dùng giờ server và ghi cờ vào log.
  - `X-Trigger` là `schedule` hoặc `command`.
  - `X-Cmd-Id` là UUID, tùy chọn.
- **Lưu file:** ghi ra file tạm rồi đổi tên (atomic). Tính sha256. Tạo bản ghi `diagnoses` ở trạng thái QUEUED. Commit.
- **Trả 201** `{"image_id":"img-<id>","diagnosis_id":"dg-<id>"}`.
  - Phía API web dùng `id` số nguyên. Tiền tố chỉ dùng cho thiết bị.
  - Ghi quy ước này vào báo cáo.
- Cập nhật `last_seen_at` của camera. Nếu camera đang PROVISIONED hoặc OFFLINE thì chuyển ACTIVE, như ingest.
- **Ack lệnh `capture`:** firmware gửi ack `executed {image_id}` qua MQTT sau khi upload. `commands.on_ack` lưu `image_id` vào kết quả lệnh. Kiểm tra lại đoạn `action == "capture"` trong `commands.py`.

### 4.4. Backend — DiagnosisWorker và luật AI_LEAF

- Thêm `DiagnosisWorker` vào `jobs.py`, hoặc viết module `diagnosis.py`.
  - Lấy bản ghi QUEUED theo thứ tự `captured_at` → chuyển RUNNING (commit) → gọi `AI_URL/v1/infer` (timeout 30 s).
  - Thành công: lưu `tiles`, `top_label`, `top_confidence`, `abnormal_tiles`, `model_version`, chuyển DONE (commit) → đẩy WS → áp luật.
  - Lỗi: thử lại tối đa 2 lần, sau đó FAILED.
  - AI service không kết nối được: giữ QUEUED và chờ, không tính vào số lần thử.
- Khi backend khởi động: đưa các bản ghi RUNNING về QUEUED rồi quét lại.
- Truyền `crop_box` và `active_tiles` từ cấu hình camera nếu có (bảng `device_configs`, xem §7 và §9). Không có thì bỏ qua.
- **Luật AI_LEAF (§15.6):**
  - Với mỗi camera, xét 3 bản ghi DONE gần nhất.
  - Ô `(r,c)` có label ∈ {YELLOW, SPOT} và `conf ≥ AI_CONF_ALERT` (0,8) ở cả 3 ảnh → `open_alert` loại AI_LEAF, mức WARNING.
  - Context của cảnh báo gồm `diagnosis_id`, danh sách ô, nhãn.
  - Dùng cooldown như các luật khác. Lấy rule AI_LEAF trong `alert_rules`; nếu chưa có thì seed một rule mặc định.
- **Telegram kèm ảnh:**
  - Thêm `telegram.send_photo(chat_id, path, caption)` dùng `sendPhoto` multipart, có retry như `send`.
  - Lỗi mạng (Telegram đang bị chặn trên mạng máy chủ, phải bật WARP) không được làm hỏng worker.
- **WS:** đẩy `{"type":"diagnosis", ...}` cho người đã subscribe thiết bị. Gửi đủ trường mà frontend cần (mục 4.5), tối thiểu theo §10.11.

### 4.5. Backend — API chẩn đoán (§10.9) khớp frontend

Prefix `/api/v1`, quyền dùng `device_for_view` và `device_for_control` có sẵn. Thiết bị không được gán trả 404 (C6).

| Method | Đường dẫn | Ghi chú |
|---|---|---|
| GET | `/devices/{id}/diagnoses?from=&to=&label=&page=&size=` | Trả `{items,page,size,total}`, mới nhất trước |
| GET | `/diagnoses/{id}` | Một bản ghi đầy đủ |
| GET | `/diagnoses/{id}/image` | `image/jpeg`, `Cache-Control: private`, kiểm quyền mỗi lần |
| POST | `/diagnoses/{id}/review` | Quyền CONTROL. Body `{verdict: CONFIRMED\|REJECTED, correctLabel?, note?}`. Ghi audit |

**Trường của một bản ghi** (khớp `frontend/src`; mở code để kiểm tra lại tên trường): `id, deviceId, capturedAt, status, topLabel, topConfidence, abnormalTiles, tiles[{r,c,label,conf}], modelVersion, trigger, cmdId, reviewVerdict, correctLabel, reviewedAt`.

Thêm vào `dashboard/summary`: ảnh hoặc chẩn đoán mới nhất của mỗi camera (§10.10).

**Gardens/Zones (§10.4):**

- `GET/POST /gardens`, `GET/POST /gardens/{id}/zones`, `PATCH/DELETE /zones/{id}`.
- ADMIN được ghi. Người đã đăng nhập đọc được các vườn/khu có thiết bị được gán (ADMIN thấy tất cả).
- Không xóa được khu vực khi còn thiết bị (trả 409).

Xong phần này thì đặt `MOCK.diagnoses = false` trong `frontend/src/config.js`, chạy `tools\node\npm.cmd run build` trong `frontend/`, và kiểm tra màn Chẩn đoán với dữ liệu thật. Không sửa giao diện ngoài cờ này; chỗ lệch ghi vào báo cáo.

### 4.6. Camera giả và kiểm thử

- **Camera giả:** mở rộng `tests/load/simulator.py` hoặc viết `tests/load/cam_sim.py`, kèm `scripts/windows/cam-sim.ps1`.
  - Đăng nhập MQTT như Node 2.
  - Nhận lệnh `capture` → upload một JPEG trong `tests/fixtures/images/` → ack `executed {image_id}`.
  - Có chế độ chụp theo chu kỳ.
  - Ảnh mẫu: tự tạo bằng PIL (khay 3×3, có ô vàng hoặc đốm) hoặc lấy ảnh có giấy phép tự do. Mỗi ảnh < 300 KB.
- **`tests/api/smoke_wp07.py`**, chạy bằng `test-backend.ps1 -Wp 07`. Tối thiểu kiểm:
  - Upload: 201; sai mật khẩu 401; thiết bị không phải camera 403; body không phải JPEG 400; ảnh > 300 KB 413; 2 ảnh trong 20 s 429; thiết bị bị suspend 403.
  - QUEUED → DONE trong ≤ 10 s (cho phép chạy `AI_MODE=stub`). Có 9 ô.
  - 3 ảnh bất thường cùng ô → có đúng một cảnh báo AI_LEAF; ảnh thứ 4 không mở thêm (cooldown).
  - Quyền: viewer GET được, review bị 403; user không được gán bị 404; ảnh không có token bị 401.
  - Review CONFIRMED lưu `reviewedAt` và có dòng audit.
  - Lệnh `capture` → ack có `image_id`.
  - AI service tắt → bản ghi giữ QUEUED; bật lại → DONE.
  - Gardens/zones: tạo, đọc, xóa khi còn thiết bị bị 409.
  - Không làm hỏng: chạy lại `-Wp 02` và `-Wp 03`.

## 5. Tiêu chí xong

1. `start.ps1` bật cả AI service. `status.ps1` báo AI service OK cùng `model_version` của mô hình thật (không phải stub).
2. `test-backend.ps1 -Wp 07` đạt toàn bộ. `-Wp 02` và `-Wp 03` vẫn đạt.
3. Đầu–cuối bằng camera giả:
   - Bấm "Chụp ngay" trên web → ảnh hiện ở màn Chẩn đoán kèm 9 ô.
   - Chụp 3 lần ảnh có ô bệnh → có cảnh báo AI_LEAF trên web.
   - Có tin Telegram kèm ảnh, nếu mạng máy chủ gửi được Telegram.
4. Frontend chạy với `MOCK.diagnoses=false`.
5. `backend/ai-service/README.md` ghi đủ:
   - Mô hình, nguồn, giấy phép, `model_version`, link tải trọng số.
   - Cách chạy, chế độ stub.
   - Độ trễ đo được.
6. Báo cáo `logs/agent/WP-07-report.md` đã viết (mục 6).

## 6. Báo cáo

Ghi vào `logs/agent/WP-07-report.md`:

- Danh sách file thêm hoặc sửa.
- Mô hình đã chọn (nguồn, giấy phép), độ trễ mỗi ảnh.
- Kết quả các bài test (dán tóm tắt).
- Lệch đặc tả và lý do.
- Việc còn lại để ráp với Node 2 thật: thông số firmware cần khớp (header, kích thước ảnh, `crop_box`, `active_tiles`).
- Đoạn ngắn cho báo cáo môn học: cách AI service gộp nhãn, ngưỡng UNKNOWN, giới hạn của mô hình PlantVillage trên ảnh thật (độ lệch miền).

## Prompt cho agent

```
Bạn là agent backend/AI làm việc trong repo vuon-uom-iot (vừa clone, nhánh dev) trên máy Windows của một thành viên nhóm, không phải máy chủ demo (chạy trực tiếp, không Docker; mọi thứ nằm trong thư mục repo). Nhiệm vụ: gói việc WP-07 — nhận ảnh từ Node 2 (ESP32-CAM), AI service chẩn đoán lá theo lưới 3×3, API chẩn đoán cho web, luật cảnh báo AI_LEAF kèm Telegram.

Đọc kỹ docs/tasks/WP-07-anh-ai.md và làm đúng theo đó: mục 1 (đọc trước), 3 (luật), 4 (việc cần làm, theo thứ tự 4.1 → 4.6), 5 (tiêu chí xong), 6 (báo cáo). Nguồn đúng duy nhất là docs/dac-ta-he-thong.md (v1.3); thấy sai hoặc thiếu thì ghi vào báo cáo, không tự đổi thiết kế.

Điểm bắt buộc:
- Dùng công cụ portable trong tools/ qua scripts/windows/common.ps1 (Ensure-Venv, Start-StandaloneProcess, Get-ToolPath). Không cài Python/Node ra ngoài, không Docker.
- AI service ở backend/ai-service, chạy 127.0.0.1:8001; mô hình tiền huấn luyện công khai trên PlantVillage (tự chọn, chạy CPU, ghi rõ nguồn và giấy phép); trọng số đặt ở runtime/ai/models; có chế độ AI_MODE=stub để kiểm thử khi chưa có mô hình.
- Backend: commit CSDL trước rồi mới publish MQTT/đẩy WS. Không làm hỏng test cũ: scripts/windows/test-backend.ps1 -Wp 02 và -Wp 03 phải vẫn đạt.
- Viết camera giả và tests/api/smoke_wp07.py (chạy bằng test-backend.ps1 -Wp 07) vì Node 2 thật có thể chưa sẵn.
- Script .ps1 lưu UTF-8 có BOM. Ảnh, trọng số, log, .env, runtime/, tools/ không commit. Không log secret.
- Xong phần API thì đặt MOCK.diagnoses=false trong frontend/src/config.js và build lại frontend bằng tools\node\npm.cmd.
- Máy này là máy mới clone: dựng môi trường theo mục 2b trước khi code (get-tools, .env, setup, init-broker, start, verify, test -Wp 02/03). Không cần phần cứng, không cần hotspot.
- Làm trên nhánh feat/wp07-ai. Được commit trên nhánh này; chỉ push khi tôi đồng ý. Không merge vào dev/main.

Làm từng phần, chạy thử sau mỗi phần. Khi xong, viết logs/agent/WP-07-report.md theo mục 6 (chép một bản sang docs/tasks/WP-07-report.md) và tóm tắt cho tôi: đã làm gì, test đạt bao nhiêu, mô hình nào, còn gì để ráp với Node 2 thật.
```
