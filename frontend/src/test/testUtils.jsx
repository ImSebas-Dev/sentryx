/**
 * Sentryx — Helper de renderizado para tests.
 * Envuelve los componentes con BrowserRouter + AuthProvider,
 * evitando repetir el boilerplate en cada test.
 */
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { AuthProvider } from '../store/AuthContext'
import { vi } from 'vitest'

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
 * Simula un usuario autenticado en localStorage antes del render.
 * El servidor MSW se encarga de responder /auth/me/ con el perfil.
 */
export function setAuthTokens() {
  localStorage.setItem('access_token',  'test-access-token')
  localStorage.setItem('refresh_token', 'test-refresh-token')
}

export function clearAuthTokens() {
  localStorage.clear()
}

// Re-exportar todo de @testing-library/react para conveniencia
export * from '@testing-library/react'
export { default as userEvent } from '@testing-library/user-event'
