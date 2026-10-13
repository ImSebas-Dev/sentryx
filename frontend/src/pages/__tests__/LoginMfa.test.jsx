/**
 * Sentryx — Tests del segundo paso del login (verificación en dos pasos).
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server, MOCK_MFA_EMAIL, MOCK_TOTP, MOCK_RECOVERY_CODE, MOCK_USER } from '../../test/mswServer'
import { renderWithProviders, clearAuthTokens } from '../../test/testUtils'
import LoginPage from '../LoginPage'

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual, useNavigate: () => mockNavigate }
})

async function passFirstStep(user) {
  renderWithProviders(<LoginPage />)
  await user.type(screen.getByLabelText('Correo electrónico'), MOCK_MFA_EMAIL)
  await user.type(screen.getByLabelText('Contraseña'), 'correcta')
  await user.click(screen.getByRole('button', { name: /entrar/i }))
  return screen.findByLabelText('Código de verificación')
}

describe('LoginPage — verificación en dos pasos', () => {
  beforeEach(() => {
    clearAuthTokens()
    mockNavigate.mockClear()
  })

  it('pide el código y no guarda tokens tras la contraseña', async () => {
    const user = userEvent.setup()
    const input = await passFirstStep(user)

    expect(input).toHaveAttribute('autocomplete', 'one-time-code')
    expect(input).toHaveAttribute('inputmode', 'numeric')
    expect(input).toHaveAttribute('type', 'text')
    expect(input).toHaveAttribute('maxlength', '6')
    expect(input).toHaveAccessibleDescription(/6 dígitos/i)
    expect(localStorage.getItem('access_token')).toBeNull()
    expect(mockNavigate).not.toHaveBeenCalled()
  })

  it('el foco pasa al título del segundo paso', async () => {
    const user = userEvent.setup()
    await passFirstStep(user)
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /verificación en dos pasos/i })).toHaveFocus())
  })

  it('código correcto inicia sesión y redirige', async () => {
    const user = userEvent.setup()
    const input = await passFirstStep(user)
    await user.type(input, MOCK_TOTP)
    await user.click(screen.getByRole('button', { name: /^verificar$/i }))

    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/'))
    expect(localStorage.getItem('access_token')).toBeTruthy()
  })

  it('solo acepta dígitos al escribir o pegar', async () => {
    const user = userEvent.setup()
    const input = await passFirstStep(user)
    await user.type(input, '12 3a45678')
    expect(input).toHaveValue('123456')
  })

  it('código incorrecto muestra los intentos restantes', async () => {
    const user = userEvent.setup()
    const input = await passFirstStep(user)
    await user.type(input, '000000')
    await user.click(screen.getByRole('button', { name: /^verificar$/i }))

    expect(await screen.findByText(/Te quedan 4 intentos/i)).toBeInTheDocument()
    expect(localStorage.getItem('access_token')).toBeNull()
  })

  it('permite usar un código de recuperación', async () => {
    const user = userEvent.setup()
    await passFirstStep(user)
    await user.click(screen.getByRole('button', { name: /usar código de recuperación/i }))

    const input = screen.getByLabelText('Código de recuperación')
    expect(input).toHaveAttribute('autocomplete', 'off')
    await user.type(input, MOCK_RECOVERY_CODE)
    await user.click(screen.getByRole('button', { name: /^verificar$/i }))

    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/'))
  })

  it('verificación expirada vuelve al primer paso con aviso', async () => {
    server.use(
      http.post('/api/v1/auth/token/', () =>
        HttpResponse.json({ mfa_required: true, mfa_token: 'mfa-token-expired', expires_in: 300 })),
    )
    const user = userEvent.setup()
    const input = await passFirstStep(user)
    await user.type(input, MOCK_TOTP)
    await user.click(screen.getByRole('button', { name: /^verificar$/i }))

    expect(await screen.findByText(/La verificación expiró/i)).toBeInTheDocument()
    expect(screen.getByLabelText('Contraseña')).toHaveValue('')
  })

  it('admin obligado a configurar 2FA va a Seguridad de la cuenta', async () => {
    server.use(
      http.get('/api/v1/auth/me/', () =>
        HttpResponse.json({ ...MOCK_USER, role: 'admin', mfa_setup_required: true })),
    )
    const user = userEvent.setup()
    renderWithProviders(<LoginPage />)
    await user.type(screen.getByLabelText('Correo electrónico'), MOCK_USER.email)
    await user.type(screen.getByLabelText('Contraseña'), 'correcta')
    await user.click(screen.getByRole('button', { name: /entrar/i }))

    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/security'))
  })
})
