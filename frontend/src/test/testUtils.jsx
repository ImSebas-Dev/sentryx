/**
 * Sentryx — Helper de renderizado para tests.
 * Envuelve los componentes con BrowserRouter + AuthProvider,
 * evitando repetir el boilerplate en cada test.
 */
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { AuthProvider } from '../store/AuthContext'
import { tokenStore } from '../services/api'
import { mockSession } from './mswServer'

/**
 * Renderiza un componente con todos los providers necesarios.
 *
 * @param {ReactElement} ui - Componente a renderizar
 * @param {object} options
 * @param {string}   options.initialPath   - Ruta inicial (default: '/')
 * @param {string[]} options.routerEntries - Historial de rutas para MemoryRouter
 * @param {object}   options.authState     - Estado inicial del contexto de auth
 */
export function renderWithProviders(ui, {
  initialPath    = '/',
  routerEntries  = [initialPath],
} = {}) {
  return render(
    <MemoryRouter initialEntries={routerEntries}>
      <AuthProvider>
        {ui}
      </AuthProvider>
    </MemoryRouter>
  )
}

/**
 * Simula una sesión abierta antes del render: access token en memoria y la
 * cookie HttpOnly del refresh. MSW responde /auth/me/ con el perfil.
 */
export function setAuthTokens() {
  tokenStore.set('test-access-token')
  mockSession.hasRefreshCookie = true
}

/** Simula un navegador sin sesión (sin access en memoria ni cookie). */
export function clearAuthTokens() {
  tokenStore.clear()
  mockSession.hasRefreshCookie = false
  localStorage.clear()
}

// Re-exportar todo de @testing-library/react para conveniencia
export * from '@testing-library/react'
export { default as userEvent } from '@testing-library/user-event'
