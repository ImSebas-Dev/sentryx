/**
 * Sentryx — Tests de los interceptores de api.js (sesión y 2FA).
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server, mockSession, MOCK_TOKENS } from '../../test/mswServer'
import api, { authAPI, SECURITY_PATH, tokenStore } from '../api'

describe('interceptores de api.js', () => {
  beforeEach(() => localStorage.clear())

  it('un 401 del login no redirige ni recarga la página', async () => {
    await expect(authAPI.login({ email: 'x@sentryx.test', password: 'mal' }))
      .rejects.toMatchObject({ response: { status: 401 } })
    expect(window.location.href).toBe('http://localhost/')
  })

  it('un 401 del segundo paso del login no redirige', async () => {
    server.use(http.post('/api/v1/auth/mfa/verify/', () =>
      HttpResponse.json({ code: 'mfa_token_used' }, { status: 401 })))
    await expect(authAPI.mfaVerify({ mfa_token: 't', code: '123456' }))
      .rejects.toMatchObject({ response: { status: 401 } })
    expect(window.location.href).toBe('http://localhost/')
  })

  it('un 401 en otra ruta sin refresh token manda al login', async () => {
    server.use(http.get('/api/v1/alerts/', () =>
      HttpResponse.json({ detail: 'expirado' }, { status: 401 })))
    await expect(api.get('/alerts/')).rejects.toBeDefined()
    expect(window.location.href).toBe('/login')
  })

  it('un 403 mfa_setup_required manda a Seguridad de la cuenta', async () => {
    server.use(http.get('/api/v1/alerts/', () =>
      HttpResponse.json({ detail: 'Activa 2FA', code: 'mfa_setup_required' }, { status: 403 })))
    await expect(api.get('/alerts/')).rejects.toBeDefined()
    expect(window.location.href).toBe(SECURITY_PATH)
  })

  it('envía X-Sentryx-Client: web para recibir el refresh en cookie HttpOnly', async () => {
    let header = null
    server.use(http.post('/api/v1/auth/token/', ({ request }) => {
      header = request.headers.get('X-Sentryx-Client')
      return HttpResponse.json({ access: 'a' })
    }))
    await authAPI.login({ email: 'x@sentryx.test', password: 'y' })
    expect(header).toBe('web')
  })

  it('un 401 renueva el access con la cookie y repite la petición', async () => {
    tokenStore.set('caducado')
    mockSession.hasRefreshCookie = true
    server.use(http.get('/api/v1/alerts/', ({ request }) =>
      request.headers.get('Authorization') === `Bearer ${MOCK_TOKENS.access}`
        ? HttpResponse.json({ count: 0, results: [] })
        : HttpResponse.json({ detail: 'expirado' }, { status: 401 })))
    const res = await api.get('/alerts/')
    expect(res.data.count).toBe(0)
    expect(tokenStore.get()).toBe(MOCK_TOKENS.access)
  })

  it('varios 401 a la vez comparten una sola renovación', async () => {
    tokenStore.set('caducado')
    mockSession.hasRefreshCookie = true
    let refreshCalls = 0
    server.use(
      http.post('/api/v1/auth/token/refresh/', () => {
        refreshCalls += 1
        return HttpResponse.json({ access: MOCK_TOKENS.access })
      }),
      http.get('/api/v1/alerts/', ({ request }) =>
        request.headers.get('Authorization') === `Bearer ${MOCK_TOKENS.access}`
          ? HttpResponse.json({ count: 0, results: [] })
          : HttpResponse.json({ detail: 'expirado' }, { status: 401 })),
    )
    await Promise.all([api.get('/alerts/'), api.get('/alerts/'), api.get('/alerts/')])
    expect(refreshCalls).toBe(1)
  })
})
