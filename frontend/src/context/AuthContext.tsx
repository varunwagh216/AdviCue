import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, setCsrf, type AuthResponse, type UserInfo } from '../lib/api'

interface AuthValue {
  user: UserInfo | null
  checking: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserInfo | null>(null)
  const [checking, setChecking] = useState(true)

  useEffect(() => {
    let active = true
    api.get<AuthResponse>('/auth/me')
      .then(({ data }) => { if (active) { setUser(data.user); setCsrf(data.csrf_token) } })
      .catch(() => { if (active) { setUser(null); setCsrf(null) } })
      .finally(() => { if (active) setChecking(false) })
    return () => { active = false }
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const { data } = await api.post<AuthResponse>('/auth/login', { email, password })
    setUser(data.user)
    setCsrf(data.csrf_token)
  }, [])

  const logout = useCallback(async () => {
    try { await api.post('/auth/logout') }
    finally { setUser(null); setCsrf(null) }
  }, [])

  const value = useMemo(() => ({ user, checking, login, logout }), [user, checking, login, logout])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be inside AuthProvider')
  return context
}
