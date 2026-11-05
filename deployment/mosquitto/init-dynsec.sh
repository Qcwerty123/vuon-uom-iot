#!/usr/bin/env bash
# init-dynsec.sh — khởi tạo Dynamic Security cho Mosquitto (chạy MỘT lần, từ thư mục deployment/)
#
#   cd deployment
#   ./mosquitto/init-dynsec.sh
#
# Việc làm:
#   1. Tạo file dynamic-security.json với tài khoản quản trị (MQTT_DYNSEC_USER)
#   2. Khởi động broker
#   3. Tạo tài khoản backend (MQTT_BACKEND_USER) + role và ACL theo đặc tả §8.8
#
# Mật khẩu lấy từ ../.env. Chạy lại khi file đã tồn tại sẽ dừng ở bước 1 để không ghi đè.
# Kiểm chứng: sau khi chạy, dùng MQTTX đăng nhập bằng tài khoản backend và subscribe "nursery/#".
set -euo pipefail

cd "$(dirname "$0")/.."            # về deployment/
ENV_FILE=../.env
[ -f "$ENV_FILE" ] || { echo "Thiếu $ENV_FILE — chạy: cp .env.example .env và sửa giá trị"; exit 1; }
set -a; . "$ENV_FILE"; set +a

DATA=./mosquitto/data
mkdir -p "$DATA"
if [ -f "$DATA/dynamic-security.json" ]; then
  echo "Đã có $DATA/dynamic-security.json — bỏ qua. Xóa file này nếu muốn khởi tạo lại."
  exit 0
fi

echo "== 1. Tạo dynamic-security.json, tài khoản quản trị: $MQTT_DYNSEC_USER"
echo "   (nhập mật khẩu = MQTT_DYNSEC_PASSWORD trong .env khi được hỏi)"
docker compose run --rm --no-deps mosquitto \
  mosquitto_ctrl dynsec init /mosquitto/data/dynamic-security.json "$MQTT_DYNSEC_USER"

# Container chạy với user mosquitto (uid 1883): cho phép đọc/ghi thư mục data
docker compose run --rm --no-deps --user root --entrypoint sh mosquitto \
  -c "chown -R 1883:1883 /mosquitto/data && chmod 700 /mosquitto/data"

echo "== 2. Khởi động broker"
docker compose up -d mosquitto
sleep 3

ctl() {
  docker compose exec -T mosquitto mosquitto_ctrl -u "$MQTT_DYNSEC_USER" -P "$MQTT_DYNSEC_PASSWORD" dynsec "$@"
}

echo "== 3. Tạo tài khoản backend: $MQTT_BACKEND_USER"
ctl createClient "$MQTT_BACKEND_USER" -p "$MQTT_BACKEND_PASSWORD"
ctl createRole backend
# Nhận mọi bản tin đi lên từ thiết bị
ctl addRoleACL backend subscribePattern     'nursery/+/+/telemetry' allow
ctl addRoleACL backend subscribePattern     'nursery/+/+/status'    allow
ctl addRoleACL backend subscribePattern     'nursery/+/+/event'     allow
ctl addRoleACL backend subscribePattern     'nursery/+/+/ack'       allow
ctl addRoleACL backend publishClientReceive 'nursery/#'             allow
# Gửi lệnh và cấu hình xuống thiết bị
ctl addRoleACL backend publishClientSend    'nursery/+/+/command'   allow
ctl addRoleACL backend publishClientSend    'nursery/+/+/config'    allow
ctl addClientRole "$MQTT_BACKEND_USER" backend

echo "== Xong. Tài khoản thiết bị do backend tạo khi cấp phát (đặc tả §8.8)."
echo "   Kiểm tra: docker compose logs -f mosquitto"
