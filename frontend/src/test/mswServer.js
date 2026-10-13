/**
 * Sentryx — Mock Service Worker (MSW) para tests.
 * Intercepta las llamadas a la API y retorna respuestas controladas
 * sin necesidad de un backend real corriendo.
 */
import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'

// ── Datos de prueba ────────────────────────────────────────
export const MOCK_USER = {
  id:           '550e8400-e29b-41d4-a716-446655440000',
  username:     'analista01',
  email:        'analista@sentryx.test',
  role:         'analyst',
  organization: 'Test Corp',
  first_name:   'Ana',
  last_name:    'Lista',
  date_joined:  '2026-01-01T00:00:00Z',
  is_analyst:   true,
  is_admin:     false,
}

export const MOCK_ADMIN = {
  ...MOCK_USER,
  id:       '550e8400-e29b-41d4-a716-446655440001',
  username: 'admin01',
  role:     'admin',
  is_analyst: true,
  is_admin:   true,
}

// Verificación en dos pasos
export const MOCK_MFA_EMAIL     = 'mfa@sentryx.test'
export const MOCK_TOTP          = '123456'
export const MOCK_RECOVERY_CODE = 'abcde-fghjk'
export const MOCK_RECOVERY_CODES = [
  'abcde-fghjk', 'mnpqr-stuvw', 'xyz23-45678', 'a2b3c-d4e5f',
  'g6h7j-k8m9n', 'pqrst-uvwxy', 'z2345-6789a', 'bcdef-ghjkm',
]

export const MOCK_TOKENS = {
  access:  'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.test_access',
  refresh: 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.test_refresh',
}

export const MOCK_ALERT = {
  id:            'alert-uuid-001',
  severity:      'CRITICAL',
  phishing_type: 'bec',
  status:        'new',
  title:         'Business Email Compromise detectado',
  description:   'Tipo: bec | Score: 88/100 | Dominio: evil.tk',
  risk_score:    88.0,
  score_headers: 95.0,
  score_content: 82.0,
  score_urls:    90.0,
  sender_domain: 'evil.tk',
  sender_hash:   'a'.repeat(64),
  subject_hash:  'b'.repeat(64),
  has_attachments:     false,
  attachment_count:    0,
  url_count:           2,
  ml_features:  {
    headers: { spf_pass: 0, spf_fail: 1, dkim_pass: 0, dkim_fail: 1,
               dmarc_pass: 0, dmarc_fail: 1, reply_to_differs: 1,
               from_suspicious_tld: 1, min_brand_distance: 1,
               subject_has_urgency: 1, received_hop_count: 5 },
    content: { urgency_count: 3, has_urgency: 1, signals_bec: 2 },
  },
  suspicious_urls: [
    { url: 'http://evil.tk/pay', score: 90.0 },
  ],
  mitre_tactic:    'Initial Access',
  mitre_technique: 'T1566.002',
  campaign:        null,
  campaign_name:   null,
  assigned_to_name:null,
  detected_at:     '2026-08-23T10:30:00Z',
  updated_at:      '2026-08-23T10:30:00Z',
  classification:  'critical',
  scores_by_layer: { headers: 95.0, content: 82.0, urls: 90.0 },
}

export const MOCK_ALERTS_LIST = {
  count:    3,
  next:     null,
  previous: null,
  results:  [
    MOCK_ALERT,
    { ...MOCK_ALERT, id: 'alert-uuid-002', phishing_type: 'spear',
      severity: 'HIGH', risk_score: 74.0, title: 'Spear phishing detectado' },
    { ...MOCK_ALERT, id: 'alert-uuid-003', phishing_type: 'whaling',
      severity: 'CRITICAL', risk_score: 91.0, title: 'Whaling detectado',
      status: 'acknowledged' },
  ],
}

export const MOCK_STATS = {
  total:             42,
  new:               12,
  critical:           5,
  week_total:        18,
  active_campaigns:   2,
  false_positive_rate: 3.2,
  by_severity: { CRITICAL: 5, HIGH: 15, MEDIUM: 14, LOW: 8 },
  by_type: { bec: 10, spear: 8, whaling: 5, clone: 7, vishing: 6, generic: 6 },
  daily_last_7_days: [
    { date: '2026-08-17', count: 3 },
    { date: '2026-08-18', count: 5 },
    { date: '2026-08-19', count: 2 },
    { date: '2026-08-20', count: 8 },
    { date: '2026-08-21', count: 4 },
    { date: '2026-08-22', count: 6 },
    { date: '2026-08-23', count: 3 },
  ],
}

