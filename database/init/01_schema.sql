-- 01_schema.sql — Schema CSDL hệ thống vườn ươm
-- Nguồn: docs/dac-ta-he-thong.md §11.2. Sửa schema thì sửa cả hai nơi.
-- PostgreSQL chạy file này tự động ở lần khởi tạo đầu tiên (volume dbdata còn trống).

CREATE TYPE user_role    AS ENUM ('ADMIN','OPERATOR','VIEWER');
CREATE TYPE user_status  AS ENUM ('PENDING','ACTIVE','LOCKED');
CREATE TYPE device_type  AS ENUM ('CONTROLLER','CAMERA');
CREATE TYPE device_status AS ENUM ('REGISTERED','PROVISIONED','ACTIVE','OFFLINE',
                                   'FAULT','MAINTENANCE','SUSPENDED','DECOMMISSIONED');
CREATE TYPE assign_perm  AS ENUM ('VIEW','CONTROL');
CREATE TYPE cmd_status   AS ENUM ('PENDING','EXECUTED','REJECTED','FAILED','TIMEOUT');
CREATE TYPE cfg_status   AS ENUM ('PENDING','APPLIED','REJECTED');
CREATE TYPE alert_status AS ENUM ('OPEN','ACKNOWLEDGED','CLOSED');
CREATE TYPE alert_sev    AS ENUM ('INFO','WARNING','CRITICAL');
CREATE TYPE diag_status  AS ENUM ('QUEUED','RUNNING','DONE','FAILED');

CREATE TABLE users (
  id            BIGSERIAL PRIMARY KEY,
  username      VARCHAR(50)  NOT NULL UNIQUE,
  email         VARCHAR(120) UNIQUE,
  full_name     VARCHAR(120),
  password_hash VARCHAR(100) NOT NULL,          -- bcrypt
  role          user_role    NOT NULL DEFAULT 'VIEWER',
  status        user_status  NOT NULL DEFAULT 'ACTIVE',
  telegram_chat_id VARCHAR(40),
  failed_logins INT NOT NULL DEFAULT 0,
  locked_until  TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE refresh_tokens (
  id          BIGSERIAL PRIMARY KEY,
  user_id     BIGINT NOT NULL REFERENCES users(id),
  token_hash  CHAR(64) NOT NULL UNIQUE,          -- SHA-256 của token
  expires_at  TIMESTAMPTZ NOT NULL,
  revoked_at  TIMESTAMPTZ,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  user_agent  VARCHAR(200), ip INET
);

CREATE TABLE gardens (id BIGSERIAL PRIMARY KEY, code VARCHAR(20) NOT NULL UNIQUE,
                      name VARCHAR(120) NOT NULL, address VARCHAR(200));
CREATE TABLE zones   (id BIGSERIAL PRIMARY KEY, garden_id BIGINT NOT NULL REFERENCES gardens(id),
                      name VARCHAR(120) NOT NULL, crop_type VARCHAR(60),
                      UNIQUE(garden_id, name));

CREATE TABLE devices (
  id              BIGSERIAL PRIMARY KEY,
  device_code     VARCHAR(20)  NOT NULL UNIQUE,   -- ctl-0001 / cam-0001 = MQTT username
  type            device_type  NOT NULL,
  name            VARCHAR(120) NOT NULL,
  zone_id         BIGINT REFERENCES zones(id),
  status          device_status NOT NULL DEFAULT 'REGISTERED',
  online          BOOLEAN NOT NULL DEFAULT false,
  credential_hash VARCHAR(100),                   -- bcrypt của secret
  hw_version      VARCHAR(30),
  fw_version      VARCHAR(30),
  last_seen_at    TIMESTAMPTZ,
  first_seen_at   TIMESTAMPTZ,
  current_config_version INT NOT NULL DEFAULT 0,
  note            TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  decommissioned_at TIMESTAMPTZ
);

CREATE TABLE device_assignments (
  user_id     BIGINT NOT NULL REFERENCES users(id),
  device_id   BIGINT NOT NULL REFERENCES devices(id),
  permission  assign_perm NOT NULL DEFAULT 'VIEW',
  assigned_by BIGINT REFERENCES users(id),
  assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, device_id)
);

