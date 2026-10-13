/**
 * Sentryx — Tests de la página de reentrenamiento.
 * Verifica que el historial muestre el origen de cada job.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/mswServer'
import { renderWithProviders, setAuthTokens } from '../../test/testUtils'
import RetrainingPage from '../RetrainingPage'

const job = (id, trigger, extra = {}) => ({
  id, status: 'completed', trigger, triggered_by_name: trigger === 'scheduled' ? null : 'admin',
  metrics_before: {}, metrics_after: {}, samples_used: 5, samples_total: 2000,
  improvement: null, triggered_at: '2026-10-01T08:00:00Z', completed_at: '2026-10-01T08:01:00Z',
  duration_seconds: 60, error_log: '', ...extra,
})

describe('RetrainingPage', () => {
  beforeEach(() => {
    setAuthTokens()
    server.use(
      http.get('/api/v1/ml/feedback/stats/', () => HttpResponse.json({
        total_pending: 2, total_used: 10, by_type: {}, last_job: null,
        can_retrain: false, min_samples_needed: 5,
      })),
      http.get('/api/v1/ml/retrain/status/', () => HttpResponse.json(job('j1', 'scheduled'))),
      http.get('/api/v1/ml/retrain/history/', () => HttpResponse.json({
        count: 3, results: [job('j1', 'scheduled'), job('j2', 'feedback'), job('j3', 'manual')],
      })),
    )
  })

  it('muestra el origen de cada reentrenamiento en el historial', async () => {
    renderWithProviders(<RetrainingPage />)
    // Con un job completado la página recarga estadísticas e historial:
    // esperar con waitFor y no con findBy, que puede devolver un nodo desmontado.
    await waitFor(() => {
      // "Programado" aparece en el último job y en el historial
      expect(screen.getAllByText('Programado').length).toBeGreaterThanOrEqual(2)
      expect(screen.getByText('Por falso positivo')).toBeInTheDocument()
      expect(screen.getByText('Manual')).toBeInTheDocument()
    })
  })

  it('explica que el reentrenamiento mensual espera el mínimo de correcciones', async () => {
    renderWithProviders(<RetrainingPage />)
    await waitFor(() =>
      expect(screen.getByText(/reentrenamiento mensual programado/i)).toBeInTheDocument())
  })
})
