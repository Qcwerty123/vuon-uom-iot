# Báo cáo WP-07 — Ảnh, AI chẩn đoán lá, cảnh báo AI_LEAF

- **Người làm:** agent Claude (Opus 5.5), trên máy Windows 11 của thành viên (không phải máy chủ demo), nhánh `feat/wp07-ai` (tách từ `dev` @ `256463b`).
- **Thời gian:** 09–10/11/2026.
- **Kết quả:** `test-backend.ps1 -Wp 07` **57/57**; `-Wp 02` **24/24**; `-Wp 03` **35/35**. `status.ps1` báo AI service OK, `model_version=mnv2-pv38-hassan-v1` (mô hình thật).
- **Chưa push.** Chờ người giao việc đồng ý.

## 1. Danh sách file

### AI service (`backend/ai-service/`)

| File | Việc |
|---|---|
| `app/main.py` | FastAPI `POST /v1/infer`, `GET /v1/health`. Nạp mô hình một lần khi khởi động. Gán UNKNOWN, chọn `top_label`. Log ra `logs/services/ai-service.log` |
| `app/preprocess.py` | `crop_box` → lưới 3×3 → resize 224×224; đọc `active_tiles` |
| `app/engine.py` | `KerasEngine` (mô hình thật: lấy lớp Tomato, chuẩn hóa lại, gộp 3 lớp) và `StubEngine` (`AI_MODE=stub`, chấm theo màu) |
| `app/config.py` | Đọc `.env` ở gốc repo (tiến trình WMI không thừa hưởng biến môi trường) |
| `model.json` (mới) | Tên, nguồn, giấy phép, URL, SHA256, 38 lớp theo đúng thứ tự đầu ra |
| `label_map.json` | Sửa khóa `Tomato___healthy` → `Tomato___Healthy` cho khớp mô hình |
| `requirements.txt`, `requirements-train.txt` (mới) | Ghim phiên bản, TensorFlow 2.20 CPU; phần train tách riêng |
| `README.md` | Mô hình, nguồn, giấy phép, link tải, cách chạy, stub, độ trễ, giới hạn |

### Backend (`backend/api/`)

| File | Việc |
|---|---|
| `app/routers/device_api.py` (mới) | `POST /device-api/v1/images` (§8.9) |
| `app/device_auth.py` (mới) | Cache kết quả bcrypt 5 phút theo `(device_code, sha256(secret))` |
| `app/diagnosis.py` (mới) | DiagnosisWorker, luật AI_LEAF, seed luật mặc định |
| `app/routers/diagnoses.py` (mới) | API chẩn đoán §10.9 |
| `app/routers/gardens.py` (mới) | Gardens/Zones §10.4 |
| `app/models.py` | ORM `Diagnosis` |
| `app/alerts.py` | `open_alert(..., defer=True)` + `announce()` để commit trước rồi mới đẩy WS/Telegram; Telegram gửi kèm ảnh, lỗi thì gửi chữ |
| `app/telegram.py` | `send_photo()` (sendPhoto multipart, thử 3 lần, không log URL chứa token) |
| `app/commands.py` | Thêm khóa cấu hình camera `crop_box`, `active_tiles`; ack `capture` lưu thêm `diagnosis_id` số |
| `app/lifecycle.py`, `app/routers/devices.py` | Xóa cache xác thực khi đổi trạng thái / cấp lại khóa |
| `app/ingest.py` | Alias `mark_seen` cho upload HTTP |
| `app/routers/admin.py` | `dashboard/summary`: `latestDiagnosis` trên mỗi camera + `latestDiagnoses` |
| `app/main.py`, `app/config.py`, `requirements.txt` | Gắn router, worker, `/health` có `ai`; thêm `AI_URL`, `AI_CONF_ALERT`; thêm `pillow` |

### Script, test, frontend

