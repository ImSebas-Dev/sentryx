/**
 * Sentryx v2 — Aprobaciones de cuatro ojos.
 * Dos pestañas: lo que me toca decidir y lo que yo pedí.
 * El correo de aviso enlaza a /approvals/:id, que resalta esa solicitud.
 */
import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Users, Check, X, Clock, Inbox, LifeBuoy } from 'lucide-react'
import { clsx } from 'clsx'
import { formatDistanceToNowStrict, format } from 'date-fns'
import { es } from 'date-fns/locale'
import { fourEyesAPI } from '../services/api'
import { useAuth } from '../store/AuthContext'
import {
  EmptyState, ErrorBanner, LoadingScreen, MessageBar, PageHeader, SeverityBadge, Spinner, tone,
} from '../components/UI'
import Modal from '../components/Modal'
import PageGuide from '../components/PageGuide'
import MfaCodeField from '../components/MfaCodeField'
import { REQUEST_STATUS } from '../components/FourEyesPanel'

const STATUS_TONES = {
  pending: 'blue', approved: 'green', rejected: 'red', expired: 'yellow', cancelled: 'gray',
}

function RequestStatusBadge({ status }) {
  return (
    <span className={clsx('badge', tone(STATUS_TONES[status]).badge)}>
      {REQUEST_STATUS[status]?.label || status}
    </span>
  )
}

function DecisionModal({ request, approve, onClose, onDone }) {
  const [code, setCode]     = useState('')
  const [note, setNote]     = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError]   = useState(null)

  const submit = async e => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      const payload = { totp_code: code, note }
      if (approve) await fourEyesAPI.approve(request.id, payload)
      else         await fourEyesAPI.reject(request.id, payload)
      onDone()
    } catch (err) {
      setError(err.response?.data?.error || err.response?.data?.detail
               || 'No se pudo registrar la decisión.')
      setCode('')
      setSaving(false)
    }
  }

  return (
    <Modal title={approve ? 'Aprobar solicitud' : 'Rechazar solicitud'} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <PageGuide id="approval-decision" />
        <ErrorBanner message={error} onDismiss={() => setError(null)} />
        {request.requires_totp && (
          <MfaCodeField id="decision-totp" label="Código de verificación" value={code}
                        onChange={setCode} autoFocus
                        hint="Escribe el código de 6 dígitos de tu app de autenticación." />
        )}
        <div>
          <label htmlFor="decision-note" className="field-label">
            {approve ? 'Nota (opcional)' : 'Motivo del rechazo'}
          </label>
          <textarea id="decision-note" rows={3} className="input resize-y" required={!approve}
                    maxLength={1000} value={note} onChange={e => setNote(e.target.value)} />
        </div>
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="btn-secondary">Cancelar</button>
          <button type="submit" disabled={saving}
                  className={approve ? 'btn-primary' : 'btn-primary bg-red-solid hover:bg-red-solid'}>
            {saving && <Spinner size="sm" inverted />}
            {approve ? 'Aprobar' : 'Rechazar'}
          </button>
        </div>
      </form>
    </Modal>
  )
}

function RequestCard({ request, highlighted, onDecide, onCancel }) {
  const status = request.effective_status
  return (
    <li className={clsx('card p-4 sm:p-5 space-y-3', highlighted && 'ring-2 ring-brand-line')}>
      <div className="flex flex-wrap items-center gap-1.5">
        <SeverityBadge severity={request.alert_severity} />
        <RequestStatusBadge status={status} />
        {status === 'pending' && (
          <span className="inline-flex items-center gap-1 text-caption text-fg-3 ml-auto">
            <Clock className="h-3.5 w-3.5" aria-hidden="true" />
            Quedan {formatDistanceToNowStrict(new Date(request.expires_at), { locale: es })}
          </span>
        )}
      </div>

      <div className="text-caption text-fg-3 space-y-0.5">
        <p>Remitente: <span className="font-mono text-fg-2">{request.sender_domain || 'sin dominio'}</span></p>
        <p>Pidió: <span className="text-fg-2">{request.requester_name || 'usuario eliminado'}</span>
           {' · '}{format(new Date(request.created_at), "d MMM 'a las' HH:mm", { locale: es })}</p>
      </div>

      <ul className="list-disc pl-5 space-y-1 text-body text-fg-2">
        {request.reasons.map((reason, i) => <li key={i}>{reason.detail}</li>)}
      </ul>

      {request.requester_note && (
        <p className="well px-3 py-2 text-caption text-fg-2">“{request.requester_note}”</p>
      )}

      {request.decided_by_name && (
        <p className="text-caption text-fg-3">
          Decidió <span className="text-fg-2">{request.decided_by_name}</span>
          {request.decided_at && `, ${format(new Date(request.decided_at), "d MMM 'a las' HH:mm", { locale: es })}`}
          {request.decision_note && `. Nota: ${request.decision_note}`}
        </p>
      )}

      {request.guided_response && (
        <Link to={request.guided_response.url}
              className="inline-flex items-center gap-1.5 text-body font-semibold text-brand-fg underline">
          <LifeBuoy className="h-4 w-4" aria-hidden="true" />
          {request.guided_response.question}
        </Link>
      )}

      {onDecide && request.can_decide && (
        <div className="flex gap-2">
          <button type="button" onClick={() => onDecide(request, true)} className="btn-primary flex-1 sm:flex-none">
            <Check className="h-4 w-4" aria-hidden="true" /> Aprobar
          </button>
          <button type="button" onClick={() => onDecide(request, false)} className="btn-secondary flex-1 sm:flex-none">
            <X className="h-4 w-4" aria-hidden="true" /> Rechazar
          </button>
        </div>
      )}
      {onCancel && status === 'pending' && (
        <button type="button" onClick={() => onCancel(request)} className="btn-secondary">
          Cancelar solicitud
        </button>
      )}
    </li>
  )
}

