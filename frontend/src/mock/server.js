// Máy chủ giả chạy trong trình duyệt — chỉ dùng khi:
//   - `npm run dev:mock` (MOCK.all): toàn bộ API + WebSocket, để làm giao diện khi chưa có backend;
//   - MOCK.diagnoses: phần ảnh/chẩn đoán (WP-07 chưa có API).
// Hình dạng dữ liệu theo đúng đặc tả §10 và code backend (camelCase). Không dùng cho bản demo thật.

import { MOCK } from '../config.js'

const now = () => Date.now()
const iso = (t = now()) => new Date(t).toISOString()
const rnd = (a, b) => a + Math.random() * (b - a)
const uuid = () => 'xxxxxxxx-xxxx-4xxx-8xxx-xxxxxxxxxxxx'.replace(/x/g, () => ((Math.random() * 16) | 0).toString(16))
const clone = (x) => JSON.parse(JSON.stringify(x))
const round = (v, d = 1) => Math.round(v * 10 ** d) / 10 ** d

// ---------------------------------------------------------------------------
// Dữ liệu

const users = [
  { id: 1, username: 'admin', fullName: 'Quản trị viên', email: null, role: 'ADMIN', status: 'ACTIVE', telegramChatId: null },
  { id: 2, username: 'operator', fullName: 'Người vận hành', email: null, role: 'OPERATOR', status: 'ACTIVE', telegramChatId: '123456789' },
  { id: 3, username: 'viewer', fullName: 'Người xem', email: null, role: 'VIEWER', status: 'ACTIVE', telegramChatId: null },
]
const devices = [
  { id: 1, deviceCode: 'ctl-0001', type: 'CONTROLLER', name: 'Khay ươm A — Node 1', zoneId: 1, status: 'ACTIVE', online: true,
    hwVersion: 'node1-r1', fwVersion: '1.0.3', lastSeenAt: iso(), firstSeenAt: iso(now() - 3 * 86400e3), currentConfigVersion: 1, note: null },
  { id: 2, deviceCode: 'cam-0001', type: 'CAMERA', name: 'Camera khay A — Node 2', zoneId: 1, status: 'ACTIVE', online: true,
    hwVersion: 'esp32-cam', fwVersion: '0.9.0', lastSeenAt: iso(), firstSeenAt: iso(now() - 86400e3), currentConfigVersion: 0, note: null },
  { id: 3, deviceCode: 'ctl-0002', type: 'CONTROLLER', name: 'Node dự phòng', zoneId: 1, status: 'REGISTERED', online: false,
    hwVersion: null, fwVersion: null, lastSeenAt: null, firstSeenAt: null, currentConfigVersion: 0, note: 'Để demo đăng ký' },
]
const assignments = [
  { userId: 2, deviceId: 1, permission: 'CONTROL' }, { userId: 2, deviceId: 2, permission: 'CONTROL' },
  { userId: 3, deviceId: 1, permission: 'VIEW' }, { userId: 3, deviceId: 2, permission: 'VIEW' },
]
const history = [
  { deviceId: 1, fromStatus: null, toStatus: 'REGISTERED', reason: 'Đăng ký', actorId: 1, at: iso(now() - 4 * 86400e3) },
  { deviceId: 1, fromStatus: 'REGISTERED', toStatus: 'PROVISIONED', reason: 'Cấp phát khóa', actorId: 1, at: iso(now() - 3.1 * 86400e3) },
  { deviceId: 1, fromStatus: 'PROVISIONED', toStatus: 'ACTIVE', reason: 'Kết nối lần đầu', actorId: null, at: iso(now() - 3 * 86400e3) },
  { deviceId: 2, fromStatus: null, toStatus: 'REGISTERED', reason: 'Đăng ký', actorId: 1, at: iso(now() - 2 * 86400e3) },
  { deviceId: 2, fromStatus: 'PROVISIONED', toStatus: 'ACTIVE', reason: 'Kết nối lần đầu', actorId: null, at: iso(now() - 86400e3) },
  { deviceId: 3, fromStatus: null, toStatus: 'REGISTERED', reason: 'Đăng ký', actorId: 1, at: iso(now() - 3600e3) },
]
const DEFAULTS = { soil_low: 35, soil_high: 55, pump_max_s: 15, cooldown_s: 120, tank_min: 15, temp_high: 32, temp_hyst: 2,
  hum_high: 90, hum_hyst: 5, telemetry_interval_s: 10, manual_ignores_cooldown: false }
const configs = [
  { id: 1, deviceId: 1, configVersion: 1, params: { ...DEFAULTS }, status: 'APPLIED', createdBy: 1, createdAt: iso(now() - 2 * 86400e3), appliedAt: iso(now() - 2 * 86400e3), rejectDetail: null },
]
const commands = []
const events = []
const audit = []
const rules = [
  { id: 1, name: 'Đất quá khô', type: 'THRESHOLD', scopeZoneId: null, scopeDeviceId: null, metric: 'soil', operator: '<', threshold: 25, hysteresis: 3, durationS: 120, eventType: null, severity: 'WARNING', cooldownMin: 30, notifyTelegram: true, enabled: true },
  { id: 2, name: 'Nhiệt độ cao', type: 'THRESHOLD', scopeZoneId: null, scopeDeviceId: null, metric: 'air_temp', operator: '>', threshold: 38, hysteresis: 1, durationS: 300, eventType: null, severity: 'WARNING', cooldownMin: 30, notifyTelegram: true, enabled: true },
  { id: 3, name: 'Thiết bị mất kết nối', type: 'OFFLINE', scopeZoneId: null, scopeDeviceId: null, metric: null, operator: null, threshold: null, hysteresis: 0, durationS: 0, eventType: null, severity: 'CRITICAL', cooldownMin: 30, notifyTelegram: true, enabled: true },
  { id: 4, name: 'Bể sắp cạn', type: 'EVENT', scopeZoneId: null, scopeDeviceId: null, metric: null, operator: null, threshold: null, hysteresis: 0, durationS: 0, eventType: 'tank_low', severity: 'WARNING', cooldownMin: 30, notifyTelegram: true, enabled: true },
  { id: 5, name: 'Cảm biến lỗi', type: 'EVENT', scopeZoneId: null, scopeDeviceId: null, metric: null, operator: null, threshold: null, hysteresis: 0, durationS: 0, eventType: 'sensor_fault', severity: 'WARNING', cooldownMin: 30, notifyTelegram: true, enabled: true },
]
const alerts = [
  { id: 1, ruleId: 4, deviceId: 1, deviceCode: 'ctl-0001', type: 'EVENT', severity: 'WARNING', message: 'ctl-0001: Bể sắp cạn (12%)', context: { tank: 12 }, status: 'OPEN', openedAt: iso(now() - 20 * 60e3), conditionClearedAt: null, ackBy: null, ackAt: null, closedBy: null, closedAt: null, closeNote: null, notifiedAt: iso(now() - 20 * 60e3) },
  { id: 2, ruleId: 3, deviceId: 1, deviceCode: 'ctl-0001', type: 'OFFLINE', severity: 'CRITICAL', message: 'ctl-0001 mất kết nối', context: {}, status: 'CLOSED', openedAt: iso(now() - 5 * 3600e3), conditionClearedAt: iso(now() - 4.9 * 3600e3), ackBy: null, ackAt: null, closedBy: null, closedAt: iso(now() - 4.9 * 3600e3), closeNote: 'auto', notifiedAt: iso(now() - 5 * 3600e3) },
]

