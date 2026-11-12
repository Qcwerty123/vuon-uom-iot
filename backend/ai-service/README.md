# AI service — chẩn đoán lá theo lưới 3×3

Đặc tả: `docs/dac-ta-he-thong.md` §15 (tích hợp §15.6). Chạy trên máy chủ Windows tại **127.0.0.1:8001**, chỉ backend gọi.

## Mô hình (C24 — tiền huấn luyện công khai, không tự huấn luyện)

| Mục | Giá trị |
|---|---|
| `model_version` | `mnv2-pv38-hassan-v1` |
| Tên | Plant Disease Detector — MobileNetV2 fine-tuned (Keras 3) |
| Tác giả | S.M Hassan (Muhammad-Hassan12) |
| Nguồn | <https://huggingface.co/rarfileexe/Plant-Disease-Detector> · mã: <https://github.com/Muhammad-Hassan12/Plant-Disease-Detector> |
| Giấy phép | **MIT** (thẻ model card + file LICENSE của repo GitHub) |
| Dữ liệu huấn luyện | PlantVillage (bản Augmented, ~87 000 ảnh, 38 lớp, 14 loài; có 10 lớp Tomato). Tác giả báo test accuracy 98,75 % trên tập test của dataset |
| Link tải trọng số | <https://huggingface.co/rarfileexe/Plant-Disease-Detector/resolve/main/model_4_mobilenet_finetuned.keras> (24 MB) |
| SHA256 | `08f285aff6d9e1ab88d4d5b2269f1cc977714003755f8553887edbf8691b325f` |
| Đầu vào | RGB 224×224, giá trị 0..255 (mô hình tự chuẩn hóa `x/127.5 − 1` bên trong) |

Toàn bộ thông tin trên nằm trong `model.json` (kèm danh sách 38 lớp đúng thứ tự đầu ra). Trọng số **không commit**, đặt ở `runtime/ai/models/plant-disease-mnv2-pv38.keras`:

```powershell
.\scripts\windows\get-model.ps1        # tải + kiểm SHA256
```

## Cách suy luận

1. Mở ảnh, cắt `crop_box` nếu có (JSON `[x0, y0, x1, y1]` theo pixel; cả 4 số trong 0..1 thì hiểu là tỉ lệ).
2. Chia lưới 3×3, mỗi ô resize 224×224 (`app/preprocess.py`).
3. Chạy mô hình theo lô các ô thuộc `active_tiles` (JSON `[[r, c], ...]`; không gửi = cả 9 ô). Ô ngoài `active_tiles` → `UNKNOWN`, `conf = 0`.
4. **Gộp nhãn:** chỉ lấy xác suất 10 lớp `Tomato___*`, chuẩn hóa lại tổng = 1, cộng theo `label_map.json` về `HEALTHY` / `YELLOW` / `SPOT`.
5. Xác suất lớn nhất < `AI_CONF_UNKNOWN` (0,6) → `UNKNOWN`.
6. `top_label`: ô YELLOW/SPOT có độ tin cậy cao nhất; không có thì HEALTHY cao nhất; không có nữa thì UNKNOWN.

Mỗi ô có thêm `tomato_mass` = tổng xác suất các lớp Tomato **trước** khi chuẩn hóa lại (để đánh giá độ lệch miền). Tùy chọn ngoài đặc tả `AI_MIN_TOMATO_MASS` (mặc định 0 = tắt): đặt ví dụ `0.5` trong `.env` thì ô có `tomato_mass` thấp hơn bị gán UNKNOWN.

## API

```
POST /v1/infer   multipart: image (JPEG), crop_box?, active_tiles?
→ 200 {"model_version":"mnv2-pv38-hassan-v1",
       "tiles":[{"r":0,"c":0,"label":"HEALTHY","conf":0.97,"probs":{"HEALTHY":0.97,"YELLOW":0.02,"SPOT":0.01},
                 "tomato_mass":0.99}, ... 9 ô],
       "top_label":"HEALTHY","top_confidence":0.99,"latency_ms":650}
   400 ảnh/tham số sai · 503 chưa nạp mô hình (backend giữ bản ghi QUEUED)
GET /v1/health → {"status":"ok","model_version":"...","mode":"model"} | {"status":"no_model","reason":"..."}
```

## Chạy

```powershell
.\scripts\windows\start.ps1           # bật PostgreSQL → Mosquitto → AI service → backend (-NoAi để bỏ AI)
.\scripts\windows\status.ps1          # dòng "AI Service" hiện model_version
.\scripts\windows\stop.ps1 -OnlyAi    # chỉ dừng AI service
```

Môi trường: `backend/ai-service/.venv` do `Ensure-Venv` tạo (uv + Python 3.11 trong `tools/`), thư viện trong `requirements.txt` (TensorFlow 2.20 CPU, ~600 MB). Log: `logs/services/ai-service.log` (và `ai-service-console.log`).

Biến `.env`: `AI_URL`, `AI_MODEL_DIR` (mặc định `runtime/ai/models`), `AI_CONF_UNKNOWN`, `AI_MODE`, `AI_MIN_TOMATO_MASS`.

### Chế độ stub (`AI_MODE=stub`) — KHÔNG phải mô hình thật

Dùng để kiểm thử luồng khi chưa có trọng số / TensorFlow. Kết quả tất định theo màu (HSV): ô có ≥ 25 % pixel vàng → YELLOW, ≥ 12 % pixel nâu sẫm → SPOT, ≥ 20 % pixel xanh lá → HEALTHY, còn lại → UNKNOWN. `model_version = stub-v0`. `test-backend.ps1 -Wp 07` tự bật AI ở chế độ này.

## Độ trễ đo được (CPU laptop, Windows 11, TensorFlow 2.20)

| Mục | Kết quả |
|---|---|
| Nạp mô hình khi khởi động | ~19 s |
| Một ảnh 800×600, 9 ô (đo trong `/v1/infer`) | 590–820 ms (mục tiêu < 3 s) |
| Stub | ~40–60 ms |

## Giới hạn (độ lệch miền)

PlantVillage là ảnh **một lá** trên nền đồng màu chụp trong phòng thí nghiệm; ảnh Node 2 là khay cây nhìn từ trên, ESP32-CAM, nhiều lá + đất. Khi thử với ảnh khay vẽ giả: ô chỉ có đất bị gán YELLOW ~0,8 vì bước "chuẩn hóa lại trên các lớp Tomato" ép mọi ô thành cà chua (`tomato_mass` chỉ 0,2–0,5). Cần cấu hình `active_tiles` cho đúng khay và đánh giá trên ảnh thật của nhóm (§15.1) trước khi tin kết quả. Các giai đoạn huấn luyện PlantDoc / ảnh tự chụp (§15.5) là hướng phát triển (`requirements-train.txt`).

## Dữ liệu cho hướng phát triển (tự tải, không commit)

| Nguồn | Đặt vào |
|---|---|
| PlantVillage (các lớp Tomato) | `runtime/ai/data/plantvillage/` |
| PlantDoc (các lớp Tomato) | `runtime/ai/data/plantdoc/` |
| Ảnh tự chụp bằng Node 2 (chia theo khay và ngày, §15.3) | `runtime/ai/data/own/` |
