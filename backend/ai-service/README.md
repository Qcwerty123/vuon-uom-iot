# AI service — chẩn đoán lá (chưa có code)

Đặc tả: `docs/dac-ta-he-thong.md` §15.

## Tóm tắt

> **Bản demo (C24, 06/11):** dùng mô hình tiền huấn luyện công khai trên PlantVillage, không tự huấn luyện. Gộp các lớp Tomato về 3 lớp bằng `label_map.json` (sửa tên lớp gốc cho khớp nhãn của mô hình được chọn). Phần huấn luyện bên dưới là hướng phát triển.

- **Đối tượng:** cây giống cà chua.
- **Lớp:** `HEALTHY` (Khỏe mạnh), `YELLOW` (Vàng lá), `SPOT` (Đốm lá); `UNKNOWN` khi độ tin cậy < 0,6.
- **Mô hình:** MobileNetV2 (ImageNet), fine-tune 3 giai đoạn: PlantVillage → PlantDoc → ảnh tự chụp.
- **Đầu vào:** ảnh khay 800×600 cắt lưới 3×3, mỗi ô resize 224×224.
- **API:** `POST /v1/infer` (multipart: `image`, tùy chọn `crop_box`, `active_tiles`), `GET /v1/health`.

## Cấu trúc đề xuất

```
ai-service/
  app/main.py            # FastAPI: /v1/infer, /v1/health
  app/preprocess.py      # cắt lưới, resize, chuẩn hóa
  notebooks/train.ipynb  # huấn luyện + đánh giá (F1, ma trận nhầm lẫn)
  label_map.json         # gộp nhãn gốc về 3 lớp
  requirements.txt
  Dockerfile             # để sau demo; hiện chạy bằng scripts/windows/start.ps1 (cổng 8001, 127.0.0.1)
  # Trọng số và dataset đặt ở runtime/ai/models, runtime/ai/data (KHÔNG commit)
```

## Dữ liệu (tự tải, không commit)

| Nguồn | Cách lấy | Đặt vào |
|---|---|---|
| PlantVillage (các lớp Tomato) | Tìm "PlantVillage dataset" (bản công khai trên GitHub hoặc Kaggle) | `runtime/ai/data/plantvillage/` |
| PlantDoc (các lớp Tomato) | Repo GitHub "PlantDoc-Dataset" | `runtime/ai/data/plantdoc/` |
| Ảnh tự chụp bằng Node 2 | Chụp từ khi Node 2 chạy (không kịp đủ 2 tuần trước demo 18/11), gán nhãn theo ô | `runtime/ai/data/own/` |

Huấn luyện trên Google Colab (GPU miễn phí), tải trọng số về `runtime/ai/models/`. Máy chủ Windows chỉ chạy suy luận.

Ghi rõ nguồn và giấy phép của dataset trong báo cáo (đề bài mục 10).

**Chia tập ảnh tự chụp theo khay và ngày**, không chia ngẫu nhiên (đặc tả §15.3).

## Trọng số mô hình

Lưu bản cuối ở Google Drive hoặc GitHub Release của nhóm, ghi link và `model_version` vào đây:

- `model_version`: `mnv2-tomato-3c-v1`
- Link tải: [__]
