# Hướng dẫn sử dụng repo khởi đầu

Gói này là **repo khởi đầu** của đồ án. Đã có: tài liệu thiết kế, sketch chẩn đoán phần cứng, firmware Node 1 (chưa thử trên mạch), schema CSDL, các file cấu hình mẫu. Chưa có: firmware Node 2, backend, frontend, AI, script triển khai Windows — mỗi thư mục có `README.md` ghi rõ cần làm gì.

> **Từ 05/11:** hệ thống chạy trực tiếp trên một máy Windows, không Docker, mọi thứ gói trong thư mục repo; demo khoảng 18/11 (đặc tả v1.3, C21–C23).

---

## 1. Đưa repo lên GitHub (Đã làm)

Đề yêu cầu mã nguồn quản lý trên GitHub của nhóm, mỗi thành viên dùng tài khoản riêng, lịch sử commit thể hiện quá trình làm việc.

1. **Giải nén** file zip, được thư mục `vuon-uom-iot/`.
2. **Tạo repository trống** trên GitHub:
   - Tên gợi ý: `vuon-uom-iot`.
   - Chọn **Private**.
   - **Không** tick "Add a README", ".gitignore" hay "license" (repo đã có sẵn).
3. **Đặt thông tin tác giả** trên máy mình (mỗi người làm một lần, dùng đúng tài khoản GitHub của mình):

   ```bash
   git config --global user.name  "ten-github-cua-ban"
   git config --global user.email "email-dang-ky-github@..."
   ```

4. **Khởi tạo và đẩy lên** (chạy trong thư mục `vuon-uom-iot/`):

   ```bash
   git init -b main
   git add .
   git status                       # kiểm tra KHÔNG có .env hay secrets.h trong danh sách
   git commit -m "chore: khởi tạo repo theo cấu trúc đề bài"
   git remote add origin https://github.com/<tai-khoan-hoac-to-chuc>/vuon-uom-iot.git
   git push -u origin main
   git checkout -b dev
   git push -u origin dev
   ```

5. Trên GitHub, vào **Settings → Collaborators**: mời 3 thành viên còn lại và **giảng viên** (đề bắt buộc cấp quyền cho giảng viên nếu repo private).
6. **Settings → Code security**: bật **Secret scanning** (nếu tài khoản cho phép) để được cảnh báo khi lỡ đẩy mật khẩu.
7. **Settings → Branches**: thêm quy tắc bảo vệ nhánh `main`, bắt buộc merge qua Pull Request.

## 2. Các thành viên còn lại

```bash
git clone https://github.com/<tai-khoan-hoac-to-chuc>/vuon-uom-iot.git
cd vuon-uom-iot
git checkout dev
cp .env.example .env          # sửa giá trị trong .env, không commit file này
```

## 3. Quy trình làm việc hằng ngày

1. Lấy code mới nhất: `git checkout dev && git pull`.
2. Tạo nhánh cho việc mình làm: `git checkout -b feat/firmware-node1-telemetry`.
3. Commit nhỏ, rõ nghĩa, bằng tài khoản của mình:
   - `feat(firmware): đọc 2 cảm biến đất và lọc trung vị`
   - `fix(api): kiểm tra quyền khi gửi lệnh`
   - `docs: cập nhật ERD`
   - `test: thêm kịch bản ST3 thu hồi thiết bị`
4. **Trước mỗi lần commit**: chạy `git status`, chắc chắn không có `.env`, `secrets.h`, file khóa, ảnh có người.
5. Đẩy nhánh lên và mở **Pull Request vào `dev`**, nhờ một người khác review.
6. Khi `dev` ổn định (trước buổi thuyết trình, trước hạn nộp), mở PR từ `dev` vào `main`.
7. **Trước 24/11/2026**: tạo tag phát hành cuối cùng.

   ```bash
   git checkout main && git pull
   git tag -a v1.0.0 -m "Bản nộp đồ án"
   git push origin v1.0.0
   ```

   Rồi vào GitHub → **Releases → Draft a new release** → chọn tag `v1.0.0`.

## 4. Việc tiếp theo (từ 05/11, 2–3 người)

Lộ trình theo ngày: đặc tả §21.2 (N0 → N5, demo khoảng 18/11).

| Vai | Việc làm ngay | Tài liệu |
|---|---|---|
| **Phần cứng, firmware** | Lắp Node 1 theo từng công đoạn, nghiệm thu bằng `firmware/test-hardware`, ghi `hardware/nhat-ky-lap-dat.md`, điền `firmware/LIBRARIES.md`. Nạp `node1-controller` khi broker đã chạy. Sau đó viết firmware Node 2 | `docs/huong-dan-lap-dat-phan-cung.md`, đặc tả §6, §7 |
| **Backend, triển khai** | Giai đoạn N0: công cụ portable trong `tools/`, script `scripts/windows/`, CSDL + seed, broker + kiểm chứng dynsec, hotspot + tường lửa. Sau đó backend theo thứ tự `backend/README.md` | đặc tả §17, §9–§13 |
| **Frontend, kiểm thử, AI** | Thiết bị mô phỏng ở `tests/load` (để có dữ liệu sớm), web đăng nhập + dashboard. Song song: tải dataset, huấn luyện giai đoạn 1–2 trên Google Colab | đặc tả §10, §16, §18.3, §15 |

Các quyết định đã chốt: đặc tả §22. Còn mở: C8 (ánh xạ nhãn AI).

## 5. Bí mật và cấu hình

| File | Commit? | Ghi chú |
|---|---|---|
| `.env.example` | ✅ | Chỉ tên biến và giá trị giả |
| `.env` | ❌ | Giá trị thật, mỗi máy một bản |
| `firmware/*/secrets.example.h` | ✅ | Mẫu |
| `firmware/*/secrets.h` | ❌ | WiFi, mật khẩu thiết bị thật |
| `deployment/mosquitto/data/` | ❌ | Chứa tài khoản broker (bản Docker) |
| `tools/`, `runtime/`, `logs/` | ❌ | Công cụ portable, dữ liệu chạy (CSDL, broker, ảnh, sao lưu), log |

Nếu lỡ commit bí mật: **đổi ngay mật khẩu đó** (WiFi, secret thiết bị, JWT secret, bot token). Xóa file khỏi commit sau là chưa đủ, vì lịch sử Git vẫn giữ.

## 6. Những thứ không có trong gói

- **Đề bài PDF** — nhóm tự thêm vào `docs/` nếu muốn.
- **Bộ slide thuyết trình** — nằm ở trang slide trên claude.ai (xem `docs/slides/README.md`). Xuất PDF/PPTX từ đó và lưu vào `docs/slides/`.
- **Dataset, trọng số mô hình AI** — quá lớn cho Git. Hướng dẫn tải ở `backend/ai-service/README.md`.
