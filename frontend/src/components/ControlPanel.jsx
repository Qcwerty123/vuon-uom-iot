// Điều khiển (đặc tả §16.1, §12.2): mỗi nút hiện trạng thái lệnh PENDING → kết quả.
import { useEffect, useRef, useState } from 'react'
import { get, post } from '../api/client.js'
import { ActuatorState } from './device.jsx'
import { Badge, Card, ErrorBox, useRealtime } from './ui.jsx'
import { ACTION, COMMAND_STATUS, commandText } from '../labels.js'

const ACCEPTS = new Set(['ACTIVE', 'FAULT', 'MAINTENANCE'])

function CmdStatus({ c }) {
  if (!c) return null
  const tone = COMMAND_STATUS[c.status]?.tone || 'muted'
  return (
    <Badge tone={tone}>
      {c.status === 'PENDING' && <span className="dot pulse" />}
      {ACTION[c.action] || c.action}: {commandText(c)}
    </Badge>
  )
}

export default function ControlPanel({ device, state }) {
  const [cmds, setCmds] = useState({}) // key -> command
  const [error, setError] = useState(null)
  const [duration, setDuration] = useState(5)
  const [flash, setFlash] = useState('off')
  const timers = useRef({})
  const seen = useRef({}) // cmdId -> bản tin command_update (ack có thể về trước cả phản hồi HTTP)

  useEffect(() => () => Object.values(timers.current).forEach(clearTimeout), [])

  useRealtime((m) => {
    if (m.type !== 'command_update' || m.deviceId !== device.id) return
    seen.current[m.cmdId] = m
    setCmds((xs) => {
      const out = { ...xs }
      Object.entries(out).forEach(([k, c]) => {
        if (c.cmdId === m.cmdId) out[k] = { ...c, status: m.status, result: m.result, detail: m.detail }
      })
      return out
    })
  }, [device.id])

  const blocked = !device.online
    ? 'Thiết bị đang offline nên không nhận lệnh.'
    : !ACCEPTS.has(device.status) ? `Thiết bị đang ở trạng thái ${device.status}, không nhận lệnh.` : null

  const send = async (key, action, params = {}) => {
    setError(null)
    setCmds((xs) => ({ ...xs, [key]: { status: 'PENDING', action, sending: true } }))
    try {
      const r = await post(`/devices/${device.id}/commands`, { action, params })
      const early = seen.current[r.cmdId]
      setCmds((xs) => ({ ...xs, [key]: early
        ? { cmdId: r.cmdId, action, status: early.status, result: early.result, detail: early.detail }
        : { cmdId: r.cmdId, action, status: 'PENDING' } }))
      // Dự phòng khi lỡ bản tin WS: hỏi lại sau 12 s (backend tự TIMEOUT sau 10 s).
      clearTimeout(timers.current[key])
      timers.current[key] = setTimeout(async () => {
        try {
          const c = await get(`/commands/${r.cmdId}`)
          setCmds((xs) => (xs[key]?.cmdId === r.cmdId ? { ...xs, [key]: c } : xs))
        } catch { /* bỏ qua */ }
      }, 12000)
    } catch (e) {
      setCmds((xs) => { const o = { ...xs }; delete o[key]; return o })
      setError(e)
    }
  }

  const pending = (key) => cmds[key]?.status === 'PENDING'
  const btn = (key, label, action, params, cls = '') => (
    <button className={`btn ${cls}`} disabled={!!blocked || pending(key)} onClick={() => send(key, action, params)}>
      {label}
    </button>
  )

  return (
    <Card title="Điều khiển">
      {blocked && <div className="alert-box warn">{blocked}</div>}
      <ErrorBox error={error} onClose={() => setError(null)} />
      {device.type === 'CONTROLLER' && (
        <div className="stack">
          <div>
            <div className="label">Trạng thái hiện tại</div>
            <ActuatorState state={state} />
          </div>
          <div className="control-row">
            <div className="control-name">Bơm tưới</div>
            <div className="row wrap gap-s">
              <label className="inline">Thời gian
                <select value={duration} onChange={(e) => setDuration(Number(e.target.value))}>
                  {[3, 5, 10, 15, 20, 30, 45, 60].map((s) => <option key={s} value={s}>{s} giây</option>)}
                </select>
              </label>
              {btn('pump_on', `Bật bơm ${duration} giây`, 'pump_on', { duration_s: duration }, 'primary')}
              {btn('pump_off', 'Tắt bơm', 'pump_off')}
            </div>
            <div className="row wrap gap-s"><CmdStatus c={cmds.pump_on} /><CmdStatus c={cmds.pump_off} /></div>
          </div>
          <div className="control-row">
            <div className="control-name">Quạt thông gió</div>
            <div className="row wrap gap-s">
              {btn('fan_on', 'Bật quạt', 'fan_on')}
              {btn('fan_off', 'Tắt quạt', 'fan_off')}
            </div>
            <div className="row wrap gap-s"><CmdStatus c={cmds.fan_on} /><CmdStatus c={cmds.fan_off} /></div>
          </div>
          <div className="control-row">
            <div className="control-name">Chế độ</div>
            <div className="row wrap gap-s">
              {btn('mode_auto', 'Tự động (AUTO)', 'set_mode', { mode: 'AUTO' })}
              {btn('mode_manual', 'Thủ công (MANUAL)', 'set_mode', { mode: 'MANUAL' })}
            </div>
            <div className="row wrap gap-s"><CmdStatus c={cmds.mode_auto} /><CmdStatus c={cmds.mode_manual} /></div>
          </div>
        </div>
      )}
      {device.type === 'CAMERA' && (
        <div className="stack">
          <div className="control-row">
            <div className="control-name">Chụp ảnh</div>
            <div className="row wrap gap-s">
              <label className="inline">Flash
                <select value={flash} onChange={(e) => setFlash(e.target.value)}>
                  <option value="off">Tắt</option>
                  <option value="on">Bật</option>
                </select>
              </label>
              {btn('capture', 'Chụp ngay', 'capture', { flash }, 'primary')}
            </div>
            <CmdStatus c={cmds.capture} />
            {cmds.capture?.status === 'EXECUTED' && (
              <div className="muted small">Ảnh sẽ có trong mục <a href={`#/diagnoses?device=${device.id}`}>Ảnh &amp; chẩn đoán</a> sau khi phân tích.</div>
            )}
          </div>
          <div className="control-row">
            <div className="control-name">Đèn flash</div>
            <div className="row wrap gap-s">
              {btn('flash_on', 'Bật 5 giây', 'flash', { state: 'on', duration_s: 5 })}
              {btn('flash_off', 'Tắt', 'flash', { state: 'off' })}
            </div>
            <div className="row wrap gap-s"><CmdStatus c={cmds.flash_on} /><CmdStatus c={cmds.flash_off} /></div>
          </div>
        </div>
      )}
      <details className="more">
        <summary>Lệnh khác</summary>
        <div className="row wrap gap-s">
          {btn('request_status', ACTION.request_status, 'request_status')}
          <button className="btn danger" disabled={!!blocked || pending('reboot')}
            onClick={() => { if (window.confirm('Khởi động lại thiết bị?')) send('reboot', 'reboot') }}>
            {ACTION.reboot}
          </button>
          <CmdStatus c={cmds.request_status} /><CmdStatus c={cmds.reboot} />
        </div>
      </details>
      <p className="muted small">Giới hạn 10 lệnh/phút cho mỗi thiết bị. Thiết bị có thể từ chối lệnh nếu bể cạn, đang nghỉ giữa hai lần tưới hoặc đang khóa tại chỗ.</p>
    </Card>
  )
}
