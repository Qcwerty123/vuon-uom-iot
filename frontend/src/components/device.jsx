import { useEffect, useRef, useState } from 'react'
import { Badge } from './ui.jsx'
import { LOCKS, METRICS, fmtValue } from '../labels.js'

/** Đánh giá số đo theo ngưỡng cấu hình (đặc tả §16.1: màu theo ngưỡng, kèm chữ). */
export function judge(metric, m, cfg = {}) {
  if (!m) return { text: 'Chưa có dữ liệu', tone: 'muted' }
  if (m.ok === false || m.value === null || m.value === undefined) return { text: 'Lỗi cảm biến', tone: 'bad' }
  const v = Number(m.value)
  switch (metric) {
    case 'soil':
    case 'soil1':
    case 'soil2': {
      const lo = cfg.soil_low ?? 35
      const hi = cfg.soil_high ?? 55
      if (v < lo) return { text: `Khô (dưới ${lo}%)`, tone: 'warn' }
      if (v > hi) return { text: `Ướt (trên ${hi}%)`, tone: 'info' }
      return { text: 'Phù hợp', tone: 'ok' }
    }
    case 'tank': {
      const min = cfg.tank_min ?? 15
      return v < min ? { text: `Sắp cạn (dưới ${min}%)`, tone: 'bad' } : { text: 'Đủ nước', tone: 'ok' }
    }
    case 'air_temp': {
      const t = cfg.temp_high ?? 32
      return v >= t ? { text: `Nóng (từ ${t}°C)`, tone: 'warn' } : { text: 'Bình thường', tone: 'ok' }
    }
    case 'air_hum': {
      const h = cfg.hum_high ?? 90
      return v >= h ? { text: `Ẩm cao (từ ${h}%)`, tone: 'warn' } : { text: 'Bình thường', tone: 'ok' }
    }
    case 'light':
      return v < 50 ? { text: 'Tối', tone: 'muted' } : { text: 'Có sáng', tone: 'ok' }
    default:
      return { text: '', tone: 'muted' }
  }
}

/** Ô số đo; nháy nhẹ khi giá trị vừa đổi. */
export function MetricTile({ metric, m, cfg, compact }) {
  const info = METRICS[metric] || { text: metric, unit: '' }
  const j = judge(metric, m, cfg)
  const [flash, setFlash] = useState(false)
  const prev = useRef(m?.ts)
  useEffect(() => {
    if (m?.ts && prev.current && m.ts !== prev.current) {
      setFlash(true)
      const t = setTimeout(() => setFlash(false), 900)
      prev.current = m.ts
      return () => clearTimeout(t)
    }
    prev.current = m?.ts
    return undefined
  }, [m?.ts])
  return (
    <div className={`metric tone-${j.tone} ${flash ? 'flash' : ''} ${compact ? 'compact' : ''}`}>
      <div className="metric-name">{info.text}</div>
      <div className="metric-value">
        {m && m.ok !== false ? fmtValue(metric, m.value) : '—'}
        <span className="unit">{info.unit}</span>
      </div>
      <div className="metric-judge">{j.text}</div>
    </div>
  )
}

/** Trạng thái bơm, quạt, chế độ, khóa an toàn (state trong telemetry §8.3). */
export function ActuatorState({ state }) {
  if (!state || !Object.keys(state).length) return <span className="muted">Chưa có trạng thái bơm/quạt</span>
  const locks = Array.isArray(state.locks) ? state.locks : []
  return (
    <div className="row wrap gap-s">
      <Badge tone={state.pump ? 'ok' : 'muted'}>Bơm: {state.pump ? 'Đang chạy' : 'Tắt'}</Badge>
      <Badge tone={state.fan ? 'ok' : 'muted'}>Quạt: {state.fan ? 'Đang chạy' : 'Tắt'}</Badge>
      {state.mode && <Badge tone="info">Chế độ: {state.mode === 'AUTO' ? 'Tự động' : 'Thủ công'}</Badge>}
      {locks.map((l) => <Badge key={l} tone="warn">Khóa: {LOCKS[l] || l}</Badge>)}
    </div>
  )
}

/** Chuyển `metrics` của /telemetry/latest hoặc `data` của WS về cùng dạng { metric: {value, ok, ts} }. */
export function mergeTelemetry(prev, msg) {
  const out = { ...(prev || {}) }
  Object.entries(msg.data || {}).forEach(([k, d]) => {
    out[k] = { value: d.v, unit: d.u, ok: d.ok, ts: msg.ts }
  })
  return out
}
