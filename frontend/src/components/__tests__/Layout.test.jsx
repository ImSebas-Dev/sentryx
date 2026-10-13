/**
 * Sentryx — Tests del Layout y sidebar de navegación.
 * Verifica que los links del nav, el nombre de usuario y el logout funcionen.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders, setAuthTokens } from '../../test/testUtils'
import Layout from '../Layout'

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    NavLink: ({ to, children, className }) => (
      <a href={to} onClick={e => { e.preventDefault(); mockNavigate(to) }}
          className={typeof className === 'function' ? className({ isActive: false }) : className}>
        {children}
      </a>
    ),
  }
})

function renderLayout() {
  return renderWithProviders(
    <Layout>
      <div data-testid="content">Contenido de prueba</div>
    </Layout>
  )
}

describe('Layout — estructura general', () => {
  beforeEach(() => { setAuthTokens(); mockNavigate.mockClear() })

  it('renderiza el logo de Sentryx', async () => {
    renderLayout()
    await waitFor(() => {
      expect(screen.getByText('Sentryx')).toBeInTheDocument()
    })
  })

  it('renderiza el subtítulo de versión', async () => {
    renderLayout()
    await waitFor(() => {
      expect(screen.getByText(/v2\.0/i)).toBeInTheDocument()
    })
  })

  it('renderiza el contenido hijo', async () => {
    renderLayout()
    expect(screen.getByTestId('content')).toBeInTheDocument()
  })
})

describe('Layout — navegación', () => {
  beforeEach(() => { setAuthTokens(); mockNavigate.mockClear() })

  it('muestra todos los links de navegación', async () => {
    renderLayout()
    await waitFor(() => {
      expect(screen.getByText('Dashboard')).toBeInTheDocument()
      expect(screen.getByText('Alertas')).toBeInTheDocument()
      expect(screen.getByText('Analizar correo')).toBeInTheDocument()
      expect(screen.getByText('Incidentes')).toBeInTheDocument()
      expect(screen.getByText('Threat Intel')).toBeInTheDocument()
    })
  })

  it('navega a la ruta correcta al hacer clic en Alertas', async () => {
    const user = userEvent.setup()
    renderLayout()
    await waitFor(() => expect(screen.getByText('Alertas')).toBeInTheDocument())
    await user.click(screen.getByText('Alertas'))
    expect(mockNavigate).toHaveBeenCalledWith('/alerts')
  })

  it('navega a la ruta correcta al hacer clic en Analizar correo', async () => {
    const user = userEvent.setup()
    renderLayout()
    await waitFor(() => expect(screen.getByText('Analizar correo')).toBeInTheDocument())
    await user.click(screen.getByText('Analizar correo'))
    expect(mockNavigate).toHaveBeenCalledWith('/analyze')
  })

  it('navega a Incidentes', async () => {
    const user = userEvent.setup()
    renderLayout()
    await waitFor(() => expect(screen.getByText('Incidentes')).toBeInTheDocument())
    await user.click(screen.getByText('Incidentes'))
    expect(mockNavigate).toHaveBeenCalledWith('/incidents')
  })

  it('navega a Threat Intel', async () => {
    const user = userEvent.setup()
    renderLayout()
    await waitFor(() => expect(screen.getByText('Threat Intel')).toBeInTheDocument())
    await user.click(screen.getByText('Threat Intel'))
    expect(mockNavigate).toHaveBeenCalledWith('/threat-intel')
  })
})

describe('Layout — perfil de usuario', () => {
  beforeEach(() => setAuthTokens())

  it('muestra el nombre de usuario del perfil cargado', async () => {
    renderLayout()
    await waitFor(() => {
      expect(screen.getByText('analista01')).toBeInTheDocument()
    })
  })

  it('muestra el rol del usuario', async () => {
    renderLayout()
    await waitFor(() => {
      expect(screen.getByText('Analista')).toBeInTheDocument()
    })
  })

  it('muestra el avatar del usuario autenticado', async () => {
    renderLayout()
    await waitFor(() => {
      // El avatar es un div con clase rounded-full que contiene la inicial
      const avatar = document.querySelector('.rounded-full')
      expect(avatar).toBeInTheDocument()
    })
  })
})

describe('Layout — logout', () => {
  beforeEach(() => { setAuthTokens(); mockNavigate.mockClear() })

  it('muestra el botón de cerrar sesión', async () => {
    renderLayout()
    await waitFor(() => {
      expect(screen.getByText('Cerrar sesión')).toBeInTheDocument()
    })
  })

  it('hace logout y redirige al login', async () => {
    const user = userEvent.setup()
    renderLayout()
    await waitFor(() => expect(screen.getByText('Cerrar sesión')).toBeInTheDocument())
    await user.click(screen.getByText('Cerrar sesión'))
    expect(mockNavigate).toHaveBeenCalledWith('/login')
    // Tokens eliminados
    expect(localStorage.getItem('access_token')).toBeNull()
  })
})
