/**
 * Sentryx — Cliente HTTP centralizado.
 * Gestiona tokens JWT, refresh automático y errores globales.
 */
import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_URL || (typeof window !== 'undefined' && window.location?.origin ? window.location.origin + '/api/v1' : 'http://localhost/api/v1')

const api = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 15000,
})

// ── Interceptor de request: adjuntar token JWT ────────────
api.interceptors.request.use(config => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Endpoints de login: un 401 aquí significa credenciales o código incorrectos,
// no una sesión caducada. No intentar refresh ni redirigir (recargaría la
// página y se perdería el mensaje de error).
const AUTH_ENDPOINTS = ['/auth/token/', '/auth/mfa/verify/']
const isAuthEndpoint = url => AUTH_ENDPOINTS.some(p => (url || '').endsWith(p))

// Ruta de la página donde un admin sin 2FA debe configurarlo cuando la
// política MFA_REQUIRED_FOR_ADMINS está activa.
export const SECURITY_PATH = '/security'

// ── Interceptor de response: refresh automático ───────────
api.interceptors.response.use(
  res => res,
  async err => {
    const original = err.config
    if (err.response?.status === 403 && err.response.data?.code === 'mfa_setup_required') {
      if (window.location.pathname !== SECURITY_PATH) window.location.href = SECURITY_PATH
      return Promise.reject(err)
    }
    if (err.response?.status === 401 && original && !original._retry && !isAuthEndpoint(original.url)) {
      original._retry = true
      const refresh = localStorage.getItem('refresh_token')
      if (refresh) {
        try {
          const { data } = await axios.post(`${BASE_URL}/auth/token/refresh/`,
            { refresh })
          localStorage.setItem('access_token', data.access)
          original.headers.Authorization = `Bearer ${data.access}`
          return api(original)
        } catch {
          // Refresh expirado → limpiar sesión (sin borrar preferencias como el tema)
          localStorage.removeItem('access_token')
          localStorage.removeItem('refresh_token')
          window.location.href = '/login'
        }
      } else {
        window.location.href = '/login'
      }
    }
    return Promise.reject(err)
  }
)

// ── Helpers ───────────────────────────────────────────────
export const authAPI = {
  login:   (credentials) => api.post('/auth/token/', credentials),
  refresh: (refresh)     => api.post('/auth/token/refresh/', { refresh }),
  me:      ()            => api.get('/auth/me/'),
  register: (data) => api.post('/auth/register/', data),
  verifyEmail: (data) => api.post('/auth/verify-email/', data),
  resendVerification: (data) => api.post('/auth/resend-verification/', data),
  passwordReset: (data) => api.post('/auth/password-reset/', data),
  passwordResetConfirm: (data) => api.post('/auth/password-reset/confirm/', data),
  pendingUsers: () => api.get('/auth/users/pending/'),
  // Verificación en dos pasos
  mfaVerify:  (data) => api.post('/auth/mfa/verify/', data),
  mfaSetup:   ()     => api.post('/auth/mfa/setup/'),
  mfaEnable:  (code) => api.post('/auth/mfa/enable/', { code }),
  mfaDisable: (data) => api.post('/auth/mfa/disable/', data),
  mfaReset:   (userId) => api.post(`/auth/users/${userId}/mfa/reset/`),
  approveUser: (data) => api.post(`/auth/users/approve/`, data),
}

export const alertsAPI = {
  list:    (params)     => api.get('/alerts/',         { params }),
  detail:  (id)         => api.get(`/alerts/${id}/`),
  update:  (id, data)   => api.patch(`/alerts/${id}/`, data),
  analyze: (payload)    => api.post('/alerts/analyze/', payload),
  stats:   ()           => api.get('/alerts/stats/'),
  campaigns: (params)   => api.get('/alerts/campaigns/', { params }),
}

export const incidentsAPI = {
  list:   (params)    => api.get('/incidents/',         { params }),
  detail: (id)        => api.get(`/incidents/${id}/`),
  create: (data)      => api.post('/incidents/',        data),
  update: (id, data)  => api.patch(`/incidents/${id}/`, data),
}

export const threatIntelAPI = {
  iocs:   (params)  => api.get('/threat-intel/iocs/',  { params }),
  check:  (data)    => api.post('/threat-intel/check/', data),
  stats:  ()        => api.get('/threat-intel/stats/'),
  addIOC: (data)    => api.post('/threat-intel/iocs/',  data),
}

export const reportsAPI = {
  options:  (period)                  => api.get('/alerts/report/options/', { params: { period } }),
  preview:  (period, offset)          => api.get('/alerts/report/preview/', { params: { period, offset } }),
  // responseType 'blob' para recibir el archivo binario (PDF o CSV)
  download: (period, offset, exportType) => api.get('/alerts/report/', {
    params: { period, offset, export: exportType },
    responseType: 'blob',
    timeout: 60000,
  }),
}

export const auditAPI = {
  list: (params) => api.get('/audit/', { params }),
}

export default api