| File | Việc |
|---|---|
| `scripts/windows/get-model.ps1` (mới) | Tải trọng số về `runtime/ai/models/`, kiểm SHA256 |
| `scripts/windows/start.ps1` | Bước AI service (sau broker, trước backend), cờ `-NoAi`, cảnh báo khi thiếu trọng số |
| `scripts/windows/stop.ps1` | Tách dừng backend / AI theo dòng lệnh, cờ `-OnlyAi` |
| `scripts/windows/status.ps1` | AI service: gọi `/v1/health`, hiện `model_version`, cảnh báo nếu là stub |
| `scripts/windows/test-backend.ps1` | `-Wp 07`: tạm dừng AI thật → test tự bật stub → xong thì bật lại AI thật |
| `scripts/windows/cam-sim.ps1`, `tests/load/cam_sim.py` (mới) | Camera giả Node 2 |
| `tests/api/smoke_wp07.py` (mới) | Kiểm thử đầu–cuối WP-07 |
| `tests/fixtures/make_images.py` (mới) | Sinh ảnh khay giả; ảnh nằm ở `tests/fixtures/images/`, đã thêm vào `.gitignore` |
| `frontend/src/config.js` | `MOCK.diagnoses = false`; đã build lại `frontend/dist` bằng `tools\node\npm.cmd` |

Tất cả `.ps1` lưu UTF-8 có BOM, CRLF. Không commit `.env`, `tools/`, `runtime/`, `logs/`, `.venv`, ảnh, trọng số.

## 2. Mô hình

| Mục | Giá trị |
|---|---|
| Tên | Plant Disease Detector — MobileNetV2 fine-tuned, Keras 3.10 |
| `model_version` | `mnv2-pv38-hassan-v1` |
| Nguồn | <https://huggingface.co/rarfileexe/Plant-Disease-Detector> (mã: github.com/Muhammad-Hassan12/Plant-Disease-Detector) |
| Giấy phép | **MIT**, đã kiểm cả thẻ model card lẫn file LICENSE trên GitHub |
| Dữ liệu | PlantVillage Augmented, 38 lớp, trong đó có 10 lớp Tomato. Tác giả báo test accuracy 98,75 % |
| Kích thước | 24 MB; SHA256 `08f285ae…b325f` |

**Lý do chọn:**

- Giấy phép rõ ràng. Ứng viên `linkanjarad/mobilenet_v2…` có license "other" nên loại.
- Danh sách lớp được công bố kèm mã. Ứng viên `Daksh159/…` (Apache-2.0) thiếu file `class_names.json`.
- Tiền xử lý nằm sẵn trong mô hình.
- Chạy CPU tốt.

**Độ trễ** (CPU laptop, TensorFlow 2.20):

| Mục | Kết quả |
|---|---|
| Nạp mô hình | ~19 s |
| `/v1/infer` một ảnh 800×600, 9 ô | **590–820 ms** (mục tiêu < 3 s) |
| Đầu–cuối: lệnh capture → ack | 0,9 s |
| Đầu–cuối: lệnh capture → DONE | 1,8 s |
| Stub | ~40–60 ms |

**Stub (`AI_MODE=stub`, `model_version = stub-v0`) KHÔNG phải mô hình thật.** Nó chỉ chấm theo tỉ lệ pixel vàng / nâu / xanh, và chỉ dùng cho kiểm thử.

## 3. Kết quả kiểm thử

```
test-backend.ps1 -Wp 02  === KẾT QUẢ: ĐẠT TẤT CẢ (24 mục) ===
test-backend.ps1 -Wp 03  === KẾT QUẢ: ĐẠT TẤT CẢ (35 mục) ===
test-backend.ps1 -Wp 07  === KẾT QUẢ: ĐẠT TẤT CẢ (57 mục) ===   (logs/tests/smoke-wp07-20261110-005626.txt)
```

WP-07 đã kiểm:

