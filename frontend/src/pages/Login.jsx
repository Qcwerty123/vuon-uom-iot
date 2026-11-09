import { useState } from 'react'
import { useAuth } from '../auth.jsx'
import { ErrorBox } from '../components/ui.jsx'
import { MOCK } from '../config.js'
import { fmtTime } from '../labels.js'

export default function Login() {
  const { login, notice } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const submit = async (e) => {
    e.preventDefault()
    if (!username.trim() || !password) { setError('Nhập tên đăng nhập và mật khẩu'); return }
    setBusy(true)
    setError(null)
    try {
      await login(username.trim(), password)
    } catch (ex) {
      if (ex.status === 423) {
        const until = ex.details?.lockedUntil
        setError(`Tài khoản tạm khóa do đăng nhập sai nhiều lần${until ? `, thử lại sau ${fmtTime(until)}` : ''}.`)
      } else if (ex.status === 401) {
        setError('Sai tên đăng nhập hoặc mật khẩu.')
      } else {
        setError(ex.message)
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="center-page login-page">
      <form className="card login-card form" onSubmit={submit}>
        <div className="login-brand">🌱</div>
        <h1>Vườn ươm thông minh</h1>
        <p className="muted">Đăng nhập để theo dõi và điều khiển vườn ươm</p>
        {notice && <div className="alert-box info">{notice}</div>}
        <label>Tên đăng nhập
          <input autoFocus autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} />
        </label>
        <label>Mật khẩu
          <input type="password" autoComplete="current-password" value={password}
            onChange={(e) => setPassword(e.target.value)} />
        </label>
        <ErrorBox error={error} />
        <button className="btn primary block" disabled={busy}>{busy ? 'Đang đăng nhập…' : 'Đăng nhập'}</button>
        {MOCK.all && (
          <p className="muted small">Chế độ dữ liệu giả: admin / operator / viewer, mật khẩu bất kỳ (gõ “sai” để thử lỗi).</p>
        )}
      </form>
    </div>
  )
}
