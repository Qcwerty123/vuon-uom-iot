import { useCallback, useEffect, useState } from 'react'
import { get, post } from '../api/client.js'
import { canControl, useAuth } from '../auth.jsx'
import { useDevices } from '../devices.jsx'
import { navigate } from '../router.js'
import { MetricChart, seriesToRows } from '../components/charts.jsx'
import ConfigPanel from '../components/ConfigPanel.jsx'
import ControlPanel from '../components/ControlPanel.jsx'
import { ActuatorState, MetricTile, mergeTelemetry } from '../components/device.jsx'
import {
  Card, Empty, ErrorBox, OnlineBadge, ReasonDialog, Spinner, StatusBadge, useLoad, useRealtime, useTick, useToast,
} from '../components/ui.jsx'
import {
  ACTION, COMMAND_STATUS, DEVICE_STATUS, DEVICE_TYPE, MAIN_METRICS, commandText, eventText, fmtAgo, fmtTime,
} from '../labels.js'

const HOUR = 3600000

export default function DeviceDetail({ params, query }) {
  const id = Number(params.id)
  const { user } = useAuth()
  const { upsert } = useDevices()
  const toast = useToast()
  const [device, setDevice] = useState(null)
  const [error, setError] = useState(null)
  const [dialog, setDialog] = useState(null)
  const tab = query.tab || 'overview'
  useTick(5000)

  const load = useCallback(async () => {
    try {
      setDevice(await get(`/devices/${id}`))
      setError(null)
    } catch (e) { setError(e) }
  }, [id])
  useEffect(() => { load() }, [load])

  useRealtime((m) => {
    if (m.deviceId !== id) return
    if (m.type === 'device_status') {
      setDevice((d) => d && ({ ...d, status: m.status, online: m.online, lastSeenAt: m.lastSeenAt ?? d.lastSeenAt }))
    } else if (m.type === 'telemetry') {
      setDevice((d) => d && ({ ...d, online: true, lastSeenAt: m.ts }))
    }
  }, [id])

  if (error) {
    return (
      <div className="stack">
        <a href="#/">‹ Tổng quan</a>
        <ErrorBox error={error.status === 404 ? 'Không tìm thấy thiết bị, hoặc bạn chưa được gán thiết bị này.' : error} />
      </div>
    )
  }
  if (!device) return <Spinner />

  const control = canControl(user, device)
  const tabs = [
    ['overview', 'Tổng quan'],
    ...(control && ['ACTIVE', 'OFFLINE', 'FAULT', 'MAINTENANCE'].includes(device.status) ? [['control', 'Điều khiển']] : []),
    ['config', 'Cấu hình'],
    ['events', 'Sự kiện'],
    ['history', 'Lịch sử lệnh & trạng thái'],
  ]
  const setTab = (t) => navigate(`/devices/${id}${t === 'overview' ? '' : `?tab=${t}`}`)

  const maint = async (reason, end) => {
    const r = await post(`/devices/${id}/maintenance${end ? '/end' : ''}`, { reason })
    setDevice((d) => ({ ...d, status: r.status }))
    upsert({ id, status: r.status })
    toast(end ? 'Đã kết thúc bảo trì' : 'Đã chuyển sang bảo trì', 'ok')
  }

  return (
    <div className="stack">
      <a href="#/">‹ Tổng quan</a>
      <div className="page-head">
        <div>
          <h1>{device.name}</h1>
          <div className="row wrap gap-s">
            <span className="mono">{device.deviceCode}</span>
            <span className="muted">{DEVICE_TYPE[device.type]}</span>
            <StatusBadge map={DEVICE_STATUS} value={device.status} />
            <OnlineBadge online={device.online} />
          </div>
        </div>
        <div className="row gap-s wrap">
          {control && ['ACTIVE', 'OFFLINE', 'FAULT'].includes(device.status) && (
            <button className="btn" onClick={() => setDialog('maint')}>Chuyển bảo trì</button>
          )}
          {control && device.status === 'MAINTENANCE' && (
            <button className="btn" onClick={() => setDialog('maint_end')}>Kết thúc bảo trì</button>
          )}
          {user.role === 'ADMIN' && <a className="btn" href={`#/admin/devices?focus=${id}`}>Quản lý</a>}
        </div>
      </div>

      <div className="tabs" role="tablist">
        {tabs.map(([k, t]) => (
          <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? 'active' : ''} onClick={() => setTab(k)}>{t}</button>
        ))}
      </div>

      {tab === 'overview' && <Overview device={device} />}
      {tab === 'control' && control && <ControlWithState device={device} />}
      {tab === 'config' && <ConfigPanel device={device} canEdit={control && !['REGISTERED', 'SUSPENDED', 'DECOMMISSIONED'].includes(device.status)} />}
      {tab === 'events' && <Events device={device} />}
      {tab === 'history' && <HistoryTab device={device} />}

      {dialog === 'maint' && (
        <ReasonDialog title="Chuyển thiết bị sang bảo trì" onClose={() => setDialog(null)}
          extra={<p className="muted">Khi bảo trì, cảnh báo vẫn được ghi nhưng không gửi Telegram.</p>}
          onSubmit={(r) => maint(r, false)} />
      )}
      {dialog === 'maint_end' && (
        <ReasonDialog title="Kết thúc bảo trì" defaultReason="Đã xử lý xong" onClose={() => setDialog(null)}
          onSubmit={(r) => maint(r, true)} />
      )}
    </div>
  )
}