// Telemetry: 2 giờ lịch sử mỗi 30 s cho ctl-0001, sau đó 3 s một bản tin.
const telemetry = [] // {deviceId, metric, ts, value, ok, seq}
let seq = 10000
const sim = { soil1: 44, soil2: 46, air_temp: 29, air_hum: 76, light: 1800, tank: 62, pump: 0, fan: 0, mode: 'AUTO', locks: [], pumpUntil: 0 }

function sample(t) {
  const h = new Date(t).getHours() + new Date(t).getMinutes() / 60
  if (sim.pump) { sim.soil1 += 0.9; sim.soil2 += 0.8; sim.tank -= 0.4 } else { sim.soil1 -= 0.02; sim.soil2 -= 0.018 }
  sim.soil1 = Math.min(85, Math.max(10, sim.soil1 + rnd(-0.3, 0.3)))
  sim.soil2 = Math.min(85, Math.max(10, sim.soil2 + rnd(-0.3, 0.3)))
  sim.tank = Math.max(0, sim.tank - 0.005)
  sim.air_temp = 27 + 4 * Math.sin(((h - 9) / 24) * 2 * Math.PI) + rnd(-0.3, 0.3)
  sim.air_hum = 78 - 6 * Math.sin(((h - 9) / 24) * 2 * Math.PI) + rnd(-1, 1)
  sim.light = Math.max(0, 2200 * Math.sin(((h - 6) / 12) * Math.PI)) + rnd(0, 80)
  const cfg = currentParams(1)
  sim.fan = sim.air_temp >= cfg.temp_high ? 1 : sim.fan && sim.air_temp > cfg.temp_high - cfg.temp_hyst ? 1 : 0
  sim.locks = sim.tank < cfg.tank_min ? ['no_water'] : []
  return {
    soil1: { v: round(sim.soil1), u: '%', ok: true },
    soil2: { v: round(sim.soil2), u: '%', ok: true },
    soil: { v: round((sim.soil1 + sim.soil2) / 2), u: '%', ok: true },
    air_temp: { v: round(sim.air_temp), u: 'C', ok: true },
    air_hum: { v: round(sim.air_hum, 0), u: '%RH', ok: true },
    light: { v: Math.round(sim.light), u: 'lux', ok: true },
    tank: { v: round(sim.tank, 0), u: '%', ok: true },
  }
}
function store(deviceId, t, data) {
  seq += 1
  Object.entries(data).forEach(([metric, d]) => telemetry.push({ deviceId, metric, ts: iso(t), value: d.v, ok: d.ok, seq }))
  if (telemetry.length > 60000) telemetry.splice(0, telemetry.length - 50000)
}
for (let t = now() - 2 * 3600e3; t < now(); t += 30e3) store(1, t, sample(t))

// Sự kiện mẫu
;[[-90, 'boot', { reset_reason: 'power_on' }], [-60, 'pump_on', { source: 'auto', duration_s: 10 }], [-59.8, 'pump_off', { source: 'auto' }],
  [-20, 'tank_low', { tank: 12 }], [-15, 'tank_ok', { tank: 62 }]].forEach(([m, type, detail], i) => {
  events.push({ id: i + 1, deviceId: 1, seq: i + 1, type, detail, ts: iso(now() + m * 60e3) })
})

function currentParams(deviceId) {
  const list = configs.filter((c) => c.deviceId === deviceId && c.status !== 'REJECTED').sort((a, b) => b.configVersion - a.configVersion)
  if (list.length) return list[0].params
  return devices.find((d) => d.id === deviceId)?.type === 'CONTROLLER' ? { ...DEFAULTS } : {}
}

// ---------------------------------------------------------------------------
// Phiên

const tokens = {} // access -> {userId, exp}
const refreshes = {} // refresh -> userId
const fails = {}

function issue(user) {
  const at = `mock-at-${user.id}-${uuid()}`
  const rt = `mock-rt-${user.id}-${uuid()}`
  tokens[at] = { userId: user.id, exp: now() + 15 * 60e3 }
  refreshes[rt] = user.id
  return { accessToken: at, refreshToken: rt, expiresIn: 900, user: clone(user) }
}
function whoami(token) {
  const t = tokens[token]
  if (!t || t.exp < now()) return null
  return users.find((u) => u.id === t.userId) || null
}
function permissionOf(user, deviceId) {
  if (user.role === 'ADMIN') return 'CONTROL'
  const a = assignments.find((x) => x.userId === user.id && x.deviceId === deviceId)
  if (!a) return null
  return user.role === 'VIEWER' ? 'VIEW' : a.permission
}
function visibleDevices(user) {
  return devices.filter((d) => permissionOf(user, d.id))
}
function log(user, action, targetType, targetId, detail, success = true) {
  audit.unshift({ id: audit.length + 1, actorId: user?.id ?? null, actorLabel: user?.username ?? null, action, targetType, targetId, detail: detail || null, ip: '127.0.0.1', success, at: iso() })
}

// ---------------------------------------------------------------------------
// WebSocket giả

const sockets = new Set()

