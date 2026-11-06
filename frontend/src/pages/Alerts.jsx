import { useCallback, useEffect, useState } from 'react'
import { get, post } from '../api/client.js'
import { canControl, useAuth } from '../auth.jsx'
import { useDevices } from '../devices.jsx'
import { Card, Empty, ErrorBox, Pager, ReasonDialog, Spinner, StatusBadge, useRealtime, useToast } from '../components/ui.jsx'
import { ALERT_STATUS, ALERT_TYPE, SEVERITY, fmtTime } from '../labels.js'

const STATUS_FILTERS = [
  ['OPEN,ACKNOWLEDGED', 'Chưa đóng'],
  ['OPEN', 'Đang mở'],
  ['ACKNOWLEDGED', 'Đã nhận xử lý'],
  ['CLOSED', 'Đã đóng'],
  ['', 'Tất cả'],
]

export default function Alerts() {
  const { user } = useAuth()
  const { devices, byId } = useDevices()
  const toast = useToast()
  const [filters, setFilters] = useState({ status: 'OPEN,ACKNOWLEDGED', severity: '', deviceId: '' })
  const [page, setPage] = useState(0)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [closing, setClosing] = useState(null)

  const load = useCallback(async () => {
    try {
      setData(await get('/alerts', { ...filters, page, size: 20 }))
      setError(null)
    } catch (e) { setError(e) }
  }, [filters, page])
  useEffect(() => { load() }, [load])
  useRealtime((m) => { if (m.type === 'alert' || m.type === 'reconnected') load() }, [load])

  const set = (k) => (e) => { setPage(0); setFilters((f) => ({ ...f, [k]: e.target.value })) }
  const ack = async (a) => {
    try { await post(`/alerts/${a.id}/acknowledge`); toast('Đã nhận xử lý', 'ok'); load() } catch (e) { setError(e) }
  }

  return (
    <div className="stack">
      <div className="page-head"><h1>Cảnh báo</h1></div>
      <Card>
        <div className="filters row wrap gap-s">
          <label className="inline">Trạng thái
            <select value={filters.status} onChange={set('status')}>
              {STATUS_FILTERS.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
            </select>
          </label>
          <label className="inline">Mức độ
            <select value={filters.severity} onChange={set('severity')}>
              <option value="">Tất cả</option>
              {Object.entries(SEVERITY).map(([k, v]) => <option key={k} value={k}>{v.text}</option>)}
            </select>
          </label>
          <label className="inline">Thiết bị
            <select value={filters.deviceId} onChange={set('deviceId')}>
              <option value="">Tất cả</option>
              {devices.map((d) => <option key={d.id} value={d.id}>{d.deviceCode} · {d.name}</option>)}
            </select>
          </label>
        </div>
        <ErrorBox error={error} onClose={() => setError(null)} />
        {!data ? <Spinner /> : data.items.length === 0 ? <Empty>Không có cảnh báo phù hợp.</Empty> : (
          <>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr><th>Mở lúc</th><th>Mức</th><th>Thiết bị</th><th>Nội dung</th><th>Trạng thái</th><th>Thao tác</th></tr>
                </thead>
                <tbody>
                  {data.items.map((a) => {
                    const ctl = canControl(user, byId[a.deviceId])
                    return (
                      <tr key={a.id}>
                        <td className="small">{fmtTime(a.openedAt)}</td>
                        <td><StatusBadge map={SEVERITY} value={a.severity} /></td>
                        <td className="mono"><a href={`#/devices/${a.deviceId}`}>{a.deviceCode || a.deviceId}</a></td>
                        <td>
                          <div>{a.message}</div>
                          <div className="muted small">{ALERT_TYPE[a.type] || a.type}
                            {a.notifiedAt && ' · đã gửi Telegram'}
                            {a.conditionClearedAt && ` · điều kiện hết lúc ${fmtTime(a.conditionClearedAt)}`}
                            {a.closeNote && ` · ghi chú: ${a.closeNote === 'auto' ? 'tự đóng khi thiết bị online lại' : a.closeNote}`}
                          </div>
                        </td>
                        <td>
                          <StatusBadge map={ALERT_STATUS} value={a.status} />
                          {a.ackAt && <div className="muted small">nhận lúc {fmtTime(a.ackAt, false)}</div>}
                          {a.closedAt && <div className="muted small">đóng lúc {fmtTime(a.closedAt, false)}</div>}
                        </td>
                        <td>
                          {ctl && a.status !== 'CLOSED' ? (
                            <div className="row wrap gap-s">
                              {a.status === 'OPEN' && <button className="btn small" onClick={() => ack(a)}>Nhận xử lý</button>}
                              <button className="btn small" onClick={() => setClosing(a)}>Đóng</button>
                            </div>
                          ) : <span className="muted small">{a.status === 'CLOSED' ? '' : 'Chỉ xem'}</span>}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <Pager page={data.page} size={data.size} total={data.total} onPage={setPage} />
          </>
        )}
      </Card>
      {closing && (
        <ReasonDialog title={`Đóng cảnh báo #${closing.id}`} label="Ghi chú xử lý" confirmText="Đóng cảnh báo" needReason
          onClose={() => setClosing(null)}
          extra={<p>{closing.message}</p>}
          onSubmit={async (note) => { await post(`/alerts/${closing.id}/close`, { note }); toast('Đã đóng cảnh báo', 'ok'); load() }} />
      )}
    </div>
  )
}
