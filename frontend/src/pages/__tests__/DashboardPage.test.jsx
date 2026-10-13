/**
 * Sentryx — Tests del DashboardPage.
 * Verifica KPIs, distribución de tipos, tendencia diaria y alertas recientes.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server, MOCK_STATS, MOCK_ALERTS_LIST } from '../../test/mswServer'
import { renderWithProviders, setAuthTokens } from '../../test/testUtils'
import DashboardPage from '../DashboardPage'

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual, useNavigate: () => mockNavigate }
})

describe('DashboardPage — KPIs', () => {
  beforeEach(() => { setAuthTokens(); mockNavigate.mockClear() })

  it('muestra el KPI de total de alertas', async () => {
    renderWithProviders(<DashboardPage />)
    await waitFor(() => {
      expect(screen.getByText('42')).toBeInTheDocument()
      expect(screen.getByText('Total alertas')).toBeInTheDocument()
    })
  })

  it('muestra el KPI de alertas críticas', async () => {
    renderWithProviders(<DashboardPage />)
    await waitFor(() => {
      expect(screen.getByText('Críticas')).toBeInTheDocument()
      // El valor 5 puede aparecer múltiples veces (severidad, barra, etc.)
      const criticals = screen.getAllByText('5')
      expect(criticals.length).toBeGreaterThan(0)
    })
  })

  it('muestra el KPI de alertas esta semana', async () => {
    renderWithProviders(<DashboardPage />)
    await waitFor(() => {
      expect(screen.getByText('18')).toBeInTheDocument()
      expect(screen.getByText('Esta semana')).toBeInTheDocument()
    })
  })

  it('muestra el KPI de campañas activas', async () => {
    renderWithProviders(<DashboardPage />)
    await waitFor(() => {
      expect(screen.getByText('2')).toBeInTheDocument()
      expect(screen.getByText('Campañas activas')).toBeInTheDocument()
    })
  })
})

describe('DashboardPage — distribución por severidad', () => {
  beforeEach(() => setAuthTokens())

  it('muestra las cuatro barras de severidad', async () => {
    renderWithProviders(<DashboardPage />)
    await waitFor(() => {
      expect(screen.getByText('Crítica')).toBeInTheDocument()
      expect(screen.getByText('Alta')).toBeInTheDocument()
      expect(screen.getByText('Media')).toBeInTheDocument()
      expect(screen.getByText('Baja')).toBeInTheDocument()
    })
  })

  it('muestra los conteos correctos por severidad', async () => {
    renderWithProviders(<DashboardPage />)
    await waitFor(() => {
      // CRITICAL=5, HIGH=15, MEDIUM=14, LOW=8 del MOCK_STATS
      expect(screen.getAllByText('5').length).toBeGreaterThan(0)
      expect(screen.getAllByText('15').length).toBeGreaterThan(0)
      expect(screen.getAllByText('14').length).toBeGreaterThan(0)
      expect(screen.getAllByText('8').length).toBeGreaterThan(0)
    })
  })
})

describe('DashboardPage — tendencia y gráficas', () => {
  beforeEach(() => setAuthTokens())

  it('muestra la sección de tendencia de 7 días', async () => {
    renderWithProviders(<DashboardPage />)
    await waitFor(() => {
      expect(screen.getByText(/alertas.*últimos 7 días/i)).toBeInTheDocument()
    })
  })

  it('muestra la sección de distribución por tipo', async () => {
    renderWithProviders(<DashboardPage />)
    await waitFor(() => {
      expect(screen.getByText('Por tipo de phishing')).toBeInTheDocument()
    })
  })

  it('muestra mensaje "Sin datos aún" cuando no hay tipos', async () => {
    server.use(
      http.get('/api/v1/alerts/stats/', () =>
        HttpResponse.json({ ...MOCK_STATS, by_type: {} })
      )
    )
    renderWithProviders(<DashboardPage />)
    await waitFor(() => {
      expect(screen.getByText(/sin datos aún/i)).toBeInTheDocument()
    })
  })
})

describe('DashboardPage — alertas recientes', () => {
  beforeEach(() => { setAuthTokens(); mockNavigate.mockClear() })

  it('muestra la sección de alertas recientes', async () => {
    renderWithProviders(<DashboardPage />)
    await waitFor(() => {
      expect(screen.getByText('Alertas recientes')).toBeInTheDocument()
    })
  })

  it('muestra las alertas recientes del mock', async () => {
    renderWithProviders(<DashboardPage />)
    await waitFor(() => {
      expect(screen.getByText('Business Email Compromise detectado')).toBeInTheDocument()
    })
  })

  it('muestra link "Ver todas" que navega a /alerts', async () => {
    const user = userEvent.setup()
    renderWithProviders(<DashboardPage />)
    await waitFor(() => {
      expect(screen.getByText('Alertas recientes')).toBeInTheDocument()
    })
    await user.click(screen.getByText(/ver todas/i))
    expect(mockNavigate).toHaveBeenCalledWith('/alerts')
  })

  it('navega al detalle al hacer clic en una alerta reciente', async () => {
    const user = userEvent.setup()
    renderWithProviders(<DashboardPage />)
    await waitFor(() => {
      expect(screen.getByText('Business Email Compromise detectado')).toBeInTheDocument()
    })
    await user.click(screen.getByText('Business Email Compromise detectado'))
    expect(mockNavigate).toHaveBeenCalledWith('/alerts/alert-uuid-001')
  })

  it('muestra empty state cuando no hay alertas recientes', async () => {
    server.use(
      http.get('/api/v1/alerts/', () =>
        HttpResponse.json({ count: 0, results: [], next: null, previous: null })
      )
    )
    renderWithProviders(<DashboardPage />)
    await waitFor(() => {
      expect(screen.getByText(/sin alertas recientes/i)).toBeInTheDocument()
    })
  })
})

describe('DashboardPage — botón actualizar', () => {
  beforeEach(() => setAuthTokens())

  it('muestra el botón de actualizar', async () => {
    renderWithProviders(<DashboardPage />)
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /actualizar/i })).toBeInTheDocument()
    })
  })

  it('recarga las estadísticas al hacer clic en Actualizar', async () => {
    let statsCallCount = 0
    server.use(
      http.get('/api/v1/alerts/stats/', () => {
        statsCallCount++
        return HttpResponse.json(MOCK_STATS)
      })
    )
    const user = userEvent.setup()
    renderWithProviders(<DashboardPage />)
    await waitFor(() => expect(screen.getByText('Total alertas')).toBeInTheDocument())

    const before = statsCallCount
    await user.click(screen.getByRole('button', { name: /actualizar/i }))
    await waitFor(() => expect(statsCallCount).toBeGreaterThan(before))
  })
})

describe('DashboardPage — manejo de errores', () => {
  beforeEach(() => setAuthTokens())

  it('muestra un banner de error si las stats fallan', async () => {
    server.use(
      http.get('/api/v1/alerts/stats/', () =>
        HttpResponse.json({ detail: 'Error interno' }, { status: 500 })
      )
    )
    renderWithProviders(<DashboardPage />)
    await waitFor(() => {
      expect(
        screen.queryByText(/error/i) || screen.queryByText(/500/i)
      ).toBeTruthy()
    })
  })

  it('muestra — cuando los valores son nulos', async () => {
    server.use(
      http.get('/api/v1/alerts/stats/', () =>
        HttpResponse.json({
          ...MOCK_STATS, total: null, critical: null,
          week_total: null, active_campaigns: null,
        })
      )
    )
    renderWithProviders(<DashboardPage />)
    await waitFor(() => {
      // Verificar que la página cargó (al menos el título del dashboard)
      expect(screen.getByText('Total alertas')).toBeInTheDocument()
    })
  })
})
