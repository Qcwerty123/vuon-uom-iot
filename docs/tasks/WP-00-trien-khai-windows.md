# WP-00 — Triển khai nền tảng trên Windows

**Mục tiêu:** trên máy Windows này, một người chạy vài script PowerShell là có PostgreSQL + Mosquitto (kèm Dynamic Security) chạy được, dữ liệu và log nằm trong repo, thiết bị trong mạng hotspot kết nối được broker. Chưa có backend.

**Hạn:** trong ngày 06/11, vì 07/11 sẽ thử nối Node 1 và Node 2 thật vào broker.

## 1. Đọc trước

| File | Phần cần đọc |
|---|---|
| `docs/dac-ta-he-thong.md` | §17 (toàn bộ), §8.1, §8.8 (ACL broker), §11 (CSDL), §22 (C17, C18, C21, C22) |
| `.env.example` | Toàn bộ |
| `database/init/01_schema.sql`, `02_seed.sql` | Toàn bộ |
| `deployment/mosquitto/init-dynsec.sh` | Bản Docker của việc khởi tạo broker — chuyển logic sang PowerShell |
| `firmware/node1-controller/net.cpp`, `secrets.example.h` | Thiết bị đăng nhập broker thế nào (username = device_code, password = secret, LWT) |

## 2. Luật bắt buộc

