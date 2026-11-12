// WebSocket /ws (đặc tả §10.11): auth trong 5 s → subscribe deviceIds (số nguyên) → nhận bản tin.
// Mất kết nối: báo trạng thái để hiện banner, tự kết nối lại lùi dần 1 → 30 s (WP-04 §3.7).
import { MOCK, WS_PATH } from '../config.js'
import { getAccessToken, refreshSession } from './client.js'
import { MockSocket } from '../mock/server.js'

const listeners = new Set()        // (msg) => void
const statusListeners = new Set()  // (state) => void; state: 'idle' | 'connecting' | 'open' | 'down'
let ws = null
let state = 'idle'
let wanted = new Set()
let backoff = 1000
let retryTimer = null
let stopped = true
let everOpened = false

function setState(s) {
  state = s
  statusListeners.forEach((fn) => fn(s))
}

function url() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${location.host}${WS_PATH}`
}

function send(obj) {
  if (ws && ws.readyState === 1) ws.send(JSON.stringify(obj))
}

function subscribe() {
  send({ type: 'subscribe', deviceIds: [...wanted] })
}

function connect() {
  if (stopped) return
  clearTimeout(retryTimer)
  setState('connecting')
  const sock = MOCK.all ? new MockSocket() : new WebSocket(url())
  ws = sock
  let authed = false
  sock.onopen = () => {
    const token = getAccessToken()
    if (!token) { sock.close(); return }
    sock.send(JSON.stringify({ type: 'auth', token }))
  }
  sock.onmessage = (ev) => {
    let msg
    try { msg = JSON.parse(ev.data) } catch { return }
    if (msg.type === 'auth_ok') {
      if (!authed) {
        authed = true
        backoff = 1000
        const reconnected = everOpened
        everOpened = true
        setState('open')
        subscribe()
        if (reconnected) listeners.forEach((fn) => fn({ type: 'reconnected' }))
      }
      return
    }
    if (msg.type === 'auth_expired' || msg.type === 'auth_error') {
      refreshSession().then(() => send({ type: 'auth', token: getAccessToken() })).catch(() => sock.close())
      return
    }
    listeners.forEach((fn) => fn(msg))
  }
  sock.onclose = () => {
    if (ws !== sock) return
    ws = null
    if (stopped) { setState('idle'); return }
    setState('down')
    retryTimer = setTimeout(connect, backoff)
    backoff = Math.min(backoff * 2, 30000)
  }
  sock.onerror = () => { /* onclose xử lý */ }
}

export const realtime = {
  start() {
    if (!stopped) return
    stopped = false
    everOpened = false
    backoff = 1000
    connect()
  },
  stop() {
    stopped = true
    clearTimeout(retryTimer)
    wanted = new Set()
    if (ws) { const s = ws; ws = null; s.close() }
    setState('idle')
  },
  /** Thêm thiết bị cần nhận dữ liệu (gộp với danh sách cũ). */
  watch(ids) {
    let changed = false
    ids.forEach((id) => {
      const n = Number(id)
      if (Number.isInteger(n) && !wanted.has(n)) { wanted.add(n); changed = true }
    })
    if (changed) subscribe()
  },
  /** Gửi lại token mới sau khi refresh (không bắt buộc, server sẽ báo auth_expired). */
  reauth() {
    const t = getAccessToken()
    if (t) send({ type: 'auth', token: t })
  },
  on(fn) { listeners.add(fn); return () => listeners.delete(fn) },
  onStatus(fn) { statusListeners.add(fn); fn(state); return () => statusListeners.delete(fn) },
  get state() { return state },
}
