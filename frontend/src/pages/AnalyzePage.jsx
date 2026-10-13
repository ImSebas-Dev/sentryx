/**
 * Sentryx v2 — Página de análisis manual de correos.
 * Móvil: formulario arriba y resultado debajo.
 * Desktop (≥ lg): formulario y resultado lado a lado.
 */
import { useState, useCallback, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  FileSearch, Send, RotateCcw, Link2, Sparkles, ShieldCheck,
  AlertTriangle, ChevronRight, Timer,
} from 'lucide-react'
import { clsx } from 'clsx'
import { alertsAPI } from '../services/api'
import { useSubmit } from '../hooks/useFetch'
import {
  TypeBadge, MitreBadge, ScoreBar, ScoreGauge, ErrorBanner, Spinner,
  PageHeader, Section, tone, scoreTone,
} from '../components/UI'

const EMPTY_FORM = { from: '', to: '', subject: '', auth: '', body: '' }

// Ejemplo para demostraciones: BEC con autenticación fallida y URL por IP
const SAMPLE_EMAIL = {
  from:    'Gerencia Financiera <cfo@empresa-pagos.tk>',
  to:      'tesoreria@empresa.co',
  subject: 'URGENTE: transferencia pendiente antes de las 3 p. m.',
  auth:    'spf=fail dkim=none dmarc=fail',
  body:    'Hola,\n\nNecesito que proceses hoy mismo una transferencia a un proveedor nuevo. ' +
           'Es confidencial, no lo comentes con nadie. Confirma los datos bancarios aquí: ' +
           'http://192.168.10.45/verificar-cuenta\n\nGracias,\nDirector Financiero',
}

function resultLabel(score) {
  if (score >= 85) return 'CRÍTICO — Phishing confirmado'
  if (score >= 70) return 'Phishing detectado'
  if (score >= 40) return 'Sospechoso'
  return 'Legítimo'
}

