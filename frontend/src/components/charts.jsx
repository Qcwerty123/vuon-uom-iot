import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { METRICS, METRIC_COLORS, fmtValue } from '../labels.js'

const timeFmt = (span) => (t) => {
  const d = new Date(t)
  if (span > 2 * 86400000) return d.toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit' })
  if (span > 86400000) return d.toLocaleString('vi-VN', { day: '2-digit', month: '2-digit', hour: '2-digit' })
  return d.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' })
}

/**
 * Biểu đồ đường nhiều metric. `rows`: [{t: epochMs, soil: 41, air_temp: 29, ...}].
 * Ánh sáng (lux) có thang khác hẳn nên vẽ trên trục phải.
 */
export function MetricChart({ rows, metrics, from, to, height = 300 }) {
  const span = (to || Date.now()) - (from || Date.now() - 3600000)
  const fmt = timeFmt(span)
  const hasLight = metrics.includes('light')
  const others = metrics.filter((m) => m !== 'light')
  return (
    <div className="chart" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rows} margin={{ top: 8, right: hasLight ? 8 : 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e9e7" />
          <XAxis dataKey="t" type="number" scale="time" domain={[from || 'dataMin', to || 'dataMax']}
            tickFormatter={fmt} minTickGap={40} fontSize={12} />
          {others.length > 0 && <YAxis yAxisId="l" fontSize={12} width={40} />}
          {hasLight && <YAxis yAxisId="r" orientation="right" fontSize={12} width={48} />}
          <Tooltip
            labelFormatter={(t) => new Date(t).toLocaleString('vi-VN')}
            formatter={(v, name) => [`${fmtValue(name, v)} ${METRICS[name]?.unit || ''}`, METRICS[name]?.text || name]} />
          <Legend formatter={(name) => METRICS[name]?.text || name} />
          {metrics.map((m) => (
            <Line key={m} dataKey={m} yAxisId={m === 'light' ? 'r' : 'l'} type="monotone" dot={false}
              stroke={METRIC_COLORS[m]} strokeWidth={2} isAnimationActive={false} connectNulls />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Gộp series từ API (`{metric: [{ts, v} | {ts, avg}]}`) thành các hàng theo thời gian. */
export function seriesToRows(series) {
  const byT = new Map()
  Object.entries(series || {}).forEach(([metric, pts]) => {
    pts.forEach((p) => {
      const t = new Date(p.ts).getTime()
      const v = p.v !== undefined ? (p.ok === false ? null : p.v) : p.avg
      if (!byT.has(t)) byT.set(t, { t })
      byT.get(t)[metric] = v
    })
  })
  return [...byT.values()].sort((a, b) => a.t - b.t)
}
