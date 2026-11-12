import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { realtime } from '../api/realtime.js'

/** Nhãn trạng thái: luôn có chữ, màu chỉ là phụ. */
export function Badge({ tone = 'muted', children, title }) {
  return <span className={`badge badge-${tone}`} title={title}>{children}</span>
}

export function StatusBadge({ map, value, suffix }) {
  const m = map[value] || { text: value || '—', tone: 'muted' }
  return <Badge tone={m.tone}>{m.text}{suffix ? `: ${suffix}` : ''}</Badge>
}

export function OnlineBadge({ online }) {
  return <Badge tone={online ? 'ok' : 'bad'}>{online ? '● Online' : '○ Offline'}</Badge>
}

export function ErrorBox({ error, onClose }) {
  if (!error) return null
  const msg = typeof error === 'string' ? error : error.message
  return (
    <div className="alert-box error" role="alert">
      <span>{msg}</span>
      {onClose && <button className="link" onClick={onClose} aria-label="Đóng">✕</button>}
    </div>
  )
}

export function Spinner({ label = 'Đang tải…' }) {
  return <div className="spinner"><span className="dot" />{label}</div>
}

export function Empty({ children }) {
  return <div className="empty">{children}</div>
}

export function Card({ title, actions, children, className = '' }) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="card-head">
          {title && <h2>{title}</h2>}
          {actions && <div className="card-actions">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  )
}

export function Modal({ title, onClose, children, footer, wide }) {
  useEffect(() => {
    const fn = (e) => { if (e.key === 'Escape') onClose?.() }
    window.addEventListener('keydown', fn)
    return () => window.removeEventListener('keydown', fn)
  }, [onClose])
  return (
    <div className="modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose?.() }}>
      <div className={`modal ${wide ? 'wide' : ''}`} role="dialog" aria-modal="true" aria-label={title}>
        <header className="modal-head">
          <h3>{title}</h3>
          {onClose && <button className="link" onClick={onClose} aria-label="Đóng">✕</button>}
        </header>
        <div className="modal-body">{children}</div>
        {footer && <footer className="modal-foot">{footer}</footer>}
      </div>
    </div>
  )
}

/** Hộp thoại nhập lý do (khóa, mở khóa, bảo trì…) hoặc chỉ xác nhận. */
export function ReasonDialog({ title, label = 'Lý do', confirmText = 'Xác nhận', danger, needReason = true,
  extra, onSubmit, onClose, defaultReason = '' }) {
  const [reason, setReason] = useState(defaultReason)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const submit = async (e) => {
    e.preventDefault()
    if (needReason && !reason.trim()) { setErr('Hãy nhập lý do'); return }
    setBusy(true); setErr(null)
    try { await onSubmit(reason.trim()); onClose() } catch (ex) { setErr(ex) } finally { setBusy(false) }
  }
  return (
    <Modal title={title} onClose={onClose}>
      <form onSubmit={submit} className="form">
        {extra}
        {needReason && (
          <label>{label}
            <input autoFocus value={reason} maxLength={200} onChange={(e) => setReason(e.target.value)} />
          </label>
        )}
        <ErrorBox error={err} />
        <div className="row end">
          <button type="button" className="btn" onClick={onClose}>Hủy</button>
          <button className={`btn ${danger ? 'danger' : 'primary'}`} disabled={busy}>{busy ? 'Đang gửi…' : confirmText}</button>
        </div>
      </form>
    </Modal>
  )
}

// ---------------------------------------------------------------------------
// Thông báo nhỏ góc màn hình

const ToastCtx = createContext(() => {})

export function ToastProvider({ children }) {
  const [items, setItems] = useState([])
  const idRef = useRef(0)
  const push = useCallback((text, tone = 'info') => {
    const id = ++idRef.current
    setItems((xs) => [...xs, { id, text, tone }])
    setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), 5000)
  }, [])
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts" aria-live="polite">
        {items.map((t) => <div key={t.id} className={`toast toast-${t.tone}`}>{t.text}</div>)}
      </div>
    </ToastCtx.Provider>
  )
}

export function useToast() {
  return useContext(ToastCtx)
}

// ---------------------------------------------------------------------------

/** Banner khi mất WebSocket (WP-04 §3.7). */
export function ConnectionBanner() {
  const [state, setState] = useState(realtime.state)
  useEffect(() => realtime.onStatus(setState), [])
  if (state !== 'down') return null
  return (
    <div className="banner" role="status">
      Mất kết nối thời gian thực với máy chủ. Đang tự kết nối lại… Số liệu trên màn hình có thể chưa mới.
    </div>
  )
}

/** Đăng ký nhận bản tin WS trong vòng đời component. */
export function useRealtime(handler, deps = []) {
  const ref = useRef(handler)
  ref.current = handler
  useEffect(() => realtime.on((m) => ref.current(m)), deps) // eslint-disable-line react-hooks/exhaustive-deps
}

/** Tải dữ liệu bất đồng bộ: { data, error, loading, reload, setData }. */
export function useLoad(fn, deps = []) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const seq = useRef(0)
  const reload = useCallback(async () => {
    const my = ++seq.current
    setLoading(true)
    try {
      const d = await fn()
      if (my === seq.current) { setData(d); setError(null) }
    } catch (e) {
      if (my === seq.current) setError(e)
    } finally {
      if (my === seq.current) setLoading(false)
    }
  }, deps) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { reload() }, [reload])
  return { data, error, loading, reload, setData }
}

/** Đồng hồ để cập nhật các chữ "x giây trước". */
export function useTick(ms = 5000) {
  const [, set] = useState(0)
  useEffect(() => {
    const t = setInterval(() => set((x) => x + 1), ms)
    return () => clearInterval(t)
  }, [ms])
}

export function CopyButton({ text, label = 'Sao chép' }) {
  const [done, setDone] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      // http (không phải https) trên điện thoại có thể chặn clipboard API
      const ta = document.createElement('textarea')
      ta.value = text
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      ta.remove()
    }
    setDone(true)
    setTimeout(() => setDone(false), 2000)
  }
  return <button type="button" className="btn small" onClick={copy}>{done ? '✓ Đã sao chép' : label}</button>
}

export function Pager({ page, size, total, onPage }) {
  const pages = Math.max(1, Math.ceil((total || 0) / size))
  return (
    <div className="pager">
      <button className="btn small" disabled={page <= 0} onClick={() => onPage(page - 1)}>‹ Trước</button>
      <span>Trang {page + 1}/{pages} · {total ?? 0} mục</span>
      <button className="btn small" disabled={page + 1 >= pages} onClick={() => onPage(page + 1)}>Sau ›</button>
    </div>
  )
}