// Muestra el resultado del análisis con el score y el desglose por capa
function AnalysisResult({ result }) {
  if (!result) return null
  const score = result.risk_score
  const t     = tone(scoreTone(score))

  return (
    <section className="card overflow-hidden animate-slide-up" aria-live="polite" aria-label="Resultado del análisis">
      {/* Franja de color según el nivel de riesgo */}
      <div className={clsx('h-1', t.solid)} aria-hidden="true" />

      <div className="p-5 sm:p-6 space-y-6">
        <div className="flex flex-col sm:flex-row items-center gap-5">
          <ScoreGauge score={score} size={120} />
          <div className="text-center sm:text-left space-y-2">
            <p className={clsx('text-subtitle font-semibold', t.text)}>{resultLabel(score)}</p>
            <div className="flex flex-wrap justify-center sm:justify-start gap-1.5">
              {/* En un correo legítimo el título ya lo dice y no hay técnica de ataque */}
              {result.classification !== 'legitimate' && <>
                <TypeBadge type={result.phishing_type} />
                <MitreBadge technique={result.mitre_technique} />
              </>}
            </div>
          </div>
        </div>

        <div className="space-y-3.5">
          <h3 className="text-overline">Desglose por capa</h3>
          {[
            { label: 'Encabezados', weight: '35%', val: result.scores_by_layer?.headers },
            { label: 'Contenido',   weight: '40%', val: result.scores_by_layer?.content },
            { label: 'URLs',        weight: '25%', val: result.scores_by_layer?.urls },
          ].map(({ label, weight, val }) => (
            <div key={label}>
              <p className="text-body text-fg-2 mb-1.5">
                {label} <span className="text-fg-3 text-caption">({weight})</span>
              </p>
              <ScoreBar score={val || 0} />
            </div>
          ))}
        </div>

        {result.urls_analyzed?.length > 0 && (
          <div>
            <h3 className="text-overline mb-2.5">
              URLs analizadas ({result.url_count} encontradas)
            </h3>
            <ul className="space-y-1.5">
              {result.urls_analyzed.map((u, i) => (
                <li key={i} className="well flex items-center gap-2.5 px-3 py-2">
                  <Link2 className="h-3.5 w-3.5 text-fg-3 flex-shrink-0" aria-hidden="true" />
                  <span className="text-caption font-mono text-fg-2 flex-1 truncate min-w-0">
                    {u.url_truncated || u.url}
                  </span>
                  <span className={clsx('badge font-mono', tone(scoreTone(u.score)).badge)}>
                    {Math.round(u.score)}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}

        <p className="flex items-center justify-end gap-1.5 text-caption text-fg-4">
          <Timer className="h-3.5 w-3.5" aria-hidden="true" />
          Inferencia: {result.inference_ms?.toFixed(0)} ms
        </p>
      </div>
    </section>
  )
}

export default function AnalyzePage() {
  const navigate  = useNavigate()
  const resultRef = useRef(null)
  const [form, setForm]     = useState(EMPTY_FORM)
  const [result, setResult] = useState(null)

  const doAnalyze = useCallback(async () => {
    const payload = {
      headers: {
        from_addr:              form.from,
        to_addr:                form.to,
        subject:                form.subject,
        authentication_results: form.auth,
      },
      body_text: form.body,
    }
    return alertsAPI.analyze(payload)
  }, [form])

  const { submit, submitting, error, setError } = useSubmit(doAnalyze)

  // En móvil el resultado queda debajo del formulario:
  // desplazar la vista hasta él cuando llegue o mientras carga
  useEffect(() => {
    if ((result || submitting) && window.innerWidth < 1024) {
      resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [result, submitting])

  const handleSubmit = async e => {
    e.preventDefault()
    setResult(null)
    try {
      const res = await submit()
      setResult(res.data)
    } catch { /* useSubmit ya expone el error */ }
  }

  const handleReset = () => {
    setForm(EMPTY_FORM)
    setResult(null)
    setError(null)
  }

  const update = key => e => setForm(f => ({ ...f, [key]: e.target.value }))

  return (
    <div className="page">
      <PageHeader
        icon={FileSearch}
        title="Analizar correo"
        description="Pega los datos del correo para analizarlo con el ensemble de tres modelos. Los datos no se almacenan en texto plano."
        actions={
          <button type="button" onClick={() => { setForm(SAMPLE_EMAIL); setResult(null) }}
                  className="btn-secondary">
            <Sparkles className="h-4 w-4" aria-hidden="true" />
            Cargar ejemplo
          </button>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6 items-start">

        {/* Formulario */}
        <form onSubmit={handleSubmit} className="space-y-4 sm:space-y-5">
          <ErrorBanner message={error} onDismiss={() => setError(null)} />

          <Section title="Encabezados" description="Opcionales, pero mejoran la precisión">
            <div className="space-y-4">
              <div>
                <label htmlFor="f-from" className="field-label">Remitente (From)</label>
                <input id="f-from" type="text" inputMode="email" autoComplete="off"
                  autoCapitalize="none" className="input"
                  placeholder="soporte@banco-seguro.tk"
                  value={form.from} onChange={update('from')} />
              </div>
              <div>
                <label htmlFor="f-to" className="field-label">Destinatario (To)</label>
                <input id="f-to" type="text" inputMode="email" autoComplete="off"
                  autoCapitalize="none" className="input"
                  placeholder="tesoreria@empresa.co"
                  value={form.to} onChange={update('to')} />
              </div>
              <div>
                <label htmlFor="f-subject" className="field-label">Asunto (Subject)</label>
                <input id="f-subject" className="input"
                  placeholder="URGENTE: Verifica tu cuenta"
                  value={form.subject} onChange={update('subject')} />
              </div>
              <div>
                <label htmlFor="f-auth" className="field-label">Authentication-Results</label>
                <input id="f-auth" autoCapitalize="none" autoComplete="off"
                  className="input font-mono text-caption"
                  placeholder="spf=fail dkim=none dmarc=fail"
                  value={form.auth} onChange={update('auth')}
                  aria-describedby="f-auth-hint" />
                <p id="f-auth-hint" className="field-hint">
                  Resultado de SPF, DKIM y DMARC que aparece en los encabezados del correo.
                </p>
              </div>
            </div>
          </Section>

          <Section title="Cuerpo del correo">
            <label htmlFor="f-body" className="field-label">
              Contenido <span className="text-red-fg" aria-hidden="true">*</span>
              <span className="sr-only">(obligatorio)</span>
            </label>
            <textarea id="f-body" required rows={9}
              className="input resize-y font-mono text-caption min-h-[180px]"
              placeholder="Pega aquí el cuerpo del correo (texto plano o HTML)…"
              value={form.body} onChange={update('body')} />
            <p className="field-hint text-right tabular-nums">{form.body.length.toLocaleString('es-CO')} caracteres</p>
          </Section>

          <div className="flex gap-2">
            <button type="submit" disabled={submitting || !form.body.trim()}
              className="btn-primary btn-lg flex-1">
              {submitting
                ? <><Spinner size="sm" inverted /> Analizando…</>
                : <><Send className="h-4 w-4" aria-hidden="true" /> Analizar correo</>}
            </button>
            <button type="button" onClick={handleReset}
              className="btn-secondary btn-lg"
              aria-label="Limpiar formulario">
              <RotateCcw className="h-4 w-4" aria-hidden="true" />
              <span className="hidden sm:inline">Limpiar</span>
            </button>
          </div>
        </form>

        {/* Resultado */}
        <div ref={resultRef} className="space-y-4 scroll-mt-4 lg:sticky lg:top-6">
          {!result && !submitting && (
            <div className="rounded-lg border-2 border-dashed border-stroke-strong/70 p-8 sm:p-10
                            flex flex-col items-center justify-center text-center min-h-[260px]">
              <div className="h-14 w-14 rounded-full bg-fg/[0.05] flex items-center justify-center mb-4">
                <FileSearch className="h-7 w-7 text-fg-3" strokeWidth={1.5} aria-hidden="true" />
              </div>
              <p className="text-subtitle2 font-semibold text-fg">El resultado del análisis aparecerá aquí</p>
              <p className="text-fg-3 text-body mt-1 max-w-xs">
                Completa el formulario y pulsa «Analizar correo», o carga el ejemplo.
              </p>
            </div>
          )}

          {submitting && (
            <div className="card p-8 sm:p-10 flex flex-col items-center justify-center min-h-[260px]">
              <Spinner size="lg" className="mb-4" />
              <p className="text-subtitle2 font-semibold text-fg">Consultando el motor ML…</p>
              <p className="text-fg-3 text-body mt-1">Analizando encabezados, contenido y URLs</p>
            </div>
          )}

          {result && <AnalysisResult result={result} />}

          {result?.alert_created && result?.alert_id && (
            <button
              onClick={() => navigate(`/alerts/${result.alert_id}`)}
              className="w-full card-interactive p-4 flex items-center gap-3 text-left group
                         border-orange-line bg-orange-tint">
              <AlertTriangle className="h-5 w-5 text-orange-fg flex-shrink-0" aria-hidden="true" />
              <div className="min-w-0 flex-1">
                <p className="text-body font-semibold text-fg">Alerta creada automáticamente</p>
                <p className="text-caption text-fg-2 mt-0.5">Ver los detalles completos de la alerta</p>
              </div>
              <ChevronRight className="h-5 w-5 text-fg-3 group-hover:text-fg group-hover:translate-x-0.5
                                       transition-transform flex-shrink-0" aria-hidden="true" />
            </button>
          )}

          {result && !result.alert_created && result.classification === 'legitimate' && (
            <div className="rounded-lg border border-green-line bg-green-tint p-4 flex gap-3 animate-fade-in">
              <ShieldCheck className="h-5 w-5 text-green-fg flex-shrink-0" aria-hidden="true" />
              <div>
                <p className="text-body font-semibold text-fg">Correo legítimo</p>
                <p className="text-caption text-fg-2 mt-0.5">
                  El score de {Math.round(result.risk_score)}/100 está por debajo del umbral.
                  No se creó ninguna alerta.
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