export default function ApprovalsPage() {
  const { id } = useParams()
  const { user } = useAuth()
  const [tab, setTab]           = useState('to_approve')
  const [items, setItems]       = useState([])
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState(null)
  const [decision, setDecision] = useState(null) // { request, approve }
  const [linked, setLinked]     = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = tab === 'to_approve' ? { to_approve: 'true' } : { mine: 'true' }
      const { data } = await fourEyesAPI.requests(params)
      setItems(data)
    } catch (err) {
      setError(err.response?.data?.detail || 'No se pudieron cargar las solicitudes.')
    } finally {
      setLoading(false)
    }
  }, [tab])

  useEffect(() => { load() }, [load])

  // Abre aquí la solicitud del enlace del correo aunque ya esté decidida
  const loadLinked = useCallback(async () => {
    if (!id) return
    try {
      const { data } = await fourEyesAPI.detail(id)
      setLinked(data)
    } catch {
      setError('No tienes acceso a esa solicitud o ya no existe.')
    }
  }, [id])

  useEffect(() => { loadLinked() }, [loadLinked])

  const handleCancel = async request => {
    try {
      await fourEyesAPI.cancel(request.id)
      load()
    } catch (err) {
      setError(err.response?.data?.error || 'No se pudo cancelar.')
    }
  }

  const afterDecision = () => {
    setDecision(null)
    load()
    loadLinked()
  }

  const onDecide = (request, approve) => setDecision({ request, approve })
  const visible = items.filter(r => r.id !== linked?.id)

  return (
    <div className="page">
      <PageHeader icon={Users} title="Aprobaciones" guide="approvals"
        description="Correos de alto riesgo que necesitan la revisión de una segunda persona." />

      {user && !user.mfa_enabled && tab === 'to_approve' && (
        <MessageBar intent="warning" title="Activa la verificación en dos pasos">
          Para aprobar o rechazar debes confirmar con tu código.{' '}
          <Link to="/security" className="underline font-semibold">Actívala aquí</Link>.
        </MessageBar>
      )}

      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

      {linked && (
        <ul aria-label="Solicitud enlazada">
          <RequestCard request={linked} highlighted onDecide={onDecide} />
        </ul>
      )}

      <div role="tablist" aria-label="Solicitudes" className="flex gap-1 border-b border-stroke">
        {[['to_approve', 'Por aprobar'], ['mine', 'Mis solicitudes']].map(([key, label]) => (
          <button key={key} type="button" role="tab" aria-selected={tab === key}
                  onClick={() => setTab(key)}
                  className={clsx('px-4 py-2 text-body font-semibold border-b-2 -mb-px',
                    tab === key ? 'border-brand text-brand-fg' : 'border-transparent text-fg-3 hover:text-fg')}>
            {label}
          </button>
        ))}
      </div>

      {loading ? <LoadingScreen /> : visible.length === 0 ? (
        <div className="card">
          <EmptyState icon={Inbox}
            title={tab === 'to_approve' ? 'No tienes nada por aprobar' : 'No has pedido aprobaciones'}
            description={tab === 'to_approve'
              ? 'Cuando alguien pida tu revisión aparecerá aquí.'
              : 'Cuando un correo requiera una segunda persona podrás pedirla desde el análisis.'} />
        </div>
      ) : (
        <ul className="space-y-3">
          {visible.map(request => (
            <RequestCard key={request.id} request={request}
                         onDecide={tab === 'to_approve' ? onDecide : null}
                         onCancel={tab === 'mine' ? handleCancel : null} />
          ))}
        </ul>
      )}

      {decision && (
        <DecisionModal request={decision.request} approve={decision.approve}
                       onClose={() => setDecision(null)} onDone={afterDecision} />
      )}
    </div>
  )
}
