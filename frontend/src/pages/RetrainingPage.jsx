/**
 * Sentryx v2 — Página de reentrenamiento activo (responsive).
 * Permite al admin disparar el reentrenamiento del modelo ML
 * con las correcciones acumuladas por los analistas.
 */
import { useState, useEffect } from 'react'
import { useAuth } from '../store/AuthContext'
import { useFetch, usePolling } from '../hooks/useFetch'
import {
  ErrorBanner, LoadingScreen, Spinner, PageHeader, Section, MessageBar, tone,
} from '../components/UI'
import {
  Brain, CheckCircle2, XCircle, Clock, RefreshCw, ArrowRight, Timer, Lock,
  CalendarClock, UserRound, Flag,
} from 'lucide-react'
import { clsx } from 'clsx'
import api from '../services/api'
import { format } from 'date-fns'
import { es } from 'date-fns/locale'

// ── Llamadas a la API ─────────────────────────────────────────────
const mlAPI = {
  feedbackStats: () => api.get('/ml/feedback/stats/'),
  retrainStatus: () => api.get('/ml/retrain/status/'),
  retrainHistory:() => api.get('/ml/retrain/history/'),
  triggerRetrain:() => api.post('/ml/retrain/'),
}

// ── Helpers ───────────────────────────────────────────────
const statusConfig = {
  pending:   { label: 'En cola',    tone: 'yellow', icon: Clock },
  running:   { label: 'Ejecutando', tone: 'blue',   icon: null },
  completed: { label: 'Completado', tone: 'green',  icon: CheckCircle2 },
  failed:    { label: 'Falló',      tone: 'red',    icon: XCircle },
}

// Origen del job. Mantener sincronizado con RetrainingJob.Trigger del backend
export const TRIGGER_LABELS = {
  scheduled: { label: 'Programado',         icon: CalendarClock },
  feedback:  { label: 'Por falso positivo', icon: Flag },
  manual:    { label: 'Manual',             icon: UserRound },
}

const correctionLabels = {
  false_positive:    'Falsos positivos',
  false_negative:    'Falsos negativos',
  wrong_type:        'Tipo incorrecto',
  confirmed_phishing:'Phishing confirmado',
}

const MODEL_LABELS = { headers_rf_v1: 'Encabezados', content_svm_v1: 'Contenido', url_rf_v1: 'URLs' }

const STEPS = [
  'Un analista revisa una alerta y detecta que el sistema la clasificó mal.',
  'Cambia el estado de la alerta a «Falso positivo» desde el detalle.',
  'El sistema guarda esa corrección como muestra de entrenamiento, sin datos personales.',
  'Cuando hay suficientes correcciones, un administrador pulsa «Reentrenar».',
  'El motor ML reentrena los tres modelos en segundo plano y valida sus métricas.',
  'Los nuevos modelos se cargan automáticamente, sin reiniciar el servicio.',
  'Además, el día 1 de cada mes a las 03:00 el sistema reentrena solo si hay suficientes correcciones y no hay otro reentrenamiento en curso.',
]

function MetricDelta({ before, after, label }) {
  if (!before || !after) return null
  const delta = after - before
  const up    = delta > 0
  const eq    = delta === 0
  return (
    <div className="well px-3 py-2.5">
      <p className="text-caption text-fg-3 mb-1">{label}</p>
      <div className="flex items-center gap-1.5 font-mono text-caption">
        <span className="text-fg-3">{before.toFixed(4)}</span>
        <ArrowRight className="h-3 w-3 text-fg-4" aria-hidden="true" />
        <span className={clsx('font-semibold', up ? 'text-green-fg' : eq ? 'text-fg' : 'text-red-fg')}>
          {after.toFixed(4)}
        </span>
      </div>
    </div>
  )
}

