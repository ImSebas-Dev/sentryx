/**
 * Sentryx — Tests de AlertDetailPage.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server, MOCK_ALERT } from '../../test/mswServer'
import { renderWithProviders, setAuthTokens } from '../../test/testUtils'
import AlertDetailPage from '../AlertDetailPage'

// ── Mocks globales ────────────────────────────────────────
const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual,
    useParams:   () => ({ id: 'alert-uuid-001' }),
    useNavigate: () => mockNavigate,
  }
})

// useAuth devuelve analista por defecto; tests específicos lo overridean
let mockRole = 'analyst'
vi.mock('../../store/AuthContext', async () => {
  const actual = await vi.importActual('../../store/AuthContext')
  return {
    ...actual,
    useAuth: () => ({
      user:       { role: mockRole, username: 'testuser' },
      loading:    false,
      isAnalyst:  mockRole === 'analyst' || mockRole === 'admin',
      isAdmin:    mockRole === 'admin',
    }),
  }
})

describe('AlertDetailPage — score y capas', () => {
  beforeEach(() => { setAuthTokens(); mockRole = 'analyst'; mockNavigate.mockClear() })

  it('muestra el score principal', async () => {
    renderWithProviders(<AlertDetailPage />)
    await waitFor(() => expect(screen.getByText('88')).toBeInTheDocument())
  })

  it('muestra los pesos de las tres capas', async () => {
    renderWithProviders(<AlertDetailPage />)
    await waitFor(() => {
      expect(screen.getByText(/35%/)).toBeInTheDocument()
      expect(screen.getByText(/40%/)).toBeInTheDocument()
      expect(screen.getByText(/25%/)).toBeInTheDocument()
    })
  })

  it('muestra el tipo de phishing BEC', async () => {
    renderWithProviders(<AlertDetailPage />)
    await waitFor(() => expect(screen.getByText('BEC')).toBeInTheDocument())
  })

  it('muestra la técnica MITRE', async () => {
    renderWithProviders(<AlertDetailPage />)
    await waitFor(() => expect(screen.getByText('T1566.002')).toBeInTheDocument())
  })

  it('muestra la táctica MITRE', async () => {
    renderWithProviders(<AlertDetailPage />)
    await waitFor(() => expect(screen.getByText('Initial Access')).toBeInTheDocument())
  })

  it('muestra el dominio del remitente', async () => {
    renderWithProviders(<AlertDetailPage />)
    await waitFor(() => expect(screen.getByText('evil.tk')).toBeInTheDocument())
  })

  it('muestra features de encabezados', async () => {
    renderWithProviders(<AlertDetailPage />)
    await waitFor(() => {
      expect(screen.getByText('SPF pass')).toBeInTheDocument()
      expect(screen.getByText('DKIM pass')).toBeInTheDocument()
      expect(screen.getByText('DMARC pass')).toBeInTheDocument()
    })
  })

  it('muestra las URLs sospechosas', async () => {
    renderWithProviders(<AlertDetailPage />)
    await waitFor(() => {
      expect(screen.getByText(/evil\.tk\/pay/)).toBeInTheDocument()
    })
  })

  it('muestra el título de la alerta', async () => {
    renderWithProviders(<AlertDetailPage />)
    await waitFor(() => {
      expect(screen.getByText('Business Email Compromise detectado')).toBeInTheDocument()
    })
  })
})

describe('AlertDetailPage — privacidad', () => {
  beforeEach(() => { setAuthTokens(); mockRole = 'analyst' })

  it('muestra bloque de privacidad Ley 1581', async () => {
    renderWithProviders(<AlertDetailPage />)
    await waitFor(() => {
      expect(screen.getByText(/privacidad/i)).toBeInTheDocument()
      expect(screen.getByText(/ley 1581/i, { exact: false })).toBeInTheDocument()
    })
  })

  it('NO muestra el email del remitente en texto plano', async () => {
    renderWithProviders(<AlertDetailPage />)
    await waitFor(() => expect(screen.getByText('evil.tk')).toBeInTheDocument())
    expect(screen.queryByText(/@evil\.tk/)).not.toBeInTheDocument()
    expect(screen.queryByText(/attacker@/i)).not.toBeInTheDocument()
  })

  it('muestra el hash truncado del remitente', async () => {
    renderWithProviders(<AlertDetailPage />)
    await waitFor(() => {
      // El hash es 64 'a' → aparece truncado como 'aaaa...a…'
      expect(screen.getByText(/aaaaaaaaaaaaaaaa…/)).toBeInTheDocument()
    })
  })
})

describe('AlertDetailPage — RBAC: acciones', () => {
  beforeEach(() => { setAuthTokens(); mockNavigate.mockClear() })

  it('analista ve el panel de Acciones', async () => {
    mockRole = 'analyst'
    renderWithProviders(<AlertDetailPage />)
    await waitFor(() => expect(screen.getByText('Acciones')).toBeInTheDocument())
  })

  it('viewer NO ve el panel de Acciones', async () => {
    mockRole = 'viewer'
    renderWithProviders(<AlertDetailPage />)
    // Esperar a que cargue (título visible)
    await waitFor(() => {
      expect(screen.getByText('Business Email Compromise detectado')).toBeInTheDocument()
    })
    expect(screen.queryByText('Acciones')).not.toBeInTheDocument()
  })

  it('botón guardar deshabilitado sin seleccionar estado', async () => {
    mockRole = 'analyst'
    renderWithProviders(<AlertDetailPage />)
    await waitFor(() => expect(screen.getByText('Acciones')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /guardar cambio/i })).toBeDisabled()
  })

  it('seleccionar estado habilita el botón guardar', async () => {
    mockRole = 'analyst'
    const user = userEvent.setup()
    renderWithProviders(<AlertDetailPage />)
    await waitFor(() => expect(screen.getByText('Acciones')).toBeInTheDocument())
    await user.selectOptions(screen.getByRole('combobox'), 'acknowledged')
    expect(screen.getByRole('button', { name: /guardar cambio/i })).not.toBeDisabled()
  })

  it('analista puede enviar un cambio de estado', async () => {
    mockRole = 'analyst'
    let patched = null
    server.use(
      http.patch('/api/v1/alerts/alert-uuid-001/', async ({ request }) => {
        patched = (await request.json()).status
        return HttpResponse.json({ ...MOCK_ALERT, status: patched })
      })
    )
    const user = userEvent.setup()
    renderWithProviders(<AlertDetailPage />)
    await waitFor(() => expect(screen.getByText('Acciones')).toBeInTheDocument())
    await user.selectOptions(screen.getByRole('combobox'), 'acknowledged')
    await user.click(screen.getByRole('button', { name: /guardar cambio/i }))
    await waitFor(() => expect(patched).toBe('acknowledged'))
  })
})

describe('AlertDetailPage — errores', () => {
  beforeEach(() => { setAuthTokens(); mockRole = 'analyst' })

  it('muestra error cuando la API falla', async () => {
    server.use(
      http.get('/api/v1/alerts/alert-uuid-001/', () =>
        HttpResponse.json({ detail: 'Not found' }, { status: 404 })
      )
    )
    renderWithProviders(<AlertDetailPage />)
    await waitFor(() => {
      expect(
        screen.queryByText(/error/i) ||
        screen.queryByText(/not found/i) ||
        screen.queryByText(/404/i)
      ).toBeTruthy()
    })
  })
})