export class MockSocket {
  constructor() {
    this.readyState = 0
    this.user = null
    this.devices = new Set()
    setTimeout(() => {
      if (this.readyState === 3) return
      this.readyState = 1
      sockets.add(this)
      this.onopen?.()
    }, 50)
  }
  send(text) {
    if (wsDown) { this.close(); return } // đang giả lập mất mạng
    const m = JSON.parse(text)
    if (m.type === 'auth') {
      const u = whoami(m.token)
      if (!u) { this._push({ type: 'auth_error' }); return }
      this.user = u
      this._push({ type: 'auth_ok' })
    } else if (m.type === 'subscribe') {
      this.devices = new Set((m.deviceIds || []).map(Number).filter((id) => this.user && permissionOf(this.user, id)))
      this._push({ type: 'subscribed', deviceIds: [...this.devices] })
    }
  }
  close() {
    if (this.readyState === 3) return
    this.readyState = 3
    sockets.delete(this)
    setTimeout(() => this.onclose?.({ code: 1000 }), 0)
  }
  _push(msg) { setTimeout(() => { if (this.readyState === 1) this.onmessage?.({ data: JSON.stringify(msg) }) }, 0) }
}

function publish(deviceId, msg) {
  sockets.forEach((s) => { if (s.user && s.devices.has(deviceId)) s._push(msg) })
}

let wsDown = false
if (typeof window !== 'undefined') {
  // Công cụ thử trong console: __mock.dropWs() (giả lập mất mạng 8 s), __mock.offline(1), __mock.online(1)
  window.__mock = {
    dropWs(ms = 8000) { wsDown = true; [...sockets].forEach((s) => s.close()); setTimeout(() => { wsDown = false }, ms) },
    offline(id) { setOnline(id, false) },
    online(id) { setOnline(id, true) },
    tankLow() { sim.tank = 8 },
  }
}

function transition(dev, to, reason, actorId) {
  history.unshift({ deviceId: dev.id, fromStatus: dev.status, toStatus: to, reason, actorId, at: iso() })
  dev.status = to
  publish(dev.id, { type: 'device_status', deviceId: dev.id, status: dev.status, online: dev.online, lastSeenAt: dev.lastSeenAt })
}

function setOnline(id, on) {
  const d = devices.find((x) => x.id === id)
  if (!d) return
  d.online = on
  if (on) d.lastSeenAt = iso()
  if (d.status === 'ACTIVE' && !on) transition(d, 'OFFLINE', 'Mất tín hiệu > 90 s', null)
  else if (d.status === 'OFFLINE' && on) transition(d, 'ACTIVE', 'Có tín hiệu lại', null)
  else publish(d.id, { type: 'device_status', deviceId: d.id, status: d.status, online: d.online, lastSeenAt: d.lastSeenAt })
  if (!on) openAlert(d, 3, 'OFFLINE', 'CRITICAL', `${d.deviceCode} mất kết nối`, {})
  else alerts.filter((a) => a.deviceId === d.id && a.type === 'OFFLINE' && a.status !== 'CLOSED').forEach((a) => {
    Object.assign(a, { status: 'CLOSED', closedAt: iso(), closeNote: 'auto', conditionClearedAt: iso() })
    publish(d.id, { type: 'alert', id: a.id, deviceId: d.id, alertType: a.type, severity: a.severity, status: a.status, message: a.message })
  })
}

function openAlert(dev, ruleId, type, severity, message, context) {
  if (alerts.some((a) => a.deviceId === dev.id && a.ruleId === ruleId && a.status !== 'CLOSED')) return
  const a = { id: alerts.length + 1, ruleId, deviceId: dev.id, deviceCode: dev.deviceCode, type, severity, message, context, status: 'OPEN', openedAt: iso(), conditionClearedAt: null, ackBy: null, ackAt: null, closedBy: null, closedAt: null, closeNote: null, notifiedAt: iso() }
  alerts.unshift(a)
  publish(dev.id, { type: 'alert', id: a.id, deviceId: dev.id, alertType: type, severity, status: 'OPEN', message })
}

function pushEvent(dev, type, detail) {
  const e = { id: events.length + 1, deviceId: dev.id, seq: events.length + 1, type, detail, ts: iso() }
  events.unshift(e)
  publish(dev.id, { type: 'device_event', deviceId: dev.id, ts: e.ts, eventType: type, detail })
}

let ticking = false
function startTicker() {
  if (ticking || !MOCK.all || typeof window === 'undefined') return
  ticking = true
  setInterval(() => {
    devices.filter((d) => d.online && ['ACTIVE', 'FAULT', 'MAINTENANCE', 'PROVISIONED'].includes(d.status)).forEach((d) => {
      d.lastSeenAt = iso()
      if (d.type !== 'CONTROLLER') return
      const t = now()
      const wasLow = sim.tank < currentParams(d.id).tank_min
      if (sim.pump && t > sim.pumpUntil) { sim.pump = 0; pushEvent(d, 'pump_off', { source: 'remote' }) }
      const data = sample(t)
      store(d.id, t, data)
      if (!wasLow && sim.tank < currentParams(d.id).tank_min) {
        pushEvent(d, 'tank_low', { tank: Math.round(sim.tank) })
        openAlert(d, 4, 'EVENT', 'WARNING', `${d.deviceCode}: Bể sắp cạn (${Math.round(sim.tank)}%)`, { tank: Math.round(sim.tank) })
      }
      publish(d.id, { type: 'telemetry', deviceId: d.id, ts: iso(t), seq, buffered: false, data,
        state: { pump: sim.pump, fan: sim.fan, mode: sim.mode, locks: sim.locks } })
    })
  }, 3000)
}

// ---------------------------------------------------------------------------
// Ảnh / chẩn đoán (WP-07)

const LABELS = ['HEALTHY', 'YELLOW', 'SPOT']
const diagnoses = {} // deviceId -> list