function JobCard({ job, compact = false }) {
  if (!job) return null
  const cfg = statusConfig[job.status] || statusConfig.pending
  const t   = tone(cfg.tone)
  const Icon = cfg.icon
  const trig = TRIGGER_LABELS[job.trigger] || TRIGGER_LABELS.manual
  const TrigIcon = trig.icon

  const beforeF1 = job.metrics_before?.f1 || 0
  const afterF1  = job.metrics_after?.f1  || 0
  const improvementTone = job.improvement > 0 ? 'text-green-fg' : job.improvement < 0 ? 'text-red-fg' : 'text-fg'

  return (
    <div className={clsx('card overflow-hidden', !compact && 'shadow-4')}>
      <div className={clsx('h-1', t.solid)} aria-hidden="true" />
      <div className="p-4 sm:p-5">
        <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 mb-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className={clsx('badge h-6 px-2.5', t.badge)}>
              {job.status === 'running'
                ? <Spinner size="sm" className="h-3 w-3 border-[1.5px]" />
                : Icon && <Icon className="h-3.5 w-3.5" aria-hidden="true" />}
              {cfg.label}
            </span>
            <span className="badge h-6 px-2.5 bg-fg/5 text-fg-2 ring-1 ring-stroke"
                  title={job.triggered_by_name ? `Iniciado por ${job.triggered_by_name}` : 'Iniciado por el sistema'}>
              <TrigIcon className="h-3.5 w-3.5" aria-hidden="true" />
              <span className="sr-only">Origen: </span>{trig.label}
            </span>
          </div>
          <span className="text-caption text-fg-3 tabular-nums">
            {format(new Date(job.triggered_at), "d MMM yyyy · HH:mm", { locale: es })}
          </span>
        </div>

        <dl className="grid grid-cols-3 gap-3">
          <div>
            <dt className="text-caption text-fg-3">Correcciones</dt>
            <dd className="text-subtitle font-semibold text-fg tabular-nums">{job.samples_used}</dd>
          </div>
          <div>
            <dt className="text-caption text-fg-3">Total muestras</dt>
            <dd className="text-subtitle font-semibold text-fg tabular-nums">{job.samples_total || '—'}</dd>
          </div>
          <div>
            <dt className="text-caption text-fg-3">Mejora F1</dt>
            <dd className={clsx('text-subtitle font-semibold tabular-nums', improvementTone)}>
              {job.improvement != null
                ? `${job.improvement > 0 ? '+' : ''}${(job.improvement * 100).toFixed(2)}%`
                : '—'}
            </dd>
          </div>
        </dl>

        {job.status === 'completed' && beforeF1 > 0 && afterF1 > 0 && (
          <div className="mt-4 pt-4 border-t border-stroke">
            <p className="text-overline mb-2">F1 por modelo</p>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              {Object.keys(MODEL_LABELS).map(model => (
                <MetricDelta key={model} label={MODEL_LABELS[model]}
                             before={job.metrics_before?.[model]?.f1}
                             after={job.metrics_after?.[model]?.f1} />
              ))}
            </div>
          </div>
        )}

        {job.status === 'failed' && job.error_log && (
          <pre className="mt-4 p-3 rounded-md bg-red-tint border border-red-line text-caption text-red-fg
                          font-mono whitespace-pre-wrap break-all max-h-32 overflow-y-auto">
            {job.error_log.slice(0, 400)}
          </pre>
        )}

        {job.duration_seconds != null && (
          <p className="flex items-center justify-end gap-1 text-caption text-fg-4 mt-3">
            <Timer className="h-3.5 w-3.5" aria-hidden="true" />
            Duración: {job.duration_seconds}s
          </p>
        )}
      </div>
    </div>
  )
}

