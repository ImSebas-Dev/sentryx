/**
 * Panel "Requiere aprobación de una segunda persona".
 * Lo usan Analizar correo y el detalle de la alerta. Muestra los motivos, permite
 * pedir la aprobación y deja a la vista quién decidió, cuándo y con qué nota.
 */
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Users, Send, Clock, CheckCircle2, XCircle, LifeBuoy } from 'lucide-react'
import { format } from 'date-fns'
import { es } from 'date-fns/locale'
import { fourEyesAPI } from '../services/api'
import { ErrorBanner, MessageBar, Spinner } from './UI'

export const REQUEST_STATUS = {
  pending:   { label: 'Pendiente', intent: 'info' },
  approved:  { label: 'Aprobada',  intent: 'success' },
  rejected:  { label: 'Rechazada', intent: 'error' },
  expired:   { label: 'Vencida',   intent: 'warning' },
  cancelled: { label: 'Cancelada', intent: 'warning' },
}

function Decision({ request }) {
  const status = request.effective_status
  const cfg = REQUEST_STATUS[status] || REQUEST_STATUS.pending
  const when = request.decided_at
    && format(new Date(request.decided_at), "d MMM yyyy 'a las' HH:mm", { locale: es })
  return (
    <MessageBar intent={cfg.intent} title={`Solicitud ${cfg.label.toLowerCase()}`}>
      {status === 'pending' && (
        <p className="flex items-center gap-1.5 text-caption">
          <Clock className="h-3.5 w-3.5" aria-hidden="true" />
          Vence el {format(new Date(request.expires_at), "d MMM 'a las' HH:mm", { locale: es })}
        </p>
      )}
      {request.decided_by_name && (
        <p className="text-caption">Decidió {request.decided_by_name}, {when}.</p>
      )}
      {request.decision_note && <p className="text-caption">Nota: {request.decision_note}</p>}
      {status === 'rejected' && (
        <Link to={`/respond?alert=${request.alert_id}`}
              className="inline-flex items-center gap-1.5 text-body font-semibold underline mt-1">
          <LifeBuoy className="h-4 w-4" aria-hidden="true" />
          ¿Ya hiciste clic o pagaste?
        </Link>
      )}
    </MessageBar>
  )
}

export default function FourEyesPanel({ alertId, reasons }) {
  const [requests, setRequests] = useState([])
  const [note, setNote]         = useState('')
  const [sending, setSending]   = useState(false)
  const [error, setError]       = useState(null)

  const load = useCallback(async () => {
    try {
      const { data } = await fourEyesAPI.requests({ alert: alertId })
      setRequests(data)
    } catch { /* El panel sigue permitiendo pedir la aprobación */ }
  }, [alertId])

  useEffect(() => { if (alertId) load() }, [alertId, load])

  if (!alertId || !reasons?.length) return null

  const latest = requests[0]
  const canRequest = !latest || ['expired', 'cancelled'].includes(latest.effective_status)

  const submit = async e => {
    e.preventDefault()
    setSending(true)
    setError(null)
    try {
      await fourEyesAPI.create({ alert_id: alertId, note })
      setNote('')
      await load()
    } catch (err) {
      setError(err.response?.data?.error || err.response?.data?.detail
               || 'No se pudo pedir la aprobación.')
    } finally {
      setSending(false)
    }
  }

  return (
    <section className="card border-orange-line" aria-label="Requiere aprobación">
      <div className="p-4 sm:p-5 space-y-3">
        <div className="flex items-start gap-3">
          <span className="h-9 w-9 rounded-md bg-orange-tint text-orange-fg flex items-center justify-center flex-shrink-0">
            <Users className="h-5 w-5" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <h2 className="text-section">Requiere aprobación de una segunda persona</h2>
            <p className="text-caption text-fg-3 mt-0.5">
              No pagues, no entregues claves ni abras adjuntos hasta que otra persona lo revise.
            </p>
          </div>
        </div>

        <ul className="list-disc pl-5 space-y-1 text-body text-fg-2">
          {reasons.map((reason, i) => <li key={i}>{reason.detail}</li>)}
        </ul>

        <ErrorBanner message={error} onDismiss={() => setError(null)} />

        {requests.map(request => <Decision key={request.id} request={request} />)}

        {canRequest && (
          <form onSubmit={submit} className="space-y-2">
            <label htmlFor="four-eyes-note" className="field-label">Nota para quien aprueba (opcional)</label>
            <textarea id="four-eyes-note" rows={2} className="input resize-y" value={note}
                      maxLength={1000} onChange={e => setNote(e.target.value)} />
            <button type="submit" disabled={sending} className="btn-primary w-full sm:w-auto">
              {sending ? <Spinner size="sm" inverted /> : <Send className="h-4 w-4" aria-hidden="true" />}
              Pedir aprobación
            </button>
          </form>
        )}

        {latest?.effective_status === 'approved' && (
          <p className="flex items-center gap-1.5 text-caption text-green-fg">
            <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
            Ya puedes continuar.
          </p>
        )}
        {latest?.effective_status === 'rejected' && (
          <p className="flex items-center gap-1.5 text-caption text-red-fg">
            <XCircle className="h-4 w-4" aria-hidden="true" />
            No continúes con lo que pide este correo.
          </p>
        )}
      </div>
    </section>
  )
}
