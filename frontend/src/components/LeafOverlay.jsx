// Vẽ viền từng lá do AI tách (MobileSAM) lên ảnh. Dùng cho trình xem ảnh gốc và khung ảnh trong trang Chẩn đoán.
//
// leaves: [{ tile: [r, c], label, conf, bbox: [x, y, w, h], polygon: [[x, y], ...] }]
//   polygon chuẩn hóa 0..1 theo VÙNG ĐÃ CẮT (crop_box), không phải cả ảnh (xem leaf_pipeline.py).
// region: vùng crop_box tính theo phân số của cả ảnh {x, y, w, h}; xem cropRegion().
// Phần tử cha phải có position: relative và đúng bằng khung ảnh (overlay phủ kín bằng inset: 0).
import { LEAF } from '../labels.js'

const STROKE = { HEALTHY: '#2f9e44', YELLOW: '#f0b400', SPOT: '#e03131', UNKNOWN: '#adb5bd' }

/** cropBox: [x0, y0, x1, y1] theo pixel hoặc tỉ lệ 0..1 (giống AI service); nat: {w, h} kích thước gốc của ảnh.
 *  Trả về null nếu cần kích thước ảnh mà chưa có. */
export function cropRegion(cropBox, nat) {
  if (!Array.isArray(cropBox) || cropBox.length !== 4) return { x: 0, y: 0, w: 1, h: 1 }
  let [x0, y0, x1, y1] = cropBox
  if (![x0, y0, x1, y1].every((v) => v >= 0 && v <= 1)) {
    if (!nat?.w || !nat?.h) return null
    x0 /= nat.w; x1 /= nat.w; y0 /= nat.h; y1 /= nat.h
  }
  const r = { x: x0, y: y0, w: x1 - x0, h: y1 - y0 }
  return r.w > 0 && r.h > 0 ? r : { x: 0, y: 0, w: 1, h: 1 }
}

function centroid(poly) {
  let sx = 0
  let sy = 0
  poly.forEach(([x, y]) => { sx += x; sy += y })
  return [sx / poly.length, sy / poly.length]
}

export default function LeafOverlay({ leaves, region, fontPx = 11, showText = true }) {
  const list = (leaves || []).filter((l) => Array.isArray(l.polygon) && l.polygon.length >= 3)
  if (!list.length || !region) return null
  const pct = (v) => `${v * 100}%`
  return (
    <div className="leaf-overlay">
      <div className="leaf-region" style={{ left: pct(region.x), top: pct(region.y), width: pct(region.w), height: pct(region.h) }}>
        <svg viewBox="0 0 1 1" preserveAspectRatio="none" className="leaf-svg">
          {list.map((l, i) => (
            <polygon key={i} points={l.polygon.map((p) => p.join(',')).join(' ')}
              fill={(LEAF[l.label] || LEAF.UNKNOWN).color} stroke={STROKE[l.label] || STROKE.UNKNOWN}
              strokeWidth="2" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
          ))}
        </svg>
        {showText && list.map((l, i) => {
          const [cx, cy] = centroid(l.polygon)
          const lf = LEAF[l.label] || LEAF.UNKNOWN
          return (
            <span key={i} className="leaf-tag" style={{ left: pct(cx), top: pct(cy), fontSize: fontPx, background: STROKE[l.label] || STROKE.UNKNOWN }}>
              {lf.text} {Math.round((l.conf || 0) * 100)}%
            </span>
          )
        })}
      </div>
    </div>
  )
}
