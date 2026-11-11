import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { authAPI, tokenStore } from '../services/api'

const AuthContext = createContext(null)

/**
 * Borra la sesión local. El access token solo vive en memoria; el refresh está
 * en una cookie HttpOnly que solo el backend puede borrar (logout).
 * Limpia también los tokens que versiones anteriores guardaban en localStorage.
 */
export function clearSession() {
  tokenStore.clear()
  try {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
  } catch { /* almacenamiento bloqueado */ }
}

export function AuthProvider({ children }) {
  const [user,    setUser]    = useState(null)
  const [loading, setLoading] = useState(true)

  // Al cargar la página: si no hay access en memoria, pedir uno con la cookie
  // del refresh. Sin cookie válida, el usuario simplemente no tiene sesión.
  useEffect(() => {
    let active = true
    const restore = tokenStore.get() ? Promise.resolve() : authAPI.refresh()
    restore
      .then(() => authAPI.me())
      .then(r => { if (active) setUser(r.data) })
      .catch(() => clearSession())
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  // Guardar el access token y cargar el perfil. Paso final de ambos caminos de login.
  const startSession = useCallback(async (tokens) => {
    tokenStore.set(tokens.access)
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
  // un access nuevo sin esa marca (y renueva la cookie): reemplazarlo.
  const replaceTokens = useCallback(tokens => {
    if (tokens?.access) tokenStore.set(tokens.access)
  }, [])

  // Revoca el refresh en el servidor (lista negra + borra la cookie)
  const logout = useCallback(async () => {
    try { await authAPI.logout() } catch { /* sin red: igual se cierra localmente */ }
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
