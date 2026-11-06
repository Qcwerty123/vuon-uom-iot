# Thiết bị mô phỏng (WP-01)

Đặc tả: `docs/dac-ta-he-thong.md` §8 (giao thức), §6.5–§6.6 (logic tại thiết bị), §18.3.

`simulator.py` đóng vai **Node 1** đúng giao thức của firmware thật: telemetry mỗi 10 s, status 30 s + LWT,
event (bơm, quạt, bể cạn, boot), lệnh + ack (chống trùng `cmd_id`, hạn lệnh `ttl_s`), cấu hình retain
(`config_version`, kiểm tra miền giá trị), tưới/thông gió tự động và khóa an toàn (bể cạn, cooldown, `pump_max_s`).
Môi trường được mô phỏng đơn giản: đất khô dần, bơm làm ẩm đất và cạn bể, quạt làm mát.

Dùng để: phát triển backend/web khi chưa có phần cứng; đo NFR05 (mất bản tin), NFR08 (trùng), NFR09 (tải).
**Không thay thế thiết bị thật trong demo.**

## Chạy (PowerShell, gốc repo)

Lần đầu `sim.ps1` tự tạo `tests/load/.venv` bằng Python trong `tools/` và cài `paho-mqtt`.

```powershell
.\scripts\windows\sim.ps1 provision --count 1        # tạo tài khoản broker ctl-9001 (Dynamic Security)
.\scripts\windows\sim.ps1 run                         # chạy các thiết bị đã tạo; Ctrl+C để dừng
.\scripts\windows\sim.ps1 watch                       # cửa sổ khác: xem bản tin như backend
.\scripts\windows\sim.ps1 cmd ctl-9001 pump_on --duration 5
.\scripts\windows\sim.ps1 cmd ctl-9001 set_mode --mode MANUAL
.\scripts\windows\sim.ps1 config ctl-9001 --set soil_low=40 --set soil_high=60
.\scripts\windows\sim.ps1 deprovision                 # xóa tài khoản mô phỏng
```

Tùy chọn của `run`: `--codes ctl-9001,ctl-9002`, `--interval 1` (đo tải), `--duplicate-rate 0.05`,
`--drop-rate 0.02`, `--offline-every 120 --offline-for 30` (mất mạng đột ngột → broker phát LWT, thiết bị đệm
và gửi bù kèm `buffered:true`), `--soil 30 --tank 20` (giá trị ban đầu).

`cmd`, `config` gửi như backend và in thời gian tới ack (đo NFR02 sơ bộ).

## Dữ liệu và log

- `runtime/sim/devices.json`: mã + secret thiết bị mô phỏng (không commit).
- `runtime/sim/state.json`: `seq`, cấu hình đang dùng (giữ qua lần chạy sau, `seq` không lặp).
- `logs/tests/simulator-<ngày>.log`: log mọi lệnh.

Mã thiết bị mô phỏng là `ctl-9xxx`, để không trùng `ctl-0001` (Node 1 thật). Khi backend có chức năng cấp phát,
thiết bị mô phỏng sẽ được cấp phát qua API thay cho lệnh `provision`.
