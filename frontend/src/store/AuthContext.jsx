import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { authAPI } from '../services/api'

const AuthContext = createContext(null)

// Solo se borran los tokens: otras preferencias (p. ej. el tema) se conservan
export function clearSession() {
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
}

export function AuthProvider({ children }) {
  const [user,    setUser]    = useState(null)
  const [loading, setLoading] = useState(true)

  // Cargar perfil si hay token guardado
  useEffect(() => {
    const token = localStorage.getItem('access_token')
    if (!token) { setLoading(false); return }
    authAPI.me()
      .then(r => setUser(r.data))
      .catch(() => clearSession())
      .finally(() => setLoading(false))
  }, [])

  // Guardar el par JWT y cargar el perfil. Paso final de ambos caminos de login.
  const startSession = useCallback(async (tokens) => {
    localStorage.setItem('access_token',  tokens.access)
    localStorage.setItem('refresh_token', tokens.refresh)
    const me = await authAPI.me()
    setUser(me.data)
    return me.data
  }, [])

  /**
   * Primer paso del login. Si la cuenta tiene 2FA devuelve
   * { mfaRequired: true, mfaToken, expiresIn } sin abrir sesión; el llamador
   * debe pedir el código y llamar a verifyMfa. Si no, devuelve el perfil.
   */
  const login = useCallback(async (email, password) => {
    const { data } = await authAPI.login({ email, password })
    if (data.mfa_required) {
      return { mfaRequired: true, mfaToken: data.mfa_token, expiresIn: data.expires_in }
    }
    return startSession(data)
  }, [startSession])

  // Segundo paso: { code } o { recovery_code }
  const verifyMfa = useCallback(async (mfaToken, payload) => {
    const { data } = await authAPI.mfaVerify({ mfa_token: mfaToken, ...payload })
    const me = await startSession(data)
    return { ...me, recovery_codes_remaining: data.recovery_codes_remaining }
  }, [startSession])

  // Recargar el perfil (p. ej. tras activar o desactivar el 2FA)
  const refreshUser = useCallback(async () => {
    const me = await authAPI.me()
    setUser(me.data)
    return me.data
  }, [])

  // Al activar el 2FA con un token mfa_setup_required el backend entrega
  // tokens nuevos sin esa marca: reemplazarlos sin cerrar sesión.
  const replaceTokens = useCallback(tokens => {
    if (tokens?.access)  localStorage.setItem('access_token',  tokens.access)
    if (tokens?.refresh) localStorage.setItem('refresh_token', tokens.refresh)
  }, [])

  const logout = useCallback(() => {
    clearSession()
    setUser(null)
  }, [])

  const isAdmin   = user?.role === 'admin' || user?.is_admin === true
  const isAnalyst = ['admin','analyst'].includes(user?.role) || user?.is_analyst === true

  return (
    <AuthContext.Provider value={{
      user, loading, login, verifyMfa, refreshUser, replaceTokens, logout, isAdmin, isAnalyst,
    }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
