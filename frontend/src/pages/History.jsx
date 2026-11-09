// Lịch sử dữ liệu (đặc tả §16.1): chọn metric + khoảng thời gian, biểu đồ, bảng, min/max/avg, xuất CSV.
import { useEffect, useMemo, useState } from 'react'
import { download, get } from '../api/client.js'
import { useDevices } from '../devices.jsx'
import { MetricChart, seriesToRows } from '../components/charts.jsx'
import { Card, Empty, ErrorBox, Spinner } from '../components/ui.jsx'
import { METRICS, fmtTime, fmtValue } from '../labels.js'

const RANGES = [
  ['1h', '1 giờ', 3600e3],
  ['6h', '6 giờ', 6 * 3600e3],
  ['24h', '24 giờ', 24 * 3600e3],
  ['7d', '7 ngày', 7 * 86400e3],
  ['30d', '30 ngày', 30 * 86400e3],
  ['custom', 'Tùy chọn', 0],
]
const ALL = ['soil', 'soil1', 'soil2', 'air_temp', 'air_hum', 'light', 'tank']

function toLocalInput(d) {
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`
}

export default function History({ query }) {
  const { devices, loaded } = useDevices()
  const controllers = devices.filter((d) => d.type === 'CONTROLLER' && d.status !== 'REGISTERED')
  const [deviceId, setDeviceId] = useState(query.device || '')
  const [metrics, setMetrics] = useState(['soil', 'air_temp', 'air_hum'])
  const [range, setRange] = useState('24h')
  const [custom, setCustom] = useState(() => ({
    from: toLocalInput(new Date(Date.now() - 86400e3)), to: toLocalInput(new Date()),
  }))
  const [interval, setInterval_] = useState('auto')
  const [result, setResult] = useState(null)
  const [stats, setStats] = useState({})
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  const [exporting, setExporting] = useState(false)

  useEffect(() => {
    if (!deviceId && controllers.length) setDeviceId(String(controllers[0].id))
  }, [controllers, deviceId])

  const span = useMemo(() => {
    if (range === 'custom') return { from: new Date(custom.from), to: new Date(custom.to) }
    const ms = RANGES.find((r) => r[0] === range)[2]
    const to = new Date()
    return { from: new Date(to.getTime() - ms), to }
  }, [range, custom])

  const load = async () => {
    if (!deviceId || !metrics.length) return
    if (!(span.from < span.to)) { setError('Thời điểm bắt đầu phải trước thời điểm kết thúc'); return }
    setLoading(true); setError(null)
    const q = { from: span.from.toISOString(), to: span.to.toISOString() }
    try {
      const [r, ...st] = await Promise.all([
        get(`/devices/${deviceId}/telemetry`, { ...q, metric: metrics.join(','), interval }),
        ...metrics.map((m) => get(`/devices/${deviceId}/telemetry/stats`, { ...q, metric: m }).catch(() => null)),
      ])
      setResult(r)
      setStats(Object.fromEntries(metrics.map((m, i) => [m, st[i]])))
    } catch (e) { setError(e) } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [deviceId, range, interval]) // eslint-disable-line react-hooks/exhaustive-deps

  const rows = useMemo(() => seriesToRows(result?.series), [result])
  const shownMetrics = metrics.filter((m) => result?.series?.[m])

  const exportCsv = async () => {
    setExporting(true); setError(null)
    try {
      if (span.to - span.from > 31 * 86400e3) throw new Error('Chỉ xuất được tối đa 31 ngày mỗi lần')
      const dev = devices.find((d) => String(d.id) === String(deviceId))
      await download(`/devices/${deviceId}/telemetry/export.csv`,
        { from: span.from.toISOString(), to: span.to.toISOString() }, `${dev?.deviceCode || 'telemetry'}.csv`)
    } catch (e) { setError(e) } finally { setExporting(false) }
  }

  const toggle = (k) => setMetrics((ms) => (ms.includes(k) ? ms.filter((x) => x !== k) : [...ms, k]))

  return (
    <div className="stack">
      <div className="page-head"><h1>Lịch sử dữ liệu</h1></div>
      <Card>
        <div className="stack-s">
          <div className="row wrap gap-s">
            <label className="inline">Thiết bị
              <select value={deviceId} onChange={(e) => setDeviceId(e.target.value)}>
                {!loaded && <option>Đang tải…</option>}
                {controllers.map((d) => <option key={d.id} value={d.id}>{d.deviceCode} · {d.name}</option>)}
              </select>
            </label>
            <label className="inline">Khoảng
              <select value={range} onChange={(e) => setRange(e.target.value)}>
                {RANGES.map(([k, t]) => <option key={k} value={k}>{t}</option>)}
              </select>
            </label>
            {range === 'custom' && (
              <>
                <label className="inline">Từ<input type="datetime-local" value={custom.from} onChange={(e) => setCustom((c) => ({ ...c, from: e.target.value }))} /></label>
                <label className="inline">Đến<input type="datetime-local" value={custom.to} onChange={(e) => setCustom((c) => ({ ...c, to: e.target.value }))} /></label>
              </>
            )}
            <label className="inline">Gộp theo
              <select value={interval} onChange={(e) => setInterval_(e.target.value)}>
                <option value="auto">Tự động</option>
                <option value="raw">Từng bản tin</option>
                <option value="1h">Theo giờ</option>
                <option value="1d">Theo ngày</option>
              </select>
            </label>
          </div>
          <div className="row wrap gap-s">
            {ALL.map((k) => (
              <label key={k} className="check small">
                <input type="checkbox" checked={metrics.includes(k)} onChange={() => toggle(k)} />{METRICS[k].text}
              </label>
            ))}
          </div>
          <div className="row gap-s">
            <button className="btn primary" onClick={load} disabled={loading || !deviceId}>{loading ? 'Đang tải…' : 'Xem'}</button>
            <button className="btn" onClick={exportCsv} disabled={exporting || !deviceId}>{exporting ? 'Đang xuất…' : '⬇ Xuất CSV'}</button>
          </div>
        </div>
      </Card>
      <ErrorBox error={error} onClose={() => setError(null)} />
      {loaded && !controllers.length && <Empty>Không có thiết bị đo nào được gán cho bạn.</Empty>}
      {result && (
        <>
          <div className="grid stats-grid">
            {shownMetrics.map((m) => (
              <div key={m} className="stat">
                <div className="metric-name">{METRICS[m].text}</div>
                {stats[m]?.count ? (
                  <div className="stat-row">
                    <span>Thấp nhất <b>{fmtValue(m, stats[m].min)}</b></span>
                    <span>Trung bình <b>{fmtValue(m, stats[m].avg)}</b></span>
                    <span>Cao nhất <b>{fmtValue(m, stats[m].max)}</b></span>
                    <span className="muted">{METRICS[m].unit} · {stats[m].count} mẫu</span>
                  </div>
                ) : <div className="muted">Không có mẫu hợp lệ</div>}
              </div>
            ))}
          </div>
          <Card title={`Biểu đồ (${result.interval === 'raw' ? 'từng bản tin' : result.interval === '1h' ? 'trung bình theo giờ' : 'trung bình theo ngày'})`}>
            {loading ? <Spinner /> : rows.length === 0 ? <Empty>Không có dữ liệu trong khoảng này.</Empty>
              : <MetricChart rows={rows} metrics={shownMetrics} from={span.from.getTime()} to={span.to.getTime()} height={340} />}
          </Card>
          {rows.length > 0 && (
            <Card title={`Bảng số liệu (${Math.min(rows.length, 200)} dòng mới nhất / ${rows.length})`}>
              <div className="table-wrap tall">
                <table>
                  <thead><tr><th>Thời gian</th>{shownMetrics.map((m) => <th key={m}>{METRICS[m].text} ({METRICS[m].unit})</th>)}</tr></thead>
                  <tbody>
                    {rows.slice(-200).reverse().map((r) => (
                      <tr key={r.t}>
                        <td className="small">{fmtTime(r.t)}</td>
                        {shownMetrics.map((m) => <td key={m}>{r[m] === null ? <span className="badge badge-bad">lỗi</span> : fmtValue(m, r[m])}</td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  )
}
