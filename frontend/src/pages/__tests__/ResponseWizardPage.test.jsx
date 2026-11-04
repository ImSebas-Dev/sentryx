import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { renderWithProviders, setAuthTokens, clearAuthTokens } from '../../test/testUtils'
import { server } from '../../test/mswServer'
import ResponseWizardPage from '../ResponseWizardPage'
import EmergencyContactsPage from '../EmergencyContactsPage'

const PLAYBOOK = {
  key: 'payment', title: 'Hice un pago o transferencia', description: 'Cada minuto cuenta',
  severity: 'CRITICAL',
  steps: [
    { id: 'llamar-banco', title: 'Llama al banco', detail: 'Pide congelar', critical: true },
    { id: 'guardar', title: 'Guarda los comprobantes', detail: 'No los borres', critical: false },
  ],
}
const SESSION = {
  id: 'abcd1234-0000', playbook: PLAYBOOK, alert_id: null, incident_id: 'inc',
  answers: {}, steps_state: {}, started_at: new Date().toISOString(),
  completed_at: null, status: 'in_progress',
}
const CONTACTS = [
  { id: 'c1', name: 'Línea de fraude', phone: '+57 601 000 0000', url: '', kind: 'bank', is_placeholder: false },
  { id: 'c2', name: 'Tu banco (complétala)', phone: '', url: '', kind: 'bank', is_placeholder: true },
]

function baseHandlers() {
  server.use(
    http.get('*/response/playbooks/', () => HttpResponse.json([PLAYBOOK])),
    http.get('*/response/contacts/', () => HttpResponse.json(CONTACTS)),
    http.get('*/response/config/', () => HttpResponse.json({
      cai_virtual_url: '', contact_warning: 'Verifica estos números con tu banco.' })),
  )
}

describe('ResponseWizardPage', () => {
  beforeEach(() => { setAuthTokens(); baseHandlers() })
  afterEach(() => clearAuthTokens())

  async function startWizard(user, onStart) {
    server.use(http.post('*/response/start/', async ({ request }) => {
      onStart?.(await request.json())
      return HttpResponse.json(SESSION, { status: 201 })
    }))
    await user.click(await screen.findByRole('button', { name: /Hice un pago/ }))
  }

  it('pregunta qué pasó y vincula la alerta del parámetro', async () => {
    let body = null
    const user = userEvent.setup()
    renderWithProviders(<ResponseWizardPage />, { initialPath: '/respond?alert=alert-9' })
    await startWizard(user, b => { body = b })
    await screen.findByText('Llama al banco')
    expect(body.playbook_key).toBe('payment')
    expect(body.alert_id).toBe('alert-9')
    expect(body.answers.cuando).toBeTruthy()
  })

  it('muestra temporizador de 15 minutos y botón de llamar', async () => {
    const user = userEvent.setup()
    renderWithProviders(<ResponseWizardPage />)
    await startWizard(user)
    expect(await screen.findByRole('timer')).toHaveTextContent(/1[45]:\d\d/)
    expect(screen.getByRole('link', { name: /Llamar/ })).toHaveAttribute('href', 'tel:+57 601 000 0000')
    expect(screen.getByText(/Verifica estos números/)).toBeInTheDocument()
    expect(screen.getByText(/Falta completarlo/)).toBeInTheDocument()
  })

  it('marca un paso con el checkbox y avanza hasta el PDF', async () => {
    let stepBody = null
    server.use(
      http.post('*/response/abcd1234-0000/steps/llamar-banco/', async ({ request }) => {
        stepBody = await request.json()
        return HttpResponse.json({ ...SESSION, steps_state: { 'llamar-banco': { done: true, note: '' } } })
      }),
      http.post('*/response/abcd1234-0000/complete/', () =>
        HttpResponse.json({ ...SESSION, status: 'completed' })),
    )
    const user = userEvent.setup()
    renderWithProviders(<ResponseWizardPage />)
    await startWizard(user)
    await user.click(await screen.findByRole('checkbox'))
    await waitFor(() => expect(stepBody).toEqual({ done: true, note: '' }))
    await user.click(screen.getByRole('button', { name: /Siguiente/ }))
    await screen.findByText('Guarda los comprobantes')
    await user.click(screen.getByRole('button', { name: /Terminar/ }))
    expect(await screen.findByRole('button', { name: /Descargar paquete/ })).toBeInTheDocument()
  })
})

describe('EmergencyContactsPage', () => {
  beforeEach(() => { setAuthTokens(); baseHandlers() })
  afterEach(() => clearAuthTokens())

  it('muestra la advertencia y marca lo que falta completar', async () => {
    renderWithProviders(<EmergencyContactsPage />)
    expect(await screen.findByText('Por completar')).toBeInTheDocument()
    expect(await screen.findByText(/Verifica estos números/)).toBeInTheDocument()
  })

  it('crea un contacto', async () => {
    let body = null
    server.use(http.post('*/response/contacts/', async ({ request }) => {
      body = await request.json()
      return HttpResponse.json({ id: 'c3', ...body }, { status: 201 })
    }))
    const user = userEvent.setup()
    renderWithProviders(<EmergencyContactsPage />)
    await user.click(await screen.findByRole('button', { name: /Nuevo contacto/ }))
    await user.type(screen.getByLabelText('Nombre'), 'Mi banco')
    await user.click(screen.getByRole('button', { name: /Guardar/ }))
    await waitFor(() => expect(body?.name).toBe('Mi banco'))
  })
})
