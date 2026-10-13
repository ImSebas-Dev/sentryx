/**
 * Sentryx — Tests de la página «Seguridad de la cuenta».
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server, MOCK_USER, MOCK_TOTP, MOCK_RECOVERY_CODES } from '../../test/mswServer'
import { renderWithProviders, setAuthTokens } from '../../test/testUtils'
import SecurityPage from '../SecurityPage'

describe('SecurityPage — activar', () => {
  beforeEach(() => {
    setAuthTokens()
    let enabled = false
    server.use(
      http.get('/api/v1/auth/me/', () => HttpResponse.json({
        ...MOCK_USER, mfa_enabled: enabled, mfa_recovery_codes_remaining: enabled ? 8 : 0,
        mfa_enabled_at: enabled ? '2026-10-10T12:00:00Z' : null,
      })),
      http.post('/api/v1/auth/mfa/enable/', async ({ request }) => {
        const body = await request.json()
        if (body.code !== MOCK_TOTP) {
          return HttpResponse.json({ error: 'El código no es válido.' }, { status: 400 })
        }
        enabled = true
        return HttpResponse.json({ recovery_codes: MOCK_RECOVERY_CODES })
      }),
    )
  })

  it('muestra el estado desactivado', async () => {
    renderWithProviders(<SecurityPage />)
    expect(await screen.findByText('Desactivada')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Seguridad de la cuenta' })).toBeInTheDocument()
  })

  it('activa con QR, muestra los 8 códigos una vez y pide confirmar que se guardaron', async () => {
    const user = userEvent.setup()
    renderWithProviders(<SecurityPage />)

    await user.click(await screen.findByRole('button', { name: /activar la verificación/i }))
    expect(await screen.findByAltText(/código QR/i)).toHaveAttribute('src', expect.stringMatching(/^data:image\/png/))
    expect(screen.getByText('JBSW Y3DP EHPK 3PXP')).toBeInTheDocument()

    await user.type(screen.getByLabelText('Código de la app'), MOCK_TOTP)
    await user.click(screen.getByRole('button', { name: /^activar$/i }))

    const list = await screen.findByRole('list', { name: /códigos de recuperación/i })
    expect(list.querySelectorAll('li')).toHaveLength(8)
    expect(screen.getByRole('button', { name: /descargar \.txt/i })).toBeInTheDocument()

    const finish = screen.getByRole('button', { name: /terminar/i })
    expect(finish).toBeDisabled()
    await user.click(screen.getByLabelText(/guardé mis códigos/i))
    await user.click(finish)

    expect(await screen.findByText(/quedó activada/i)).toBeInTheDocument()
    expect(screen.getByText('Activada')).toBeInTheDocument()
    expect(screen.queryByRole('list', { name: /códigos de recuperación/i })).not.toBeInTheDocument()
  })

  it('código incorrecto al activar muestra error', async () => {
    const user = userEvent.setup()
    renderWithProviders(<SecurityPage />)
    await user.click(await screen.findByRole('button', { name: /activar la verificación/i }))
    await user.type(await screen.findByLabelText('Código de la app'), '000000')
    await user.click(screen.getByRole('button', { name: /^activar$/i }))
    expect(await screen.findByText('El código no es válido.')).toBeInTheDocument()
  })
})

describe('SecurityPage — desactivar', () => {
  beforeEach(() => {
    setAuthTokens()
    server.use(
      http.get('/api/v1/auth/me/', () => HttpResponse.json({
        ...MOCK_USER, mfa_enabled: true, mfa_recovery_codes_remaining: 2,
        mfa_enabled_at: '2026-10-10T12:00:00Z',
      })),
    )
  })

  it('avisa cuando quedan pocos códigos de recuperación', async () => {
    renderWithProviders(<SecurityPage />)
    expect(await screen.findByText(/te quedan pocos códigos/i)).toBeInTheDocument()
    expect(screen.getByText('2 de 8')).toBeInTheDocument()
  })

  it('exige contraseña y código', async () => {
    const user = userEvent.setup()
    renderWithProviders(<SecurityPage />)
    await user.click(await screen.findByRole('button', { name: /desactivar la verificación/i }))

    const submit = screen.getByRole('button', { name: /^desactivar$/i })
    expect(submit).toBeDisabled()
    await user.type(screen.getByLabelText('Contraseña actual'), 'mala')
    await user.type(screen.getByLabelText(/código de la app o de recuperación/i), '123456')
    await user.click(submit)
    expect(await screen.findByText(/contraseña o el código no son correctos/i)).toBeInTheDocument()
  })
})

describe('SecurityPage — política para administradores', () => {
  it('explica que el 2FA es obligatorio', async () => {
    setAuthTokens()
    server.use(
      http.get('/api/v1/auth/me/', () => HttpResponse.json({
        ...MOCK_USER, role: 'admin', mfa_enabled: false, mfa_setup_required: true,
      })),
    )
    renderWithProviders(<SecurityPage />)
    expect(await screen.findByText(/debes activar la verificación en dos pasos/i)).toBeInTheDocument()
  })
})
