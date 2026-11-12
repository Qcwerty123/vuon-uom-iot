# AI service — chẩn đoán lá mồng tơi

Đặc tả gốc: `docs/dac-ta-he-thong.md` §15 (xem mục "Lệch đặc tả" bên dưới: đặc tả vẫn ghi cà chua/MobileNetV2).

## Luồng xử lý

```
ảnh khay (Node 2, 800×600)
  └─ crop_box? ──► cắt vùng khay
       └─ MobileSAM: tìm điểm gợi ý từ màu lá (HSV) + distance transform → SamPredictor tinh chỉnh từng lá
            └─ mỗi lá: cắt theo mask, nền ngoài lá xám 128, đệm vuông, resize 224×224, chuẩn hóa ImageNet, RGB
                 └─ ConvNeXt-Tiny (ONNX): HEALTHY / SPOT / YELLOW / PEST
                      └─ gộp PEST vào SPOT; xác suất lớn nhất < AI_CONF_UNKNOWN (0,6) → UNKNOWN
                           └─ lá gán vào ô 3×3 chứa tâm của nó (active_tiles lọc ô)
                                └─ nhãn ô: lá bệnh (SPOT/YELLOW) conf cao nhất; không có thì lá HEALTHY kém chắc nhất; không có lá = UNKNOWN, conf 0
```

API (chỉ nghe `127.0.0.1:8001`, chỉ backend gọi):

- `POST /v1/infer` — multipart: `image`, `crop_box?` (JSON `[x0,y0,x1,y1]`, pixel hoặc tỉ lệ 0..1), `active_tiles?` (JSON `[[r,c],...]`).
  Trả về đúng §15.6 (`model_version`, `tiles` đủ 9 ô, `top_label`, `top_confidence`, `latency_ms`), **thêm 2 trường**: `n_leaves` trong mỗi ô và mảng `leaves` (`tile [r,c]`, `label`, `conf`, `bbox [x,y,w,h]` theo pixel ảnh gốc, `polygon` chuẩn hóa 0–1 theo vùng đã cắt).
  Lỗi: 400 (ảnh/`crop_box`/`active_tiles` sai), 413 (> 5 MB), 503 (thiếu mô hình; thông báo nêu file nào thiếu và đặt ở đâu).
- `GET /v1/health` — `{"status":"ok","model_version":...}` hoặc `{"status":"no_model","model_version":null}`. Thiếu file thì service vẫn khởi động.
- Log: `logs/services/ai-service.log` (độ trễ, số lá; không ghi nội dung ảnh).

## Cài đặt và chạy

```powershell
.\scripts\windows\start.ps1        # Ensure-Venv cài backend/ai-service/requirements.txt rồi chạy uvicorn app.main:app
```

`requirements.txt` có dòng `mobile_sam @ git+https://github.com/ChaoningZhang/MobileSAM.git`; uv xử lý được (đã thử), **cần `git` trong PATH và mạng** lần cài đầu (torch + torchvision + timm khoảng vài trăm MB). Nếu mạng/git bị chặn, cài tay: `.venv\Scripts\python.exe -m pip install "git+https://github.com/ChaoningZhang/MobileSAM.git"` (hoặc `uv pip install --python .venv\Scripts\python.exe ...`). Chạy tay: `cd backend/ai-service; .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001`.

Biến `.env`: `AI_URL`, `AI_MODEL_DIR` (mặc định `runtime/ai/models`), `AI_CONF_UNKNOWN` (0,6), `AI_MODEL_VERSION` (mặc định `convnext-t-leaf-v1`), `AI_MODE=stub` (xem dưới). `AI_CONF_ALERT` (0,6) **do backend dùng**, service không đọc.

## File mô hình (KHÔNG commit) — đặt ở `runtime/ai/models/`

| File | Nguồn |
|---|---|
| `mobile_sam.pt` (40,7 MB) | https://raw.githubusercontent.com/ChaoningZhang/MobileSAM/master/weights/mobile_sam.pt |
| `leaf.onnx` | Train trên Kaggle: ConvNeXt-Tiny (`convnext_tiny.fb_in22k_ft_in1k`, timm), đầu vào `1×3×224×224` chuẩn hóa ImageNet, đầu ra logits 4 lớp theo thứ tự **HEALTHY, SPOT, YELLOW, PEST**. Tiền xử lý lúc train phải giống `crop_leaf()` trong `app/leaf_pipeline.py` (cắt theo mask, nền xám 128, đệm vuông, resize 224, KHÔNG cắt giữa). |
| `model_meta.json` (tùy chọn) | `{"classes": [...], "input": [224,224], "mean": [...], "std": [...]}`. Có thì thứ tự lớp đọc từ đây; số lớp phải bằng đầu ra ONNX, sai thì service báo lỗi rõ ràng (health `no_model`, lý do ở trường `reason`). |

## Thử bằng mô hình giả (khi chưa có leaf.onnx thật)

