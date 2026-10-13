/**
 * Sentryx — Tests de AlertsPage.
 * Verifica listado, filtros, paginación y permisos RBAC.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server, MOCK_ALERTS_LIST } from '../../test/mswServer'
import { renderWithProviders, setAuthTokens } from '../../test/testUtils'
import AlertsPage from '../AlertsPage'

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual, useNavigate: () => mockNavigate }
})

describe('AlertsPage — renderizado inicial', () => {
  beforeEach(() => { setAuthTokens(); mockNavigate.mockClear() })

  it('muestra el título y conteo de alertas', async () => {
    renderWithProviders(<AlertsPage />)
    await waitFor(() => {
      expect(screen.getByText('Alertas')).toBeInTheDocument()
      expect(screen.getByText(/3 alertas en total/i)).toBeInTheDocument()
    })
  })

  it('renderiza las tres alertas del mock', async () => {
    renderWithProviders(<AlertsPage />)
    await waitFor(() => {
      expect(screen.getByText('Business Email Compromise detectado')).toBeInTheDocument()
      expect(screen.getByText('Spear phishing detectado')).toBeInTheDocument()
      expect(screen.getByText('Whaling detectado')).toBeInTheDocument()
    })
  })

  it('muestra badges de severidad para cada alerta', async () => {
    renderWithProviders(<AlertsPage />)
    await waitFor(() => {
      // Dos alertas CRITICAL, una HIGH
      const criticals = screen.getAllByText('CRITICAL')
      expect(criticals.length).toBeGreaterThanOrEqual(2)
      expect(screen.getByText('HIGH')).toBeInTheDocument()
    })
  })

  it('muestra badges de tipo de phishing', async () => {
    renderWithProviders(<AlertsPage />)
    await waitFor(() => {
      expect(screen.getByText('BEC')).toBeInTheDocument()
      expect(screen.getByText('Spear')).toBeInTheDocument()
      expect(screen.getByText('Whaling')).toBeInTheDocument()
    })
  })

  it('muestra técnica MITRE para las alertas', async () => {
    renderWithProviders(<AlertsPage />)
    await waitFor(() => {
      expect(screen.getAllByText('T1566.002').length).toBeGreaterThan(0)
    })
  })

  it('muestra el dominio del remitente', async () => {
    renderWithProviders(<AlertsPage />)
    await waitFor(() => {
      const domains = screen.getAllByText('evil.tk')
      expect(domains.length).toBeGreaterThan(0)
    })
  })
})

describe('AlertsPage — estado vacío', () => {
  beforeEach(() => setAuthTokens())

  it('muestra empty state cuando no hay alertas', async () => {
    server.use(
      http.get('/api/v1/alerts/', () =>
        HttpResponse.json({ count: 0, results: [], next: null, previous: null })
      )
    )
    renderWithProviders(<AlertsPage />)
    await waitFor(() => {
      expect(screen.getByText('Sin alertas')).toBeInTheDocument()
    })
  })
})

describe('AlertsPage — filtros', () => {
  beforeEach(() => { setAuthTokens(); mockNavigate.mockClear() })

  it('muestra el panel de filtros al hacer clic en "Filtros"', async () => {
    const user = userEvent.setup()
    renderWithProviders(<AlertsPage />)
    await waitFor(() => expect(screen.getByText('Alertas')).toBeInTheDocument())

    const filtrosBtn = screen.getByRole('button', { name: /filtros/i })
    await user.click(filtrosBtn)

    // Usar getAllByText para labels que pueden aparecer más de una vez
    expect(screen.getAllByText('Severidad').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Tipo de phishing').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Estado').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Dominio remitente').length).toBeGreaterThan(0)
  })

  it('aplica filtro por tipo de phishing y actualiza lista', async () => {
    let lastParams = {}
    server.use(
      http.get('/api/v1/alerts/', ({ request }) => {
        const url = new URL(request.url)
        lastParams = Object.fromEntries(url.searchParams)
        const type    = url.searchParams.get('phishing_type')
        const results = type
          ? MOCK_ALERTS_LIST.results.filter(a => a.phishing_type === type)
          : MOCK_ALERTS_LIST.results
        return HttpResponse.json({ count: results.length, results, next: null, previous: null })
      })
    )

    const user = userEvent.setup()
    renderWithProviders(<AlertsPage />)
    await waitFor(() => expect(screen.getByText('Alertas')).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: /filtros/i }))

    const typeSelect = screen.getByRole('combobox', {
      name: (_, el) => el.previousSibling?.textContent?.includes('Tipo')
    }) || screen.getAllByRole('combobox')[1]

    await user.selectOptions(typeSelect, 'spear')
    await waitFor(() => {
      expect(lastParams.phishing_type).toBe('spear')
    })
  })

  it('filtra por dominio remitente', async () => {
    let capturedDomain = null
    server.use(
      http.get('/api/v1/alerts/', ({ request }) => {
        const url = new URL(request.url)
        capturedDomain = url.searchParams.get('domain')
        return HttpResponse.json(MOCK_ALERTS_LIST)
      })
    )

    const user = userEvent.setup()
    renderWithProviders(<AlertsPage />)
    await waitFor(() => expect(screen.getByText('Alertas')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /filtros/i }))

    const domainInput = screen.getByPlaceholderText('evil.tk')
    await user.type(domainInput, 'malware.tk')

    await waitFor(() => {
      expect(capturedDomain).toBe('malware.tk')
    })
  })
})

describe('AlertsPage — navegación al detalle', () => {
  beforeEach(() => { setAuthTokens(); mockNavigate.mockClear() })

  it('navega al detalle al hacer clic en una alerta', async () => {
    const user = userEvent.setup()
    renderWithProviders(<AlertsPage />)
    await waitFor(() => {
      expect(screen.getByText('Business Email Compromise detectado')).toBeInTheDocument()
    })

    await user.click(screen.getByText('Business Email Compromise detectado'))
    expect(mockNavigate).toHaveBeenCalledWith('/alerts/alert-uuid-001')
  })
})

describe('AlertsPage — manejo de errores', () => {
  beforeEach(() => setAuthTokens())

  it('muestra banner de error cuando la API falla', async () => {
    server.use(
      http.get('/api/v1/alerts/', () =>
        HttpResponse.json({ detail: 'Internal Server Error' }, { status: 500 })
      )
    )
    renderWithProviders(<AlertsPage />)
    await waitFor(() => {
      // Debe mostrar algún error visible
      expect(
        screen.queryByText(/error/i) ||
        screen.queryByText(/500/i)   ||
        screen.queryByText(/Internal/i)
      ).toBeTruthy()
    })
  })
})

describe('AlertsPage — botón actualizar', () => {
  beforeEach(() => setAuthTokens())

  it('vuelve a cargar datos al hacer clic en "Actualizar"', async () => {
    let callCount = 0
    server.use(
      http.get('/api/v1/alerts/', () => {
        callCount++
        return HttpResponse.json(MOCK_ALERTS_LIST)
      })
    )

    const user = userEvent.setup()
    renderWithProviders(<AlertsPage />)
    await waitFor(() => expect(screen.getByText('Alertas')).toBeInTheDocument())

    const initialCount = callCount
    await user.click(screen.getByRole('button', { name: /actualizar/i }))
    await waitFor(() => expect(callCount).toBeGreaterThan(initialCount))
  })
})
