// Gọi REST API (đặc tả §10). Access token chỉ giữ trong bộ nhớ, refresh token trong sessionStorage (WP-04 §3.4).
import { API_BASE, MOCK } from '../config.js'
import { mockFetch, isDiagnosisPath } from '../mock/server.js'

const RT_KEY = 'vuonuom.refreshToken'

let accessToken = null
let refreshTimer = null
let refreshing = null
let onSessionEnd = () => {}
let onSession = () => {}

export class ApiError extends Error {
  constructor(status, body) {
    super(messageOf(status, body))
    this.status = status
    this.code = body?.code || 'ERROR'
    this.details = body?.details || {}
  }
}

function messageOf(status, body) {
  const errs = body?.details?.errors
  if (Array.isArray(errs) && errs.length) {
    return `${body.message || 'Dữ liệu không hợp lệ'}: ` + errs.map((e) => `${e.field} — ${e.message}`).join('; ')
  }
  if (body?.message) return body.message
  if (status === 0) return 'Không kết nối được máy chủ'
  return `Lỗi ${status}`
}

function readRefresh() {
  try { return sessionStorage.getItem(RT_KEY) } catch { return null }
}
function writeRefresh(v) {
  try { v ? sessionStorage.setItem(RT_KEY, v) : sessionStorage.removeItem(RT_KEY) } catch { /* trình duyệt chặn */ }
}

export function getAccessToken() { return accessToken }
export function hasRefreshToken() { return !!readRefresh() }

/** Đăng ký hàm được gọi khi có phiên mới (user) và khi phiên kết thúc. */
export function onAuthChange(sessionCb, endCb) {
  onSession = sessionCb
  onSessionEnd = endCb
}

function setSession(tok) {
  accessToken = tok.accessToken
  writeRefresh(tok.refreshToken)
  clearTimeout(refreshTimer)
  // Làm mới chủ động trước khi hết hạn (80% thời gian sống), WS cũng dùng token mới.
  const ms = Math.max(10, (tok.expiresIn || 900) * 0.8) * 1000
  refreshTimer = setTimeout(() => { refreshSession().catch(() => {}) }, ms)
  onSession(tok.user, accessToken)
}

export function clearSession() {
  accessToken = null
  writeRefresh(null)
  clearTimeout(refreshTimer)
}

async function transport(method, path, { body, query, raw } = {}) {
  let url = API_BASE + path
  if (query) {
    const qs = new URLSearchParams()
    Object.entries(query).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') qs.append(k, v)
    })
    const s = qs.toString()
    if (s) url += '?' + s
  }
  if (MOCK.all || (MOCK.diagnoses && isDiagnosisPath(path))) {
    return mockFetch(method, path, query || {}, body, accessToken, raw)
  }
  const headers = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`
  let res
  try {
    res = await fetch(url, { method, headers, body: body !== undefined ? JSON.stringify(body) : undefined })
  } catch {
    return { status: 0, data: null }
  }
  if (raw && res.ok) return { status: res.status, data: await res.blob(), headers: res.headers }
  let data = null
  const text = await res.text()
  if (text) {
    try { data = JSON.parse(text) } catch { data = { message: text.slice(0, 200) } }
  }
  return { status: res.status, data, headers: res.headers }
}

/** Gọi API. Gặp 401 thì refresh một lần rồi thử lại; vẫn 401 thì kết thúc phiên. */
export async function api(method, path, opts = {}) {
  let r = await transport(method, path, opts)
  if (r.status === 401 && !path.startsWith('/auth/')) {
    const ok = await refreshSession().then(() => true, () => false)
    if (ok) r = await transport(method, path, opts)
    if (r.status === 401) {
      clearSession()
      onSessionEnd('Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại')
    }
  }
  if (r.status < 200 || r.status >= 300) throw new ApiError(r.status, r.data)
  return r.data
}

export const get = (p, query) => api('GET', p, { query })
export const post = (p, body = {}) => api('POST', p, { body })
export const put = (p, body = {}) => api('PUT', p, { body })
export const patch = (p, body = {}) => api('PATCH', p, { body })
export const del = (p) => api('DELETE', p)
export const getBlob = (p, query) => api('GET', p, { query, raw: true })

export async function login(username, password) {
  const r = await transport('POST', '/auth/login', { body: { username, password } })
  if (r.status !== 200) throw new ApiError(r.status, r.data)
  setSession(r.data)
  return r.data.user
}

/** Dùng refresh token để lấy cặp token mới. Nhiều lời gọi cùng lúc chỉ refresh một lần. */
export function refreshSession() {
  if (refreshing) return refreshing
  const rt = readRefresh()
  if (!rt) return Promise.reject(new ApiError(401, { message: 'Chưa đăng nhập' }))
  refreshing = transport('POST', '/auth/refresh', { body: { refreshToken: rt } })
    .then((r) => {
      if (r.status !== 200) {
        // Lỗi mạng: giữ refresh token để thử lại sau; 401: token đã hết hiệu lực.
        if (r.status === 401) clearSession()
        throw new ApiError(r.status, r.data)
      }
      setSession(r.data)
      return r.data.user
    })
    .finally(() => { refreshing = null })
  return refreshing
}

export async function logout() {
  const rt = readRefresh()
  if (rt && accessToken) {
    await transport('POST', '/auth/logout', { body: { refreshToken: rt } }).catch(() => {})
  }
  clearSession()
}

/** Tải tệp (CSV, ảnh) có kèm Authorization, rồi cho trình duyệt lưu. */
export async function download(path, query, fallbackName) {
  const r = await transport('GET', path, { query, raw: true })
  if (r.status === 401) {
    await refreshSession()
    return download(path, query, fallbackName)
  }
  if (r.status !== 200) throw new ApiError(r.status, r.data)
  const cd = r.headers?.get?.('Content-Disposition') || ''
  const m = /filename="?([^";]+)"?/.exec(cd)
  const a = document.createElement('a')
  a.href = URL.createObjectURL(r.data)
  a.download = m ? m[1] : fallbackName
  document.body.appendChild(a)
  a.click()
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove() }, 1000)
}
