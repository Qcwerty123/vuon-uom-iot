// Ảnh và chẩn đoán (đặc tả §10.9, §15, §16.1). API thuộc WP-07: hiện chạy bằng dữ liệu giả (config.js MOCK.diagnoses).
import { useCallback, useEffect, useState } from 'react'
import { get, getBlob, post } from '../api/client.js'
import { canControl, useAuth } from '../auth.jsx'
import { useDevices } from '../devices.jsx'
import { navigate } from '../router.js'
import { Badge, Card, Empty, ErrorBox, Spinner, StatusBadge, useRealtime, useToast } from '../components/ui.jsx'
import { MOCK } from '../config.js'
import ImageViewer from '../components/ImageViewer.jsx'
import { DIAG_STATUS, LEAF, fmtTime } from '../labels.js'

export default function Diagnoses({ query }) {
  const { user } = useAuth()
  const { devices, loaded } = useDevices()
  const cameras = devices.filter((d) => d.type === 'CAMERA' && d.status !== 'REGISTERED')
  const deviceId = Number(query.device) || cameras[0]?.id
  const device = devices.find((d) => d.id === deviceId)
  const [list, setList] = useState(null)
  const [selected, setSelected] = useState(null)
  const [error, setError] = useState(null)
  const [label, setLabel] = useState('')

  const load = useCallback(async () => {
    if (!deviceId) return
    try {
      const r = await get(`/devices/${deviceId}/diagnoses`, { label, size: 30 })
      const items = r.items || r
      setList(items)
      setSelected((s) => (s && items.some((x) => x.id === s) ? s : items[0]?.id ?? null))
      setError(null)
    } catch (e) { setError(e); setList([]) }
  }, [deviceId, label])
  useEffect(() => { setList(null); load() }, [load])
  useRealtime((m) => {
    if ((m.type === 'diagnosis' && m.deviceId === deviceId) || m.type === 'reconnected') load()
  }, [deviceId, load])

  return (
    <div className="stack">
      <div className="page-head">
        <h1>Ảnh &amp; chẩn đoán</h1>
        {MOCK.diagnoses && <Badge tone="warn">Dữ liệu giả — chờ backend WP-07</Badge>}
      </div>
      <Card>
        <div className="row wrap gap-s">
          <label className="inline">Camera
            <select value={deviceId || ''} onChange={(e) => navigate(`/diagnoses?device=${e.target.value}`)}>
              {cameras.map((d) => <option key={d.id} value={d.id}>{d.deviceCode} · {d.name}</option>)}
            </select>
          </label>
          <label className="inline">Kết luận
            <select value={label} onChange={(e) => setLabel(e.target.value)}>
              <option value="">Tất cả</option>
              {Object.entries(LEAF).map(([k, v]) => <option key={k} value={k}>{v.text}</option>)}
            </select>
          </label>
        </div>
      </Card>
      {loaded && !cameras.length && <Empty>Không có camera nào được gán cho bạn.</Empty>}
      <ErrorBox error={error} />
      {deviceId && (
        <div className="grid diag-layout">
          <Card title="Các lần chụp">
            {!list ? <Spinner /> : !list.length ? <Empty>Chưa có ảnh.</Empty> : (
              <ul className="list selectable">
                {list.map((d) => (
                  <li key={d.id} className={`list-item ${selected === d.id ? 'selected' : ''}`} onClick={() => setSelected(d.id)}>
                    <div className="grow">
                      <div className="small">{fmtTime(d.capturedAt)}</div>
                      <div className="row gap-s wrap">
                        {d.status === 'DONE'
                          ? <Badge tone={(LEAF[d.topLabel] || LEAF.UNKNOWN).tone}>{(LEAF[d.topLabel] || LEAF.UNKNOWN).text}</Badge>
                          : <StatusBadge map={DIAG_STATUS} value={d.status} />}
                        {d.reviewVerdict && <Badge tone="muted">{d.reviewVerdict === 'CONFIRMED' ? '✓ đã xác nhận' : '✗ đã báo sai'}</Badge>}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          {selected && <DiagnosisView id={selected} canReview={canControl(user, device)} onReviewed={load} />}
        </div>
      )}
    </div>
  )
}

function DiagnosisView({ id, canReview, onReviewed }) {
  const toast = useToast()
  const [d, setD] = useState(null)
  const [img, setImg] = useState(null)
  const [imgBytes, setImgBytes] = useState(0)
  const [viewer, setViewer] = useState(false)
  const [cropBox, setCropBox] = useState(null)
  const [error, setError] = useState(null)
  const [correct, setCorrect] = useState('')
  const [note, setNote] = useState('')
  const [reviewErr, setReviewErr] = useState(null)

  useEffect(() => {
    let url = null
    let alive = true
    setD(null); setImg(null); setError(null); setViewer(false)
    get(`/diagnoses/${id}`).then((x) => {
      if (!alive) return
      setD(x)
      // crop_box hiện tại của camera, để vẽ lưới 3×3 đúng vùng AI cắt (§15.4)
      get(`/devices/${x.deviceId}/config`).then((c) => alive && setCropBox(c.params?.crop_box ?? null)).catch(() => {})
    }).catch((e) => alive && setError(e))
    // Ảnh lấy qua API có kiểm tra quyền (không có URL tĩnh công khai, §10.9).
    getBlob(`/diagnoses/${id}/image`).then((b) => {
      url = URL.createObjectURL(b)
      if (alive) { setImg(url); setImgBytes(b.size || 0) }
    }).catch(() => {})
    return () => { alive = false; if (url) URL.revokeObjectURL(url) }
  }, [id])

  if (error) return <Card><ErrorBox error={error} /></Card>
  if (!d) return <Card><Spinner /></Card>

  const tiles = d.tiles || []
  const tileAt = (r, c) => tiles.find((t) => t.r === r && t.c === c)
  const abnormal = new Set((d.abnormalTiles || []).map(([r, c]) => `${r}-${c}`))
  const top = LEAF[d.topLabel] || LEAF.UNKNOWN

  const review = async (verdict) => {
    setReviewErr(null)
    if (verdict === 'REJECTED' && !correct) { setReviewErr('Chọn nhãn đúng trước khi báo sai'); return }
    try {
      await post(`/diagnoses/${id}/review`, { verdict, correctLabel: verdict === 'REJECTED' ? correct : undefined, note: note || undefined })
      toast('Đã lưu đánh giá', 'ok')
      setD((x) => ({ ...x, reviewVerdict: verdict, correctLabel: verdict === 'REJECTED' ? correct : null }))
      onReviewed()
    } catch (e) { setReviewErr(e) }
  }

  return (
    <Card title={`Ảnh lúc ${fmtTime(d.capturedAt)}`} actions={(
      <span className="row gap-s">
        {img && <button className="btn" onClick={() => setViewer(true)}>Xem ảnh gốc</button>}
        <StatusBadge map={DIAG_STATUS} value={d.status} />
      </span>
    )}>
      {viewer && img && (
        <ImageViewer src={img} bytes={imgBytes} fileName={`dg-${d.id}.jpg`} cropBox={cropBox}
          title={`Ảnh #${d.id} · ${fmtTime(d.capturedAt)}`} onClose={() => setViewer(false)} />
      )}
      <div className="diag-view">
        <div className="tray" onClick={() => img && setViewer(true)} style={{ cursor: img ? 'zoom-in' : undefined }}
          title={img ? 'Bấm để xem ảnh gốc' : undefined}>
          {img ? <img src={img} alt="Ảnh khay cây" /> : <div className="tray-placeholder">Đang tải ảnh…</div>}
          {d.status === 'DONE' && (
            <div className="tray-grid">
              {[0, 1, 2].map((r) => [0, 1, 2].map((c) => {
                const t = tileAt(r, c)
                const l = LEAF[t?.label] || LEAF.UNKNOWN
                return (
                  <div key={`${r}-${c}`} className={`tile ${abnormal.has(`${r}-${c}`) ? 'abnormal' : ''}`}
                    style={{ background: t ? l.color : 'transparent' }}
                    title={t ? `${l.text} ${Math.round(t.conf * 100)}%` : 'Không có cây'}>
                    {t && <span className="tile-label">{l.text}<br />{Math.round(t.conf * 100)}%</span>}
                  </div>
                )
              }))}
            </div>
          )}
        </div>
        <div className="stack-s">
          {d.status === 'DONE' ? (
            <>
              <div className="row gap-s wrap">
                <Badge tone={top.tone}>Kết luận: {top.text}</Badge>
                <Badge tone="muted">Độ tin cậy {Math.round((d.topConfidence || 0) * 100)}%</Badge>
                {abnormal.size > 0 && <Badge tone="warn">{abnormal.size} ô bất thường</Badge>}
              </div>
              <div className="legend row wrap gap-s small">
                {Object.entries(LEAF).map(([k, v]) => (
                  <span key={k} className="row gap-xs"><span className="swatch" style={{ background: v.color }} />{v.text}</span>
                ))}
              </div>
              <div className="muted small">Mô hình: {d.modelVersion || '—'} · Chụp do: {d.trigger === 'command' ? 'lệnh từ web' : 'lịch'}</div>
            </>
          ) : <div className="muted">Chưa có kết quả phân tích.</div>}

          {d.reviewVerdict && (
            <div className="alert-box info">
              Đã đánh giá: {d.reviewVerdict === 'CONFIRMED' ? 'kết quả đúng' : `kết quả sai, nhãn đúng là ${LEAF[d.correctLabel]?.text || d.correctLabel}`}
              {d.reviewedAt && ` (${fmtTime(d.reviewedAt)})`}
            </div>
          )}
          {canReview && d.status === 'DONE' && (
            <div className="stack-s review">
              <div className="label">Xác nhận kết quả AI</div>
              <label className="inline">Nhãn đúng (khi báo sai)
                <select value={correct} onChange={(e) => setCorrect(e.target.value)}>
                  <option value="">— chọn —</option>
                  {Object.entries(LEAF).map(([k, v]) => <option key={k} value={k}>{v.text}</option>)}
                </select>
              </label>
              <input placeholder="Ghi chú (không bắt buộc)" maxLength={300} value={note} onChange={(e) => setNote(e.target.value)} />
              <div className="row gap-s">
                <button className="btn primary" onClick={() => review('CONFIRMED')}>✓ Đúng</button>
                <button className="btn danger" onClick={() => review('REJECTED')}>✗ Sai</button>
              </div>
            </div>
          )}
          <ErrorBox error={reviewErr} onClose={() => setReviewErr(null)} />
        </div>
      </div>
    </Card>
  )
}
