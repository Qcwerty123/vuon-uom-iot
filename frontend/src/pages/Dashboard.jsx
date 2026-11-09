import { useCallback, useEffect, useState } from 'react'
import { get, post } from '../api/client.js'
import { canControl, useAuth } from '../auth.jsx'
import { useDevices } from '../devices.jsx'
import { ActuatorState, MetricTile, mergeTelemetry } from '../components/device.jsx'
import { Badge, Card, Empty, ErrorBox, OnlineBadge, Spinner, StatusBadge, useRealtime, useTick, useToast } from '../components/ui.jsx'
import { ALERT_STATUS, DEVICE_STATUS, DEVICE_TYPE, LEAF, MAIN_METRICS, SEVERITY, fmtAgo, fmtTime } from '../labels.js'

const LIVE = new Set(['PROVISIONED', 'ACTIVE', 'OFFLINE', 'FAULT', 'MAINTENANCE'])

export default function Dashboard() {
  const { user } = useAuth()
  const { byId } = useDevices()
  const toast = useToast()
  const [summary, setSummary] = useState(null)
  const [error, setError] = useState(null)
  const [latest, setLatest] = useState({})   // deviceId -> metrics
  const [states, setStates] = useState({})   // deviceId -> state
  const [configs, setConfigs] = useState({}) // deviceId -> params
  const [diag, setDiag] = useState({})       // deviceId -> chẩn đoán mới nhất
  useTick(5000)

  const loadSummary = useCallback(async () => {
    try {
      const s = await get('/dashboard/summary')
      setSummary(s)
      setError(null)
      return s
    } catch (e) {
      setError(e)
      return null
    }
  }, [])

  const loadAll = useCallback(async () => {
    const s = await loadSummary()
    if (!s) return
    const st = {}
    s.devices.forEach((d) => { if (d.state) st[d.id] = d.state })
    setStates((x) => ({ ...x, ...st }))
    await Promise.all(s.devices.filter((d) => LIVE.has(d.status)).map(async (d) => {
      if (d.type === 'CONTROLLER') {
        const [lt, cfg] = await Promise.all([
          get(`/devices/${d.id}/telemetry/latest`).catch(() => null),
          get(`/devices/${d.id}/config`).catch(() => null),
        ])
        if (lt) {
          const m = {}
          Object.entries(lt.metrics || {}).forEach(([k, v]) => { m[k] = { value: v.value, ok: v.ok, ts: v.ts } })
          setLatest((x) => ({ ...x, [d.id]: m }))
          if (lt.state) setStates((x) => ({ ...x, [d.id]: lt.state }))
        }
        if (cfg) setConfigs((x) => ({ ...x, [d.id]: cfg.params || {} }))
      } else if (d.type === 'CAMERA') {
        const r = await get(`/devices/${d.id}/diagnoses`, { size: 1 }).catch(() => null)
        const item = r?.items?.[0]
        if (item) setDiag((x) => ({ ...x, [d.id]: item }))
      }
    }))
  }, [loadSummary])

  useEffect(() => { loadAll() }, [loadAll])

  useRealtime((m) => {
    if (m.type === 'telemetry') {
      setLatest((x) => ({ ...x, [m.deviceId]: mergeTelemetry(x[m.deviceId], m) }))
      if (m.state) setStates((x) => ({ ...x, [m.deviceId]: m.state }))
    } else if (m.type === 'alert') {
      loadSummary()
      if (m.status === 'OPEN') toast(`Cảnh báo mới: ${m.message}`, 'warn')
    } else if (m.type === 'config_update' && m.status === 'APPLIED') {
      get(`/devices/${m.deviceId}/config`).then((c) => setConfigs((x) => ({ ...x, [m.deviceId]: c.params || {} }))).catch(() => {})
    } else if (m.type === 'diagnosis') {
      setDiag((x) => ({ ...x, [m.deviceId]: { ...m, status: 'DONE' } }))
    } else if (m.type === 'reconnected') {
      loadAll()
    }
  }, [loadAll, loadSummary])

  if (error && !summary) return <ErrorBox error={error} />
  if (!summary) return <Spinner />

  // Trạng thái/online lấy từ danh sách dùng chung (đã cập nhật realtime qua device_status).
  const devices = summary.devices.map((d) => ({ ...d, ...(byId[d.id] ? {
    status: byId[d.id].status, online: byId[d.id].online, lastSeenAt: byId[d.id].lastSeenAt } : {}) }))
  const online = devices.filter((d) => d.online).length

  return (
    <div className="stack">
      <div className="page-head">
        <h1>Tổng quan</h1>
        <div className="row gap-s wrap">
          <Badge tone="ok">{online} thiết bị online</Badge>
          <Badge tone="muted">{devices.length - online} offline</Badge>
          <Badge tone={summary.openAlerts.length ? 'bad' : 'ok'}>{summary.openAlerts.length} cảnh báo đang mở</Badge>
        </div>
      </div>

      {devices.length === 0 && (
        <Empty>Bạn chưa được gán thiết bị nào. {user.role === 'ADMIN' && <a href="#/admin/devices">Đăng ký thiết bị</a>}</Empty>
      )}

      <div className="grid devices-grid">
        {devices.map((d) => (
          <Card key={d.id} className="device-card"
            title={<a href={`#/devices/${d.id}`}>{d.name}</a>}
            actions={<OnlineBadge online={d.online} />}>
            <div className="row wrap gap-s small-gap">
              <span className="mono">{d.deviceCode}</span>
              <span className="muted">· {DEVICE_TYPE[d.type] || d.type}</span>
              <StatusBadge map={DEVICE_STATUS} value={d.status} />
            </div>
            <div className="muted small">Lần cuối: {fmtAgo(d.lastSeenAt)}</div>
            {d.type === 'CONTROLLER' && LIVE.has(d.status) && (
              <>
                <div className="metrics">
                  {MAIN_METRICS.map((k) => (
                    <MetricTile key={k} metric={k} m={latest[d.id]?.[k]} cfg={configs[d.id]} compact />
                  ))}
                </div>
                <ActuatorState state={states[d.id]} />
              </>
            )}
            {d.type === 'CAMERA' && LIVE.has(d.status) && <CameraSummary d={diag[d.id]} />}
            <div className="row gap-s card-links">
              <a className="btn small" href={`#/devices/${d.id}`}>Chi tiết</a>
              {canControl(user, d) && d.type === 'CONTROLLER' && <a className="btn small" href={`#/devices/${d.id}?tab=control`}>Điều khiển</a>}
              {d.type === 'CAMERA' && <a className="btn small" href={`#/diagnoses?device=${d.id}`}>Ảnh</a>}
            </div>
          </Card>
        ))}
      </div>

      <OpenAlerts alerts={summary.openAlerts} devicesById={Object.fromEntries(devices.map((d) => [d.id, d]))}
        onChange={loadSummary} />
    </div>
  )
}

