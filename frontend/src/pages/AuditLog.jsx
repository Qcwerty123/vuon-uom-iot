import { useCallback, useEffect, useState } from 'react'
import { get } from '../api/client.js'
import { Badge, Card, Empty, ErrorBox, Pager, Spinner } from '../components/ui.jsx'
import { AUDIT_ACTIONS, fmtTime } from '../labels.js'

export default function AuditLog() {
  const [users, setUsers] = useState([])
  const [f, setF] = useState({ actorId: '', action: '', from: '', to: '' })
  const [page, setPage] = useState(0)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => { get('/users').then(setUsers).catch(() => {}) }, [])
  const load = useCallback(async () => {
    try {
      setData(await get('/audit-logs', {
        actorId: f.actorId, action: f.action, page, size: 50,
        from: f.from ? new Date(f.from).toISOString() : '', to: f.to ? new Date(f.to).toISOString() : '',
      }))
      setError(null)
    } catch (e) { setError(e) }
  }, [f, page])
  useEffect(() => { load() }, [load])
  const set = (k) => (e) => { setPage(0); setF({ ...f, [k]: e.target.value }) }
  const userName = Object.fromEntries(users.map((u) => [u.id, u.username]))

  return (
    <div className="stack">
      <div className="page-head"><h1>Nhật ký audit</h1></div>
      <Card>
        <div className="row wrap gap-s filters">
          <label className="inline">Người thực hiện
            <select value={f.actorId} onChange={set('actorId')}>
              <option value="">Tất cả</option>
              {users.map((u) => <option key={u.id} value={u.id}>{u.username}</option>)}
            </select>
          </label>
          <label className="inline">Hành động
            <select value={f.action} onChange={set('action')}>
              <option value="">Tất cả</option>
              {AUDIT_ACTIONS.map((a) => <option key={a}>{a}</option>)}
            </select>
          </label>
          <label className="inline">Từ<input type="datetime-local" value={f.from} onChange={set('from')} /></label>
          <label className="inline">Đến<input type="datetime-local" value={f.to} onChange={set('to')} /></label>
        </div>
        <ErrorBox error={error} />
        {!data ? <Spinner /> : !data.items.length ? <Empty>Không có bản ghi.</Empty> : (
          <>
            <div className="table-wrap">
              <table>
                <thead><tr><th>Thời gian</th><th>Người</th><th>Hành động</th><th>Đối tượng</th><th>Chi tiết</th><th>IP</th><th>Kết quả</th></tr></thead>
                <tbody>
                  {data.items.map((r) => (
                    <tr key={r.id}>
                      <td className="small">{fmtTime(r.at)}</td>
                      <td>{userName[r.actorId] || r.actorLabel || (r.actorId ? `#${r.actorId}` : '—')}</td>
                      <td className="mono small">{r.action}</td>
                      <td className="small">{r.targetType ? `${r.targetType} #${r.targetId}` : '—'}</td>
                      <td className="mono small params">{r.detail ? JSON.stringify(r.detail) : ''}</td>
                      <td className="mono small">{r.ip || '—'}</td>
                      <td><Badge tone={r.success === false ? 'bad' : 'ok'}>{r.success === false ? 'Thất bại' : 'Thành công'}</Badge></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pager page={data.page} size={data.size} total={data.total} onPage={setPage} />
          </>
        )}
      </Card>
    </div>
  )
}
