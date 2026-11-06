// Cấu hình ngưỡng (đặc tả §8.7, §12.5, §16.1): kiểm tra trước khi gửi, hiện "chờ thiết bị áp dụng".
import { useCallback, useEffect, useRef, useState } from 'react'
import { get, put } from '../api/client.js'
import { Card, ErrorBox, Spinner, StatusBadge, useRealtime, useToast } from './ui.jsx'
import { CONFIG_STATUS, fmtTime } from '../labels.js'

// Miền giá trị khớp backend (commands.py CFG_RANGES).
const CONTROLLER_FIELDS = [
  { k: 'soil_low', label: 'Độ ẩm đất bắt đầu tưới', unit: '%', min: 0, max: 100, step: 1 },
  { k: 'soil_high', label: 'Độ ẩm đất ngừng tưới', unit: '%', min: 0, max: 100, step: 1 },
  { k: 'pump_max_s', label: 'Thời gian bơm tối đa mỗi lần', unit: 'giây', min: 1, max: 60, int: true },
  { k: 'cooldown_s', label: 'Nghỉ giữa hai lần tưới', unit: 'giây', min: 0, max: 3600, int: true },
  { k: 'tank_min', label: 'Mực nước bể tối thiểu', unit: '%', min: 0, max: 100, step: 1 },
  { k: 'temp_high', label: 'Nhiệt độ bật quạt', unit: '°C', min: -10, max: 60, step: 0.5 },
  { k: 'temp_hyst', label: 'Độ trễ nhiệt độ', unit: '°C', min: 0.5, max: 10, step: 0.5 },
  { k: 'hum_high', label: 'Độ ẩm không khí bật quạt', unit: '%', min: 0, max: 100, step: 1 },
  { k: 'hum_hyst', label: 'Độ trễ độ ẩm', unit: '%', min: 1, max: 20, step: 1 },
  { k: 'telemetry_interval_s', label: 'Chu kỳ gửi dữ liệu', unit: 'giây', min: 2, max: 300, int: true },
]
const CAMERA_FIELDS = [
  { k: 'capture_interval_min', label: 'Chu kỳ chụp ảnh', unit: 'phút', min: 1, max: 1440, int: true },
  { k: 'jpeg_quality', label: 'Chất lượng JPEG (số nhỏ = nét hơn)', unit: '', min: 10, max: 63, int: true },
]

function validate(type, v) {
  const errs = {}
  const fields = type === 'CAMERA' ? CAMERA_FIELDS : CONTROLLER_FIELDS
  fields.forEach((f) => {
    const raw = v[f.k]
    if (raw === '' || raw === undefined || raw === null) return
    const n = Number(raw)
    if (Number.isNaN(n)) errs[f.k] = 'Phải là số'
    else if (n < f.min || n > f.max) errs[f.k] = `Trong khoảng ${f.min}–${f.max}`
    else if (f.int && !Number.isInteger(n)) errs[f.k] = 'Phải là số nguyên'
  })
  if (type !== 'CAMERA') {
    if (v.soil_low !== '' && v.soil_high !== '' && Number(v.soil_low) >= Number(v.soil_high)) {
      errs.soil_low = 'Phải nhỏ hơn ngưỡng ngừng tưới'
    }
    ;['s1', 's2'].forEach((s) => {
      const dry = v[`cal_${s}_dry`]; const wet = v[`cal_${s}_wet`]
      if (dry === '' && wet === '') return
      const d = Number(dry); const w = Number(wet)
      if (!Number.isInteger(d) || !Number.isInteger(w) || d < 0 || d > 4095 || w < 0 || w > 4095 || d - w < 200) {
        errs[`cal_${s}`] = 'Khô/ướt là ADC 0–4095 (số nguyên), khô lớn hơn ướt ít nhất 200'
      }
    })
    const e = v.tank_empty_cm; const f = v.tank_full_cm
    if (e !== '' || f !== '') {
      const en = Number(e); const fn = Number(f)
      if (Number.isNaN(en) || Number.isNaN(fn) || en < 2 || en > 400 || fn < 2 || fn > 400 || en - fn < 2) {
        errs.tank_cal = 'Khoảng cách 2–400 cm, lúc cạn lớn hơn lúc đầy ít nhất 2 cm'
      }
    }
  }
  return errs
}

function toForm(params = {}) {
  const f = {}
  ;[...CONTROLLER_FIELDS, ...CAMERA_FIELDS].forEach(({ k }) => { f[k] = params[k] ?? '' })
  f.manual_ignores_cooldown = !!params.manual_ignores_cooldown
  f.flash = params.flash ?? 'auto'
  f.cal_s1_dry = params.soil_cal?.s1?.dry ?? ''
  f.cal_s1_wet = params.soil_cal?.s1?.wet ?? ''
  f.cal_s2_dry = params.soil_cal?.s2?.dry ?? ''
  f.cal_s2_wet = params.soil_cal?.s2?.wet ?? ''
  f.tank_empty_cm = params.tank_cal?.empty_cm ?? ''
  f.tank_full_cm = params.tank_cal?.full_cm ?? ''
  return f
}

