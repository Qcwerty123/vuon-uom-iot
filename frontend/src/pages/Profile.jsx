import { useState } from 'react'
import { patch, post } from '../api/client.js'
import { useAuth } from '../auth.jsx'
import { Card, ErrorBox, useToast } from '../components/ui.jsx'
import { ROLE } from '../labels.js'

export default function Profile() {
  const { user, setUser, logout } = useAuth()
  const toast = useToast()
  const [info, setInfo] = useState({ fullName: user.fullName || '', email: user.email || '', telegramChatId: user.telegramChatId || '' })
  const [pw, setPw] = useState({ currentPassword: '', newPassword: '', confirm: '' })
  const [err1, setErr1] = useState(null)
  const [err2, setErr2] = useState(null)
  const [busy, setBusy] = useState(false)

  const saveInfo = async (e) => {
    e.preventDefault()
    setErr1(null)
    if (info.telegramChatId && !/^-?\d{3,20}$/.test(info.telegramChatId.trim())) {
      setErr1('Telegram chat id là một dãy số (có thể có dấu - ở đầu)'); return
    }
    try {
      const u = await patch('/users/me', {
        fullName: info.fullName.trim() || null,
        email: info.email.trim() || null,
        telegramChatId: info.telegramChatId.trim() || null,
      })
      setUser(u)
      toast('Đã lưu hồ sơ', 'ok')
    } catch (ex) { setErr1(ex) }
  }

  const changePw = async (e) => {
    e.preventDefault()
    setErr2(null)
    if (pw.newPassword.length < 8) { setErr2('Mật khẩu mới phải có ít nhất 8 ký tự'); return }
    if (pw.newPassword !== pw.confirm) { setErr2('Nhập lại mật khẩu mới không khớp'); return }
    setBusy(true)
    try {
      await post('/users/me/password', { currentPassword: pw.currentPassword, newPassword: pw.newPassword })
      toast('Đã đổi mật khẩu. Vui lòng đăng nhập lại.', 'ok')
      // Backend thu hồi mọi refresh token → đăng nhập lại cho chắc chắn.
      await logout()
    } catch (ex) { setErr2(ex) } finally { setBusy(false) }
  }

  return (
    <div className="stack">
      <div className="page-head"><h1>Hồ sơ cá nhân</h1></div>
      <div className="grid two">
        <Card title="Thông tin">
          <form className="form" onSubmit={saveInfo}>
            <dl className="kv">
              <dt>Tên đăng nhập</dt><dd className="mono">{user.username}</dd>
              <dt>Vai trò</dt><dd>{ROLE[user.role]}</dd>
            </dl>
            <label>Họ tên<input maxLength={120} value={info.fullName} onChange={(e) => setInfo({ ...info, fullName: e.target.value })} /></label>
            <label>Email<input type="email" maxLength={120} value={info.email} onChange={(e) => setInfo({ ...info, email: e.target.value })} /></label>
            <label>Telegram chat id
              <input inputMode="numeric" maxLength={40} value={info.telegramChatId} onChange={(e) => setInfo({ ...info, telegramChatId: e.target.value })} />
              <span className="hint">Nhắn <code>/start</code> cho bot Telegram của hệ thống để nhận chat id, rồi dán vào đây để nhận cảnh báo.</span>
            </label>
            <ErrorBox error={err1} />
            <div className="row end"><button className="btn primary">Lưu</button></div>
          </form>
        </Card>
        <Card title="Đổi mật khẩu">
          <form className="form" onSubmit={changePw}>
            <label>Mật khẩu hiện tại<input type="password" autoComplete="current-password" value={pw.currentPassword} onChange={(e) => setPw({ ...pw, currentPassword: e.target.value })} /></label>
            <label>Mật khẩu mới (ít nhất 8 ký tự)<input type="password" autoComplete="new-password" value={pw.newPassword} onChange={(e) => setPw({ ...pw, newPassword: e.target.value })} /></label>
            <label>Nhập lại mật khẩu mới<input type="password" autoComplete="new-password" value={pw.confirm} onChange={(e) => setPw({ ...pw, confirm: e.target.value })} /></label>
            <p className="muted small">Đổi xong, mọi phiên đăng nhập khác của bạn bị đăng xuất.</p>
            <ErrorBox error={err2} />
            <div className="row end"><button className="btn primary" disabled={busy}>Đổi mật khẩu</button></div>
          </form>
        </Card>
      </div>
    </div>
  )
}