function useLatest(device) {
  const [metrics, setMetrics] = useState({})
  const [state, setState] = useState(null)
  const load = useCallback(async () => {
    try {
      const lt = await get(`/devices/${device.id}/telemetry/latest`)
      const m = {}
      Object.entries(lt.metrics || {}).forEach(([k, v]) => { m[k] = { value: v.value, ok: v.ok, ts: v.ts } })
      setMetrics(m)
      if (lt.state) setState(lt.state)
    } catch { /* thiết bị chưa có dữ liệu */ }
  }, [device.id])
  useEffect(() => { load() }, [load])
  useRealtime((m) => {
    if (m.type === 'reconnected') load()
    if (m.type !== 'telemetry' || m.deviceId !== device.id) return
    setMetrics((x) => mergeTelemetry(x, m))
    if (m.state) setState(m.state)
  }, [device.id, load])
  return { metrics, state }
}

function ControlWithState({ device }) {
  const { state } = useLatest(device)
  return <ControlPanel device={device} state={state} />
}

function Overview({ device }) {
  const { metrics, state } = useLatest(device)
  const [cfg, setCfg] = useState({})
  useEffect(() => {
    if (device.type === 'CONTROLLER') get(`/devices/${device.id}/config`).then((c) => setCfg(c.params || {})).catch(() => {})
  }, [device.id, device.type])
  return (
    <div className="stack">
      <div className="grid two">
        <Card title="Thông tin">
          <dl className="kv">
            <dt>Mã thiết bị</dt><dd className="mono">{device.deviceCode}</dd>
            <dt>Loại</dt><dd>{DEVICE_TYPE[device.type]}</dd>
            <dt>Trạng thái</dt><dd><StatusBadge map={DEVICE_STATUS} value={device.status} /></dd>
            <dt>Kết nối</dt><dd><OnlineBadge online={device.online} /></dd>
            <dt>Lần cuối thấy</dt><dd>{fmtTime(device.lastSeenAt)} <span className="muted">({fmtAgo(device.lastSeenAt)})</span></dd>
            <dt>Lần đầu kết nối</dt><dd>{fmtTime(device.firstSeenAt)}</dd>
            <dt>Firmware</dt><dd>{device.fwVersion || '—'}</dd>
            <dt>Phần cứng</dt><dd>{device.hwVersion || '—'}</dd>
            <dt>Phiên bản cấu hình</dt><dd>{device.currentConfigVersion ?? '—'}</dd>
            <dt>Quyền của bạn</dt><dd>{device.permission === 'CONTROL' ? 'Điều khiển' : 'Chỉ xem'}</dd>
            {device.note && <><dt>Ghi chú</dt><dd>{device.note}</dd></>}
          </dl>
        </Card>
        {device.type === 'CONTROLLER' && (
          <Card title="Số đo mới nhất">
            <div className="metrics">
              {['soil', 'soil1', 'soil2', 'air_temp', 'air_hum', 'light', 'tank'].map((k) => (
                <MetricTile key={k} metric={k} m={metrics[k]} cfg={cfg} />
              ))}
            </div>
            <ActuatorState state={state} />
          </Card>
        )}
        {device.type === 'CAMERA' && (
          <Card title="Ảnh chẩn đoán">
            <p>Xem ảnh khay cây và kết quả AI trong mục <a href={`#/diagnoses?device=${device.id}`}>Ảnh &amp; chẩn đoán</a>.</p>
          </Card>
        )}
      </div>
      {device.type === 'CONTROLLER' && <LiveChart device={device} />}
    </div>
  )
}

