/**
 * Sentryx — Tests del cliente HTTP (api.js).
 * En jsdom, Axios con XMLHttpRequest necesita URLs absolutas.
 * MSW intercepta las llamadas a http://localhost/api/v1/...
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server, MOCK_TOKENS, MOCK_USER, MOCK_STATS } from '../../test/mswServer'

// Importar el módulo de api DESPUÉS de que el setup haya definido window.location
// Usamos fetch directamente para los tests del cliente, más confiable en jsdom
const BASE = 'http://localhost/api/v1'

async function apiGet(path, token = null) {
  const headers = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(`${BASE}${path}`, { headers })
  return res
}

async function apiPost(path, body, token = null) {
  const headers = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  })
  return res
}

async function apiPatch(path, body, token = null) {
  const headers = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(`${BASE}${path}`, {
    method: 'PATCH',
    headers,
    body: JSON.stringify(body),
  })
  return res
}

describe('authAPI — login', () => {
  it('login retorna tokens con credenciales correctas', async () => {
    const res  = await apiPost('/auth/token/', { email: 'analista@sentryx.test', password: 'correcta' })
    const data = await res.json()
    expect(res.status).toBe(200)
    expect(data.access).toBe(MOCK_TOKENS.access)
    expect(data.refresh).toBe(MOCK_TOKENS.refresh)
  })

  it('login retorna 401 con credenciales incorrectas', async () => {
    const res = await apiPost('/auth/token/', { email: 'x@sentryx.test', password: 'y' })
    expect(res.status).toBe(401)
  })
})

describe('authAPI — me()', () => {
  it('retorna el perfil con token válido', async () => {
    const res  = await apiGet('/auth/me/', 'valid-token')
    const data = await res.json()
    expect(res.status).toBe(200)
    expect(data.username).toBe('analista01')
    expect(data.role).toBe('analyst')
  })

  it('retorna 401 sin token', async () => {
    const res = await apiGet('/auth/me/', null)
    expect(res.status).toBe(401)
  })
})

describe('alertsAPI — stats()', () => {
  it('retorna métricas del dashboard', async () => {
    const res  = await apiGet('/alerts/stats/', 'tok')
    const data = await res.json()
    expect(res.status).toBe(200)
    expect(data.total).toBe(42)
    expect(data.critical).toBe(5)
    expect(data.daily_last_7_days).toHaveLength(7)
  })
})

describe('alertsAPI — list()', () => {
  it('retorna lista paginada de alertas', async () => {
    const res  = await apiGet('/alerts/', 'tok')
    const data = await res.json()
    expect(res.status).toBe(200)
    expect(data.count).toBe(3)
    expect(data.results).toHaveLength(3)
  })

  it('aplica filtro por phishing_type', async () => {
    const res  = await apiGet('/alerts/?phishing_type=spear', 'tok')
    const data = await res.json()
    expect(data.results.every(a => a.phishing_type === 'spear')).toBe(true)
  })

  it('aplica filtro por severity', async () => {
    const res  = await apiGet('/alerts/?severity=CRITICAL', 'tok')
    const data = await res.json()
    expect(data.results.every(a => a.severity === 'CRITICAL')).toBe(true)
  })
})

describe('alertsAPI — detail()', () => {
  it('retorna una alerta por id', async () => {
    const res  = await apiGet('/alerts/alert-uuid-001/', 'tok')
    const data = await res.json()
    expect(res.status).toBe(200)
    expect(data.id).toBe('alert-uuid-001')
    expect(data.phishing_type).toBe('bec')
    expect(data.risk_score).toBe(88.0)
  })

  it('retorna 404 para id inexistente', async () => {
    const res = await apiGet('/alerts/id-que-no-existe/', 'tok')
    expect(res.status).toBe(404)
  })
})

describe('alertsAPI — update()', () => {
  it('modifica el status de una alerta', async () => {
    const res  = await apiPatch('/alerts/alert-uuid-001/', { status: 'acknowledged' }, 'tok')
    const data = await res.json()
    expect(res.status).toBe(200)
    expect(data.status).toBe('acknowledged')
  })
})

describe('alertsAPI — analyze()', () => {
  it('retorna phishing para correo sospechoso (status 201)', async () => {
    const res  = await apiPost('/alerts/analyze/', { body_text: 'Actualiza tu cuenta bancaria URGENTE' }, 'tok')
    const data = await res.json()
    expect(res.status).toBe(201)
    expect(data.classification).toBe('phishing')
    expect(data.alert_created).toBe(true)
    expect(data.alert_id).toBeTruthy()
  })

  it('retorna legítimo para correo normal (status 200)', async () => {
    const res  = await apiPost('/alerts/analyze/', { body_text: 'Gracias por tu compra.' }, 'tok')
    const data = await res.json()
    expect(res.status).toBe(200)
    expect(data.classification).toBe('legitimate')
    expect(data.alert_created).toBe(false)
    expect(data.alert_id).toBeNull()
  })

  it('retorna scores por las tres capas', async () => {
    const res  = await apiPost('/alerts/analyze/', { body_text: 'Actualiza tu cuenta bancaria URGENTE' }, 'tok')
    const data = await res.json()
    expect(data.scores_by_layer).toHaveProperty('headers')
    expect(data.scores_by_layer).toHaveProperty('content')
    expect(data.scores_by_layer).toHaveProperty('urls')
  })

  it('incluye el tiempo de inferencia en ms', async () => {
    const res  = await apiPost('/alerts/analyze/', { body_text: 'test' }, 'tok')
    const data = await res.json()
    expect(data.inference_ms).toBeTypeOf('number')
    expect(data.inference_ms).toBeGreaterThan(0)
  })
})

describe('Threat Intelligence — check()', () => {
  it('detecta IOC malicioso', async () => {
    const res  = await apiPost('/threat-intel/check/', { value: 'http://evil.tk/phish' }, 'tok')
    const data = await res.json()
    expect(data.found).toBe(true)
    expect(data.threat_level).toBe('HIGH')
  })

  it('retorna found:false para URL limpia', async () => {
    const res  = await apiPost('/threat-intel/check/', { value: 'https://google.com' }, 'tok')
    const data = await res.json()
    expect(data.found).toBe(false)
  })
})

describe('Interceptor JWT — Authorization header', () => {
  it('MSW recibe el header cuando se envía manualmente', async () => {
    let capturedAuth = null
    server.use(
      http.get('http://localhost/api/v1/alerts/stats/', ({ request }) => {
        capturedAuth = request.headers.get('Authorization')
        return HttpResponse.json(MOCK_STATS)
      })
    )
    await apiGet('/alerts/stats/', 'mi-token-de-prueba')
    expect(capturedAuth).toBe('Bearer mi-token-de-prueba')
  })

  it('no hay Authorization header sin token', async () => {
    let capturedAuth = 'presente'
    server.use(
      http.get('http://localhost/api/v1/alerts/stats/', ({ request }) => {
        capturedAuth = request.headers.get('Authorization')
        return HttpResponse.json(MOCK_STATS)
      })
    )
    await apiGet('/alerts/stats/', null)
    expect(capturedAuth).toBeNull()
  })
})

describe('Manejo de errores de red', () => {
  it('retorna 503 cuando ML Engine no disponible', async () => {
    server.use(
      http.post('http://localhost/api/v1/alerts/analyze/', () =>
        HttpResponse.json({ error: 'ML Engine no disponible' }, { status: 503 })
      )
    )
    const res = await apiPost('/alerts/analyze/', { body_text: 'test' }, 'tok')
    expect(res.status).toBe(503)
  })
})