function makeDiagnosis(deviceId, id, t, sick) {
  const tiles = []
  for (let r = 0; r < 3; r++) {
    for (let c = 0; c < 3; c++) {
      if (r === 2 && c === 2) continue // ô trống (active_tiles)
      let label = 'HEALTHY'
      if (sick && ((r === 0 && c === 1) || (r === 1 && c === 2))) label = r === 0 ? 'SPOT' : 'YELLOW'
      const conf = round(rnd(0.82, 0.97), 2)
      const probs = Object.fromEntries(LABELS.map((l) => [l, l === label ? conf : round((1 - conf) / 2, 2)]))
      tiles.push({ r, c, label: Math.random() < 0.05 ? 'UNKNOWN' : label, conf, probs })
    }
  }
  const abnormal = tiles.filter((x) => x.label === 'YELLOW' || x.label === 'SPOT').map((x) => [x.r, x.c])
  const top = abnormal.length ? tiles.find((x) => x.r === abnormal[0][0] && x.c === abnormal[0][1]) : { label: 'HEALTHY', conf: 0.93 }
  return { id, deviceId, capturedAt: iso(t), trigger: Math.random() < 0.3 ? 'command' : 'schedule', cmdId: null, status: 'DONE',
    modelVersion: 'mnv2-tomato-3c-v1', tiles, topLabel: top.label, topConfidence: top.conf, abnormalTiles: abnormal,
    reviewVerdict: null, correctLabel: null, reviewedBy: null, reviewedAt: null, createdAt: iso(t) }
}
function diagList(deviceId) {
  if (!diagnoses[deviceId]) {
    const list = []
    for (let i = 0; i < 8; i++) list.push(makeDiagnosis(deviceId, deviceId * 1000 + 8 - i, now() - i * 30 * 60e3, i < 3))
    diagnoses[deviceId] = list
  }
  return diagnoses[deviceId]
}
function findDiag(id) {
  const dev = Math.floor(id / 1000)
  return diagList(dev).find((d) => d.id === id)
}

function trayImage(d) {
  const sickAt = new Set((d.abnormalTiles || []).map(([r, c]) => `${r}-${c}`))
  let s = '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="450" viewBox="0 0 600 450">'
  s += '<rect width="600" height="450" fill="#6b4f3a"/>'
  for (let r = 0; r < 3; r++) {
    for (let c = 0; c < 3; c++) {
      const x = c * 200 + 100; const y = r * 150 + 75
      s += `<rect x="${x - 90}" y="${y - 68}" width="180" height="136" rx="10" fill="#4a3426"/>`
      if (r === 2 && c === 2) continue
      const sick = sickAt.has(`${r}-${c}`)
      const leaf = sick ? (r === 0 ? '#7a8f2b' : '#c9b52e') : '#3f9a3a'
      for (let k = 0; k < 5; k++) {
        const a = (k / 5) * Math.PI * 2
        s += `<ellipse cx="${x + Math.cos(a) * 30}" cy="${y + Math.sin(a) * 22}" rx="34" ry="16" fill="${leaf}" transform="rotate(${(a * 180) / Math.PI} ${x + Math.cos(a) * 30} ${y + Math.sin(a) * 22})"/>`
        if (sick && r === 0) s += `<circle cx="${x + Math.cos(a) * 34}" cy="${y + Math.sin(a) * 24}" r="5" fill="#3b2a12"/>`
      }
      s += `<circle cx="${x}" cy="${y}" r="9" fill="#2f6e2a"/>`
    }
  }
  s += '<text x="12" y="440" font-size="14" fill="#fff" font-family="sans-serif">ẢNH GIẢ LẬP</text></svg>'
  return new Blob([s], { type: 'image/svg+xml' })
}

export function isDiagnosisPath(path) {
  return /^\/devices\/\d+\/diagnoses$/.test(path) || path.startsWith('/diagnoses/')
}

// ---------------------------------------------------------------------------
// Bộ định tuyến

const ok = (data, status = 200) => ({ status, data })
const err = (status, code, message, details) => ({ status, data: { code, message, details: details || {}, traceId: 'mock' } })
const deviceOut = (d, user) => ({ ...clone(d), permission: permissionOf(user, d.id) })

function needDevice(user, id) {
  const d = devices.find((x) => x.id === id)
  if (!d || !permissionOf(user, id)) return [null, err(404, 'NOT_FOUND', 'Không tìm thấy thiết bị')]
  return [d, null]
}
function needControl(user, id, what) {
  const [d, e] = needDevice(user, id)
  if (e) return [null, e]
  if (permissionOf(user, id) !== 'CONTROL') {
    log(user, 'COMMAND_DENIED', 'device', id, { what }, false)
    return [null, err(403, 'FORBIDDEN', 'Cần quyền CONTROL trên thiết bị này')]
  }
  return [d, null]
}

const routes = []
const route = (method, pattern, fn, opts = {}) => {
  const keys = []
  const re = new RegExp('^' + pattern.replace(/:(\w+)/g, (_, k) => { keys.push(k); return '([^/]+)' }) + '$')
  routes.push({ method, re, keys, fn, pub: !!opts.pub })
}

route('POST', '/auth/login', ({ body }) => {
  const u = users.find((x) => x.username === body.username)
  if (u && fails[u.id] >= 5) return err(423, 'ACCOUNT_LOCKED', 'Tài khoản tạm khóa do đăng nhập sai nhiều lần', { lockedUntil: iso(now() + 15 * 60e3) })
  if (!u || body.password === 'sai') {
    if (u) fails[u.id] = (fails[u.id] || 0) + 1
    log(u, 'LOGIN_FAILED', null, null, null, false)
    return err(401, 'UNAUTHORIZED', 'Sai tên đăng nhập hoặc mật khẩu')
  }
  if (u.status !== 'ACTIVE') return err(403, 'FORBIDDEN', 'Tài khoản không hoạt động')
  fails[u.id] = 0
  log(u, 'LOGIN_SUCCESS')
  return ok(issue(u))
}, { pub: true })
route('POST', '/auth/refresh', ({ body }) => {
  // Tải lại trang làm mất dữ liệu giả trong bộ nhớ: chấp nhận token dạng mock-rt-<id>-… để giữ phiên.
  const uid = refreshes[body.refreshToken] || Number(/^mock-rt-(\d+)-/.exec(body.refreshToken || '')?.[1]) || null
  if (!uid) return err(401, 'UNAUTHORIZED', 'Phiên đã hết hạn, đăng nhập lại')
  delete refreshes[body.refreshToken]
  return ok(issue(users.find((u) => u.id === uid)))
}, { pub: true })
route('POST', '/auth/logout', ({ body, user }) => { delete refreshes[body.refreshToken]; log(user, 'LOGOUT'); return ok(null, 204) })
route('GET', '/users/me', ({ user }) => ok(clone(user)))
route('PATCH', '/users/me', ({ user, body }) => { Object.assign(user, body); return ok(clone(user)) })
route('POST', '/users/me/password', ({ user, body }) => {
  if (body.currentPassword === 'sai') return err(400, 'VALIDATION_ERROR', 'Mật khẩu hiện tại không đúng')
  log(user, 'PASSWORD_CHANGED')
  return ok(null, 204)
})

