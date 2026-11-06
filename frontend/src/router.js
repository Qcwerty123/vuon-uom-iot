// Định tuyến bằng hash (#/devices/1): backend chỉ phục vụ tệp tĩnh trong frontend/dist,
// nên dùng hash để tải lại trang ở mọi màn hình vẫn đúng mà không phải sửa backend.
import { useEffect, useState } from 'react'

function current() {
  const h = location.hash.replace(/^#/, '') || '/'
  const [path, qs = ''] = h.split('?')
  return { path, query: Object.fromEntries(new URLSearchParams(qs)) }
}

export function useRoute() {
  const [r, setR] = useState(current)
  useEffect(() => {
    const fn = () => setR(current())
    window.addEventListener('hashchange', fn)
    return () => window.removeEventListener('hashchange', fn)
  }, [])
  return r
}

export function navigate(path) {
  if (location.hash !== '#' + path) location.hash = path
}

/** So khớp mẫu '/devices/:id' → { id: '3' } hoặc null. */
export function match(pattern, path) {
  const a = pattern.split('/').filter(Boolean)
  const b = path.split('/').filter(Boolean)
  if (a.length !== b.length) return null
  const params = {}
  for (let i = 0; i < a.length; i++) {
    if (a[i].startsWith(':')) params[a[i].slice(1)] = decodeURIComponent(b[i])
    else if (a[i] !== b[i]) return null
  }
  return params
}
