import { useState } from 'react'
import { AuthProvider, useAuth } from './auth.jsx'
import { DevicesProvider } from './devices.jsx'
import { match, navigate, useRoute } from './router.js'
import { ConnectionBanner, Spinner, ToastProvider } from './components/ui.jsx'
import { MOCK } from './config.js'
import { ROLE } from './labels.js'
import Login from './pages/Login.jsx'
import Dashboard from './pages/Dashboard.jsx'
import DeviceDetail from './pages/DeviceDetail.jsx'
import Alerts from './pages/Alerts.jsx'
import History from './pages/History.jsx'
import Diagnoses from './pages/Diagnoses.jsx'
import Profile from './pages/Profile.jsx'
import AdminDevices from './pages/AdminDevices.jsx'
import AdminUsers from './pages/AdminUsers.jsx'
import AlertRules from './pages/AlertRules.jsx'
import AuditLog from './pages/AuditLog.jsx'

const MENU = [
  { path: '/', text: 'Tổng quan', icon: '◧' },
  { path: '/alerts', text: 'Cảnh báo', icon: '⚠' },
  { path: '/history', text: 'Lịch sử dữ liệu', icon: '📈' },
  { path: '/diagnoses', text: 'Ảnh & chẩn đoán', icon: '🌿' },
  { path: '/rules', text: 'Luật cảnh báo', icon: '⚙' },
  { path: '/admin/devices', text: 'Quản lý thiết bị', icon: '🛠', admin: true },
  { path: '/admin/users', text: 'Người dùng', icon: '👥', admin: true },
  { path: '/admin/audit', text: 'Nhật ký audit', icon: '📜', admin: true },
  { path: '/profile', text: 'Hồ sơ', icon: '👤' },
]

const ROUTES = [
  ['/', Dashboard],
  ['/devices/:id', DeviceDetail],
  ['/alerts', Alerts],
  ['/history', History],
  ['/diagnoses', Diagnoses],
  ['/rules', AlertRules],
  ['/profile', Profile],
  ['/admin/devices', AdminDevices, true],
  ['/admin/users', AdminUsers, true],
  ['/admin/audit', AuditLog, true],
]

function Shell() {
  const { user, ready, logout, isAdmin } = useAuth()
  const { path, query } = useRoute()
  const [menuOpen, setMenuOpen] = useState(false)

  if (!ready) return <div className="center-page"><Spinner label="Đang khôi phục phiên…" /></div>
  if (!user) return <Login />

  let page = <div className="card"><h2>Không tìm thấy trang</h2><a href="#/">Về trang tổng quan</a></div>
  for (const [pattern, Comp, adminOnly] of ROUTES) {
    const params = match(pattern, path)
    if (params) {
      page = adminOnly && !isAdmin
        ? <div className="card"><h2>Không đủ quyền</h2><p>Chức năng này chỉ dành cho quản trị viên.</p></div>
        : <Comp params={params} query={query} />
      break
    }
  }
  const active = (p) => (p === '/' ? path === '/' || path.startsWith('/devices/') : path.startsWith(p))

  return (
    <DevicesProvider>
      <div className="layout">
        <aside className={`sidebar ${menuOpen ? 'open' : ''}`}>
          <div className="brand">🌱 Vườn ươm</div>
          <nav onClick={() => setMenuOpen(false)}>
            {MENU.filter((m) => !m.admin || isAdmin).map((m) => (
              <a key={m.path} href={`#${m.path}`} className={active(m.path) ? 'active' : ''}>
                <span className="icon" aria-hidden="true">{m.icon}</span>{m.text}
              </a>
            ))}
          </nav>
          <div className="who">
            <div><b>{user.fullName || user.username}</b></div>
            <div className="muted">{user.username} · {ROLE[user.role] || user.role}</div>
            <button className="btn small" onClick={() => { logout(); navigate('/') }}>Đăng xuất</button>
          </div>
        </aside>
        <div className="main">
          <div className="topbar">
            <button className="btn small menu-btn" onClick={() => setMenuOpen((v) => !v)} aria-label="Mở menu">☰</button>
            <span className="topbar-title">Hệ thống chăm sóc vườn ươm</span>
            {MOCK.all && <span className="badge badge-warn">Dữ liệu giả</span>}
            <span className="muted topbar-user">{user.username} · {ROLE[user.role]}</span>
          </div>
          <ConnectionBanner />
          <main className="content">{page}</main>
        </div>
      </div>
    </DevicesProvider>
  )
}

export default function App() {
  return (
    <ToastProvider>
      <AuthProvider>
        <Shell />
      </AuthProvider>
    </ToastProvider>
  )
}