// ── Página principal ──────────────────────────────────────
export default function RetrainingPage() {
  const { isAdmin } = useAuth()
  const [triggering, setTriggering] = useState(false)
  const [triggerError, setTriggerError] = useState(null)
  const [triggerSuccess, setTriggerSuccess] = useState(null)
  const [isRetraining, setIsRetraining] = useState(false)

  // Stats de feedback
  const { data: stats, loading: statsLoading, refetch: refetchStats } =
    useFetch(() => mlAPI.feedbackStats())

  // Historial de jobs
  const { data: history, refetch: refetchHistory } =
    useFetch(() => mlAPI.retrainHistory())

  // Polling del job activo cuando está corriendo
  const { data: currentJob } = usePolling(
    () => mlAPI.retrainStatus(),
    isRetraining ? 3000 : 30000   // cada 3s si está corriendo, 30s si no
  )

  // Detectar si hay un job corriendo. Depende también del id: si el job
  // anterior ya había fallado y el nuevo también falla, el status no cambia
  // y isRetraining quedaría en true (polling cada 3 s → 429 del throttle).
  useEffect(() => {
    const running = currentJob?.status === 'running' || currentJob?.status === 'pending'
    setIsRetraining(!!running)
    if (currentJob?.status === 'completed' || currentJob?.status === 'failed') {
      // Recarga silenciosa: sin el true la página entera vuelve a la pantalla de carga
      refetchStats(true)
      refetchHistory(true)
    }
  }, [currentJob?.id, currentJob?.status])

  const handleRetrain = async () => {
    setTriggering(true)
    setTriggerError(null)
    setTriggerSuccess(null)
    try {
      const res = await mlAPI.triggerRetrain()
      setTriggerSuccess(
        `Reentrenamiento iniciado con ${res.data.pending_feedback} correcciones. ` +
        `Suele tardar menos de un minuto.`
      )
      setIsRetraining(true)
      refetchStats()
      refetchHistory()
    } catch (err) {
      setTriggerError(
        err.response?.data?.error ||
        err.response?.data?.detail ||
        'Error al iniciar el reentrenamiento.'
      )
    } finally {
      setTriggering(false)
    }
  }

  if (statsLoading) return <LoadingScreen />

  const pending      = stats?.total_pending       || 0
  const used         = stats?.total_used          || 0
  const canRetrain   = stats?.can_retrain         || false
  const minNeeded    = stats?.min_samples_needed  || 5
  const byType       = stats?.by_type             || {}
  const jobs         = history?.results || history || []
  const progress     = Math.min(pending / minNeeded, 1)

  return (
    <div className="page">
      <PageHeader
        icon={Brain}
        title="Reentrenamiento del modelo"
        description="Mejora la detección con las correcciones que marcan los analistas."
        actions={
          <button onClick={() => { refetchStats(); refetchHistory() }}
            className="btn-secondary" aria-label="Actualizar datos">
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            <span className="hidden sm:inline">Actualizar</span>
          </button>
        }
      />

      <ErrorBanner message={triggerError} onDismiss={() => setTriggerError(null)} />
      {triggerSuccess && (
        <MessageBar intent="success" onDismiss={() => setTriggerSuccess(null)}>{triggerSuccess}</MessageBar>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4 sm:gap-5 items-start">
        <div className="lg:col-span-3 space-y-4 sm:space-y-5">

          {/* Correcciones acumuladas */}
          <Section title="Correcciones acumuladas"
                   description="Cada alerta marcada como «Falso positivo» añade una muestra.">
            <div className="grid grid-cols-2 gap-3 mb-5">
              <div className="well p-4">
                <p className="text-caption text-fg-3">Pendientes</p>
                <p className={clsx('text-title2 font-semibold tabular-nums',
                                   pending >= minNeeded ? 'text-brand-fg' : 'text-fg')}>
                  {pending}
                </p>
              </div>
              <div className="well p-4">
                <p className="text-caption text-fg-3">Usadas en entrenamientos previos</p>
                <p className="text-title2 font-semibold text-fg tabular-nums">{used}</p>
              </div>
            </div>

            {/* Progreso hacia el mínimo necesario */}
            <div className="mb-5">
              <div className="flex justify-between text-caption mb-1.5">
                <span className="text-fg-2 font-semibold">Mínimo para reentrenar</span>
                <span className="text-fg-3 tabular-nums">{Math.min(pending, minNeeded)} / {minNeeded}</span>
              </div>
              <div className="h-2 bg-fg/10 rounded-full overflow-hidden"
                   role="progressbar" aria-valuemin={0} aria-valuemax={minNeeded}
                   aria-valuenow={Math.min(pending, minNeeded)} aria-label="Correcciones reunidas">
                <div className={clsx('h-full rounded-full transition-[width] duration-700 ease-decelerate',
                                     canRetrain ? 'bg-green-solid' : 'bg-brand-fg')}
                     style={{ width: `${progress * 100}%` }} />
              </div>
            </div>

            {Object.keys(byType).length > 0 && (
              <div className="space-y-2.5 mb-5">
                <p className="text-overline">Por tipo de corrección</p>
                {Object.entries(byType).map(([type, count]) => (
                  <div key={type} className="flex items-center justify-between gap-3">
                    <span className="text-body text-fg-2 min-w-0 truncate">{correctionLabels[type] || type}</span>
                    <div className="flex items-center gap-3 flex-shrink-0">
                      <div className="w-20 sm:w-28 h-1.5 bg-fg/10 rounded-full overflow-hidden">
                        <div className="h-full bg-brand-fg rounded-full"
                             style={{ width: `${Math.min((count / (pending || 1)) * 100, 100)}%` }} />
                      </div>
                      <span className="text-fg font-mono font-semibold text-caption w-5 text-right tabular-nums">
                        {count}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {!canRetrain && (
              <MessageBar intent="warning" className="mb-5">
                Se necesitan al menos <strong>{minNeeded} correcciones</strong> para reentrenar.
                Tienes {pending}. Marca más alertas como «Falso positivo» desde el listado de alertas.
                El reentrenamiento mensual programado también espera a reunir este mínimo.
              </MessageBar>
            )}

            {isAdmin ? (
              <button onClick={handleRetrain}
                disabled={!canRetrain || triggering || isRetraining}
                className="btn-primary btn-lg w-full sm:w-auto">
                {triggering || isRetraining
                  ? <><Spinner size="sm" inverted /> {isRetraining ? 'Reentrenando…' : 'Iniciando…'}</>
                  : <><Brain className="h-4 w-4" aria-hidden="true" /> Reentrenar con {pending} correcciones</>}
              </button>
            ) : (
              <p className="flex items-center gap-2 text-body text-fg-3 well px-4 py-3">
                <Lock className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
                Solo los administradores pueden iniciar el reentrenamiento.
              </p>
            )}
          </Section>

          {/* Job actual */}
          {currentJob && currentJob.status !== 'no_jobs' && (
            <section aria-labelledby="current-job-title" className="space-y-2">
              <h2 id="current-job-title" className="text-section">Último reentrenamiento</h2>
              <JobCard job={currentJob} />
              {isRetraining && (
                <p className="text-caption text-brand-fg text-center animate-pulse" aria-live="polite">
                  Reentrenando… esta página se actualiza sola cada 3 segundos.
                </p>
              )}
            </section>
          )}
        </div>

        {/* Cómo funciona */}
        <Section title="¿Cómo funciona?" className="lg:col-span-2">
          <ol className="relative space-y-4">
            {STEPS.map((text, i) => (
              <li key={i} className="flex gap-3 items-start">
                <span className="relative flex-shrink-0 h-6 w-6 rounded-full bg-brand-tint text-brand-fg
                                 ring-1 ring-brand-line text-caption font-semibold flex items-center justify-center">
                  {i + 1}
                </span>
                <p className="text-body text-fg-2 leading-relaxed pt-0.5">{text}</p>
              </li>
            ))}
          </ol>
        </Section>
      </div>

      {/* Historial */}
      {jobs.length > 1 && (
        <section aria-labelledby="history-title" className="space-y-3">
          <h2 id="history-title" className="text-section">Historial de reentrenamientos</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 sm:gap-4">
            {jobs.slice(0, 6).map(job => <JobCard key={job.id} job={job} compact />)}
          </div>
        </section>
      )}
    </div>
  )
}
