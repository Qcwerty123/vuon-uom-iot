# Kiểm thử

Đặc tả: `docs/dac-ta-he-thong.md` §19.

| Thư mục / file | Nội dung |
|---|---|
| `scenarios.md` | Kịch bản và kết quả: chức năng (FT), phi chức năng (NFR), bảo mật (ST) |
| `api/` | Kiểm thử API tự động (theo ngôn ngữ backend) |
| `security/` | Script và bằng chứng cho ST1–ST6 |
| `load/` | Thiết bị mô phỏng: phát triển khi chưa có phần cứng, đo NFR09 |
| `results/` | Số liệu đo thô (CSV), ảnh chụp màn hình, log — dẫn chứng cho báo cáo |

Nguyên tắc: mỗi use case có ít nhất một ca kiểm thử. Mỗi chỉ tiêu phi chức năng ghi đủ **phương pháp đo, dữ liệu, nhận xét**.