/** Chỉ gửi những khóa đã đổi so với cấu hình hiện tại. */
function diff(type, form, params = {}) {
  const out = {}
  const fields = type === 'CAMERA' ? CAMERA_FIELDS : CONTROLLER_FIELDS
  fields.forEach(({ k, int }) => {
    if (form[k] === '' || form[k] === undefined) return
    const n = int ? parseInt(form[k], 10) : Number(form[k])
    if (params[k] !== n) out[k] = n
  })
  if (type === 'CAMERA') {
    if (form.flash !== (params.flash ?? 'auto')) out.flash = form.flash
    return out
  }
  if (form.manual_ignores_cooldown !== !!params.manual_ignores_cooldown) out.manual_ignores_cooldown = form.manual_ignores_cooldown
  const cal = {}
  ;['s1', 's2'].forEach((s) => {
    const d = form[`cal_${s}_dry`]; const w = form[`cal_${s}_wet`]
    if (d === '' || w === '') return
    const cur = params.soil_cal?.[s]
    if (!cur || cur.dry !== Number(d) || cur.wet !== Number(w)) cal[s] = { dry: Number(d), wet: Number(w) }
  })
  if (Object.keys(cal).length) out.soil_cal = cal
  if (form.tank_empty_cm !== '' && form.tank_full_cm !== '') {
    const t = { empty_cm: Number(form.tank_empty_cm), full_cm: Number(form.tank_full_cm) }
    const cur = params.tank_cal
    if (!cur || cur.empty_cm !== t.empty_cm || cur.full_cm !== t.full_cm) out.tank_cal = t
  }
  return out
}

