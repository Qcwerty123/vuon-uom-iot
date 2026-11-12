// Trình xem ảnh gốc toàn màn hình: phóng to/thu nhỏ (cuộn chuột, nút, phím + -), kéo để di chuyển,
// xoay 90°, lưới 3×3 theo crop_box (nếu có), tải ảnh gốc. Esc để đóng.
import { useCallback, useEffect, useRef, useState } from 'react'

const MIN = 0.2
const MAX = 8

/**
 * src: object URL của ảnh (đã tải qua API có kiểm tra quyền).
 * cropBox: [x0, y0, x1, y1] theo pixel, hoặc tỉ lệ 0..1 (như AI service); null = cả ảnh.
 */
export default function ImageViewer({ src, fileName = 'anh-goc.jpg', bytes, title, cropBox, onClose }) {
  const box = useRef(null)
  const [nat, setNat] = useState(null)        // {w, h} kích thước gốc
  const [scale, setScale] = useState(1)
  const [rot, setRot] = useState(0)
  const [pos, setPos] = useState({ x: 0, y: 0 })
  const [grid, setGrid] = useState(false)
  const drag = useRef(null)

  const fit = useCallback(() => {
    const el = box.current
    if (!el || !nat) return
    const sideways = rot % 180 !== 0
    const w = sideways ? nat.h : nat.w
    const h = sideways ? nat.w : nat.h
    setScale(Math.min(el.clientWidth / w, el.clientHeight / h, 1) * 0.95)
    setPos({ x: 0, y: 0 })
  }, [nat, rot])

  useEffect(() => { fit() }, [fit])

  const zoom = useCallback((f) => setScale((s) => Math.min(MAX, Math.max(MIN, s * f))), [])

  useEffect(() => {
    const fn = (e) => {
      if (e.key === 'Escape') onClose()
      else if (e.key === '+' || e.key === '=') zoom(1.25)
      else if (e.key === '-') zoom(0.8)
      else if (e.key === '0') fit()
      else if (e.key === '1') { setScale(1); setPos({ x: 0, y: 0 }) }
      else if (e.key === 'r' || e.key === 'R') setRot((r) => (r + (e.shiftKey ? 270 : 90)) % 360)
      else if (e.key === 'g' || e.key === 'G') setGrid((g) => !g)
    }
    window.addEventListener('keydown', fn)
    return () => window.removeEventListener('keydown', fn)
  }, [onClose, zoom, fit])

  const onWheel = (e) => { e.preventDefault(); zoom(e.deltaY < 0 ? 1.15 : 0.87) }
  useEffect(() => {  // passive: false để chặn cuộn trang khi phóng to
    const el = box.current
    if (!el) return undefined
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  })

  const down = (e) => { drag.current = { x: e.clientX - pos.x, y: e.clientY - pos.y }; e.currentTarget.setPointerCapture?.(e.pointerId) }
  const move = (e) => { if (drag.current) setPos({ x: e.clientX - drag.current.x, y: e.clientY - drag.current.y }) }
  const up = () => { drag.current = null }

  // Vùng lưới 3×3 theo pixel ảnh gốc
  let g = null
  if (nat) {
    let [x0, y0, x1, y1] = Array.isArray(cropBox) && cropBox.length === 4 ? cropBox : [0, 0, nat.w, nat.h]
    if ([x0, y0, x1, y1].every((v) => v >= 0 && v <= 1) && Array.isArray(cropBox)) {
      x0 *= nat.w; x1 *= nat.w; y0 *= nat.h; y1 *= nat.h
    }
    g = { x0, y0, w: x1 - x0, h: y1 - y0 }
  }

  return (
    <div className="viewer" role="dialog" aria-modal="true" aria-label="Xem ảnh gốc">
      <div className="viewer-bar">
        <span className="viewer-title">{title}</span>
        <span className="muted small">
          {nat ? `${nat.w}×${nat.h} px` : ''}{bytes ? ` · ${Math.round(bytes / 1024)} KB` : ''} · {Math.round(scale * 100)}%
        </span>
        <span className="row gap-s wrap">
          <button className="btn" onClick={() => zoom(0.8)} title="Thu nhỏ (−)">−</button>
          <button className="btn" onClick={() => zoom(1.25)} title="Phóng to (+)">+</button>
          <button className="btn" onClick={fit} title="Vừa màn hình (0)">Vừa khung</button>
          <button className="btn" onClick={() => { setScale(1); setPos({ x: 0, y: 0 }) }} title="Kích thước gốc (1)">1:1</button>
          <button className="btn" onClick={() => setRot((r) => (r + 270) % 360)} title="Xoay trái (Shift+R)">⟲</button>
          <button className="btn" onClick={() => setRot((r) => (r + 90) % 360)} title="Xoay phải (R)">⟳</button>
          <button className={`btn ${grid ? 'primary' : ''}`} onClick={() => setGrid((x) => !x)} title="Lưới 3×3 (G)">Lưới</button>
          <a className="btn" href={src} download={fileName}>Tải ảnh gốc</a>
          <button className="btn" onClick={onClose} title="Đóng (Esc)">✕</button>
        </span>
      </div>
      <div className="viewer-stage" ref={box} onPointerDown={down} onPointerMove={move} onPointerUp={up}
        onPointerCancel={up} onDoubleClick={() => (scale < 1.5 ? zoom(2) : fit())}>
        <div className="viewer-img" style={{
          width: nat?.w, height: nat?.h,
          transform: `translate(-50%, -50%) translate(${pos.x}px, ${pos.y}px) rotate(${rot}deg) scale(${scale})`,
        }}>
          <img src={src} alt="Ảnh gốc" draggable={false}
            onLoad={(e) => setNat({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })} />
          {grid && g && (
            <div className="viewer-grid" style={{ left: g.x0, top: g.y0, width: g.w, height: g.h }}>
              {Array.from({ length: 9 }, (_, i) => <span key={i}>{Math.floor(i / 3)},{i % 3}</span>)}
            </div>
          )}
        </div>
      </div>
      <div className="viewer-help muted small">
        Cuộn chuột để phóng to · kéo để di chuyển · nháy đúp: phóng to / vừa khung · R xoay · G lưới
        {Array.isArray(cropBox) ? ' (lưới theo crop_box)' : ' (lưới trên cả ảnh, chưa đặt crop_box)'} · Esc đóng
      </div>
    </div>
  )
}
