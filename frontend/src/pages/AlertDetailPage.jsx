import { useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  ArrowLeft, User, Link2, LockKeyhole, CheckCircle2, XCircle,
  CalendarClock, Save,
} from 'lucide-react'
import { clsx } from 'clsx'
import { alertsAPI } from '../services/api'
import { useFetch, useSubmit } from '../hooks/useFetch'
import { useAuth } from '../store/AuthContext'
import {
  SeverityBadge, TypeBadge, StatusBadge, MitreBadge,
  ScoreBar, ScoreGauge, LoadingScreen, ErrorBanner, Section, Spinner,
  tone, scoreTone,
} from '../components/UI'
import { format } from 'date-fns'
import { es } from 'date-fns/locale'

const STATUS_OPTIONS = [
  { value: 'new',          label: 'Nueva' },
  { value: 'acknowledged', label: 'En revisión' },
  { value: 'resolved',     label: 'Resuelta' },
  { value: 'false_pos',    label: 'Falso positivo' },
]

const CLASSIFICATION_LABELS = {
  legitimate: 'Legítimo', suspicious: 'Sospechoso', phishing: 'Phishing', critical: 'Phishing crítico',
}

function LayerScore({ label, hint, score, weight }) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 mb-1.5">
        <p className="text-body text-fg font-medium">
          {label} <span className="text-fg-3 font-normal hidden sm:inline">· {hint}</span>
        </p>
        <span className="text-caption text-fg-3 whitespace-nowrap">peso {Math.round(weight * 100)}%</span>
      </div>
      <ScoreBar score={score} />
    </div>
  )
}

// Fila de feature: booleanos como Sí/No con icono; resto como valor
function FeatureRow({ label, value, highlight }) {
  const isBool  = typeof value === 'boolean' || value === 0 || value === 1
  const yes     = value === true || value === 1
  return (
    <div className="flex items-center justify-between gap-3 py-2.5 border-b border-stroke last:border-0">
      <span className="text-body text-fg-2">{label}</span>
      {isBool ? (
        <span className={clsx('inline-flex items-center gap-1.5 text-caption font-semibold',
                              highlight ? 'text-orange-fg' : 'text-fg-2')}>
          {yes
            ? <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
            : <XCircle className="h-4 w-4" aria-hidden="true" />}
          {yes ? 'Sí' : 'No'}
        </span>
      ) : (
        <span className={clsx('text-caption font-mono font-semibold',
                              highlight ? 'text-orange-fg' : 'text-fg-2')}>{String(value)}</span>
      )}
    </div>
  )
}

function MetaRow({ label, children }) {
  return (
    <div className="flex items-center justify-between gap-3 py-2 border-b border-stroke last:border-0">
      <dt className="text-body text-fg-3 flex-shrink-0">{label}</dt>
      <dd className="text-body text-fg text-right min-w-0 truncate">{children}</dd>
    </div>
  )
}

