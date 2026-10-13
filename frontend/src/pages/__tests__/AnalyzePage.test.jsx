/**
 * Sentryx — Tests de la página de análisis de correos.
 * Verifica el flujo: formulario → API → resultado visual.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server, MOCK_ANALYZE_PHISHING, MOCK_ANALYZE_LEGIT } from '../../test/mswServer'
import { renderWithProviders, setAuthTokens } from '../../test/testUtils'
import AnalyzePage from '../AnalyzePage'

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual, useNavigate: () => mockNavigate }
})

describe('AnalyzePage — renderizado inicial', () => {
  beforeEach(() => { setAuthTokens(); mockNavigate.mockClear() })

  it('muestra el título y descripción de la página', () => {
    renderWithProviders(<AnalyzePage />)
    expect(screen.getAllByText('Analizar correo').length).toBeGreaterThan(0)
    expect(screen.getByText(/pega los datos del correo/i)).toBeInTheDocument()
  })

  it('muestra los campos del formulario', () => {
    renderWithProviders(<AnalyzePage />)
    expect(screen.getByPlaceholderText(/soporte@banco-seguro/i)).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/URGENTE: Verifica tu cuenta/i)).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/spf=fail/i)).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/pega aquí el cuerpo/i)).toBeInTheDocument()
  })

  it('muestra el estado vacío inicial en el panel de resultados', () => {
    renderWithProviders(<AnalyzePage />)
    expect(screen.getByText(/el resultado del análisis aparecerá aquí/i)).toBeInTheDocument()
  })

  it('el botón de analizar está deshabilitado sin cuerpo del correo', () => {
    renderWithProviders(<AnalyzePage />)
    expect(screen.getByRole('button', { name: /analizar correo/i })).toBeDisabled()
  })

  it('el botón de analizar se habilita al escribir en el cuerpo', async () => {
    const user = userEvent.setup()
    renderWithProviders(<AnalyzePage />)
    const textarea = screen.getByPlaceholderText(/pega aquí el cuerpo/i)
    await user.type(textarea, 'Texto del correo')
    expect(screen.getByRole('button', { name: /analizar correo/i })).not.toBeDisabled()
  })
})

describe('AnalyzePage — análisis de correo phishing', () => {
  beforeEach(() => { setAuthTokens(); mockNavigate.mockClear() })

  async function submitEmail(body, from = '', subject = '') {
    const user = userEvent.setup()
    renderWithProviders(<AnalyzePage />)
    if (from)    await user.type(screen.getByPlaceholderText(/soporte@banco/i), from)
    if (subject) await user.type(screen.getByPlaceholderText(/URGENTE/i), subject)
    await user.type(screen.getByPlaceholderText(/pega aquí/i), body)
    await user.click(screen.getByRole('button', { name: /analizar correo/i }))
    await waitFor(() => expect(
      screen.queryByText(/analizando/i)
    ).not.toBeInTheDocument(), { timeout: 5000 })
  }

  it('muestra score y clasificación tras analizar correo phishing', async () => {
    await submitEmail('Actualiza tu cuenta bancaria URGENTE')
    await waitFor(() => {
      expect(screen.getByText('83')).toBeInTheDocument() // 82.5 redondeado
    })
    expect(screen.getByText(/phishing detectado/i)).toBeInTheDocument()
  })

  it('muestra los scores de las tres capas ML', async () => {
    await submitEmail('Actualiza tu cuenta bancaria URGENTE')
    await waitFor(() => {
      expect(screen.getAllByText(/encabezados/i).length).toBeGreaterThan(0)
      expect(screen.getAllByText(/contenido/i).length).toBeGreaterThan(0)
      expect(screen.getAllByText(/urls/i).length).toBeGreaterThan(0)
    })
  })

  it('muestra el tipo de phishing detectado', async () => {
    await submitEmail('Actualiza tu cuenta bancaria URGENTE')
    await waitFor(() => {
      expect(screen.getByText('BEC')).toBeInTheDocument()
    })
  })

  it('muestra la técnica MITRE ATT&CK', async () => {
    await submitEmail('Actualiza tu cuenta bancaria URGENTE')
    await waitFor(() => {
      expect(screen.getByText('T1566.002')).toBeInTheDocument()
    })
  })

  it('muestra las URLs sospechosas encontradas', async () => {
    await submitEmail('Actualiza tu cuenta bancaria URGENTE')
    await waitFor(() => {
      expect(screen.getByText(/http:\/\/evil\.tk\/pay/i)).toBeInTheDocument()
    })
  })

  it('muestra botón de enlace a la alerta creada', async () => {
    await submitEmail('Actualiza tu cuenta bancaria URGENTE')
    await waitFor(() => {
      expect(screen.getByText(/alerta creada automáticamente/i)).toBeInTheDocument()
    })
  })

  it('navega al detalle de la alerta al hacer clic', async () => {
    await submitEmail('Actualiza tu cuenta bancaria URGENTE')
    await waitFor(() => {
      expect(screen.getByText(/alerta creada automáticamente/i)).toBeInTheDocument()
    })
    const alertBtn = screen.getByText(/alerta creada automáticamente/i).closest('button')
    await userEvent.setup().click(alertBtn)
    expect(mockNavigate).toHaveBeenCalledWith(`/alerts/${MOCK_ANALYZE_PHISHING.alert_id}`)
  })
})

describe('AnalyzePage — correo legítimo', () => {
  beforeEach(() => setAuthTokens())

  it('muestra mensaje de correo legítimo', async () => {
    const user = userEvent.setup()
    renderWithProviders(<AnalyzePage />)
    await user.type(
      screen.getByPlaceholderText(/pega aquí/i),
      'Gracias por tu compra en Amazon.'
    )
    await user.click(screen.getByRole('button', { name: /analizar correo/i }))
    await waitFor(() => {
      expect(screen.getByText(/correo legítimo/i)).toBeInTheDocument()
    })
  })

  it('muestra score bajo para correo legítimo', async () => {
    const user = userEvent.setup()
    renderWithProviders(<AnalyzePage />)
    await user.type(
      screen.getByPlaceholderText(/pega aquí/i),
      'Gracias por tu compra en Amazon.'
    )
    await user.click(screen.getByRole('button', { name: /analizar correo/i }))
    await waitFor(() => {
      // Score 8 del correo legítimo — puede aparecer en varias formas
      expect(screen.getAllByText('8').length).toBeGreaterThan(0)
    })
  })

  it('no muestra botón de alerta para correo legítimo', async () => {
    const user = userEvent.setup()
    renderWithProviders(<AnalyzePage />)
    await user.type(
      screen.getByPlaceholderText(/pega aquí/i),
      'Gracias por tu compra.'
    )
    await user.click(screen.getByRole('button', { name: /analizar correo/i }))
    await waitFor(() => {
      expect(screen.queryByText(/alerta creada/i)).not.toBeInTheDocument()
    })
  })
})

describe('AnalyzePage — botón limpiar', () => {
  beforeEach(() => setAuthTokens())

  it('limpia el formulario y el resultado', async () => {
    const user = userEvent.setup()
    renderWithProviders(<AnalyzePage />)

    await user.type(screen.getByPlaceholderText(/pega aquí/i), 'Texto de prueba')
    await user.click(screen.getByRole('button', { name: /analizar correo/i }))
    await waitFor(() => expect(screen.queryByText(/analizando/i)).not.toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: /limpiar/i }))

    expect(screen.getByPlaceholderText(/pega aquí/i).value).toBe('')
    expect(screen.getByText(/el resultado del análisis aparecerá aquí/i)).toBeInTheDocument()
  })
})

describe('AnalyzePage — errores del ML Engine', () => {
  beforeEach(() => setAuthTokens())

  it('muestra error cuando ML Engine no está disponible', async () => {
    server.use(
      http.post('/api/v1/alerts/analyze/', () =>
        HttpResponse.json({ error: 'ML Engine no disponible.' }, { status: 503 })
      )
    )
    const user = userEvent.setup()
    renderWithProviders(<AnalyzePage />)
    await user.type(screen.getByPlaceholderText(/pega aquí/i), 'Texto de prueba')
    await user.click(screen.getByRole('button', { name: /analizar correo/i }))
    await waitFor(() => {
      expect(
        screen.queryByText(/error/i) || screen.queryByText(/ml engine/i)
      ).toBeTruthy()
    })
  })
})

describe('AnalyzePage — destinatario', () => {
  beforeEach(() => { setAuthTokens(); mockNavigate.mockClear() })

  it('envía el destinatario como to_addr para seudonimizarlo', async () => {
    let sent = null
    server.use(http.post('/api/v1/alerts/analyze/', async ({ request }) => {
      sent = await request.json()
      return HttpResponse.json(MOCK_ANALYZE_LEGIT)
    }))
    const user = userEvent.setup()
    renderWithProviders(<AnalyzePage />)
    await user.type(screen.getByLabelText('Destinatario (To)'), 'tesoreria@empresa.co')
    await user.type(screen.getByPlaceholderText(/pega aquí/i), 'Hola')
    await user.click(screen.getByRole('button', { name: /analizar correo/i }))
    await waitFor(() => expect(sent).not.toBeNull())
    expect(sent.headers.to_addr).toBe('tesoreria@empresa.co')
  })
})