export const MOCK_ANALYZE_PHISHING = {
  alert_id:       'alert-uuid-new-001',
  risk_score:     82.5,
  classification: 'phishing',
  phishing_type:  'bec',
  mitre_technique:'T1566.002',
  scores_by_layer:{ headers: 90.0, content: 75.0, urls: 85.0 },
  url_count:       2,
  urls_analyzed:  [{ url_truncated: 'http://evil.tk/pay', score: 85.0 }],
  inference_ms:   142.3,
  alert_created:  true,
}

export const MOCK_ANALYZE_LEGIT = {
  alert_id:       null,
  risk_score:     8.0,
  classification: 'legitimate',
  phishing_type:  'legitimate',
  mitre_technique:'T1566',
  scores_by_layer:{ headers: 5.0, content: 8.0, urls: 0.0 },
  url_count:       0,
  urls_analyzed:  [],
  inference_ms:   98.1,
  alert_created:  false,
}

// ── Handlers MSW ──────────────────────────────────────────
export const handlers = [
  // Auth
  http.post('/api/v1/auth/token/', async ({ request }) => {
    const body = await request.json()
    // El backend autentica por correo (USERNAME_FIELD = "email")
    if (body.email === MOCK_USER.email && body.password === 'correcta') {
      return HttpResponse.json(MOCK_TOKENS)
    }
    if (body.email === 'admin@sentryx.test' && body.password === 'correcta') {
      return HttpResponse.json(MOCK_TOKENS)
    }
    // Cuenta con verificación en dos pasos: no entrega JWT en el primer paso
    if (body.email === MOCK_MFA_EMAIL && body.password === 'correcta') {
      return HttpResponse.json({ mfa_required: true, mfa_token: 'mfa-token-ok', expires_in: 300 })
    }
    return HttpResponse.json(
      { detail: 'No active account found with the given credentials' },
      { status: 401 }
    )
  }),

  http.post('/api/v1/auth/mfa/verify/', async ({ request }) => {
    const body = await request.json()
    if (body.mfa_token === 'mfa-token-expired') {
      return HttpResponse.json(
        { error: 'La verificación expiró. Inicia sesión de nuevo.', code: 'mfa_token_expired' },
        { status: 401 })
    }
    if (body.code === MOCK_TOTP) return HttpResponse.json(MOCK_TOKENS)
    if (body.recovery_code === MOCK_RECOVERY_CODE) {
      return HttpResponse.json({ ...MOCK_TOKENS, recovery_codes_remaining: 7 })
    }
    return HttpResponse.json(
      { error: 'El código no es válido.', code: 'mfa_invalid_code', attempts_left: 4 },
      { status: 400 })
  }),

  http.post('/api/v1/auth/mfa/setup/', () => HttpResponse.json({
    secret: 'JBSWY3DPEHPK3PXP',
    otpauth_url: 'otpauth://totp/Sentryx:analista%40sentryx.test?secret=JBSWY3DPEHPK3PXP&issuer=Sentryx',
    qr_code: 'data:image/png;base64,iVBORw0KGgo=',
  })),

  http.post('/api/v1/auth/mfa/enable/', async ({ request }) => {
    const body = await request.json()
    if (body.code !== MOCK_TOTP) {
      return HttpResponse.json({ error: 'El código no es válido.', code: 'mfa_invalid_code' }, { status: 400 })
    }
    return HttpResponse.json({ recovery_codes: MOCK_RECOVERY_CODES })
  }),

  http.post('/api/v1/auth/mfa/disable/', async ({ request }) => {
    const body = await request.json()
    if (body.password !== 'correcta') {
      return HttpResponse.json({ error: 'La contraseña o el código no son correctos.' }, { status: 400 })
    }
    return HttpResponse.json({ message: 'Verificación en dos pasos desactivada.' })
  }),

  http.post('/api/v1/auth/token/refresh/', () =>
    HttpResponse.json({ access: MOCK_TOKENS.access })
  ),

  http.get('/api/v1/auth/me/', ({ request }) => {
    const auth = request.headers.get('Authorization')
    if (!auth) return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    return HttpResponse.json(MOCK_USER)
  }),

  // Alerts
  http.get('/api/v1/alerts/', ({ request }) => {
    const url    = new URL(request.url)
    const type   = url.searchParams.get('phishing_type')
    const sev    = url.searchParams.get('severity')
    let results  = MOCK_ALERTS_LIST.results
    if (type)  results = results.filter(a => a.phishing_type === type)
    if (sev)   results = results.filter(a => a.severity === sev)
    return HttpResponse.json({ ...MOCK_ALERTS_LIST, results, count: results.length })
  }),

  http.get('/api/v1/alerts/stats/', () => HttpResponse.json(MOCK_STATS)),

  http.get('/api/v1/alerts/campaigns/', () =>
    HttpResponse.json({ count: 1, results: [
      { id: 'camp-001', name: 'Campaña evil.tk', indicator: 'evil.tk',
        alert_count: 3, is_active: true, mitre_technique: 'T1566.001',
        first_seen: '2026-08-23T09:00:00Z', last_seen: '2026-08-23T10:30:00Z' },
    ]})
  ),

  http.get('/api/v1/alerts/:id/', ({ params }) => {
    const alert = MOCK_ALERTS_LIST.results.find(a => a.id === params.id)
    if (!alert) return HttpResponse.json({ detail: 'Not found' }, { status: 404 })
    return HttpResponse.json(alert)
  }),

  http.patch('/api/v1/alerts/:id/', async ({ params, request }) => {
    const body  = await request.json()
    const alert = MOCK_ALERTS_LIST.results.find(a => a.id === params.id)
    if (!alert) return HttpResponse.json({ detail: 'Not found' }, { status: 404 })
    return HttpResponse.json({ ...alert, ...body })
  }),

  http.post('/api/v1/alerts/analyze/', async ({ request }) => {
    const body = await request.json()
    const text = body.body_text || ''
    // Simular phishing si el cuerpo tiene palabras clave
    if (text.toLowerCase().includes('urgente') ||
        text.toLowerCase().includes('cuenta bancaria')) {
      return HttpResponse.json(MOCK_ANALYZE_PHISHING, { status: 201 })
    }
    return HttpResponse.json(MOCK_ANALYZE_LEGIT, { status: 200 })
  }),

  // Incidents
  http.get('/api/v1/incidents/', () =>
    HttpResponse.json({ count: 1, results: [
      { id: 'inc-001', title: 'Campaña BEC activa', severity: 'CRITICAL',
        status: 'investigating', alert_count: 3,
        mitre_technique: 'T1566.002', assigned_to_name: 'analista01',
        created_at: '2026-08-23T09:00:00Z', updated_at: '2026-08-23T10:00:00Z' },
    ]})
  ),

  http.post('/api/v1/incidents/', async ({ request }) => {
    const body = await request.json()
    return HttpResponse.json({
      id: 'inc-new', ...body, status: 'new',
      created_at: new Date().toISOString(), alert_count: 0,
    }, { status: 201 })
  }),

  http.get('/api/v1/incidents/:id/', ({ params }) =>
    HttpResponse.json({
      id: params.id, title: 'Campaña BEC activa', severity: 'CRITICAL',
      status: 'investigating', description: 'Descripción del incidente.',
      mitre_tactic: 'Initial Access', mitre_technique: 'T1566.002',
      alerts: [MOCK_ALERT], timeline: [],
      assigned_to_name: 'analista01', created_by_name: 'admin01',
      created_at: '2026-08-23T09:00:00Z',
      updated_at: '2026-08-23T10:00:00Z', closed_at: null,
    })
  ),

  // Threat Intel
  http.get('/api/v1/threat-intel/stats/', () =>
    HttpResponse.json({
      total_active: 1250,
      by_source: { phishtank: 800, openphish: 350, misp: 80, manual: 20 },
      by_type:   { url: 1100, domain: 120, ip: 30 },
    })
  ),

  http.get('/api/v1/threat-intel/iocs/', () =>
    HttpResponse.json({ count: 2, results: [
      { id: 'ioc-1', ioc_type: 'url', value: 'http://evil.tk/phish',
        threat_level: 'HIGH', source: 'phishtank', mitre_technique: 'T1566.001',
        brand_targeted: 'Bancolombia', description: '', is_active: true,
        first_seen: '2026-08-23T00:00:00Z', last_seen: '2026-08-23T10:00:00Z' },
      { id: 'ioc-2', ioc_type: 'domain', value: 'bancolombia-seguro.tk',
        threat_level: 'CRITICAL', source: 'openphish', mitre_technique: 'T1566.001',
        brand_targeted: 'Bancolombia', description: '', is_active: true,
        first_seen: '2026-08-22T00:00:00Z', last_seen: '2026-08-23T09:00:00Z' },
    ]})
  ),

  http.post('/api/v1/threat-intel/check/', async ({ request }) => {
    const body = await request.json()
    if (body.value.includes('evil')) {
      return HttpResponse.json({
        found: true, ioc_type: 'url', threat_level: 'HIGH',
        source: 'phishtank', mitre_technique: 'T1566.001',
        brand_targeted: 'Bancolombia',
      })
    }
    return HttpResponse.json({ found: false, ioc_type: null, threat_level: null,
                               source: null, mitre_technique: null, brand_targeted: null })
  }),

  http.post('/api/v1/threat-intel/iocs/', async ({ request }) => {
    const body = await request.json()
    return HttpResponse.json({
      id: 'ioc-new', ...body, source: 'manual', is_active: true,
      first_seen: new Date().toISOString(), last_seen: new Date().toISOString(),
    }, { status: 201 })
  }),
]

// Servidor MSW
export const server = setupServer(...handlers)