```powershell
.venv\Scripts\python.exe scripts\make_dummy_model.py <thư_mục_đích>   # tạo leaf.onnx NGẪU NHIÊN
```

Nhãn của mô hình giả vô nghĩa, **không dùng cho demo**. Script từ chối ghi đè nếu đích đã có `leaf.onnx`. Test tự động (dùng mô hình giả trong thư mục tạm, chỉ kiểm tra luồng):

```powershell
.venv\Scripts\python.exe tests\test_infer.py     # hoặc pytest tests
```

Xem kết quả bằng mắt: `.venv\Scripts\python.exe scripts\viz_infer.py khay.jpg ket_qua.jpg [--url http://127.0.0.1:8001/v1/infer]` (vẽ viền + nhãn từng lá; lưu ảnh kết quả vào `runtime/`, không commit).

`AI_MODE=stub`: bộ chấm theo màu (`model_version=stub-v0`), KHÔNG phải mô hình thật; `test-backend.ps1 -Wp 07` dùng chế độ này. Stub không tách lá (`leaves` rỗng).

## Chất lượng mô hình

Đo trên tập test 451 ảnh lá của dataset (lá trên nền xám, mức tốt nhất, **không phải ảnh Node 2**):

| | accuracy | macro-F1 | HEALTHY | SPOT | YELLOW | PEST |
|---|---|---|---|---|---|---|
| 4 lớp | 0,749 | 0,704 | 0,859 | 0,711 | 0,684 | 0,560 |
| 3 lớp (PEST→SPOT) | 0,840 | 0,798 | 0,859 | 0,850 | 0,684 | — |

(F1 theo lớp.) Nhầm lẫn chủ yếu SPOT↔PEST, hai lớp được gộp khi chạy thật.

Theo ngưỡng độ tin cậy (từng ảnh; nhãn bệnh = SPOT/YELLOW gộp):

| Ngưỡng | Phủ | Đúng/phủ | Báo nhầm lá khỏe | Bỏ sót lá bệnh |
|---|---|---|---|---|
| 0,5 | 93 % | 85,5 % | 15,7 % | 12,4 % |
| **0,6 (đã chọn)** | 75 % | 90,3 % | 8,1 % | 24,9 % |
| 0,8 | 37 % | 94,6 % | 2,9 % | 49,4 % |

Hạn chế: ảnh Node 2 mờ hơn và lá chồng nhau nên điểm thực tế sẽ thấp hơn; các lá cùng một cây có thể nằm cả ở train lẫn test (rò rỉ); lớp YELLOW chỉ 240 ảnh (36 ảnh test). **Điểm báo cáo cuối phải đo trên ảnh Node 2 của nhóm.**

Tốc độ đo trên máy này (CPU, Windows 11): ảnh khay giả 800×600 có 9 lá rời → ~2,1 s mỗi ảnh (`latency_ms` 2064–2093), nạp mô hình khi khởi động vài giây.

## Giới hạn đã biết

- Lọc lá theo màu (hue 15–95): lá nâu/héo nhiều có thể bị bỏ sót.
- Lá nhỏ hơn 0,4 % diện tích ảnh bị bỏ (`min_frac`); tối đa 30 lá (lấy 30 lá lớn nhất).
- Lá chồng nhau: lá bị che chỉ có khung phần nhìn thấy (thử trên ảnh giả: 9/9 lá rời, 7/8 lá chồng).
- `SamAutomaticMaskGenerator` đã bỏ: chậm (44 s/ảnh, CPU 2 nhân) và gộp nhiều lá thành một mask.
- Điểm âm cho SAM chỉ lấy tối đa 3 lá lân cận; phải giữ vùng liền lớn nhất của mask.
- Mô hình chỉ học mồng tơi; ảnh không có lá cho 9 ô UNKNOWN, conf 0.

## Lệch đặc tả (không sửa đặc tả)

§15 vẫn ghi cà chua / MobileNetV2 / PlantVillage, 3 lớp huấn luyện, ngưỡng cảnh báo 0,8. Hiện là: mồng tơi, MobileSAM + ConvNeXt-Tiny, 4 lớp gộp thành 3, ngưỡng UNKNOWN và AI_LEAF đều 0,6. `crop_box` giữ quy ước hiện có của backend: `[x0,y0,x1,y1]`.

## Nguồn và giấy phép

- Dữ liệu huấn luyện: IDDMSLD, Sayeem và cộng sự, Mendeley Data V2, doi:10.17632/sy69db2nz5.2 — CC BY 4.0.
- MobileSAM: https://github.com/ChaoningZhang/MobileSAM — Apache-2.0 (đã kiểm tra file LICENSE).
- ConvNeXt: qua thư viện timm (https://github.com/huggingface/pytorch-image-models, Apache-2.0); trọng số khởi tạo `convnext_tiny.fb_in22k_ft_in1k`.
- Tệp `model.json`, `requirements-train.txt` và `scripts/windows/get-model.ps1` là của luồng Keras/PlantVillage cũ, không còn dùng.