const adminOnly = (fn) => (ctx) => (ctx.user.role === 'ADMIN' ? fn(ctx) : err(403, 'FORBIDDEN', 'Chỉ dành cho quản trị viên'))

route('GET', '/users', adminOnly(({ query }) => ok(users.filter((u) => (!query.role || u.role === query.role)
  && (!query.status || u.status === query.status)
  && (!query.q || `${u.username} ${u.fullName || ''}`.toLowerCase().includes(query.q.toLowerCase()))).map(clone))))
route('POST', '/users', adminOnly(({ body, user }) => {
  if (users.some((u) => u.username === body.username)) return err(409, 'CONFLICT', 'Tên đăng nhập đã tồn tại')
  const u = { id: users.length + 1, username: body.username, fullName: body.fullName, email: body.email, role: body.role, status: 'ACTIVE', telegramChatId: null }
  users.push(u)
  log(user, 'USER_CREATED', 'user', u.id, { username: u.username, role: u.role })
  return ok(clone(u), 201)
}))
route('PATCH', '/users/:id', adminOnly(({ params, body, user }) => {
  const u = users.find((x) => x.id === Number(params.id))
  if (!u) return err(404, 'NOT_FOUND', 'Không tìm thấy người dùng')
  if (body.role && body.role !== u.role && u.id === user.id) return err(409, 'CONFLICT', 'Không tự đổi vai trò của chính mình')
  Object.assign(u, body)
  log(user, 'USER_UPDATED', 'user', u.id, body)
  return ok(clone(u))
}))
route('POST', '/users/:id/:action', adminOnly(({ params, user }) => {
  const u = users.find((x) => x.id === Number(params.id))
  if (!u) return err(404, 'NOT_FOUND', 'Không tìm thấy người dùng')
  if (params.action === 'reset-password') return ok({ userId: u.id, temporaryPassword: Math.random().toString(36).slice(2, 12), note: 'Mật khẩu tạm chỉ hiển thị một lần' })
  if (params.action === 'lock') {
    if (u.id === user.id) return err(409, 'CONFLICT', 'Không tự khóa chính mình')
    u.status = 'LOCKED'
  } else u.status = 'ACTIVE'
  log(user, params.action === 'lock' ? 'USER_LOCKED' : 'USER_UNLOCKED', 'user', u.id)
  return ok(clone(u))
}))

route('GET', '/devices', ({ user }) => ok(visibleDevices(user).map((d) => deviceOut(d, user))))
route('POST', '/devices', adminOnly(({ body, user }) => {
  const prefix = body.type === 'CAMERA' ? 'cam' : 'ctl'
  const n = devices.filter((d) => d.deviceCode.startsWith(prefix)).length + 1
  const d = { id: devices.length + 1, deviceCode: `${prefix}-${String(n).padStart(4, '0')}`, type: body.type, name: body.name, zoneId: body.zoneId || null,
    status: 'REGISTERED', online: false, hwVersion: body.hwVersion || null, fwVersion: null, lastSeenAt: null, firstSeenAt: null, currentConfigVersion: 0, note: null }
  devices.push(d)
  history.unshift({ deviceId: d.id, fromStatus: null, toStatus: 'REGISTERED', reason: 'Đăng ký', actorId: user.id, at: iso() })
  log(user, 'DEVICE_REGISTERED', 'device', d.id, { device_code: d.deviceCode })
  return ok(deviceOut(d, user), 201)
}))
route('GET', '/devices/:id', ({ params, user }) => {
  const [d, e] = needDevice(user, Number(params.id))
  return e || ok(deviceOut(d, user))
})
route('PATCH', '/devices/:id', adminOnly(({ params, body, user }) => {
  const d = devices.find((x) => x.id === Number(params.id))
  if (!d) return err(404, 'NOT_FOUND', 'Không tìm thấy thiết bị')
  Object.assign(d, body)
  return ok(deviceOut(d, user))
}))
const provisionOut = (d) => ({ deviceCode: d.deviceCode, secret: Array.from({ length: 32 }, () => 'abcdefghijkmnpqrstuvwxyz23456789'[(Math.random() * 32) | 0]).join(''),
  gardenCode: 'g01', mqttHost: '192.168.137.1', mqttPort: 1883, uploadUrl: 'http://192.168.137.1:8000/device-api/v1/images',
  note: 'Secret chỉ hiển thị một lần. Chép vào secrets.h rồi nạp firmware.' })