export default function ConfigPanel({ device, canEdit }) {
  const toast = useToast()
  const [cfg, setCfg] = useState(null)
  const [hist, setHist] = useState([])
  const [form, setForm] = useState(null)
  const [errs, setErrs] = useState({})
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const seen = useRef({}) // configVersion -> bản tin config_update

  const load = useCallback(async () => {
    try {
      const [c, h] = await Promise.all([
        get(`/devices/${device.id}/config`),
        get(`/devices/${device.id}/config/history`).catch(() => []),
      ])
      setCfg(c)
      setHist(h)
      setForm(toForm(c.params))
      setError(null)
    } catch (e) { setError(e) }
  }, [device.id])

  useEffect(() => { load() }, [load])

  useRealtime((m) => {
    if (m.type !== 'config_update' || m.deviceId !== device.id) return
    seen.current[m.configVersion] = m
    setCfg((c) => (c?.latest?.configVersion === m.configVersion
      ? { ...c, latest: { ...c.latest, status: m.status, rejectDetail: m.detail } } : c))
    setHist((h) => h.map((x) => (x.configVersion === m.configVersion ? { ...x, status: m.status, rejectDetail: m.detail } : x)))
    if (m.status === 'APPLIED') toast(`Thiết bị đã áp dụng cấu hình phiên bản ${m.configVersion}`, 'ok')
    if (m.status === 'REJECTED') toast(`Thiết bị từ chối cấu hình phiên bản ${m.configVersion}`, 'bad')
  }, [device.id])

  if (error && !cfg) return <Card title="Cấu hình"><ErrorBox error={error} /></Card>
  if (!cfg || !form) return <Card title="Cấu hình"><Spinner /></Card>

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }))
  const fields = device.type === 'CAMERA' ? CAMERA_FIELDS : CONTROLLER_FIELDS

  const submit = async (e) => {
    e.preventDefault()
    const v = validate(device.type, form)
    setErrs(v)
    if (Object.keys(v).length) return
    const params = diff(device.type, form, cfg.params)
    if (!Object.keys(params).length) { toast('Không có thay đổi nào', 'info'); return }
    setBusy(true); setError(null)
    try {
      const out = await put(`/devices/${device.id}/config`, { params })
      const early = seen.current[out.configVersion]
      const latest = early ? { ...out, status: early.status, rejectDetail: early.detail } : out
      setCfg((c) => ({ ...c, params: out.params, latest }))
      setHist((h) => [latest, ...h.filter((x) => x.configVersion !== out.configVersion)])
      setForm(toForm(out.params))
      toast(`Đã gửi cấu hình phiên bản ${out.configVersion}`, 'info')
    } catch (ex) {
      setError(ex)
      if (ex.details?.field) setErrs({ [ex.details.field.replace(/^params\./, '')]: ex.message })
    } finally { setBusy(false) }
  }

  const latest = cfg.latest
  return (
    <div className="stack">
      <Card title="Cấu hình thiết bị" actions={latest && (
        <span className="row gap-s">
          <span className="muted">Phiên bản {latest.configVersion}</span>
          <StatusBadge map={CONFIG_STATUS} value={latest.status} />
        </span>
      )}>
        {latest?.status === 'PENDING' && (
          <div className="alert-box info">
            <span className="dot pulse" /> Đang chờ thiết bị áp dụng phiên bản {latest.configVersion}…
            {!device.online && ' Thiết bị đang offline, sẽ áp dụng khi kết nối lại.'}
          </div>
        )}
        {latest?.status === 'REJECTED' && (
          <div className="alert-box error">Thiết bị từ chối phiên bản {latest.configVersion}
            {latest.rejectDetail ? `: ${JSON.stringify(latest.rejectDetail)}` : ''}</div>
        )}
        {!canEdit && <div className="alert-box info">Bạn chỉ có quyền xem cấu hình của thiết bị này.</div>}
        <form className="form config-form" onSubmit={submit}>
          <fieldset disabled={!canEdit || busy}>
            <div className="grid form-grid">
              {fields.map((f) => (
                <label key={f.k} className={errs[f.k] ? 'has-error' : ''}>
                  {f.label}{f.unit && <span className="muted"> ({f.unit})</span>}
                  <input type="number" min={f.min} max={f.max} step={f.step || 1} value={form[f.k]} onChange={set(f.k)} />
                  <span className="hint">{errs[f.k] || `${f.min}–${f.max}`}</span>
                </label>
              ))}
              {device.type === 'CAMERA' && (
                <label>Flash khi chụp theo lịch
                  <select value={form.flash} onChange={set('flash')}>
                    <option value="auto">Tự động</option><option value="on">Luôn bật</option><option value="off">Tắt</option>
                  </select>
                </label>
              )}
            </div>
            {device.type !== 'CAMERA' && (
              <>
                <label className="check">
                  <input type="checkbox" checked={form.manual_ignores_cooldown} onChange={set('manual_ignores_cooldown')} />
                  Lệnh bơm từ web bỏ qua thời gian nghỉ
                </label>
                <details className="more">
                  <summary>Hiệu chuẩn cảm biến (nâng cao)</summary>
                  <div className="grid form-grid">
                    {['s1', 's2'].map((s, i) => (
                      <div key={s} className={errs[`cal_${s}`] ? 'has-error' : ''}>
                        <div className="label">Cảm biến đất {i + 1} (giá trị ADC)</div>
                        <div className="row gap-s">
                          <label className="inline">Khô <input type="number" value={form[`cal_${s}_dry`]} onChange={set(`cal_${s}_dry`)} /></label>
                          <label className="inline">Ướt <input type="number" value={form[`cal_${s}_wet`]} onChange={set(`cal_${s}_wet`)} /></label>
                        </div>
                        {errs[`cal_${s}`] && <span className="hint">{errs[`cal_${s}`]}</span>}
                      </div>
                    ))}
                    <div className={errs.tank_cal ? 'has-error' : ''}>
                      <div className="label">Bể nước (khoảng cách cảm biến → mặt nước, cm)</div>
                      <div className="row gap-s">
                        <label className="inline">Lúc cạn <input type="number" step="0.1" value={form.tank_empty_cm} onChange={set('tank_empty_cm')} /></label>
                        <label className="inline">Lúc đầy <input type="number" step="0.1" value={form.tank_full_cm} onChange={set('tank_full_cm')} /></label>
                      </div>
                      {errs.tank_cal && <span className="hint">{errs.tank_cal}</span>}
                    </div>
                  </div>
                </details>
              </>
            )}
            <ErrorBox error={error} onClose={() => setError(null)} />
            {canEdit && (
              <div className="row end gap-s">
                <button type="button" className="btn" onClick={() => { setForm(toForm(cfg.params)); setErrs({}) }}>Hoàn tác</button>
                <button className="btn primary">{busy ? 'Đang gửi…' : 'Lưu và gửi xuống thiết bị'}</button>
              </div>
            )}
          </fieldset>
        </form>
      </Card>
      <Card title="Lịch sử phiên bản cấu hình">
        {hist.length === 0 ? <p className="muted">Chưa đổi cấu hình lần nào.</p> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Phiên bản</th><th>Trạng thái</th><th>Tạo lúc</th><th>Áp dụng lúc</th><th>Giá trị</th></tr></thead>
              <tbody>
                {hist.map((h) => (
                  <tr key={h.configVersion}>
                    <td>{h.configVersion}</td>
                    <td><StatusBadge map={CONFIG_STATUS} value={h.status} /></td>
                    <td>{fmtTime(h.createdAt)}</td>
                    <td>{fmtTime(h.appliedAt)}</td>
                    <td className="mono small params">{Object.entries(h.params || {}).filter(([, v]) => typeof v !== 'object')
                      .map(([k, v]) => `${k}=${v}`).join(', ')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