function CameraSummary({ d }) {
  if (!d) return <div className="muted">Chưa có ảnh chẩn đoán.</div>
  const label = LEAF[d.topLabel] || LEAF.UNKNOWN
  return (
    <div className="stack-s">
      <div>Ảnh mới nhất: {fmtTime(d.capturedAt || d.createdAt)}</div>
      <div className="row gap-s wrap">
        <Badge tone={label.tone}>Kết luận: {label.text}</Badge>
        {d.topConfidence != null && <Badge tone="muted">Độ tin cậy {Math.round(d.topConfidence * 100)}%</Badge>}
        {Array.isArray(d.abnormalTiles) && d.abnormalTiles.length > 0 && (
          <Badge tone="warn">{d.abnormalTiles.length} ô bất thường</Badge>
        )}
      </div>
    </div>
  )
}

function OpenAlerts({ alerts, devicesById, onChange }) {
  const { user } = useAuth()
  const toast = useToast()
  const [err, setErr] = useState(null)
  const ack = async (a) => {
    try {
      await post(`/alerts/${a.id}/acknowledge`)
      toast('Đã nhận xử lý cảnh báo', 'ok')
      onChange()
    } catch (e) { setErr(e) }
  }
  return (
    <Card title="Cảnh báo đang mở" actions={<a href="#/alerts" className="btn small">Xem tất cả</a>}>
      <ErrorBox error={err} onClose={() => setErr(null)} />
      {alerts.length === 0 ? <Empty>Không có cảnh báo nào đang mở.</Empty> : (
        <ul className="list">
          {alerts.map((a) => (
            <li key={a.id} className="list-item">
              <div className="grow">
                <div className="row gap-s wrap">
                  <StatusBadge map={SEVERITY} value={a.severity} />
                  <StatusBadge map={ALERT_STATUS} value={a.status} />
                  <span className="mono">{a.deviceCode}</span>
                </div>
                <div>{a.message}</div>
                <div className="muted small">{fmtTime(a.openedAt)}</div>
              </div>
              {a.status === 'OPEN' && canControl(user, devicesById[a.deviceId]) && (
                <button className="btn small" onClick={() => ack(a)}>Nhận xử lý</button>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}
