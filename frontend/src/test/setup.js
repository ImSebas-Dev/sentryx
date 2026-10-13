/**
 * Sentryx — Setup global de Vitest
 */
import '@testing-library/jest-dom'
import { cleanup } from '@testing-library/react'
import { afterEach, beforeAll, afterAll, vi } from 'vitest'
import { server } from './mswServer'

// ── Polyfills para jsdom ──────────────────────────────────

global.ResizeObserver = class ResizeObserver {
  observe()   {}
  unobserve() {}
  disconnect(){}
}

window.SVGElement.prototype.getTotalLength = () => 0

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation(query => ({
    matches: false, media: query, onchange: null,
    addListener: vi.fn(), removeListener: vi.fn(),
    addEventListener: vi.fn(), removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
})

// Base URL para Axios — CRÍTICO: sin esto /api/v1/... da ERR_INVALID_URL
// Axios 1.x usa XMLHttpRequest en jsdom; el interceptor MSW necesita URL absoluta
Object.defineProperty(window, 'location', {
  writable: true,
  configurable: true,
  value: {
    origin:   'http://localhost',
    href:     'http://localhost/',
    protocol: 'http:',
    host:     'localhost',
    hostname: 'localhost',
    port:     '',
    pathname: '/',
    search:   '',
    hash:     '',
    assign:   vi.fn(),
    replace:  vi.fn(),
    reload:   vi.fn(),
  },
})

// No mockear services/api: con window.location.origin simulado arriba, el
// módulo real arma URLs absolutas y MSW las intercepta. Así las pruebas
// cubren los interceptores reales (refresh, 2FA) en vez de una copia.

// MSW lifecycle
beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }))
afterEach(() => {
  server.resetHandlers()
  cleanup()
  // El interceptor de api.js redirige con location.href = '/login'; restaurar
  // la URL absoluta o MSW no podrá resolver las peticiones de la siguiente prueba.
  window.location.href = 'http://localhost/'
  window.location.pathname = '/'
})
afterAll(() => server.close())

// Silenciar warnings de React/Router
vi.spyOn(console, 'error').mockImplementation((msg, ...args) => {
  if (typeof msg === 'string' && (
    msg.includes('Warning:') || msg.includes('act(') ||
    msg.includes('ReactDOM.render')
  )) return
})
vi.spyOn(console, 'warn').mockImplementation((msg) => {
  if (typeof msg === 'string' && msg.includes('Future Flag')) return
})

// localStorage mock
const localStorageMock = (() => {
  let store = {}
  return {
    getItem:    (k)    => store[k] ?? null,
    setItem:    (k, v) => { store[k] = String(v) },
    removeItem: (k)    => { delete store[k] },
    clear:      ()     => { store = {} },
    get length() { return Object.keys(store).length },
    key: (i) => Object.keys(store)[i] ?? null,
  }
})()
Object.defineProperty(window, 'localStorage', { value: localStorageMock })
