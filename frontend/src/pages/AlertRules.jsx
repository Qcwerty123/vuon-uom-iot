// Luật cảnh báo (đặc tả §13, §10.8): mọi vai trò xem, ADMIN ghi. Xóa = tắt luật.
import { useState } from 'react'
import { del, get, patch, post } from '../api/client.js'
import { useAuth } from '../auth.jsx'
import { useDevices } from '../devices.jsx'
import { Badge, Card, Empty, ErrorBox, Modal, Spinner, StatusBadge, useLoad, useToast } from '../components/ui.jsx'
import { ALERT_TYPE, EVENT, METRICS, SEVERITY } from '../labels.js'

const EMPTY = {
  name: '', type: 'THRESHOLD', scopeDeviceId: '', metric: 'soil', operator: '<', threshold: '', hysteresis: 0,
  durationS: 0, eventType: 'tank_low', severity: 'WARNING', cooldownMin: 30, notifyTelegram: true, enabled: true,
}

function condition(r) {
  if (r.type === 'THRESHOLD') {
    return `${METRICS[r.metric]?.text || r.metric} ${r.operator} ${r.threshold}${METRICS[r.metric]?.unit || ''}`
      + (r.durationS ? ` trong ${r.durationS} giây` : '') + (r.hysteresis ? `, trễ ${r.hysteresis}` : '')
  }
  if (r.type === 'EVENT') return `Sự kiện: ${EVENT[r.eventType] || r.eventType}`
  if (r.type === 'OFFLINE') return 'Thiết bị mất kết nối'
  return 'Lá bất thường ở cùng ô trong 3 ảnh liên tiếp'
}