- **Mã lỗi upload:** 401 (sai mật khẩu, thiếu header), 403 (không phải camera), 400 (không phải JPEG, JPEG cụt), 413 (> 300 KB), 201, 429 (ảnh thứ 2 trong 20 s).
- **Trạng thái thiết bị khi upload:** PROVISIONED → ACTIVE, có cập nhật `lastSeenAt`.
- **Xử lý ảnh:** QUEUED → DONE trong 0,8 s, đủ 9 ô, đủ các trường frontend dùng.
- **Quyền:** viewer đọc được danh sách và ảnh (`image/jpeg`, `Cache-Control: private`, đúng byte đã upload). Không token → 401. Viewer review → 403. User không được gán → 404 ở cả chi tiết, ảnh, danh sách.
- **Review:** báo sai thiếu `correctLabel` → 400. CONFIRMED lưu `reviewedAt`, có dòng audit `DIAGNOSIS_REVIEWED`.
- **Camera giả qua MQTT:** lệnh `capture` → EXECUTED, ack có `image_id`. 3 ảnh theo lệnh được miễn giới hạn 20 s.
- **Ảnh bệnh:** ô (0,1) SPOT, ô (1,2) YELLOW, `trigger=command`, có `cmdId`.
- **Luật AI_LEAF:**
  - Đúng 1 cảnh báo AI_LEAF mức WARNING.
  - Context có `diagnosis_id`, danh sách ô, nhãn.
  - Ảnh thứ 4 không mở thêm cảnh báo.
  - WebSocket nhận cả `diagnosis` lẫn `alert`.
- **AI tắt:**
  - Upload vẫn 201 và bản ghi giữ QUEUED.
  - `/health` báo `aiUp=false`.
  - Bật lại AI thì bản ghi tự chuyển DONE.
- **Dashboard:** `dashboard/summary` có chẩn đoán mới nhất của camera.
- **Cấu hình camera:**
  - `active_tiles` được áp dụng: ô ngoài danh sách là UNKNOWN với `conf=0`.
  - `crop_box` sai → 400.
- **Gardens/Zones:**
  - Tạo / sửa vườn và khu được; trùng mã → 409; operator ghi → 403.
  - Viewer chỉ thấy g01; khu của vườn không được gán → 404.
  - Xóa khu còn thiết bị → 409; xóa khu trống → 204.
- **Khóa và thu hồi:** suspend → 403. Rotate-secret: secret cũ 401, secret mới 201 (cache đã bị xóa). Đã thu hồi → 401.

**Đầu–cuối với mô hình thật** (camera giả `cam-0004` chạy bằng `cam-sim.ps1`, gửi đúng API mà nút "Chụp ngay" gọi: `POST /devices/{id}/commands {action:"capture"}`): EXECUTED, ack `img-9`, DONE, `mnv2-pv38-hassan-v1`, 9 ô. Web phục vụ ở `:8000` với bản build `MOCK.diagnoses=false`.

**Chưa kiểm:**

- Chưa nhìn trực tiếp màn Chẩn đoán trên trình duyệt. Chỉ kiểm qua API và bản build, nên cần bấm thử một lần trên web.
- Chưa gửi Telegram thật: `TELEGRAM_BOT_TOKEN=change-me` nên backend tự tắt Telegram. Đường `send_photo` mới viết, chưa chạy với bot thật.
- Cảnh báo AI_LEAF chỉ mở được với stub. Mô hình thật chấm ảnh vẽ giả là HEALTHY (mục 5).

`verify.ps1` sau khi chạy test báo 2 mục FAIL ("CSDL: 2 thiết bị", "dữ liệu còn nguyên"). Lý do: script mong CSDL mới tinh với đúng 2 thiết bị seed. Đây không phải lỗi chức năng; lúc CSDL còn mới thì verify đạt hết.

## 4. Lệch đặc tả và lựa chọn