route('POST', '/devices/:id/provision', adminOnly(({ params, user }) => {
  const d = devices.find((x) => x.id === Number(params.id))
  if (d.status !== 'REGISTERED') return err(409, 'INVALID_STATE_TRANSITION', 'Chỉ cấp phát được thiết bị ở trạng thái REGISTERED; muốn đổi khóa hãy dùng rotate-secret')
  transition(d, 'PROVISIONED', 'Cấp phát khóa', user.id)
  log(user, 'DEVICE_PROVISIONED', 'device', d.id)
  // Giả lập: thiết bị kết nối sau 6 s → ACTIVE.
  setTimeout(() => { if (d.status === 'PROVISIONED') { d.online = true; d.firstSeenAt = d.firstSeenAt || iso(); d.lastSeenAt = iso(); d.fwVersion = '1.0.3'; transition(d, 'ACTIVE', 'Kết nối lần đầu', null) } }, 6000)
  return ok(provisionOut(d))
}))
route('POST', '/devices/:id/rotate-secret', adminOnly(({ params, user }) => {
  const d = devices.find((x) => x.id === Number(params.id))
  log(user, 'DEVICE_SECRET_ROTATED', 'device', d.id)
  return ok(provisionOut(d))
}))
route('POST', '/devices/:id/suspend', adminOnly(({ params, body, user }) => {
  const d = devices.find((x) => x.id === Number(params.id))
  if (d.status === 'SUSPENDED') return ok(deviceOut(d, user))
  d.online = false
  transition(d, 'SUSPENDED', body.reason, user.id)
  log(user, 'DEVICE_SUSPENDED', 'device', d.id, { reason: body.reason })
  return ok(deviceOut(d, user))
}))
route('POST', '/devices/:id/resume', adminOnly(({ params, body, user }) => {
  const d = devices.find((x) => x.id === Number(params.id))
  if (d.status !== 'SUSPENDED') return err(409, 'INVALID_STATE_TRANSITION', `Không chuyển được ${d.status} → PROVISIONED`)
  transition(d, 'PROVISIONED', body.reason, user.id)
  setTimeout(() => { if (d.status === 'PROVISIONED') { d.online = true; d.lastSeenAt = iso(); transition(d, 'ACTIVE', 'Kết nối lại', null) } }, 5000)
  log(user, 'DEVICE_RESUMED', 'device', d.id, { reason: body.reason })
  return ok(deviceOut(d, user))
}))
route('POST', '/devices/:id/decommission', adminOnly(({ params, body, user }) => {
  const d = devices.find((x) => x.id === Number(params.id))
  if (body.confirm !== d.deviceCode) return err(400, 'VALIDATION_ERROR', 'Nhập đúng mã thiết bị để xác nhận thu hồi')
  d.online = false
  transition(d, 'DECOMMISSIONED', body.reason, user.id)
  log(user, 'DEVICE_DECOMMISSIONED', 'device', d.id, { reason: body.reason })
  return ok(deviceOut(d, user))
}))
route('POST', '/devices/:id/maintenance', ({ params, body, user }) => {
  const [d, e] = needControl(user, Number(params.id), 'maintenance')
  if (e) return e
  transition(d, 'MAINTENANCE', body.reason, user.id)
  return ok({ id: d.id, status: d.status })
})
route('POST', '/devices/:id/maintenance/end', ({ params, body, user }) => {
  const [d, e] = needControl(user, Number(params.id), 'maintenance_end')
  if (e) return e
  if (d.status !== 'MAINTENANCE') return err(409, 'INVALID_STATE_TRANSITION', 'Thiết bị không ở trạng thái bảo trì')
  transition(d, d.online ? 'ACTIVE' : 'OFFLINE', body.reason, user.id)
  return ok({ id: d.id, status: d.status })
})
route('GET', '/devices/:id/history', ({ params, user }) => {
  const [d, e] = needDevice(user, Number(params.id))
  return e || ok(history.filter((h) => h.deviceId === d.id).map(({ deviceId, ...h }) => h))
})
route('GET', '/devices/:id/assignments', adminOnly(({ params }) => ok(assignments.filter((a) => a.deviceId === Number(params.id)).map((a) => {
  const u = users.find((x) => x.id === a.userId)
  return { userId: u.id, username: u.username, role: u.role, permission: u.role === 'VIEWER' ? 'VIEW' : a.permission }
}))))
route('POST', '/devices/:id/assignments', adminOnly(({ params, body }) => {
  const u = users.find((x) => x.id === body.userId)
  if (!u) return err(400, 'VALIDATION_ERROR', 'Người dùng không tồn tại')
  const perm = u.role === 'VIEWER' ? 'VIEW' : body.permission
  const a = assignments.find((x) => x.userId === u.id && x.deviceId === Number(params.id))
  if (a) a.permission = perm
  else assignments.push({ userId: u.id, deviceId: Number(params.id), permission: perm })
  return ok({ userId: u.id, username: u.username, role: u.role, permission: perm })
}))
route('DELETE', '/devices/:id/assignments/:uid', adminOnly(({ params }) => {
  const i = assignments.findIndex((x) => x.userId === Number(params.uid) && x.deviceId === Number(params.id))
  if (i >= 0) assignments.splice(i, 1)
  return ok(null, 204)
}))

route('GET', '/devices/:id/telemetry/latest', ({ params, user }) => {
  const [d, e] = needDevice(user, Number(params.id))
  if (e) return e
  const metrics = {}
  for (let i = telemetry.length - 1; i >= 0 && Object.keys(metrics).length < 7; i--) {
    const r = telemetry[i]
    if (r.deviceId === d.id && !metrics[r.metric]) metrics[r.metric] = { value: r.value, unit: '', ok: r.ok, ts: r.ts, seq: r.seq }
  }
  return ok({ deviceId: d.id, metrics, state: d.id === 1 ? { pump: sim.pump, fan: sim.fan, mode: sim.mode, locks: sim.locks } : null })
})
function rangeOf(query, hours = 1) {
  const to = query.to ? new Date(query.to).getTime() : now()
  const from = query.from ? new Date(query.from).getTime() : to - hours * 3600e3
  return [from, to]
}
route('GET', '/devices/:id/telemetry', ({ params, query, user }) => {
  const [d, e] = needDevice(user, Number(params.id))
  if (e) return e
  const metrics = (query.metric || 'soil,air_temp,air_hum,light,tank').split(',')
  const [from, to] = rangeOf(query)
  let interval = query.interval || 'auto'
  if (interval === 'auto') interval = to - from <= 2 * 86400e3 ? 'raw' : '1h'
  const series = Object.fromEntries(metrics.map((m) => [m, []]))
  const rows = telemetry.filter((r) => r.deviceId === d.id && metrics.includes(r.metric) && new Date(r.ts).getTime() >= from && new Date(r.ts).getTime() <= to)
  if (interval === 'raw') rows.forEach((r) => series[r.metric].push({ ts: r.ts, v: r.value, ok: r.ok }))
  else {
    const size = interval === '1h' ? 3600e3 : 86400e3
    const b = {}
    rows.forEach((r) => {
      const k = `${r.metric}|${Math.floor(new Date(r.ts).getTime() / size) * size}`
      ;(b[k] = b[k] || []).push(r.value)
    })
    Object.entries(b).sort().forEach(([k, vs]) => {
      const [m, t] = k.split('|')
      series[m].push({ ts: iso(Number(t)), min: Math.min(...vs), max: Math.max(...vs), avg: vs.reduce((a, x) => a + x, 0) / vs.length, count: vs.length })
    })
  }
  return ok({ deviceId: d.id, from: iso(from), to: iso(to), interval, series })
})
route('GET', '/devices/:id/telemetry/stats', ({ params, query, user }) => {
  const [d, e] = needDevice(user, Number(params.id))
  if (e) return e
  const [from, to] = rangeOf(query, 24)
  const vs = telemetry.filter((r) => r.deviceId === d.id && r.metric === query.metric && r.ok && new Date(r.ts).getTime() >= from && new Date(r.ts).getTime() <= to).map((r) => r.value)
  return ok({ metric: query.metric, from: iso(from), to: iso(to), min: vs.length ? Math.min(...vs) : null, max: vs.length ? Math.max(...vs) : null, avg: vs.length ? vs.reduce((a, x) => a + x, 0) / vs.length : null, count: vs.length })
})
route('GET', '/devices/:id/telemetry/export.csv', ({ params, query, user }) => {
  const [d, e] = needDevice(user, Number(params.id))
  if (e) return e
  const [from, to] = rangeOf(query, 24)
  const lines = ['ts,metric,value,unit,ok,seq', ...telemetry.filter((r) => r.deviceId === d.id && new Date(r.ts).getTime() >= from && new Date(r.ts).getTime() <= to)
    .map((r) => `${r.ts},${r.metric},${r.value},,${r.ok},${r.seq}`)]
  return { status: 200, data: new Blob(['﻿' + lines.join('\n')], { type: 'text/csv' }), headers: new Headers({ 'Content-Disposition': `attachment; filename="${d.deviceCode}.csv"` }) }
})
route('GET', '/devices/:id/events', ({ params, user }) => {
  const [d, e] = needDevice(user, Number(params.id))
  return e || ok(events.filter((x) => x.deviceId === d.id).map(({ deviceId, ...x }) => x))
})

