/**
 * Sentryx — Tests de los hooks useFetch, usePolling y useSubmit.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/mswServer'
import { useFetch, usePolling, useSubmit } from '../useFetch'
import { alertsAPI } from '../../services/api'

// Helper que usa la API real (interceptada por MSW)
const fetchStats = () => alertsAPI.stats()

describe('useFetch', () => {
  beforeEach(() => {
    localStorage.setItem('access_token', 'test-token')
  })

  it('inicia con loading=true y data=null', () => {
    const { result } = renderHook(() => useFetch(fetchStats))
    expect(result.current.loading).toBe(true)
    expect(result.current.data).toBeNull()
    expect(result.current.error).toBeNull()
  })

  it('carga datos correctamente cuando la petición tiene éxito', async () => {
    const { result } = renderHook(() => useFetch(fetchStats))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data).toBeTruthy()
    expect(result.current.data.total).toBe(42)
    expect(result.current.error).toBeNull()
  })

  it('captura error cuando la petición falla', async () => {
    server.use(
      http.get('/api/v1/alerts/stats/', () =>
        HttpResponse.json({ detail: 'Forbidden' }, { status: 403 })
      )
    )
    const { result } = renderHook(() => useFetch(fetchStats))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBeTruthy()
    expect(result.current.data).toBeNull()
  })

  it('permite refetch manual', async () => {
    let callCount = 0
    server.use(
      http.get('/api/v1/alerts/stats/', () => {
        callCount++
        return HttpResponse.json({ total: callCount * 10, critical: 0,
          week_total: 0, active_campaigns: 0, by_severity: {},
          by_type: {}, daily_last_7_days: [], false_positive_rate: 0, new: 0 })
      })
    )
    const { result } = renderHook(() => useFetch(fetchStats))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data.total).toBe(10)

    await act(async () => { result.current.refetch() })
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data.total).toBe(20)
    expect(callCount).toBe(2)
  })

  it('actualiza datos cuando cambian las dependencias', async () => {
    let id = 'alert-uuid-001'
    const fetchAlert = () => alertsAPI.detail(id)

    const { result, rerender } = renderHook(() => useFetch(fetchAlert, [id]))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data.id).toBe('alert-uuid-001')

    id = 'alert-uuid-002'
    rerender()
    await waitFor(() => {
      expect(result.current.data?.id).toBe('alert-uuid-002')
    })
  })
})

describe('usePolling', () => {
  beforeEach(() => {
    localStorage.setItem('access_token', 'test-token')
  })

  it('carga datos en el primer render igual que useFetch', async () => {
    const { result } = renderHook(() => usePolling(fetchStats, 30000))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data).toBeTruthy()
    expect(result.current.data.total).toBe(42)
  })

  it('expone función refetch', async () => {
    const { result } = renderHook(() => usePolling(fetchStats, 30000))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(typeof result.current.refetch).toBe('function')
  })
})

describe('useSubmit', () => {
  beforeEach(() => {
    localStorage.setItem('access_token', 'test-token')
  })

  it('inicia sin error ni success', () => {
    const { result } = renderHook(() =>
      useSubmit(() => alertsAPI.analyze({ body_text: 'test' }))
    )
    expect(result.current.submitting).toBe(false)
    expect(result.current.error).toBeNull()
    expect(result.current.success).toBe(false)
  })

  it('marca success tras submit exitoso', async () => {
    const { result } = renderHook(() =>
      useSubmit(() => alertsAPI.analyze({ body_text: 'test' }))
    )
    await act(async () => { await result.current.submit() })
    expect(result.current.success).toBe(true)
    expect(result.current.error).toBeNull()
    expect(result.current.submitting).toBe(false)
  })

  it('captura mensaje de error en formato string', async () => {
    server.use(
      http.post('/api/v1/alerts/analyze/', () =>
        HttpResponse.json({ error: 'ML Engine no disponible.' }, { status: 503 })
      )
    )
    const { result } = renderHook(() =>
      useSubmit(() => alertsAPI.analyze({ body_text: 'test' }))
    )
    await act(async () => {
      try { await result.current.submit() } catch { /* esperado */ }
    })
    expect(result.current.error).toBeTruthy()
    expect(result.current.success).toBe(false)
  })

  it('submitting cambia a false después de completar', async () => {
    const { result } = renderHook(() =>
      useSubmit(() => alertsAPI.analyze({ body_text: 'test' }))
    )
    await act(async () => { await result.current.submit() })
    // Después de completar, submitting=false y success=true
    expect(result.current.submitting).toBe(false)
    expect(result.current.success).toBe(true)
  })
})
