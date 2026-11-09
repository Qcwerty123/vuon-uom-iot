# Nginx (để sau demo)

> Từ 05/11 bản demo không dùng Nginx: backend FastAPI phục vụ trực tiếp ở cổng 8000 (đặc tả §17, C15, C21). Nội dung dưới đây giữ cho bản Docker sau này.

Nginx nằm trong image `web` (thư mục `frontend/`), làm 3 việc:

1. Phục vụ bản build của frontend.
2. Proxy `/api/` và `/device-api/` sang `backend`, proxy `/ws` (WebSocket, cần header `Upgrade`) sang `backend`.
3. HTTPS bằng chứng chỉ tự ký (hoặc `mkcert`) cho IP máy chủ trong LAN; chuyển hướng HTTP → HTTPS.

Header bảo mật cần thêm: `X-Content-Type-Options nosniff`, `X-Frame-Options DENY`, `Content-Security-Policy` cơ bản. Giới hạn kích thước body cho `/device-api/v1/images` khoảng 300 KB.

Lưu ý: nếu Node 2 gửi ảnh qua HTTPS với chứng chỉ tự ký, firmware ESP32-CAM phải nhúng chứng chỉ CA hoặc tạm bỏ kiểm tra chứng chỉ. Phương án đơn giản cho đồ án: để `/device-api/` chạy HTTP trong LAN và ghi rõ vào phần hạn chế của báo cáo.

Đặc tả: `docs/dac-ta-he-thong.md` §14.2, §17.
