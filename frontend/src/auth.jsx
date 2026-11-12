import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import * as client from './api/client.js'
import { realtime } from './api/realtime.js'

const AuthCtx = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [ready, setReady] = useState(false)
  const [notice, setNotice] = useState('')

  useEffect(() => {
    client.onAuthChange(
      (u) => { setUser(u); realtime.reauth() },
      (msg) => { realtime.stop(); setUser(null); setNotice(msg || '') },
    )
    // Tải lại trang: access token mất (chỉ ở bộ nhớ), dùng refresh token để khôi phục phiên.
    if (client.hasRefreshToken()) {
      client.refreshSession().catch(() => {}).finally(() => setReady(true))
    } else {
      setReady(true)
    }
  }, [])

  useEffect(() => {
    if (user) realtime.start()
  }, [user])

  const login = useCallback(async (username, password) => {
    setNotice('')
    const u = await client.login(username, password)
    setUser(u)
    return u
  }, [])

  const logout = useCallback(async () => {
    realtime.stop()
    await client.logout()
    setUser(null)
  }, [])

  const value = useMemo(() => ({
    user,
    ready,
    notice,
    setUser,
    login,
    logout,
    isAdmin: user?.role === 'ADMIN',
  }), [user, ready, notice, login, logout])

  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>
}

export function useAuth() {
  return useContext(AuthCtx)
}

/** Quyền trên một thiết bị: backend trả `permission` = VIEW/CONTROL (ADMIN luôn CONTROL). */
export function canControl(user, device) {
  if (!user || !device) return false
  if (user.role === 'ADMIN') return true
  return user.role === 'OPERATOR' && device.permission === 'CONTROL'
}