1. **`image_id` và `diagnosis_id` cùng số.** Mỗi ảnh là một bản ghi `diagnoses`, nên trả `img-<id>` và `dg-<id>` với cùng id. API web dùng id số; tiền tố chỉ dùng cho thiết bị.
2. **Miễn giới hạn 20 s.** Ảnh có `X-Cmd-Id` hợp lệ được miễn: phải là lệnh `capture` của chính thiết bị, phát trong 60 s và chưa có ảnh nào dùng. Ảnh này không tính vào cửa sổ 20 s của ảnh theo lịch, để ảnh lịch đến ngay sau không bị 429.
3. **Định dạng `crop_box` / `active_tiles`.** Đặc tả không ghi định dạng. Đã chọn:
   - `crop_box = [x0, y0, x1, y1]` theo pixel; cả 4 số trong 0..1 thì hiểu là tỉ lệ.
   - `active_tiles = [[r, c], ...]`, cùng dạng với `abnormal_tiles`.
   - Hai khóa này được thêm vào `validate_config` (trước đây cấu hình camera từ chối khóa lạ). ⚠ Firmware Node 2 phải chấp nhận hoặc bỏ qua hai khóa này. Nếu không, theo §8.7 bước 1 thiết bị sẽ ack `invalid`, cấu hình chuyển REJECTED và backend không dùng được crop/active nữa.
4. **WS `diagnosis`.** §10.11 ghi trường `confidence`, còn frontend đọc `topConfidence`. Đã gửi cả hai, kèm `capturedAt`, `status`, `modelVersion`, `trigger`. Bản ghi FAILED không đẩy WS, vì Dashboard coi mọi bản tin `diagnosis` là DONE.
5. **Ngưỡng AI_LEAF.** Ưu tiên `alert_rules.threshold` (seed 0,8). Nếu rỗng thì dùng `AI_CONF_ALERT`. Nhãn trong 3 ảnh có thể khác nhau (YELLOW ở ảnh này, SPOT ở ảnh kia) vẫn tính, vì §15.6 chỉ yêu cầu "label ∈ {YELLOW, SPOT}".
6. **Số lần thử của worker giữ trong RAM.** Bảng `diagnoses` không có cột đếm. Khởi động lại backend thì đếm lại.
7. **Gộp nhãn và "ô đất → UNKNOWN".**
   - §15.2 cho rằng ô chỉ có đất "thường rơi vào UNKNOWN".
   - Thực tế, quy tắc chuẩn hóa lại trên các lớp Tomato (§15.5) ép mọi ô thành cà chua. Ô đất trong ảnh thử bị gán YELLOW 0,65–0,87, trong khi `tomato_mass` chỉ 0,2–0,56.
   - Đã thêm tùy chọn `AI_MIN_TOMATO_MASS`, **mặc định 0 = tắt** để giữ đúng đặc tả.
   - Đề nghị nhóm chốt (C8): bật khoảng 0,5 và/hoặc luôn cấu hình `active_tiles`. Nếu không, khay có ô trống có thể sinh AI_LEAF giả.
8. **JPEG có byte 0x00 sau `FF D9` vẫn được nhận.** Một số frame buffer ESP32 có đệm.
9. **Audit gardens/zones.** Ghi `GARDEN_CHANGED` / `ZONE_CHANGED`, hai tên này chưa có trong danh sách §14.3. `DELETE /zones` cũng trả 409 khi khu còn được luật cảnh báo tham chiếu. Không có API xóa vườn (§10.4 không có), nên vườn thử `smoke-wp07` còn lại trong CSDL (test dùng lại nó).
10. **Không làm trong gói này:**
    - Tác vụ Retention xóa ảnh > 14 ngày (§9.1).
    - Script `export_feedback` (§15.6).
11. **Thiết bị MAINTENANCE vẫn upload được.** §8.9 chỉ chặn SUSPENDED/DECOMMISSIONED.
12. **Lỗi chú thích trong đặc tả.** §7.1 ghi "Upload ảnh qua HTTP POST (§8.7)". Đúng phải là §8.9.

## 5. Lỗi môi trường khi dựng máy và cách xử lý

