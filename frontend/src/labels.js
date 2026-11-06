// Chữ hiển thị tiếng Việt cho mọi mã trạng thái (đặc tả §16.2: trạng thái luôn có chữ, không chỉ màu).

export const DEVICE_STATUS = {
  REGISTERED: { text: 'Đã đăng ký', tone: 'muted' },
  PROVISIONED: { text: 'Đã cấp phát, chờ kết nối', tone: 'info' },
  ACTIVE: { text: 'Hoạt động', tone: 'ok' },
  OFFLINE: { text: 'Mất kết nối', tone: 'bad' },
  FAULT: { text: 'Lỗi cảm biến', tone: 'warn' },
  MAINTENANCE: { text: 'Bảo trì', tone: 'info' },
  SUSPENDED: { text: 'Tạm khóa', tone: 'bad' },
  DECOMMISSIONED: { text: 'Đã thu hồi', tone: 'muted' },
}

export const DEVICE_TYPE = { CONTROLLER: 'Node điều khiển', CAMERA: 'Camera' }

export const ROLE = { ADMIN: 'Quản trị', OPERATOR: 'Vận hành', VIEWER: 'Người xem' }
export const USER_STATUS = {
  ACTIVE: { text: 'Hoạt động', tone: 'ok' },
  LOCKED: { text: 'Đã khóa', tone: 'bad' },
  INACTIVE: { text: 'Ngừng', tone: 'muted' },
}
export const PERMISSION = { VIEW: 'Chỉ xem', CONTROL: 'Điều khiển' }

export const COMMAND_STATUS = {
  PENDING: { text: 'Đang chờ thiết bị', tone: 'info' },
  EXECUTED: { text: 'Đã thực hiện', tone: 'ok' },
  REJECTED: { text: 'Bị từ chối', tone: 'warn' },
  FAILED: { text: 'Thất bại', tone: 'bad' },
  TIMEOUT: { text: 'Không phản hồi (quá 10 giây)', tone: 'bad' },
}

export const COMMAND_RESULT = {
  executed: 'đã chạy',
  duration_capped: 'đã chạy, thời gian bị giới hạn',
  failed: 'thiết bị báo lỗi',
  blocked_no_water: 'bể cạn',
  blocked_cooldown: 'đang nghỉ giữa hai lần tưới',
  blocked_sensor_fault: 'cảm biến lỗi',
  blocked_local: 'đang thao tác tại chỗ',
  invalid: 'lệnh không hợp lệ',
  expired: 'lệnh hết hạn',
  unsupported: 'thiết bị không hỗ trợ',
  broker_unavailable: 'không gửi được tới broker',
}

export const ACTION = {
  pump_on: 'Bật bơm',
  pump_off: 'Tắt bơm',
  fan_on: 'Bật quạt',
  fan_off: 'Tắt quạt',
  set_mode: 'Đổi chế độ',
  reboot: 'Khởi động lại',
  request_status: 'Hỏi trạng thái',
  capture: 'Chụp ảnh',
  flash: 'Đèn flash',
}

export const CONFIG_STATUS = {
  PENDING: { text: 'Chờ thiết bị áp dụng', tone: 'info' },
  APPLIED: { text: 'Đã áp dụng', tone: 'ok' },
  REJECTED: { text: 'Thiết bị từ chối', tone: 'bad' },
}

export const ALERT_STATUS = {
  OPEN: { text: 'Đang mở', tone: 'bad' },
  ACKNOWLEDGED: { text: 'Đã nhận xử lý', tone: 'warn' },
  CLOSED: { text: 'Đã đóng', tone: 'muted' },
}
export const SEVERITY = {
  INFO: { text: 'Thông tin', tone: 'info' },
  WARNING: { text: 'Cảnh báo', tone: 'warn' },
  CRITICAL: { text: 'Nghiêm trọng', tone: 'bad' },
}
export const ALERT_TYPE = { THRESHOLD: 'Vượt ngưỡng', OFFLINE: 'Mất kết nối', EVENT: 'Sự kiện', AI_LEAF: 'AI lá cây' }

export const METRICS = {
  soil: { text: 'Độ ẩm đất', unit: '%', digits: 1 },
  soil1: { text: 'Độ ẩm đất 1', unit: '%', digits: 1 },
  soil2: { text: 'Độ ẩm đất 2', unit: '%', digits: 1 },
  air_temp: { text: 'Nhiệt độ', unit: '°C', digits: 1 },
  air_hum: { text: 'Độ ẩm không khí', unit: '%', digits: 0 },
  light: { text: 'Ánh sáng', unit: 'lux', digits: 0 },
  tank: { text: 'Mực nước bể', unit: '%', digits: 0 },
}
export const MAIN_METRICS = ['soil', 'air_temp', 'air_hum', 'light', 'tank']
export const METRIC_COLORS = {
  soil: '#1f7a4d', soil1: '#58a37a', soil2: '#8cc5a2', air_temp: '#d9480f', air_hum: '#1971c2',
  light: '#e8a400', tank: '#7048e8',
}