export default function AlertDetailPage() {
  const { id }        = useParams()
  const navigate      = useNavigate()
  const { isAnalyst } = useAuth()

  const fetchAlert = useCallback(() => alertsAPI.detail(id), [id])
  const { data: alert, loading, error, refetch } = useFetch(fetchAlert, [id])

  const { submit: updateAlert, submitting } = useSubmit(
    useCallback((data) => alertsAPI.update(id, data), [id])
  )
  const [newStatus, setNewStatus] = useState('')

  if (loading) return <LoadingScreen />
  if (error)   return <div className="page"><ErrorBanner message={error} /></div>
  if (!alert)  return null

  const handleStatusChange = async () => {
    if (!newStatus) return
    await updateAlert({ status: newStatus })
    refetch()
    setNewStatus('')
  }

  const headerFeatures = alert.ml_features?.headers || {}
  const scores         = alert.scores_by_layer || {}
  const riskTone       = tone(scoreTone(alert.risk_score))

  return (
    <div className="page">

      {/* Encabezado */}
      <div className="space-y-3">
        <button onClick={() => navigate('/alerts')} className="btn-ghost -ml-2 text-fg-2">
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          Volver a alertas
        </button>
        <div>
          <div className="flex flex-wrap gap-1.5 mb-2">
            <SeverityBadge severity={alert.severity} />
            <TypeBadge    type={alert.phishing_type} />
            <StatusBadge  status={alert.status} />
          </div>
          <h1 className="text-page-title leading-snug">{alert.title}</h1>
          <p className="text-fg-3 text-body mt-1">{alert.description}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-5 items-start">

        {/* Columna principal */}
        <div className="lg:col-span-2 space-y-4 sm:space-y-5">

          <Section title="Score del ensemble"
                   description="Combinación ponderada de los tres modelos de detección">
            <div className="flex flex-col sm:flex-row items-center gap-6 sm:gap-8">
              <div className="flex flex-col items-center gap-2">
                <ScoreGauge score={alert.risk_score} />
                <span className={clsx('badge', riskTone.badge)}>
                  {CLASSIFICATION_LABELS[alert.classification] || alert.classification || alert.phishing_type}
                </span>
              </div>
              <div className="flex-1 w-full space-y-4">
                <LayerScore label="Encabezados" hint="SPF, DKIM, typosquatting"
                  score={scores.headers || alert.score_headers || 0} weight={0.35} />
                <LayerScore label="Contenido" hint="texto, urgencia, patrones"
                  score={scores.content || alert.score_content || 0} weight={0.40} />
                <LayerScore label="URLs" hint="enlaces embebidos"
                  score={scores.urls || alert.score_urls || 0} weight={0.25} />
              </div>
            </div>
          </Section>

          {Object.keys(headerFeatures).length > 0 && (
            <Section title="Features de encabezados"
                     description="Señales que el modelo de encabezados tuvo en cuenta"
                     bodyClassName="px-4 sm:px-5 py-1">
              <div className="grid grid-cols-1 sm:grid-cols-2 sm:gap-x-8">
                <FeatureRow label="SPF pass"           value={headerFeatures.spf_pass}            highlight={!headerFeatures.spf_pass} />
                <FeatureRow label="DKIM pass"          value={headerFeatures.dkim_pass}           highlight={!headerFeatures.dkim_pass} />
                <FeatureRow label="DMARC pass"         value={headerFeatures.dmarc_pass}          highlight={!headerFeatures.dmarc_pass} />
                <FeatureRow label="Reply-To difiere"   value={headerFeatures.reply_to_differs}    highlight={headerFeatures.reply_to_differs} />
                <FeatureRow label="TLD sospechoso"     value={headerFeatures.from_suspicious_tld} highlight={headerFeatures.from_suspicious_tld} />
                <FeatureRow label="Dist. marca (typo)" value={headerFeatures.min_brand_distance}  highlight={headerFeatures.min_brand_distance <= 2} />
                <FeatureRow label="Urgencia en asunto" value={headerFeatures.subject_has_urgency} highlight={headerFeatures.subject_has_urgency} />
                <FeatureRow label="Hops recibidos"     value={headerFeatures.received_hop_count} />
              </div>
            </Section>
          )}

          {alert.suspicious_urls?.length > 0 && (
            <Section title={`URLs sospechosas (${alert.url_count} total)`}>
              <ul className="space-y-2">
                {alert.suspicious_urls.map((u, i) => (
                  <li key={i} className="well flex items-center gap-3 px-3 py-2.5">
                    <Link2 className="h-4 w-4 text-fg-3 flex-shrink-0" aria-hidden="true" />
                    <span className="text-caption font-mono text-fg-2 flex-1 truncate min-w-0" title={u.url}>
                      {u.url}
                    </span>
                    <span className={clsx('badge font-mono', tone(scoreTone(u.score)).badge)}>
                      {Math.round(u.score)}
                    </span>
                  </li>
                ))}
              </ul>
            </Section>
          )}
        </div>

        {/* Columna lateral */}
        <div className="space-y-4 sm:space-y-5 lg:sticky lg:top-4">

          {isAnalyst && (
            <Section title="Acciones">
              <div className="space-y-3">
                <div>
                  <label htmlFor="alert-status" className="field-label">Cambiar estado</label>
                  <select id="alert-status" className="input" value={newStatus}
                    onChange={e => setNewStatus(e.target.value)}>
                    <option value="">Selecciona un estado…</option>
                    {STATUS_OPTIONS
                      .filter(o => o.value !== alert.status)
                      .map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                  {newStatus === 'false_pos' && (
                    <p className="field-hint">
                      Se guardará como corrección para reentrenar el modelo.
                    </p>
                  )}
                </div>
                <button disabled={!newStatus || submitting} onClick={handleStatusChange}
                  className="btn-primary w-full">
                  {submitting
                    ? <><Spinner size="sm" inverted /> Guardando…</>
                    : <><Save className="h-4 w-4" aria-hidden="true" /> Guardar cambio</>}
                </button>
              </div>
            </Section>
          )}

          <Section title="Metadatos" bodyClassName="px-4 sm:px-5 py-1.5">
            <dl>
              <MetaRow label="MITRE ATT&CK"><MitreBadge technique={alert.mitre_technique} /></MetaRow>
              <MetaRow label="Táctica">{alert.mitre_tactic}</MetaRow>
              <MetaRow label="Dominio"><span className="font-mono">{alert.sender_domain || '—'}</span></MetaRow>
              <MetaRow label="URLs en correo">{alert.url_count}</MetaRow>
              <MetaRow label="Adjuntos">{alert.has_attachments ? 'Sí' : 'No'}</MetaRow>
              <MetaRow label="Campaña">
                <span className={alert.campaign_name ? 'text-purple-fg font-semibold' : 'text-fg-3'}>
                  {alert.campaign_name || 'Sin campaña'}
                </span>
              </MetaRow>
            </dl>
            <div className="flex flex-col gap-1.5 py-3 text-caption text-fg-3">
              <p className="flex items-center gap-1.5">
                <CalendarClock className="h-3.5 w-3.5" aria-hidden="true" />
                {format(new Date(alert.detected_at), "d MMM yyyy 'a las' HH:mm", { locale: es })}
              </p>
              {alert.assigned_to_name && (
                <p className="flex items-center gap-1.5">
                  <User className="h-3.5 w-3.5" aria-hidden="true" />
                  {alert.assigned_to_name}
                </p>
              )}
            </div>
          </Section>

          <div className="rounded-lg border border-brand-line bg-brand-tint p-4">
            <div className="flex items-center gap-2 mb-1.5">
              <LockKeyhole className="h-4 w-4 text-brand-fg" aria-hidden="true" />
              <h2 className="text-body font-semibold text-fg">Privacidad · Ley 1581/2012</h2>
            </div>
            <p className="text-caption text-fg-2 leading-relaxed">
              Datos seudonimizados con SHA-256. No se almacenan emails en texto plano.
            </p>
            <p className="text-caption text-fg-3 font-mono truncate mt-2">
              {alert.sender_hash?.slice(0, 16)}…
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