1. **Service Mosquitto còn sót (quan trọng).**
   - Lỗi: bộ cài Mosquitto đăng ký Windows service `mosquitto` (Automatic). `get-tools.ps1` gọi `Stop-Service` / `sc.exe delete` mà không có quyền Admin, lỗi bị nuốt (`SilentlyContinue`, `| Out-Null`), nhưng script vẫn in "Cài đặt thành công".
   - Hậu quả: sau khi máy khởi động lại, service chiếm `127.0.0.1:1883` (không dynsec, không xác thực). Backend kết nối nhầm vào service đó, cấp phát thiết bị trả 503 "Broker không phản hồi lệnh dynsec".
   - Đã xử lý: được người dùng đồng ý, mở PowerShell nâng quyền (UAC) và chạy `Stop-Service mosquitto; sc.exe delete mosquitto`.
   - **Đề nghị sửa `get-tools.ps1`** (ngoài phạm vi 4.2 nên chưa sửa): kiểm tra quyền Admin, báo ERROR rõ ràng khi gỡ service thất bại. `verify.ps1` nên thêm một mục "không có service mosquitto / chỉ một tiến trình nghe 1883".
2. **Máy tắt đột ngột giữa phiên làm làm hỏng file.**
   - 34 file `.py` của TensorFlow trong `.venv` bị ghi toàn byte 0. Đã xử lý bằng `uv cache clean tensorflow` rồi cài lại.
   - `backend/api/app/alerts.py` cũng bị ghi toàn byte 0. Đã khôi phục từ git và áp lại thay đổi.
   - Đã quét lại toàn bộ mã nguồn, `.venv`, `.env` và `dynamic-security.json`: không còn file hỏng.
3. **`verify.ps1` chỉ đạt trên CSDL mới.** Xem mục 3.

## 6. Việc còn lại để ráp với Node 2 thật

| Thông số | Firmware phải làm |
|---|---|
| URL | `http://192.168.137.1:8000/device-api/v1/images`. Trường `uploadUrl` trong phản hồi cấp phát đã có sẵn |
| Header | `Authorization: Basic base64(device_code:secret)`, `Content-Type: image/jpeg`, `X-Captured-At` (epoch **ms**, sau NTP; thiếu hoặc lệch > 24 h thì server dùng giờ nhận), `X-Trigger: schedule\|command`, `X-Cmd-Id: <cmd_id>` khi chụp theo lệnh |
| Ảnh | JPEG nguyên frame (bắt đầu `FF D8`, kết thúc `FF D9`), **≤ 300 KB**. SVGA 800×600, `jpeg_quality` 12 thường 40–90 KB. Gửi kèm `Content-Length` |
| Phản hồi | 201 `{"image_id":"img-N","diagnosis_id":"dg-N"}`. Ack `executed {"image_id":"img-N"}` |
| Thử lại | Chỉ thử lại khi 429 / 5xx / lỗi mạng (3 lần × 5 s). Lỗi 400/401/403/413 không thử lại: gửi `event upload_failed` |
| Thời hạn | Lệnh hết hạn sau 10 s: phải upload rồi ack trong 10 s, nếu không web hiện TIMEOUT. Thử lại 3 × 5 s có thể vượt hạn này (ảnh vẫn được lưu, ack đến muộn được ghi `late_ack`) |
| Tần suất | Ảnh theo lịch: ≥ 20 s / ảnh. Ảnh theo lệnh có `X-Cmd-Id` thì không giới hạn |
| Cấu hình retain | Chấp nhận hoặc bỏ qua khóa `crop_box`, `active_tiles` (và `capture_interval_min`, `jpeg_quality`, `flash`); không ack `invalid` vì khóa lạ |
| `crop_box` | Đo trên ảnh thật sau khi cố định camera (§7.5), ví dụ `[40, 20, 780, 590]`. Đặt qua `PUT /devices/{id}/config {"params":{"crop_box":[...]}}` |
| `active_tiles` | Liệt kê các ô có cây, ví dụ `[[0,0],[0,1],...]`. Đặt cùng cách |

**Phát sinh sau khi đồng bộ `origin/dev` (10/11):**