/** Biểu đồ 1 giờ gần nhất, thêm điểm mới từ WebSocket. */
function LiveChart({ device }) {
  const [rows, setRows] = useState(null)
  const [metrics, setMetrics] = useState(['soil', 'air_temp', 'air_hum', 'tank'])
  const [err, setErr] = useState(null)
  const [now, setNow] = useState(Date.now())
  const load = useCallback(async () => {
    try {
      const r = await get(`/devices/${device.id}/telemetry`, { metric: MAIN_METRICS.join(','), interval: 'raw' })
      setRows(seriesToRows(r.series))
      setErr(null)
    } catch (e) { setErr(e); setRows([]) }
  }, [device.id])
  useEffect(() => { load() }, [load])
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 10000); return () => clearInterval(t) }, [])
  useRealtime((m) => {
    if (m.type === 'reconnected') load()
    if (m.type !== 'telemetry' || m.deviceId !== device.id) return
    const row = { t: new Date(m.ts).getTime() }
    Object.entries(m.data || {}).forEach(([k, d]) => { row[k] = d.ok === false ? null : d.v })
    setRows((xs) => [...(xs || []).filter((r) => r.t > Date.now() - HOUR && r.t !== row.t), row].sort((a, b) => a.t - b.t))
    setNow(Date.now())
  }, [device.id, load])
  const toggle = (k) => setMetrics((ms) => (ms.includes(k) ? ms.filter((x) => x !== k) : [...ms, k]))
  return (
    <Card title="Biểu đồ 1 giờ gần nhất (cập nhật trực tiếp)" actions={
      <div className="row wrap gap-s">
        {MAIN_METRICS.map((k) => (
          <label key={k} className="check small">
            <input type="checkbox" checked={metrics.includes(k)} onChange={() => toggle(k)} />
            {({ soil: 'Đất', air_temp: 'Nhiệt độ', air_hum: 'Độ ẩm KK', light: 'Ánh sáng', tank: 'Bể' })[k]}
          </label>
        ))}
      </div>
    }>
      <ErrorBox error={err} />
      {rows === null ? <Spinner /> : rows.length === 0 ? <Empty>Chưa có dữ liệu trong 1 giờ qua.</Empty>
        : <MetricChart rows={rows} metrics={metrics} from={now - HOUR} to={now} />}
    </Card>
  )
}

function Events({ device }) {
  const { data, error, loading, setData, reload } = useLoad(() => get(`/devices/${device.id}/events`, { limit: 200 }), [device.id])
  useRealtime((m) => {
    if (m.type === 'reconnected') reload()
    if (m.type !== 'device_event' || m.deviceId !== device.id) return
    setData((xs) => [{ id: `ws-${m.ts}-${m.eventType}`, type: m.eventType, detail: m.detail, ts: m.ts }, ...(xs || [])])
  }, [device.id, reload])
  return (
    <Card title="Sự kiện 24 giờ qua">
      <ErrorBox error={error} />
      {loading && !data ? <Spinner /> : !data?.length ? <Empty>Không có sự kiện.</Empty> : (
        <ul className="list timeline">
          {data.map((e) => (
            <li key={e.id} className="list-item">
              <span className="muted small time">{fmtTime(e.ts)}</span>
              <span>{eventText(e.type, e.detail)}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

function HistoryTab({ device }) {
  const hist = useLoad(() => get(`/devices/${device.id}/history`), [device.id])
  const cmds = useLoad(() => get(`/devices/${device.id}/commands`, { limit: 50 }), [device.id])
  useRealtime((m) => {
    if (m.deviceId !== device.id) return
    if (m.type === 'device_status') hist.reload()
    if (m.type === 'command_update') {
      if (cmds.data?.some((c) => c.cmdId === m.cmdId)) {
        cmds.setData((xs) => xs.map((c) => (c.cmdId === m.cmdId ? { ...c, ...m } : c)))
      } else {
        cmds.reload()
      }
    }
  }, [device.id])
  return (
    <div className="grid two">
      <Card title="Lịch sử lệnh">
        <ErrorBox error={cmds.error} />
        {!cmds.data ? <Spinner /> : !cmds.data.length ? <Empty>Chưa có lệnh.</Empty> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Thời gian</th><th>Lệnh</th><th>Kết quả</th></tr></thead>
              <tbody>
                {cmds.data.map((c) => (
                  <tr key={c.cmdId}>
                    <td>{fmtTime(c.issuedAt)}</td>
                    <td>{ACTION[c.action] || c.action}{c.params?.duration_s ? ` ${c.params.duration_s} giây` : ''}{c.params?.mode ? ` ${c.params.mode}` : ''}</td>
                    <td><span className={`badge badge-${COMMAND_STATUS[c.status]?.tone || 'muted'}`}>{commandText(c)}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <Card title="Lịch sử trạng thái">
        <ErrorBox error={hist.error} />
        {!hist.data ? <Spinner /> : (
          <ul className="list timeline">
            {hist.data.map((h, i) => (
              <li key={i} className="list-item">
                <span className="muted small time">{fmtTime(h.at)}</span>
                <span>
                  {h.fromStatus ? `${DEVICE_STATUS[h.fromStatus]?.text || h.fromStatus} → ` : ''}
                  <b>{DEVICE_STATUS[h.toStatus]?.text || h.toStatus}</b>
                  {h.reason && <span className="muted"> · {h.reason}</span>}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}
