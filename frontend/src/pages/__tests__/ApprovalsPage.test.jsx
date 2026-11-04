import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { Routes, Route } from 'react-router-dom'
import { renderWithProviders, setAuthTokens, clearAuthTokens } from '../../test/testUtils'
import { server, MOCK_ADMIN } from '../../test/mswServer'
import ApprovalsPage from '../ApprovalsPage'
import FourEyesPolicyPage from '../FourEyesPolicyPage'
import FourEyesPanel from '../../components/FourEyesPanel'

const REQUEST = {
  id: 'req-1', alert_id: 'alert-1', alert_severity: 'HIGH', sender_domain: 'evil.tk',
  reasons: [{ trigger: 'payment', detail: 'pide pagar a una cuenta que no coincide con Proveedor X' }],
  requester_name: 'ana', requester_note: 'Es urgente', status: 'pending', effective_status: 'pending',
  decided_by_name: null, decided_at: null, decision_note: '',
  expires_at: new Date(Date.now() + 3600000).toISOString(), created_at: new Date().toISOString(),
  can_decide: true, requires_totp: true, guided_response: null,
}

const POLICY = {
  organization: 'Test Corp', enabled: true, min_severity: 'HIGH', require_for_payment: true,
  require_for_credentials: true, require_for_attachments: true, expiry_minutes: 240,
  require_mfa_for_approval: true, approvers: [], eligible_count: 1,
  candidates: [{ id: 'u1', username: 'admin01', email: 'a@t.co', role: 'admin', mfa_enabled: true }],
}

const renderApprovals = () => renderWithProviders(
  <Routes><Route path="/" element={<ApprovalsPage />} /></Routes>)

describe('ApprovalsPage', () => {
  beforeEach(() => {
    setAuthTokens()
    server.use(http.get('*/auth/me/', () => HttpResponse.json({ ...MOCK_ADMIN, mfa_enabled: true })))
  })
  afterEach(() => clearAuthTokens())

  it('muestra motivos, dominio y quién pidió', async () => {
    server.use(http.get('*/four-eyes/requests/', () => HttpResponse.json([REQUEST])))
    renderApprovals()
    expect(await screen.findByText(/no coincide con Proveedor X/)).toBeInTheDocument()
    expect(screen.getByText('evil.tk')).toBeInTheDocument()
    expect(screen.getByText('ana')).toBeInTheDocument()
    expect(screen.getByText(/Quedan/)).toBeInTheDocument()
  })

  it('aprueba con el código TOTP en el modal', async () => {
    let sent = null
    server.use(
      http.get('*/four-eyes/requests/', () => HttpResponse.json([REQUEST])),
      http.post('*/four-eyes/requests/req-1/approve/', async ({ request }) => {
        sent = await request.json()
        return HttpResponse.json({ ...REQUEST, status: 'approved' })
      }),
    )
    const user = userEvent.setup()
    renderApprovals()
    await user.click(await screen.findByRole('button', { name: /Aprobar/ }))
    await user.type(screen.getByLabelText('Código de verificación'), '123456')
    await user.click(screen.getAllByRole('button', { name: 'Aprobar' }).at(-1))
    await waitFor(() => expect(sent).toEqual({ totp_code: '123456', note: '' }))
  })

  it('muestra el error del backend si el código es inválido', async () => {
    server.use(
      http.get('*/four-eyes/requests/', () => HttpResponse.json([REQUEST])),
      http.post('*/four-eyes/requests/req-1/approve/', () => HttpResponse.json(
        { error: 'El código no es válido o ya se usó.', code: 'invalid_totp' }, { status: 400 })),
    )
    const user = userEvent.setup()
    renderApprovals()
    await user.click(await screen.findByRole('button', { name: /Aprobar/ }))
    await user.type(screen.getByLabelText('Código de verificación'), '000000')
    await user.click(screen.getAllByRole('button', { name: 'Aprobar' }).at(-1))
    expect(await screen.findByText(/no es válido/)).toBeInTheDocument()
  })

  it('el rechazo exige escribir el motivo', async () => {
    server.use(http.get('*/four-eyes/requests/', () => HttpResponse.json([REQUEST])))
    const user = userEvent.setup()
    renderApprovals()
    await user.click(await screen.findByRole('button', { name: /Rechazar/ }))
    expect(screen.getByLabelText('Motivo del rechazo')).toBeRequired()
  })
})

describe('FourEyesPanel', () => {
  beforeEach(() => setAuthTokens())
  afterEach(() => clearAuthTokens())

  it('pide la aprobación con nota', async () => {
    let sent = null
    server.use(
      http.get('*/four-eyes/requests/', () => HttpResponse.json([])),
      http.post('*/four-eyes/requests/', async ({ request }) => {
        sent = await request.json()
        return HttpResponse.json(REQUEST, { status: 201 })
      }),
    )
    const user = userEvent.setup()
    renderWithProviders(<FourEyesPanel alertId="alert-1" reasons={REQUEST.reasons} />)
    await user.type(await screen.findByLabelText(/Nota para quien aprueba/), 'Revisa porfa')
    await user.click(screen.getByRole('button', { name: /Pedir aprobación/ }))
    await waitFor(() => expect(sent).toEqual({ alert_id: 'alert-1', note: 'Revisa porfa' }))
  })

  it('al rechazar ofrece la respuesta guiada y no permite pedir de nuevo', async () => {
    server.use(http.get('*/four-eyes/requests/', () => HttpResponse.json([{
      ...REQUEST, status: 'rejected', effective_status: 'rejected',
      decided_by_name: 'jefa', decided_at: new Date().toISOString(), decision_note: 'Es fraude',
    }])))
    renderWithProviders(<FourEyesPanel alertId="alert-1" reasons={REQUEST.reasons} />)
    expect(await screen.findByText(/Es fraude/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Ya hiciste clic/ }))
      .toHaveAttribute('href', '/respond?alert=alert-1')
    expect(screen.queryByRole('button', { name: /Pedir aprobación/ })).not.toBeInTheDocument()
  })

  it('no pinta nada sin motivos', () => {
    const { container } = renderWithProviders(<FourEyesPanel alertId="a" reasons={[]} />)
    expect(container.querySelector('section')).toBeNull()
  })
})

describe('FourEyesPolicyPage', () => {
  beforeEach(() => {
    setAuthTokens()
    server.use(http.get('*/auth/me/', () => HttpResponse.json(MOCK_ADMIN)))
  })
  afterEach(() => clearAuthTokens())

  it('advierte si hay menos de dos aprobadores', async () => {
    server.use(http.get('*/four-eyes/policy/', () => HttpResponse.json(POLICY)))
    renderWithProviders(<FourEyesPolicyPage />)
    expect(await screen.findByText(/al menos dos personas/)).toBeInTheDocument()
  })

  it('guarda los cambios', async () => {
    let sent = null
    server.use(
      http.get('*/four-eyes/policy/', () => HttpResponse.json(POLICY)),
      http.put('*/four-eyes/policy/', async ({ request }) => {
        sent = await request.json()
        return HttpResponse.json(POLICY)
      }),
    )
    const user = userEvent.setup()
    renderWithProviders(<FourEyesPolicyPage />)
    await user.click(await screen.findByLabelText(/Correos que piden credenciales/))
    await user.click(screen.getByRole('button', { name: /Guardar política/ }))
    await waitFor(() => expect(sent?.require_for_credentials).toBe(false))
    expect(await screen.findByText('Política guardada.')).toBeInTheDocument()
  })
})