- Đặc tả §6.11 thêm cột `diagnoses.lamp_on`: backend ghi trạng thái đèn Node 1 cùng vườn lúc chụp. Cột đã có trong `01_schema.sql`, nhưng **WP-07 chưa ghi cột này**. CSDL dựng trước đó cũng chưa có cột, nên cần `ALTER TABLE diagnoses ADD COLUMN lamp_on BOOLEAN` hoặc `reset-db.ps1`.
- Firmware Node 2 (`config_store.cpp`) bỏ qua khóa lạ, nên `crop_box` / `active_tiles` dùng được.
- Miền giá trị lệch nhau: firmware nhận `jpeg_quality` 8–30 và có `frame_size`, `warmup_frames`; `validate_config` ở backend nhận `jpeg_quality` 10–63 và chưa nhận `frame_size`, `warmup_frames`.

Thử với Node 2 thật:

1. Admin cấp phát `cam-0001` trên web và nạp secret vào `secrets.h`.
2. Bấm "Chụp ngay".
3. Mở màn Chẩn đoán, xem `logs/services/backend.log` (tìm "Nhận ảnh", "Chẩn đoán … DONE").
4. Chạy `status.ps1`.
5. Nếu cần bot Telegram để thử ảnh, đặt `TELEGRAM_BOT_TOKEN` trong `.env`.

## 7. Đoạn cho báo cáo môn học

> **AI chẩn đoán lá.** Do không đủ thời gian tự huấn luyện (C24), hệ thống dùng mô hình MobileNetV2 tiền huấn luyện công khai trên PlantVillage (38 lớp, giấy phép MIT, tác giả S.M Hassan). Ảnh khay 800×600 từ ESP32-CAM được cắt theo `crop_box`, chia lưới 3×3 và đưa từng ô (224×224) qua mô hình. Từ 38 xác suất, dịch vụ chỉ giữ 10 lớp cà chua, chuẩn hóa lại cho tổng bằng 1, rồi cộng gộp về 3 lớp đích theo `label_map.json`: *Khỏe* (Tomato healthy), *Vàng lá* (Yellow Leaf Curl Virus, Leaf Mold, Spider mites, Mosaic virus), *Đốm lá* (Bacterial spot, Early/Late blight, Septoria, Target Spot). Nếu xác suất lớn nhất sau khi gộp nhỏ hơn 0,6 thì ô được gán *Không xác định*. Ô không có cây (cấu hình `active_tiles`) cũng là *Không xác định* với độ tin cậy 0. Backend mở cảnh báo AI_LEAF khi cùng một ô là Vàng lá/Đốm lá với độ tin cậy ≥ 0,8 ở 3 ảnh liên tiếp, có cooldown 30 phút, và gửi Telegram kèm ảnh. Trên CPU laptop, một ảnh 9 ô mất khoảng 0,6–0,8 s.
>
> **Giới hạn.** PlantVillage là ảnh một lá đặt trên nền đồng màu, chụp trong điều kiện phòng thí nghiệm. Ảnh của Node 2 là khay nhiều cây nhìn từ trên xuống, có đất, ánh sáng thay đổi, chất lượng ESP32-CAM thấp. Đây là độ lệch miền lớn. Độ chính xác 98,75 % mà tác giả công bố là trên tập test của chính PlantVillage, không áp dụng cho ảnh của nhóm. Thử nghiệm cho thấy:
>
> - Ô chỉ có đất vẫn bị gán Vàng lá với độ tin cậy cao, vì bước chuẩn hóa lại trên các lớp cà chua "ép" mọi ô thành cà chua (tổng xác suất cà chua ban đầu của ô đất chỉ khoảng 0,2–0,5).
> - Lá vẽ giả có màu vàng bị coi là khỏe.
>
> Vì vậy nhóm cấu hình `active_tiles`, có tùy chọn loại ô có tổng xác suất cà chua thấp, và đánh giá trung thực trên ảnh Node 2 chụp được (accuracy, F1 từng lớp, ma trận nhầm lẫn, §15.1). Hướng phát triển: fine-tune trên PlantDoc và ảnh tự chụp, chia tập theo khay và ngày (§15.3, §15.5).