CREATE TABLE device_status_history (
  id BIGSERIAL PRIMARY KEY,
  device_id  BIGINT NOT NULL REFERENCES devices(id),
  from_status device_status, to_status device_status NOT NULL,
  reason VARCHAR(200), actor_id BIGINT REFERENCES users(id),   -- null = hệ thống
  at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE device_configs (
  id BIGSERIAL PRIMARY KEY,
  device_id BIGINT NOT NULL REFERENCES devices(id),
  config_version INT NOT NULL,
  params JSONB NOT NULL,
  status cfg_status NOT NULL DEFAULT 'PENDING',
  created_by BIGINT REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  applied_at TIMESTAMPTZ, reject_detail JSONB,
  UNIQUE(device_id, config_version)
);

CREATE TABLE commands (
  cmd_id     UUID PRIMARY KEY,
  device_id  BIGINT NOT NULL REFERENCES devices(id),
  action     VARCHAR(30) NOT NULL,
  params     JSONB,
  status     cmd_status NOT NULL DEFAULT 'PENDING',
  result     VARCHAR(40),            -- executed / blocked_no_water / ...
  detail     JSONB,
  issued_by  BIGINT REFERENCES users(id),
  issued_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  ack_at     TIMESTAMPTZ
);
CREATE INDEX ON commands(device_id, issued_at DESC);
CREATE INDEX ON commands(status) WHERE status = 'PENDING';

CREATE TABLE telemetry (
  device_id   BIGINT NOT NULL REFERENCES devices(id),
  seq         BIGINT NOT NULL,
  metric      VARCHAR(20) NOT NULL,     -- soil1, soil2, soil, air_temp, air_hum, light, tank
  value       DOUBLE PRECISION,
  unit        VARCHAR(8) NOT NULL,
  ok          BOOLEAN NOT NULL DEFAULT true,
  ts          TIMESTAMPTZ NOT NULL,     -- thời điểm đo trên thiết bị (hoặc received_at nếu chưa NTP)
  received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  buffered    BOOLEAN NOT NULL DEFAULT false,
  PRIMARY KEY (device_id, seq, metric)
);
CREATE INDEX ON telemetry(device_id, metric, ts DESC);

CREATE TABLE telemetry_hourly (
  device_id BIGINT NOT NULL, metric VARCHAR(20) NOT NULL, hour TIMESTAMPTZ NOT NULL,
  min DOUBLE PRECISION, max DOUBLE PRECISION, avg DOUBLE PRECISION, count INT,
  PRIMARY KEY (device_id, metric, hour)
);

CREATE TABLE device_events (
  id BIGSERIAL PRIMARY KEY,
  device_id BIGINT NOT NULL REFERENCES devices(id),
  seq BIGINT, type VARCHAR(30) NOT NULL, detail JSONB,
  ts TIMESTAMPTZ NOT NULL, received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(device_id, seq)
);
CREATE INDEX ON device_events(device_id, ts DESC);

CREATE TABLE diagnoses (
  id BIGSERIAL PRIMARY KEY,
  device_id BIGINT NOT NULL REFERENCES devices(id),
  image_path VARCHAR(200) NOT NULL,        -- đường dẫn trong volume, không public
  image_sha256 CHAR(64) NOT NULL,
  captured_at TIMESTAMPTZ NOT NULL,
  trigger VARCHAR(10) NOT NULL,            -- schedule / command
  cmd_id UUID,
  lamp_on BOOLEAN,                         -- trạng thái đèn Node 1 lúc chụp (§6.11)
  status diag_status NOT NULL DEFAULT 'QUEUED',
  model_version VARCHAR(30),
  tiles JSONB,                             -- [{r,c,label,conf,probs:{...}}] × 9
  top_label VARCHAR(20), top_confidence REAL,
  abnormal_tiles JSONB,                    -- [[r,c],...]
  review_verdict VARCHAR(10), correct_label VARCHAR(20),
  reviewed_by BIGINT REFERENCES users(id), reviewed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON diagnoses(device_id, captured_at DESC);

CREATE TABLE alert_rules (
  id BIGSERIAL PRIMARY KEY,
  name VARCHAR(120) NOT NULL,
  type VARCHAR(20) NOT NULL,         -- THRESHOLD / OFFLINE / EVENT / AI_LEAF
  scope_zone_id BIGINT REFERENCES zones(id),
  scope_device_id BIGINT REFERENCES devices(id),
  metric VARCHAR(20), operator VARCHAR(2),   -- < <= > >=
  threshold DOUBLE PRECISION, hysteresis DOUBLE PRECISION DEFAULT 0,
  duration_s INT NOT NULL DEFAULT 0,
  event_type VARCHAR(30),
  severity alert_sev NOT NULL DEFAULT 'WARNING',
  cooldown_min INT NOT NULL DEFAULT 30,
  notify_telegram BOOLEAN NOT NULL DEFAULT true,
  enabled BOOLEAN NOT NULL DEFAULT true,
  created_by BIGINT REFERENCES users(id), created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE alerts (
  id BIGSERIAL PRIMARY KEY,
  rule_id BIGINT REFERENCES alert_rules(id),
  device_id BIGINT NOT NULL REFERENCES devices(id),
  type VARCHAR(20) NOT NULL, severity alert_sev NOT NULL,
  message VARCHAR(300) NOT NULL, context JSONB,     -- giá trị, ngưỡng, diagnosis_id...
  status alert_status NOT NULL DEFAULT 'OPEN',
  opened_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  condition_cleared_at TIMESTAMPTZ,
  ack_by BIGINT REFERENCES users(id), ack_at TIMESTAMPTZ,
  closed_by BIGINT REFERENCES users(id), closed_at TIMESTAMPTZ, close_note VARCHAR(300),
  notified_at TIMESTAMPTZ
);
CREATE INDEX ON alerts(device_id, opened_at DESC);
CREATE INDEX ON alerts(status) WHERE status <> 'CLOSED';

CREATE TABLE audit_logs (
  id BIGSERIAL PRIMARY KEY,
  actor_id BIGINT REFERENCES users(id),     -- null = hệ thống / thiết bị
  actor_label VARCHAR(60),                  -- username hoặc device_code
  action VARCHAR(40) NOT NULL,
  target_type VARCHAR(20), target_id VARCHAR(40),
  detail JSONB, ip INET, success BOOLEAN NOT NULL DEFAULT true,
  at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON audit_logs(at DESC);
-- Chỉ INSERT: tài khoản ứng dụng bị REVOKE UPDATE, DELETE trên bảng này
