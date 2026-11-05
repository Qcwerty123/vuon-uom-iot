# AI service — chẩn đoán lá (chưa có code)

Đặc tả: `docs/dac-ta-he-thong.md` §15.

## Tóm tắt

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
  Dockerfile
  models/                # trọng số — KHÔNG commit (đã .gitignore)
  data/                  # dataset — KHÔNG commit
```

## Dữ liệu (tự tải, không commit)

| Nguồn | Cách lấy | Đặt vào |
|---|---|---|
| PlantVillage (các lớp Tomato) | Tìm "PlantVillage dataset" (bản công khai trên GitHub hoặc Kaggle) | `data/plantvillage/` |
| PlantDoc (các lớp Tomato) | Repo GitHub "PlantDoc-Dataset" | `data/plantdoc/` |
| Ảnh tự chụp bằng Node 2 | Chụp hằng ngày ≥ 2 tuần, gán nhãn theo ô | `data/own/` |

Ghi rõ nguồn và giấy phép của dataset trong báo cáo (đề bài mục 10).

**Chia tập ảnh tự chụp theo khay và ngày**, không chia ngẫu nhiên (đặc tả §15.3).

## Trọng số mô hình

Lưu bản cuối ở Google Drive hoặc GitHub Release của nhóm, ghi link và `model_version` vào đây:

- `model_version`: `mnv2-tomato-3c-v1`
- Link tải: [__]
