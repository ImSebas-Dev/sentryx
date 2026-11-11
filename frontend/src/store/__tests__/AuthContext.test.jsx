/**
 * Sentryx — Tests del AuthContext.
 * Verifica login, logout, carga de perfil y guards de permisos.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server, mockSession, MOCK_TOKENS, MOCK_USER, MOCK_ADMIN } from '../../test/mswServer'
import { AuthProvider, useAuth } from '../AuthContext'
import { MemoryRouter } from 'react-router-dom'
import { tokenStore } from '../../services/api'

// Wrapper que incluye los providers necesarios
const wrapper = ({ children }) => (
  <MemoryRouter>
    <AuthProvider>{children}</AuthProvider>
  </MemoryRouter>
)

describe('useAuth — estado inicial', () => {
  beforeEach(() => localStorage.clear())

  it('inicia en estado sin usuario autenticado', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper })
    // Sin token, termina sin usuario
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.user).toBeNull()
  })

  it('termina en loading=false sin token guardado', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.user).toBeNull()
  })

  it('carga el perfil automáticamente si hay un access token en memoria', async () => {
    tokenStore.set('test-token-valid')
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.user).toBeTruthy()
    expect(result.current.user.username).toBe('analista01')
  })

  it('no carga el perfil si el token es inválido', async () => {
    server.use(
      http.get('/api/v1/auth/me/', () =>
        HttpResponse.json({ detail: 'Token inválido' }, { status: 401 })
      )
    )
    tokenStore.set('token-invalido')
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.user).toBeNull()
    // El token inválido se descarta
    expect(tokenStore.get()).toBeNull()
  })

  it('al recargar la página restaura la sesión con la cookie del refresh', async () => {
    mockSession.hasRefreshCookie = true
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.user.username).toBe('analista01')
    expect(tokenStore.get()).toBe(MOCK_TOKENS.access)
  })

  it('sin cookie del refresh no hay sesión', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.user).toBeNull()
    expect(tokenStore.get()).toBeNull()
  })
})

describe('useAuth — login', () => {
  beforeEach(() => localStorage.clear())

  it('login exitoso establece el usuario', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.loading).toBe(false))

    await act(async () => {
      await result.current.login('analista@sentryx.test', 'correcta')
    })

    expect(result.current.user).toBeTruthy()
    expect(result.current.user.username).toBe('analista01')
  })

  it('login guarda el access solo en memoria y el refresh queda en la cookie', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.loading).toBe(false))

    await act(async () => {
      await result.current.login('analista@sentryx.test', 'correcta')
    })

    expect(tokenStore.get()).toBe(MOCK_TOKENS.access)
    expect(mockSession.hasRefreshCookie).toBe(true)
    // Nada de tokens en localStorage: un XSS podría leerlos de ahí
    expect(localStorage.getItem('access_token')).toBeNull()
    expect(localStorage.getItem('refresh_token')).toBeNull()
  })

  it('login lanza error con credenciales incorrectas', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.loading).toBe(false))

    await expect(
      act(async () => {
        await result.current.login('analista@sentryx.test', 'contraseña_mal')
      })
    ).rejects.toBeDefined()

    expect(result.current.user).toBeNull()
  })

  it('login retorna el perfil del usuario', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.loading).toBe(false))

    let returnedUser
    await act(async () => {
      returnedUser = await result.current.login('analista@sentryx.test', 'correcta')
    })

    expect(returnedUser.username).toBe('analista01')
    expect(returnedUser.role).toBe('analyst')
  })
})

describe('useAuth — logout', () => {
  beforeEach(() => {
    tokenStore.set('tok')
    mockSession.hasRefreshCookie = true
  })

  it('logout limpia el usuario', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.loading).toBe(false))

    await act(async () => { await result.current.logout() })

    expect(result.current.user).toBeNull()
  })

  it('logout borra el access de memoria y revoca la cookie en el servidor', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.loading).toBe(false))

    await act(async () => { await result.current.logout() })

    expect(tokenStore.get()).toBeNull()
    expect(mockSession.hasRefreshCookie).toBe(false)
  })
})

describe('useAuth — permisos RBAC', () => {
  beforeEach(() => localStorage.clear())

  it('isAnalyst=true para rol analyst', async () => {
    tokenStore.set('tok')
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.loading).toBe(false))
    // MOCK_USER tiene role: 'analyst'
    expect(result.current.isAnalyst).toBe(true)
    expect(result.current.isAdmin).toBe(false)
  })

  it('isAdmin=false para rol analyst', async () => {
    tokenStore.set('tok')
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.isAdmin).toBe(false)
  })

  it('isAdmin=true y isAnalyst=true para rol admin', async () => {
    server.use(
      http.get('/api/v1/auth/me/', () => HttpResponse.json(MOCK_ADMIN))
    )
    tokenStore.set('tok')
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.isAdmin).toBe(true)
    expect(result.current.isAnalyst).toBe(true)
  })

  it('isAnalyst=false e isAdmin=false para rol viewer', async () => {
    server.use(
      http.get('/api/v1/auth/me/', () =>
        HttpResponse.json({ ...MOCK_USER, role: 'viewer', is_analyst: false, is_admin: false })
      )
    )
    tokenStore.set('tok')
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.isAnalyst).toBe(false)
    expect(result.current.isAdmin).toBe(false)
  })
})