export const LOCKS = {
  no_water: 'hết nước',
  cooldown: 'đang nghỉ',
  soil_fault: 'cảm biến đất lỗi',
  local: 'đang khóa tại chỗ',
}

export const EVENT = {
  pump_on: 'Bơm bật',
  pump_off: 'Bơm tắt',
  fan_on: 'Quạt bật',
  fan_off: 'Quạt tắt',
  tank_low: 'Bể sắp cạn',
  tank_ok: 'Bể đủ nước',
  sensor_fault: 'Cảm biến lỗi',
  sensor_ok: 'Cảm biến bình thường',
  local_override: 'Thao tác tại chỗ',
  upload_failed: 'Gửi ảnh thất bại',
  boot: 'Khởi động',
}
export const EVENT_SOURCE = { auto: 'tự động', remote: 'từ web', local: 'tại chỗ' }

export const LEAF = {
  HEALTHY: { text: 'Khỏe', color: 'rgba(47, 158, 68, 0.35)', tone: 'ok' },
  YELLOW: { text: 'Vàng lá', color: 'rgba(240, 180, 0, 0.45)', tone: 'warn' },
  SPOT: { text: 'Đốm lá', color: 'rgba(224, 49, 49, 0.45)', tone: 'bad' },
  UNKNOWN: { text: 'Không rõ', color: 'rgba(134, 142, 150, 0.35)', tone: 'muted' },
}
export const DIAG_STATUS = {
  QUEUED: { text: 'Đang xếp hàng', tone: 'info' },
  RUNNING: { text: 'Đang phân tích', tone: 'info' },
  DONE: { text: 'Đã có kết quả', tone: 'ok' },
  FAILED: { text: 'Phân tích lỗi', tone: 'bad' },
}

export const AUDIT_ACTIONS = [
  'LOGIN_SUCCESS', 'LOGIN_FAILED', 'LOGOUT', 'PASSWORD_CHANGED', 'USER_CREATED', 'USER_UPDATED', 'ROLE_CHANGED',
  'USER_LOCKED', 'USER_UNLOCKED', 'DEVICE_REGISTERED', 'DEVICE_UPDATED', 'DEVICE_PROVISIONED', 'DEVICE_SECRET_ROTATED',
  'DEVICE_SUSPENDED', 'DEVICE_RESUMED', 'DEVICE_DECOMMISSIONED', 'DEVICE_ASSIGNED', 'DEVICE_UNASSIGNED',
  'DEVICE_MAINTENANCE', 'COMMAND_SENT', 'COMMAND_DENIED', 'CONFIG_CHANGED', 'ALERT_ACKNOWLEDGED', 'ALERT_CLOSED',
  'ALERT_RULE_CHANGED', 'SECURITY_TOPIC_MISMATCH',
]

// ---------------------------------------------------------------------------

export function fmtTime(v, withSeconds = true) {
  if (!v) return '—'
  const d = new Date(v)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString('vi-VN', {
    hour: '2-digit', minute: '2-digit', second: withSeconds ? '2-digit' : undefined,
    day: '2-digit', month: '2-digit', year: 'numeric',
  })
}

export function fmtAgo(v) {
  if (!v) return 'chưa có'
  const s = Math.round((Date.now() - new Date(v).getTime()) / 1000)
  if (s < 5) return 'vừa xong'
  if (s < 60) return `${s} giây trước`
  if (s < 3600) return `${Math.floor(s / 60)} phút trước`
  if (s < 86400) return `${Math.floor(s / 3600)} giờ trước`
  return `${Math.floor(s / 86400)} ngày trước`
}

export function fmtValue(metric, v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '—'
  const m = METRICS[metric]
  return Number(v).toLocaleString('vi-VN', { maximumFractionDigits: m ? m.digits : 1 })
}

export function commandText(c) {
  if (!c) return ''
  const s = COMMAND_STATUS[c.status]?.text || c.status
  if (c.status === 'REJECTED' || c.status === 'FAILED') {
    const r = COMMAND_RESULT[c.result] || c.result
    return r ? `${s}: ${r}` : s
  }
  if (c.status === 'EXECUTED' && c.result === 'duration_capped') return `${s} (thời gian bị giới hạn)`
  return s
}

export function eventText(type, detail) {
  const base = EVENT[type] || type
  if (!detail || typeof detail !== 'object') return base
  const parts = []
  if (detail.source) parts.push(EVENT_SOURCE[detail.source] || detail.source)
  if (detail.duration_s) parts.push(`${detail.duration_s} giây`)
  if (detail.sensor) parts.push(`cảm biến ${detail.sensor}`)
  if (detail.tank !== undefined) parts.push(`bể ${detail.tank}%`)
  if (detail.reset_reason) parts.push(`lý do: ${detail.reset_reason}`)
  return parts.length ? `${base} (${parts.join(', ')})` : base
}
