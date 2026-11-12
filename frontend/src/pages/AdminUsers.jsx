import { useCallback, useEffect, useState } from 'react'
import { get, patch, post } from '../api/client.js'
import { useAuth } from '../auth.jsx'
import { Card, CopyButton, Empty, ErrorBox, Modal, Spinner, StatusBadge, useToast } from '../components/ui.jsx'
import { ROLE, USER_STATUS } from '../labels.js'

export default function AdminUsers() {
  const { user: me } = useAuth()
  const toast = useToast()
  const [filters, setFilters] = useState({ role: '', status: '', q: '' })
  const [list, setList] = useState(null)
  const [error, setError] = useState(null)
  const [dialog, setDialog] = useState(null)
  const [tempPw, setTempPw] = useState(null)

  const load = useCallback(async () => {
    try { setList(await get('/users', filters)); setError(null) } catch (e) { setError(e) }
  }, [filters])
  useEffect(() => { const t = setTimeout(load, 250); return () => clearTimeout(t) }, [load])

  const act = async (u, action, okText) => {
    try { await post(`/users/${u.id}/${action}`); toast(okText, 'ok'); load() } catch (e) { setError(e) }
  }
  const reset = async (u) => {
    if (!window.confirm(`Đặt mật khẩu tạm cho ${u.username}? Các phiên đăng nhập của họ sẽ bị đăng xuất.`)) return
    try { setTempPw({ username: u.username, ...(await post(`/users/${u.id}/reset-password`)) }) } catch (e) { setError(e) }
  }

  return (
    <div className="stack">
      <div className="page-head">
        <h1>Người dùng</h1>
        <button className="btn primary" onClick={() => setDialog({ kind: 'create' })}>+ Thêm người dùng</button>
      </div>
      <Card>
        <div className="row wrap gap-s filters">
          <label className="inline">Tìm<input value={filters.q} onChange={(e) => setFilters({ ...filters, q: e.target.value })} placeholder="tên đăng nhập, họ tên" /></label>
          <label className="inline">Vai trò
            <select value={filters.role} onChange={(e) => setFilters({ ...filters, role: e.target.value })}>
              <option value="">Tất cả</option>
              {Object.entries(ROLE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <label className="inline">Trạng thái
            <select value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })}>
              <option value="">Tất cả</option>
              {Object.entries(USER_STATUS).map(([k, v]) => <option key={k} value={k}>{v.text}</option>)}
            </select>
          </label>
        </div>
        <ErrorBox error={error} onClose={() => setError(null)} />
        {!list ? <Spinner /> : !list.length ? <Empty>Không có người dùng.</Empty> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Tên đăng nhập</th><th>Họ tên</th><th>Email</th><th>Vai trò</th><th>Trạng thái</th><th>Telegram</th><th>Thao tác</th></tr></thead>
              <tbody>
                {list.map((u) => (
                  <tr key={u.id}>
                    <td className="mono">{u.username}{u.id === me.id && <span className="muted"> (bạn)</span>}</td>
                    <td>{u.fullName || '—'}</td>
                    <td>{u.email || '—'}</td>
                    <td>{ROLE[u.role]}</td>
                    <td><StatusBadge map={USER_STATUS} value={u.status} /></td>
                    <td>{u.telegramChatId ? 'Đã liên kết' : '—'}</td>
                    <td>
                      <div className="row wrap gap-s">
                        <button className="btn small" onClick={() => setDialog({ kind: 'edit', user: u })}>Sửa</button>
                        {u.id !== me.id && u.status === 'ACTIVE' && <button className="btn small warn" onClick={() => act(u, 'lock', 'Đã khóa tài khoản')}>Khóa</button>}
                        {u.status !== 'ACTIVE' && <button className="btn small" onClick={() => act(u, 'unlock', 'Đã mở khóa')}>Mở khóa</button>}
                        <button className="btn small" onClick={() => reset(u)}>Đặt lại mật khẩu</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      {dialog && <UserForm u={dialog.user} isMe={dialog.user?.id === me.id} onClose={() => setDialog(null)} onDone={() => { load(); toast('Đã lưu', 'ok') }} />}
      {tempPw && (
        <Modal title={`Mật khẩu tạm của ${tempPw.username}`} onClose={() => setTempPw(null)}>
          <div className="stack">
            <div className="alert-box warn">Mật khẩu tạm chỉ hiển thị một lần. Gửi cho người dùng và nhắc họ đổi ngay.</div>
            <div className="secret-row"><code className="secret">{tempPw.temporaryPassword}</code><CopyButton text={tempPw.temporaryPassword} /></div>
            <div className="row end"><button className="btn primary" onClick={() => setTempPw(null)}>Xong</button></div>
          </div>
        </Modal>
      )}
    </div>
  )
}

function UserForm({ u, isMe, onClose, onDone }) {
  const editing = !!u
  const [f, setF] = useState({
    username: u?.username || '', fullName: u?.fullName || '', email: u?.email || '', role: u?.role || 'VIEWER',
    password: '', telegramChatId: u?.telegramChatId || '',
  })
  const [err, setErr] = useState(null)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const submit = async (e) => {
    e.preventDefault()
    setErr(null)
    try {
      if (editing) {
        const body = { fullName: f.fullName || null, email: f.email || null, telegramChatId: f.telegramChatId || null }
        if (!isMe && f.role !== u.role) body.role = f.role
        await patch(`/users/${u.id}`, body)
      } else {
        if (!/^[a-zA-Z0-9_.-]{3,50}$/.test(f.username)) { setErr('Tên đăng nhập 3–50 ký tự: chữ không dấu, số, dấu . _ -'); return }
        if (f.password.length < 8) { setErr('Mật khẩu ít nhất 8 ký tự'); return }
        await post('/users', { username: f.username, fullName: f.fullName || null, email: f.email || null, role: f.role, password: f.password })
      }
      onDone()
      onClose()
    } catch (ex) { setErr(ex) }
  }
  return (
    <Modal title={editing ? `Sửa ${u.username}` : 'Thêm người dùng'} onClose={onClose}>
      <form className="form" onSubmit={submit}>
        {!editing && <label>Tên đăng nhập<input autoFocus value={f.username} onChange={set('username')} /></label>}
        <label>Họ tên<input value={f.fullName} maxLength={120} onChange={set('fullName')} /></label>
        <label>Email<input type="email" value={f.email} maxLength={120} onChange={set('email')} /></label>
        <label>Vai trò
          <select value={f.role} onChange={set('role')} disabled={isMe}>
            {Object.entries(ROLE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          {isMe && <span className="hint">Không tự đổi vai trò của chính mình.</span>}
        </label>
        {editing && <label>Telegram chat id<input value={f.telegramChatId} maxLength={40} onChange={set('telegramChatId')} /></label>}
        {!editing && <label>Mật khẩu ban đầu (ít nhất 8 ký tự)<input type="password" autoComplete="new-password" value={f.password} onChange={set('password')} /></label>}
        <ErrorBox error={err} />
        <div className="row end gap-s">
          <button type="button" className="btn" onClick={onClose}>Hủy</button>
          <button className="btn primary">{editing ? 'Lưu' : 'Tạo'}</button>
        </div>
      </form>
    </Modal>
  )
}