route('POST', '/devices/:id/commands', ({ params, body, user }) => {
  const [d, e] = needControl(user, Number(params.id), body.action)
  if (e) return e
  if (!d.online) return err(409, 'DEVICE_OFFLINE', 'Thiết bị đang offline')
  if (!['ACTIVE', 'FAULT', 'MAINTENANCE'].includes(d.status)) return err(409, 'INVALID_STATE', `Thiết bị đang ${d.status}, không nhận lệnh`)
  const recent = commands.filter((c) => c.deviceId === d.id && now() - new Date(c.issuedAt).getTime() < 60e3)
  if (recent.length >= 10) return err(429, 'RATE_LIMITED', 'Tối đa 10 lệnh/phút cho mỗi thiết bị')
  const c = { cmdId: uuid(), deviceId: d.id, action: body.action, params: body.params || {}, status: 'PENDING', result: null, detail: null, issuedBy: user.id, issuedAt: iso(), ackAt: null }
  commands.unshift(c)
  log(user, 'COMMAND_SENT', 'device', d.id, { cmd_id: c.cmdId, action: c.action, params: c.params })
  setTimeout(() => {
    const cfg = currentParams(d.id)
    if (c.action === 'pump_on' && sim.tank < cfg.tank_min) { c.status = 'REJECTED'; c.result = 'blocked_no_water' } else {
      c.status = 'EXECUTED'; c.result = 'executed'
      if (c.action === 'pump_on') { sim.pump = 1; sim.pumpUntil = now() + Math.min(c.params.duration_s, cfg.pump_max_s) * 1000; pushEvent(d, 'pump_on', { source: 'remote', duration_s: c.params.duration_s }) }
      if (c.action === 'pump_off' && sim.pump) { sim.pump = 0; pushEvent(d, 'pump_off', { source: 'remote' }) }
      if (c.action === 'fan_on') { sim.fan = 1; pushEvent(d, 'fan_on', { source: 'remote' }) }
      if (c.action === 'fan_off') { sim.fan = 0; pushEvent(d, 'fan_off', { source: 'remote' }) }
      if (c.action === 'set_mode') sim.mode = c.params.mode
      if (c.action === 'capture') {
        const list = diagList(d.id)
        const dg = makeDiagnosis(d.id, list[0].id + 1, now(), Math.random() < 0.5)
        dg.trigger = 'command'
        list.unshift(dg)
        setTimeout(() => publish(d.id, { type: 'diagnosis', id: dg.id, deviceId: d.id, topLabel: dg.topLabel, confidence: dg.topConfidence, abnormalTiles: dg.abnormalTiles }), 2000)
      }
    }
    c.ackAt = iso()
    publish(d.id, { type: 'command_update', cmdId: c.cmdId, deviceId: d.id, status: c.status, result: c.result, detail: c.detail, action: c.action })
  }, 900)
  return ok({ cmdId: c.cmdId, status: 'PENDING' }, 202)
})
route('GET', '/devices/:id/commands', ({ params, user }) => {
  const [d, e] = needDevice(user, Number(params.id))
  return e || ok(commands.filter((c) => c.deviceId === d.id).slice(0, 50))
})
route('GET', '/commands/:id', ({ params, user }) => {
  const c = commands.find((x) => x.cmdId === params.id)
  if (!c || !permissionOf(user, c.deviceId)) return err(404, 'NOT_FOUND', 'Không tìm thấy lệnh')
  return ok(c)
})
route('GET', '/devices/:id/config', ({ params, user }) => {
  const [d, e] = needDevice(user, Number(params.id))
  if (e) return e
  const latest = configs.filter((c) => c.deviceId === d.id).sort((a, b) => b.configVersion - a.configVersion)[0] || null
  return ok({ deviceId: d.id, deviceConfigVersion: d.currentConfigVersion, params: clone(currentParams(d.id)), latest: latest && clone(latest) })
})
route('PUT', '/devices/:id/config', ({ params, body, user }) => {
  const [d, e] = needControl(user, Number(params.id), 'config')
  if (e) return e
  const merged = { ...currentParams(d.id), ...body.params }
  if (d.type === 'CONTROLLER' && merged.soil_low >= merged.soil_high) return err(400, 'VALIDATION_ERROR', 'soil_low phải nhỏ hơn soil_high', { field: 'soil_low' })
  const ver = Math.max(0, ...configs.filter((c) => c.deviceId === d.id).map((c) => c.configVersion), d.currentConfigVersion) + 1
  const c = { id: configs.length + 1, deviceId: d.id, configVersion: ver, params: merged, status: 'PENDING', createdBy: user.id, createdAt: iso(), appliedAt: null, rejectDetail: null }
  configs.push(c)
  log(user, 'CONFIG_CHANGED', 'device', d.id, { config_version: ver, changes: body.params })
  if (d.online) {
    setTimeout(() => {
      c.status = 'APPLIED'; c.appliedAt = iso(); d.currentConfigVersion = ver
      publish(d.id, { type: 'config_update', deviceId: d.id, configVersion: ver, status: 'APPLIED', detail: null })
    }, 1500)
  }
  return ok(clone(c), 202)
})
route('GET', '/devices/:id/config/history', ({ params, user }) => {
  const [d, e] = needDevice(user, Number(params.id))
  return e || ok(configs.filter((c) => c.deviceId === d.id).sort((a, b) => b.configVersion - a.configVersion).map(clone))
})