1. Mọi thứ nằm trong gốc repo. Công cụ vào `tools/`, dữ liệu vào `runtime/`, log vào `logs/`. Không cài gì ra ngoài nếu có bản portable. Không cài Windows service.
2. Script chỉ dùng đường dẫn tính từ gốc repo (tự xác định từ vị trí script). Không ghi cứng `C:\` hay `D:\`.
3. Script chạy được trên **Windows PowerShell 5.1** (mặc định của Windows). Lưu file `.ps1` dạng **UTF-8 có BOM** nếu có tiếng Việt có dấu.
4. Mọi giá trị bí mật đọc từ `.env`. Không in mật khẩu ra màn hình hay log.
5. Script chạy lại nhiều lần không phá dữ liệu (idempotent): thấy đã khởi tạo thì bỏ qua và báo.
6. Không sửa: firmware, `database/init/*.sql`, bản Docker (`docker-compose.yml`, `init-dynsec.sh`, `mosquitto/config/mosquitto.conf`).
7. Không commit, không push.

## 3. Việc cần làm

### 3.1. `scripts/windows/get-tools.ps1` — tải công cụ portable

Tải và giải nén, **ghim phiên bản cụ thể** (ghi vào `tools/VERSIONS.txt` và bảng "Phiên bản công cụ" trong `deployment/README.md`):

| Công cụ | Đích | Ghi chú |
|---|---|---|
| `uv` (bản zip Windows x64 từ GitHub release astral-sh/uv) | `tools/uv/` | |
| Python 3.11 | `tools/python/` | `uv python install 3.11` với `UV_PYTHON_INSTALL_DIR=tools/python` |
| PostgreSQL 16.x — gói zip "binaries" Windows x64 | `tools/pgsql/` | Chỉ cần `bin/`, `lib/`, `share/` |
| Mosquitto 2.0.x — bộ cài Windows x64 | `tools/mosquitto/` | Cài im lặng vào thư mục này (`/S /D=...`). Nếu bộ cài tự đăng ký service `mosquitto` thì dừng và xóa service đó; broker chỉ chạy bằng `start.ps1` |
| Node.js 20 LTS — zip Windows x64 | `tools/node/` | Chỉ để build frontend sau này |

Nếu một bước bắt buộc phải tải thủ công (ví dụ trang tải chặn script), ghi rõ URL và chỗ đặt file vào báo cáo, script nhận file đã tải sẵn.

### 3.2. `scripts/windows/common.ps1`

Hàm dùng chung: xác định gốc repo, đọc `.env` thành biến, đường dẫn chuẩn (`tools`, `runtime`, `logs`), ghi log có thời gian, kiểm tra cổng đang nghe, dừng tiến trình theo PID file.

### 3.3. Thêm biến vào `.env.example`

`PG_SUPERUSER_PASSWORD=change-me` (mật khẩu tài khoản `postgres` của cụm cục bộ). Ghi chú ngắn ở chỗ thêm.

### 3.4. `scripts/windows/setup.ps1`

1. Kiểm tra `tools/` đủ; thiếu thì bảo chạy `get-tools.ps1`.
2. Kiểm tra `.env` tồn tại và không còn `change-me` ở các biến bắt buộc.
3. Tạo `runtime/{pgdata,mosquitto,images,ai,backups,pids}`, `logs/{services,firmware,tests,agent}`.
4. Nếu `runtime/pgdata` trống: `initdb` (UTF8, locale C hoặc tương đương, `--auth=scram-sha-256`, superuser `postgres` với `PG_SUPERUSER_PASSWORD`); đặt `listen_addresses='127.0.0.1'`, `port` theo `DB_PORT`, log vào `logs/services/`.
5. Khởi động tạm PostgreSQL, tạo role `POSTGRES_USER` (mật khẩu `POSTGRES_PASSWORD`), CSDL `POSTGRES_DB` thuộc role đó, chạy `database/init/01_schema.sql` rồi `02_seed.sql` **bằng role ứng dụng** (để bảng thuộc role đó). Chỉ chạy khi CSDL vừa được tạo.
6. Dừng PostgreSQL tạm, báo kết quả.

### 3.5. `deployment/mosquitto/mosquitto.windows.conf` + `scripts/windows/init-broker.ps1`

- Mẫu cấu hình: `listener 1883 0.0.0.0`, `allow_anonymous false`, plugin Dynamic Security (`mosquitto_dynamic_security.dll` trong `tools/mosquitto`), `plugin_opt_config_file` → `runtime/mosquitto/dynamic-security.json`, `persistence true` vào `runtime/mosquitto/`, `log_dest file` → `logs/services/mosquitto.log`, `connection_messages true`. Dùng chỗ giữ chỗ (ví dụ `{{REPO}}`) để script điền đường dẫn tuyệt đối.
- `init-broker.ps1`: sinh `runtime/mosquitto/mosquitto.conf`; nếu chưa có `dynamic-security.json` thì tạo bằng `mosquitto_ctrl dynsec init` với `MQTT_DYNSEC_USER`/`MQTT_DYNSEC_PASSWORD`; khởi động broker; tạo client `MQTT_BACKEND_USER` + role `backend` với **đúng ACL như** `init-dynsec.sh` / đặc tả §8.8; dừng broker.

### 3.6. `scripts/windows/dev-device.ps1` — tài khoản thiết bị tạm thời

Backend chưa có, nhưng 07/11 cần nối thiết bị thật. Script quản lý tài khoản thiết bị trên broker, đúng như backend sẽ làm khi cấp phát (đặc tả §8.8):

```
dev-device.ps1 create  -Code ctl-0001 [-Garden g01]   # sinh secret ngẫu nhiên 32 byte base64url, in ra MỘT lần
dev-device.ps1 disable -Code ctl-0001
dev-device.ps1 enable  -Code ctl-0001
dev-device.ps1 delete  -Code ctl-0001
dev-device.ps1 list
```

Role riêng cho mỗi thiết bị: `publishClientSend` vào `nursery/G/D/{telemetry,status,event,ack}`; `subscribeLiteral` + `publishClientReceive` cho `nursery/G/D/{command,config}`; mọi thứ khác bị từ chối. Ghi audit đơn giản (thời gian, hành động, mã thiết bị — **không ghi secret**) vào `logs/services/dev-device.log`.

### 3.7. `firewall.ps1`, `start.ps1`, `stop.ps1`, `status.ps1`, `backup.ps1`, `reset-db.ps1`

Theo bảng đặc tả §17.4. Riêng:

- `firewall.ps1`: tự kiểm tra quyền Administrator; tạo (hoặc cập nhật) luật inbound TCP 1883 và 8000 cho mọi profile, tên luật bắt đầu bằng `VuonUom-`.
- `start.ps1`: chạy được khi chưa có backend/AI (bỏ qua và báo "chưa có"); ghi PID vào `runtime/pids/`.
- `status.ps1`: in bảng: PostgreSQL (cổng + `select count(*) from devices`), Mosquitto (cổng + đăng nhập thử bằng tài khoản backend), backend/AI (cổng), IP `192.168.137.1` có trên máy không (hotspot đang bật), luật tường lửa có chưa.
- `reset-db.ps1`: hỏi xác nhận gõ `XOA`; sao lưu trước khi xóa.

### 3.8. Kiểm chứng C18 (quan trọng)

Viết `tests/security/st3-dynsec-windows.ps1` và chạy:

1. Tạo thiết bị thử `test-0001` bằng `dev-device.ps1`.
2. Mở `mosquitto_sub` bằng tài khoản đó (chạy nền, ghi output vào `logs/tests/`).
3. `dev-device.ps1 disable -Code test-0001` → phiên đang mở **có bị ngắt ngay không**?
4. Kết nối lại bằng secret cũ → phải bị từ chối (not authorized).
5. `enable` → kết nối lại được. `delete` → dọn dẹp.

Ghi kết quả vào `logs/tests/st3-dynsec-windows.txt`. Nếu bước 3 không ngắt được, thử `disable → enable → disable` và ghi lại kết quả.

### 3.9. Tài liệu

Cập nhật `deployment/README.md`: bảng phiên bản công cụ, các bước chạy lần đầu, kết quả kiểm chứng C18. Không sửa đặc tả; điều gì cần sửa đặc tả thì ghi vào báo cáo.

## 4. Tiêu chí xong

- [ ] Trên một clone sạch: `get-tools.ps1` → tạo `.env` → `setup.ps1` → `init-broker.ps1` → `firewall.ps1` → `start.ps1` → `status.ps1` báo PostgreSQL và Mosquitto OK.
- [ ] `psql` (trong `tools/pgsql/bin`) truy vấn ra 2 thiết bị `ctl-0001`, `cam-0001` trạng thái `REGISTERED`.
- [ ] Ẩn danh bị từ chối; tài khoản backend subscribe `nursery/+/+/telemetry` được; tài khoản backend publish vào `.../telemetry` bị từ chối.
- [ ] Thiết bị tạo bằng `dev-device.ps1` publish được vào nhánh của mình, bị từ chối ở nhánh thiết bị khác (ST4).
- [ ] Có kết quả kiểm chứng C18.
- [ ] `stop.ps1` dừng sạch; chạy lại `start.ps1` dữ liệu còn nguyên.
- [ ] `git status` không xuất hiện file nào trong `tools/`, `runtime/`, `logs/`, `.env`.

## 5. Báo cáo

Ghi `logs/agent/WP-00-report.md`: việc đã làm, phiên bản công cụ, kết quả từng tiêu chí ở §4, kết quả C18, lỗi gặp phải và cách xử lý, điểm cần sửa đặc tả, việc còn lại.

## 6. Ngoài phạm vi

Backend, frontend, AI, firmware, Docker, HTTPS.

## 7. Checklist ngày 07/11 — nối Node 1, Node 2 thật vào broker (WP-N1)

Làm sau khi WP-00 đạt. Chưa cần backend.

1. Bật Mobile Hotspot (2,4 GHz) → `status.ps1` thấy `192.168.137.1` và tường lửa OK → `start.ps1`.
2. `dev-device.ps1 create -Code ctl-0001` và `-Code cam-0001`, chép secret.
3. **Node 1:** người giữ node mở `firmware/node1-controller` trong Arduino IDE 2, tạo `secrets.h` từ `secrets.example.h` (WiFi hotspot, `MQTT_HOST 192.168.137.1`, `DEVICE_CODE ctl-0001`, secret vừa tạo), nạp. Serial Monitor phải thấy `WiFi OK` rồi `MQTT OK`.
4. Trên máy chủ: `tools\mosquitto\mosquitto_sub -h 127.0.0.1 -u backend -P <MQTT_BACKEND_PASSWORD> -t "nursery/g01/ctl-0001/#" -v` → thấy `status` và `telemetry` mỗi 10 giây. Lưu output vào `logs/firmware/`.
5. Gửi lệnh bật bơm 5 giây bằng `mosquitto_pub` (lệnh mẫu trong `firmware/node1-controller/README.md`) → thấy `ack`.
6. Gửi cấu hình hiệu chuẩn (retain) theo số đo thật → thấy ack `cfg-1`.
7. Rút nguồn Node 1 → sau khoảng 45 giây thấy `status` `online:false` (LWT).
8. **Node 2:** chưa có firmware chính. Nạp ví dụ `CameraWebServer`, kiểm tra ảnh rõ, không brownout với củ sạc 5V/2A (hướng dẫn lắp §D2, §D3).

---

## Prompt cho agent

```
Bạn là agent làm việc trong repo vuon-uom-iot trên máy Windows này (thư mục gốc là repo). Nhiệm vụ: thực hiện gói việc WP-00 — triển khai nền tảng PostgreSQL + Mosquitto chạy trực tiếp trên Windows, không Docker.

Đọc kỹ docs/tasks/WP-00-trien-khai-windows.md và làm đúng theo đó: phần "Đọc trước", "Luật bắt buộc", "Việc cần làm" (3.1–3.9), "Tiêu chí xong". Đặc tả docs/dac-ta-he-thong.md v1.3 là nguồn đúng; không tự đổi thiết kế, điều gì cần đổi thì ghi vào báo cáo.

Cách làm:
- Bạn có quyền chạy PowerShell trên máy này: hãy tự chạy từng script, đọc log trong logs/, sửa cho tới khi đạt từng tiêu chí ở mục 4.
- Mọi thứ phải nằm trong repo (tools/, runtime/, logs/), đường dẫn tương đối, tương thích Windows PowerShell 5.1, không cài Windows service, không in mật khẩu.
- Nếu .env chưa có, tạo từ .env.example với mật khẩu ngẫu nhiên mạnh cho mọi biến change-me (trừ TELEGRAM_BOT_TOKEN: để nguyên change-me).
- Việc cần quyền Administrator (firewall.ps1) hoặc thao tác tay (bật Mobile Hotspot, tải file bị chặn): dừng lại, ghi rõ người dùng cần làm gì, rồi làm tiếp phần còn lại.
- Không sửa firmware, database/init/*.sql, các file Docker. Không commit, không push.

Khi xong, ghi báo cáo vào logs/agent/WP-00-report.md theo mục 5 và trả lời ngắn gọn: đạt những tiêu chí nào, kết quả kiểm chứng C18, người dùng còn phải làm gì.
```
