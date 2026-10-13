/**
 * Sentryx — Tests de los interceptores de api.js (sesión y 2FA).
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/mswServer'
import api, { authAPI, SECURITY_PATH } from '../api'

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
})
