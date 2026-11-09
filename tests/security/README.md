# Kiểm thử bảo mật

Ca kiểm thử ST1–ST6 ở `../scenarios.md` mục 3. Lưu script (curl, mosquitto_pub, Postman collection) và bằng chứng (ảnh chụp, log) tại đây.

Gợi ý kiểm thử ở tầng broker (ST3, ST4) bằng `mosquitto_pub` / `mosquitto_sub` hoặc MQTTX:

```bash
# ST4: thiết bị ctl-0001 cố publish sang nhánh của cam-0001 -> phải bị chặn
mosquitto_pub -h <IP> -p 1883 -u ctl-0001 -P '<secret>' \
  -t nursery/g01/cam-0001/telemetry -m '{"v":1,"device_id":"cam-0001"}' -d
```

Đối chiếu log broker (`logs/services/mosquitto.log`) và CSDL (không có bản ghi mới) làm bằng chứng.
