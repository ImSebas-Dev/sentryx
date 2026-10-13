/**
 * Sentryx — Tema claro / oscuro.
 *
 * mode:  preferencia del usuario ('light' | 'dark' | 'system')
 * theme: tema efectivo ('light' | 'dark'); con 'system' sigue al sistema
 *        operativo y cambia en vivo si el usuario lo cambia allí.
 *
 * El script inline de index.html aplica el tema antes del primer pintado;
 * este contexto lo mantiene sincronizado después.
 */
import { createContext, useContext, useEffect, useState, useCallback } from 'react'

const STORAGE_KEY = 'sentryx-theme'
const THEME_COLORS = { light: '#fafafa', dark: '#141414' }

function readMode() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'light' || stored === 'dark' || stored === 'system') return stored
  } catch { /* almacenamiento bloqueado: usar el sistema */ }
  return 'system'
}

function systemPrefersDark() {
  return typeof window !== 'undefined'
    && !!window.matchMedia?.('(prefers-color-scheme: dark)')?.matches
}

const ThemeContext = createContext({
  mode: 'system',
  theme: 'light',
  setMode: () => {},
})

export function ThemeProvider({ children }) {
  const [mode, setModeState]     = useState(readMode)
  const [systemDark, setSystemDark] = useState(systemPrefersDark)

  // Seguir los cambios del sistema operativo
  useEffect(() => {
    const mq = window.matchMedia?.('(prefers-color-scheme: dark)')
    if (!mq) return
    const onChange = e => setSystemDark(e.matches)
    mq.addEventListener?.('change', onChange)
    return () => mq.removeEventListener?.('change', onChange)
  }, [])

  const theme = mode === 'system' ? (systemDark ? 'dark' : 'light') : mode

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    document.querySelector('meta[name="theme-color"]')
      ?.setAttribute('content', THEME_COLORS[theme])
  }, [theme])

  const setMode = useCallback(next => {
    setModeState(next)
    try { localStorage.setItem(STORAGE_KEY, next) } catch { /* sin persistencia */ }
  }, [])

  return (
    <ThemeContext.Provider value={{ mode, theme, setMode }}>
      {children}
    </ThemeContext.Provider>
  )
}

export const useTheme = () => useContext(ThemeContext)