export default function AlertRules() {
  const { isAdmin } = useAuth()
  const { byId } = useDevices()
  const toast = useToast()
  const { data, error, reload } = useLoad(() => get('/alert-rules'), [])
  const [edit, setEdit] = useState(null)
  const [err, setErr] = useState(null)

  const disable = async (r) => {
    if (!window.confirm(`Tắt luật “${r.name}”?`)) return
    try { await del(`/alert-rules/${r.id}`); toast('Đã tắt luật', 'ok'); reload() } catch (e) { setErr(e) }
  }

  return (
    <div className="stack">
      <div className="page-head">
        <h1>Luật cảnh báo</h1>
        {isAdmin && <button className="btn primary" onClick={() => setEdit({ ...EMPTY })}>+ Thêm luật</button>}
      </div>
      {!isAdmin && <div className="alert-box info">Bạn chỉ có quyền xem. Quản trị viên mới sửa được luật.</div>}
      <ErrorBox error={error || err} onClose={() => setErr(null)} />
      <Card>
        {!data ? <Spinner /> : !data.length ? <Empty>Chưa có luật nào.</Empty> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Tên</th><th>Loại</th><th>Điều kiện</th><th>Phạm vi</th><th>Mức</th><th>Lặp lại sau</th><th>Telegram</th><th>Bật</th>{isAdmin && <th />}</tr></thead>
              <tbody>
                {data.map((r) => (
                  <tr key={r.id} className={r.enabled ? '' : 'dim'}>
                    <td>{r.name}</td>
                    <td>{ALERT_TYPE[r.type] || r.type}</td>
                    <td>{condition(r)}</td>
                    <td>{r.scopeDeviceId ? (byId[r.scopeDeviceId]?.deviceCode || `#${r.scopeDeviceId}`) : 'Mọi thiết bị'}</td>
                    <td><StatusBadge map={SEVERITY} value={r.severity} /></td>
                    <td>{r.cooldownMin} phút</td>
                    <td>{r.notifyTelegram ? 'Có' : 'Không'}</td>
                    <td><Badge tone={r.enabled ? 'ok' : 'muted'}>{r.enabled ? 'Đang bật' : 'Đã tắt'}</Badge></td>
                    {isAdmin && (
                      <td><div className="row gap-s">
                        <button className="btn small" onClick={() => setEdit({ ...EMPTY, ...r, scopeDeviceId: r.scopeDeviceId ?? '', threshold: r.threshold ?? '' })}>Sửa</button>
                        {r.enabled && <button className="btn small warn" onClick={() => disable(r)}>Tắt</button>}
                      </div></td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      {edit && <RuleForm rule={edit} onClose={() => setEdit(null)} onDone={() => { reload(); toast('Đã lưu luật', 'ok') }} />}
    </div>
  )
}

function RuleForm({ rule, onClose, onDone }) {
  const { devices } = useDevices()
  const [f, setF] = useState(rule)
  const [err, setErr] = useState(null)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
  const submit = async (e) => {
    e.preventDefault()
    setErr(null)
    if (!f.name.trim()) { setErr('Nhập tên luật'); return }
    if (f.type === 'THRESHOLD' && (f.threshold === '' || Number.isNaN(Number(f.threshold)))) { setErr('Nhập ngưỡng là số'); return }
    const body = {
      name: f.name.trim(), type: f.type, severity: f.severity, cooldownMin: Number(f.cooldownMin),
      notifyTelegram: f.notifyTelegram, enabled: f.enabled,
      scopeDeviceId: f.scopeDeviceId ? Number(f.scopeDeviceId) : null,
      hysteresis: Number(f.hysteresis) || 0, durationS: Number(f.durationS) || 0,
      metric: f.type === 'THRESHOLD' ? f.metric : null,
      operator: f.type === 'THRESHOLD' ? f.operator : null,
      threshold: f.type === 'THRESHOLD' ? Number(f.threshold) : null,
      eventType: f.type === 'EVENT' ? f.eventType : null,
    }
    try {
      if (f.id) await patch(`/alert-rules/${f.id}`, body)
      else await post('/alert-rules', body)
      onDone()
      onClose()
    } catch (ex) { setErr(ex) }
  }
  return (
    <Modal title={f.id ? `Sửa luật #${f.id}` : 'Thêm luật cảnh báo'} onClose={onClose}>
      <form className="form" onSubmit={submit}>
        <label>Tên<input autoFocus maxLength={120} value={f.name} onChange={set('name')} /></label>
        <label>Loại
          <select value={f.type} onChange={set('type')}>
            {Object.entries(ALERT_TYPE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        {f.type === 'THRESHOLD' && (
          <div className="row wrap gap-s">
            <label className="inline">Đại lượng
              <select value={f.metric} onChange={set('metric')}>
                {Object.entries(METRICS).map(([k, v]) => <option key={k} value={k}>{v.text}</option>)}
              </select>
            </label>
            <label className="inline">Điều kiện
              <select value={f.operator} onChange={set('operator')}>
                {['<', '<=', '>', '>='].map((o) => <option key={o}>{o}</option>)}
              </select>
            </label>
            <label className="inline">Ngưỡng<input type="number" step="any" value={f.threshold} onChange={set('threshold')} /></label>
            <label className="inline">Kéo dài (giây)<input type="number" min="0" max="86400" value={f.durationS} onChange={set('durationS')} /></label>
            <label className="inline">Độ trễ<input type="number" min="0" step="any" value={f.hysteresis} onChange={set('hysteresis')} /></label>
          </div>
        )}
        {f.type === 'EVENT' && (
          <label>Sự kiện
            <select value={f.eventType} onChange={set('eventType')}>
              {Object.entries(EVENT).map(([k, v]) => <option key={k} value={k}>{v} ({k})</option>)}
            </select>
          </label>
        )}
        <label>Áp dụng cho
          <select value={f.scopeDeviceId} onChange={set('scopeDeviceId')}>
            <option value="">Mọi thiết bị</option>
            {devices.map((d) => <option key={d.id} value={d.id}>{d.deviceCode} · {d.name}</option>)}
          </select>
        </label>
        <div className="row wrap gap-s">
          <label className="inline">Mức độ
            <select value={f.severity} onChange={set('severity')}>
              {Object.entries(SEVERITY).map(([k, v]) => <option key={k} value={k}>{v.text}</option>)}
            </select>
          </label>
          <label className="inline">Không lặp lại trong (phút)<input type="number" min="0" max="1440" value={f.cooldownMin} onChange={set('cooldownMin')} /></label>
        </div>
        <label className="check"><input type="checkbox" checked={f.notifyTelegram} onChange={set('notifyTelegram')} />Gửi Telegram</label>
        <label className="check"><input type="checkbox" checked={f.enabled} onChange={set('enabled')} />Đang bật</label>
        <ErrorBox error={err} />
        <div className="row end gap-s">
          <button type="button" className="btn" onClick={onClose}>Hủy</button>
          <button className="btn primary">Lưu</button>
        </div>
      </form>
    </Modal>
  )
}
