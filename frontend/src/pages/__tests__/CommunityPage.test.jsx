import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { renderWithProviders, setAuthTokens, clearAuthTokens } from '../../test/testUtils'
import { server } from '../../test/mswServer'
import CommunityPage from '../CommunityPage'
import CommunityNotice from '../../components/CommunityNotice'

const SETTINGS = {
  organization: 'Test Corp', enabled: false, sector: '', region: '', node_status: 'disabled',
  last_sync_at: null, last_error: '', deletion_pending: false, configured: true,
  consent_text: 'Qué nunca se comparte: el cuerpo de los correos.',
  sector_options: [{ value: 'H', label: 'H · Transporte' }],
  region_options: ['Cundinamarca', 'Bogotá D.C.'],
}

describe('CommunityPage', () => {
  beforeEach(() => setAuthTokens())
  afterEach(() => clearAuthTokens())

  it('no deja activar sin aceptar el consentimiento', async () => {
    server.use(http.get('*/community/settings/', () => HttpResponse.json(SETTINGS)))
    const user = userEvent.setup()
    renderWithProviders(<CommunityPage />)
    expect(await screen.findByText(/nunca se comparte/)).toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText(/Sector/), 'H')
    await user.selectOptions(screen.getByLabelText('Departamento'), 'Cundinamarca')
    expect(screen.getByRole('button', { name: /Activar/ })).toBeDisabled()
  })

  it('activa con consentimiento, sector y departamento', async () => {
    let body = null
    server.use(
      http.get('*/community/settings/', () => HttpResponse.json(SETTINGS)),
      http.post('*/community/enable/', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ ...SETTINGS, enabled: true, node_status: 'active', ...body })
      }),
    )
    const user = userEvent.setup()
    renderWithProviders(<CommunityPage />)
    await user.selectOptions(await screen.findByLabelText(/Sector/), 'H')
    await user.selectOptions(screen.getByLabelText('Departamento'), 'Cundinamarca')
    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: /Activar/ }))
    await waitFor(() => expect(body).toEqual({
      accept_consent: true, sector: 'H', region: 'Cundinamarca' }))
    expect(await screen.findByText('Conectado')).toBeInTheDocument()
  })

  it('avisa si el servidor no está conectado a un hub', async () => {
    server.use(http.get('*/community/settings/', () => HttpResponse.json({ ...SETTINGS, configured: false })))
    renderWithProviders(<CommunityPage />)
    expect(await screen.findByText(/aún no está conectado/)).toBeInTheDocument()
  })
})

describe('CommunityNotice', () => {
  it('muestra el aviso en lenguaje sencillo', () => {
    renderWithProviders(<CommunityNotice signal={{
      message: 'Este dominio fue reportado por 3 empresas de tu sector en los últimos días.',
      regions: ['Meta'] }} />)
    expect(screen.getByText(/reportado por 3 empresas/)).toBeInTheDocument()
  })
})
