import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api, setSessionLostHandler } from '../api'

// ---------- toasts ----------
const ToastCtx = createContext(null)
export const useToast = () => useContext(ToastCtx)

export function ToastProvider({ children }) {
  const [items, setItems] = useState([])
  const push = useCallback((message, kind = 'info') => {
    const id = Math.random().toString(36).slice(2)
    setItems((xs) => [...xs, { id, message, kind }])
    setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), 4500)
  }, [])
  const toast = useMemo(() => ({ info: (m) => push(m), success: (m) => push(m, 'success'), error: (m) => push(m, 'error') }), [push])
  return (
    <ToastCtx.Provider value={toast}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {items.map((t) => <div key={t.id} className={`toast ${t.kind}`}>{t.message}</div>)}
      </div>
    </ToastCtx.Provider>
  )
}

// ---------- theme ----------
const ThemeCtx = createContext(null)
export const useTheme = () => useContext(ThemeCtx)

function applyTheme(theme) {
  const dark = theme === 'dark' || (theme === 'system' && window.matchMedia?.('(prefers-color-scheme: dark)').matches)
  document.documentElement.dataset.theme = dark ? 'dark' : 'light'
}

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(() => { try { return localStorage.getItem('theme') || 'system' } catch { return 'system' } })
  useEffect(() => { applyTheme(theme) }, [theme])
  const setTheme = useCallback((t) => {
    setThemeState(t)
    try { localStorage.setItem('theme', t) } catch { /* storage blocked: theme just won't persist locally */ }
  }, [])
  return <ThemeCtx.Provider value={{ theme, setTheme }}>{children}</ThemeCtx.Provider>
}

// ---------- auth ----------
const AuthCtx = createContext(null)
export const useAuth = () => useContext(AuthCtx)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(undefined) // undefined = still checking, null = logged out
  const { setTheme } = useTheme()

  useEffect(() => { setSessionLostHandler(() => setUser(null)) }, [])
  useEffect(() => {
    api.me().then(setUser).catch(() => setUser(null))
  }, [])
  useEffect(() => {
    if (user) api.preferences().then((p) => setTheme(p.theme)).catch(() => {})
  }, [user?.id]) // eslint-disable-line

  const enter = (res) => { setUser(res.user); return res.user }
  const value = {
    user,
    setUser,
    login: (e, p) => api.login(e, p).then(enter),
    register: (e, p) => api.register(e, p).then(enter),
    logout: async () => { try { await api.logout() } finally { setUser(null) } },
  }
  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>
}