route('GET', '/alerts', ({ query, user }) => {
  const st = query.status ? query.status.split(',') : null
  const list = alerts.filter((a) => permissionOf(user, a.deviceId) && (!st || st.includes(a.status))
    && (!query.severity || a.severity === query.severity) && (!query.deviceId || a.deviceId === Number(query.deviceId)))
  const page = Number(query.page || 0); const size = Number(query.size || 20)
  return ok({ items: list.slice(page * size, page * size + size).map(clone), page, size, total: list.length })
})
route('POST', '/alerts/:id/:action', ({ params, body, user }) => {
  const a = alerts.find((x) => x.id === Number(params.id))
  if (!a || !permissionOf(user, a.deviceId)) return err(404, 'NOT_FOUND', 'Không tìm thấy cảnh báo')
  if (permissionOf(user, a.deviceId) !== 'CONTROL') return err(403, 'FORBIDDEN', 'Cần quyền CONTROL trên thiết bị này')
  if (params.action === 'acknowledge') {
    if (a.status !== 'OPEN') return err(409, 'INVALID_STATE_TRANSITION', `Cảnh báo đang ${a.status}`)
    Object.assign(a, { status: 'ACKNOWLEDGED', ackBy: user.id, ackAt: iso() })
  } else {
    if (a.status === 'CLOSED') return err(409, 'INVALID_STATE_TRANSITION', 'Cảnh báo đã đóng')
    Object.assign(a, { status: 'CLOSED', closedBy: user.id, closedAt: iso(), closeNote: body?.note || null })
  }
  publish(a.deviceId, { type: 'alert', id: a.id, deviceId: a.deviceId, alertType: a.type, severity: a.severity, status: a.status, message: a.message })
  return ok(clone(a))
})
route('GET', '/alert-rules', () => ok(clone(rules)))
route('POST', '/alert-rules', adminOnly(({ body }) => { const r = { ...body, id: rules.length + 1 }; rules.push(r); return ok(r, 201) }))
route('PATCH', '/alert-rules/:id', adminOnly(({ params, body }) => { const r = rules.find((x) => x.id === Number(params.id)); Object.assign(r, body); return ok(clone(r)) }))
route('DELETE', '/alert-rules/:id', adminOnly(({ params }) => { rules.find((x) => x.id === Number(params.id)).enabled = false; return ok(null, 204) }))
route('GET', '/audit-logs', adminOnly(({ query }) => {
  const list = audit.filter((r) => (!query.actorId || r.actorId === Number(query.actorId)) && (!query.action || r.action === query.action))
  const page = Number(query.page || 0); const size = Number(query.size || 50)
  return ok({ items: list.slice(page * size, page * size + size), page, size, total: list.length })
}))
route('GET', '/dashboard/summary', ({ user }) => {
  const list = visibleDevices(user).filter((d) => d.status !== 'DECOMMISSIONED')
  const byStatus = {}
  list.forEach((d) => { byStatus[d.status] = (byStatus[d.status] || 0) + 1 })
  return ok({
    devices: list.map((d) => ({ id: d.id, deviceCode: d.deviceCode, name: d.name, type: d.type, status: d.status, online: d.online, lastSeenAt: d.lastSeenAt,
      permission: permissionOf(user, d.id), state: d.id === 1 ? { pump: sim.pump, fan: sim.fan, mode: sim.mode, locks: sim.locks } : null })),
    countByStatus: byStatus,
    onlineCount: list.filter((d) => d.online).length,
    openAlerts: alerts.filter((a) => permissionOf(user, a.deviceId) && a.status !== 'CLOSED').map(clone),
  })
})

// Chẩn đoán — dùng được cả khi chạy với backend thật (chỉ MOCK.diagnoses), nên không bắt buộc user giả.
route('GET', '/devices/:id/diagnoses', ({ params, query }) => {
  const list = diagList(Number(params.id)).filter((d) => !query.label || d.topLabel === query.label)
  const size = Number(query.size || 20)
  return ok({ items: list.slice(0, size).map(({ tiles, ...d }) => d), page: 0, size, total: list.length })
}, { pub: true, diag: true })
route('GET', '/diagnoses/:id', ({ params }) => {
  const d = findDiag(Number(params.id))
  return d ? ok(clone(d)) : err(404, 'NOT_FOUND', 'Không tìm thấy chẩn đoán')
}, { pub: true })
route('GET', '/diagnoses/:id/image', ({ params }) => {
  const d = findDiag(Number(params.id))
  return d ? { status: 200, data: trayImage(d) } : err(404, 'NOT_FOUND', 'Không tìm thấy ảnh')
}, { pub: true })
route('POST', '/diagnoses/:id/review', ({ params, body }) => {
  const d = findDiag(Number(params.id))
  if (!d) return err(404, 'NOT_FOUND', 'Không tìm thấy chẩn đoán')
  Object.assign(d, { reviewVerdict: body.verdict, correctLabel: body.correctLabel || null, reviewedAt: iso() })
  return ok(clone(d))
}, { pub: true })

export async function mockFetch(method, path, query, body, token) {
  startTicker()
  await new Promise((r) => setTimeout(r, 80 + Math.random() * 120)) // độ trễ mạng giả
  for (const r of routes) {
    if (r.method !== method) continue
    const m = r.re.exec(path)
    if (!m) continue
    const params = Object.fromEntries(r.keys.map((k, i) => [k, decodeURIComponent(m[i + 1])]))
    const user = whoami(token)
    if (!r.pub && !user) return err(401, 'UNAUTHORIZED', 'Thiếu hoặc sai token')
    try {
      return r.fn({ params, query: query || {}, body: body || {}, user })
    } catch (e) {
      console.error('[mock]', e) // eslint-disable-line no-console
      return err(500, 'INTERNAL_ERROR', 'Lỗi máy chủ giả')
    }
  }
  return err(404, 'NOT_FOUND', `Máy chủ giả chưa có ${method} ${path}`)
}
