-- 02_seed.sql — Dữ liệu mẫu ban đầu
-- Nguồn: docs/dac-ta-he-thong.md §11.5, §13.2.
--
-- KHÔNG tạo tài khoản người dùng ở đây, vì mật khẩu phải băm bcrypt.
-- Backend tạo 3 tài khoản admin / operator / viewer lúc khởi động lần đầu,
-- lấy mật khẩu từ SEED_*_PASSWORD trong .env.

-- Vườn và khu vực
INSERT INTO gardens (code, name, address)
VALUES ('g01', 'Vườn ươm thử nghiệm', '[địa chỉ]');

INSERT INTO zones (garden_id, name, crop_type)
SELECT id, 'Khay A', 'Cà chua giống' FROM gardens WHERE code = 'g01';
INSERT INTO zones (garden_id, name, crop_type)
SELECT id, 'Khay B', 'Cà chua giống' FROM gardens WHERE code = 'g01';

-- Hai thiết bị ở trạng thái REGISTERED, chờ admin cấp phát trên web
INSERT INTO devices (device_code, type, name, zone_id, status, hw_version)
SELECT 'ctl-0001', 'CONTROLLER', 'Node 1 - Điều khiển khay A', z.id, 'REGISTERED', 'node1-r1'
FROM zones z JOIN gardens g ON g.id = z.garden_id
WHERE g.code = 'g01' AND z.name = 'Khay A';

INSERT INTO devices (device_code, type, name, zone_id, status, hw_version)
SELECT 'cam-0001', 'CAMERA', 'Node 2 - Camera khay A', z.id, 'REGISTERED', 'node2-r1'
FROM zones z JOIN gardens g ON g.id = z.garden_id
WHERE g.code = 'g01' AND z.name = 'Khay A';

-- Luật cảnh báo mặc định (áp dụng toàn hệ thống: scope để trống)
INSERT INTO alert_rules (name, type, metric, operator, threshold, hysteresis, duration_s, severity, cooldown_min)
VALUES
  ('Đất quá khô',      'THRESHOLD', 'soil',     '<', 25, 3, 600, 'WARNING',  30),
  ('Quá nóng',         'THRESHOLD', 'air_temp', '>', 35, 1, 300, 'CRITICAL', 30);

INSERT INTO alert_rules (name, type, severity, cooldown_min)
VALUES ('Mất kết nối', 'OFFLINE', 'CRITICAL', 30);

INSERT INTO alert_rules (name, type, event_type, severity, cooldown_min)
VALUES
  ('Bể sắp cạn',   'EVENT', 'tank_low',     'WARNING', 30),
  ('Cảm biến lỗi', 'EVENT', 'sensor_fault', 'WARNING', 30);

INSERT INTO alert_rules (name, type, threshold, duration_s, severity, cooldown_min)
VALUES ('Lá bất thường', 'AI_LEAF', 0.8, 0, 'WARNING', 30);
