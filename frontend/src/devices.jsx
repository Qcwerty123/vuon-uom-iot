// Danh sách thiết bị dùng chung cho mọi màn hình; cập nhật trạng thái realtime qua WS `device_status`.
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { get } from './api/client.js'
import { realtime } from './api/realtime.js'
import { useRealtime } from './components/ui.jsx'

const Ctx = createContext(null)

export function DevicesProvider({ children }) {
  const [devices, setDevices] = useState([])
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState(null)

  const reload = useCallback(async () => {
    try {
      const list = await get('/devices')
      setDevices(list)
      setError(null)
      realtime.watch(list.map((d) => d.id))
    } catch (e) {
      setError(e)
    } finally {
      setLoaded(true)
    }
  }, [])

  useEffect(() => { reload() }, [reload])
  // Tải lại định kỳ: thiết bị mới đăng ký sau khi mở web (ví dụ sim.ps1 register) cũng được đăng ký nhận WS,
  // và trạng thái vẫn đúng nếu lỡ một bản tin device_status.
  useEffect(() => {
    const t = setInterval(() => { reload() }, 30000)
    return () => clearInterval(t)
  }, [reload])

  useRealtime((m) => {
    if (m.type === 'device_status') {
      setDevices((xs) => xs.map((d) => (d.id === m.deviceId
        ? { ...d, status: m.status, online: m.online, lastSeenAt: m.lastSeenAt ?? d.lastSeenAt }
        : d)))
    } else if (m.type === 'telemetry') {
      setDevices((xs) => xs.map((d) => (d.id === m.deviceId ? { ...d, lastSeenAt: m.ts, online: true } : d)))
    } else if (m.type === 'reconnected') {
      reload()
    }
  }, [reload])

  const value = useMemo(() => ({
    devices,
    loaded,
    error,
    reload,
    byId: Object.fromEntries(devices.map((d) => [d.id, d])),
    /** Cập nhật một thiết bị sau khi gọi API (khóa, mở khóa…). */
    upsert: (dev) => setDevices((xs) => (xs.some((d) => d.id === dev.id)
      ? xs.map((d) => (d.id === dev.id ? { ...d, ...dev } : d))
      : [...xs, dev])),
  }), [devices, loaded, error, reload])

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useDevices() {
  return useContext(Ctx)
}
