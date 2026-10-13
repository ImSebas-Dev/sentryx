/**
 * Sentryx — Tests de la página de Login.
 * Verifica el flujo completo: form → API → redirección.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/mswServer'
import { renderWithProviders, clearAuthTokens } from '../../test/testUtils'
import LoginPage from '../LoginPage'

// Mock de useNavigate para verificar redirecciones
const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual, useNavigate: () => mockNavigate }
})

describe('LoginPage', () => {
  beforeEach(() => {
    clearAuthTokens()
    mockNavigate.mockClear()
  })

  it('renderiza el formulario de login', () => {
    renderWithProviders(<LoginPage />)
    expect(screen.getAllByText('Sentryx').length).toBeGreaterThan(0)
    expect(screen.getByLabelText('Correo electrónico')).toBeInTheDocument()
    expect(screen.getByLabelText('Contraseña')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /entrar/i })).toBeInTheDocument()
  })

  it('muestra el subtítulo de la plataforma', () => {
    renderWithProviders(<LoginPage />)
    expect(screen.getByText(/plataforma de detección de phishing/i)).toBeInTheDocument()
  })

  it('el botón de login está habilitado inicialmente', () => {
    renderWithProviders(<LoginPage />)
    expect(screen.getByRole('button', { name: /entrar/i })).not.toBeDisabled()
  })

  it('login exitoso redirige al dashboard', async () => {
    const user = userEvent.setup()
    renderWithProviders(<LoginPage />)

    await user.type(screen.getByLabelText('Correo electrónico'), 'analista@sentryx.test')
    await user.type(screen.getByLabelText('Contraseña'), 'correcta')
    await user.click(screen.getByRole('button', { name: /entrar/i }))

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/')
    })
  })

  it('guarda tokens en localStorage tras login exitoso', async () => {
    const user = userEvent.setup()
    renderWithProviders(<LoginPage />)

    await user.type(screen.getByLabelText('Correo electrónico'), 'analista@sentryx.test')
    await user.type(screen.getByLabelText('Contraseña'), 'correcta')
    await user.click(screen.getByRole('button', { name: /entrar/i }))

    await waitFor(() => {
      expect(localStorage.getItem('access_token')).toBeTruthy()
      expect(localStorage.getItem('refresh_token')).toBeTruthy()
    })
  })

  it('muestra error con credenciales incorrectas', async () => {
    const user = userEvent.setup()
    renderWithProviders(<LoginPage />)

    await user.type(screen.getByLabelText('Correo electrónico'), 'analista@sentryx.test')
    await user.type(screen.getByLabelText('Contraseña'), 'contraseña_incorrecta')
    await user.click(screen.getByRole('button', { name: /entrar/i }))

    await waitFor(() => {
      expect(screen.getAllByText(/Correo o contraseña incorrectos/i).length).toBeGreaterThan(0)
    })
    expect(mockNavigate).not.toHaveBeenCalled()
  })

  it('no guarda tokens si el login falla', async () => {
    const user = userEvent.setup()
    renderWithProviders(<LoginPage />)

    await user.type(screen.getByLabelText('Correo electrónico'), 'analista@sentryx.test')
    await user.type(screen.getByLabelText('Contraseña'), 'mal')
    await user.click(screen.getByRole('button', { name: /entrar/i }))

    await waitFor(() => {
      expect(screen.getAllByText(/Correo o contraseña incorrectos/i).length).toBeGreaterThan(0)
    })
    expect(localStorage.getItem('access_token')).toBeNull()
  })

  it('muestra el botón de submit con texto Entrar', async () => {
    renderWithProviders(<LoginPage />)
    expect(screen.getByRole('button', { name: /entrar/i })).toBeInTheDocument()
  })

  it('el error se puede descartar', async () => {
    const user = userEvent.setup()
    renderWithProviders(<LoginPage />)

    await user.type(screen.getByLabelText('Correo electrónico'), 'x@sentryx.test')
    await user.type(screen.getByLabelText('Contraseña'), 'y')
    await user.click(screen.getByRole('button', { name: /entrar/i }))

    await waitFor(() => {
      expect(screen.getAllByText(/Correo o contraseña incorrectos/i).length).toBeGreaterThan(0)
    })

    // Cerrar el mensaje no debe reenviar el formulario (el botón vive dentro del <form>)
    await user.click(screen.getByRole('button', { name: /cerrar mensaje de error/i }))

    await waitFor(() =>
      expect(screen.queryAllByText(/Correo o contraseña incorrectos/i).length).toBe(0))
  })

  it('muestra error cuando el servidor no está disponible', async () => {
    server.use(
      http.post('/api/v1/auth/token/', () => HttpResponse.error())
    )
    const user = userEvent.setup()
    renderWithProviders(<LoginPage />)

    await user.type(screen.getByLabelText('Correo electrónico'), 'analista@sentryx.test')
    await user.type(screen.getByLabelText('Contraseña'), 'correcta')
    await user.click(screen.getByRole('button', { name: /entrar/i }))

    await waitFor(() => {
      // Debe mostrar algún mensaje de error
      expect(screen.getByText(/No se pudo conectar con el servidor/i)).toBeInTheDocument()
    })
  })
})
