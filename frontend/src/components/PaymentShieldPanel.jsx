/**
 * Panel "Escudo de pagos": semáforo, checks, proveedor y registro de la llamada.
 * Lo usan Analizar correo y el detalle de la alerta con la misma forma de datos
 * (risk_signals.payment_shield del backend).
 */
import { useState } from 'react'
import {
  CheckCircle2, XCircle, MinusCircle, Phone, ExternalLink, ShieldAlert, ShieldCheck, Landmark,
} from 'lucide-react'
import { clsx } from 'clsx'
import { paymentShieldAPI } from '../services/api'
import { useAuth } from '../store/AuthContext'
import { ErrorBanner, Spinner, Section } from './UI'
import Modal from './Modal'

const STATUS_LABELS = {
  pending_verification: 'Pendiente de verificación',
  verified_by_call:     'Verificado por llamada',
  rejected:             'Rechazado',
  approved:             'Aprobado',
}

const CHECK_ICONS = {
  pass: { icon: CheckCircle2, cls: 'text-green-fg', label: 'Correcto' },
  fail: { icon: XCircle,      cls: 'text-red-fg',   label: 'Falló' },
  na:   { icon: MinusCircle,  cls: 'text-fg-4',     label: 'No aplica' },
}

function Traffic({ shield }) {
  const color = shield.risky ? 'red' : shield.intent_detected ? 'green' : 'yellow'
  const cfg = {
    red:    { box: 'bg-red-tint border-red-line',       Icon: ShieldAlert, icon: 'text-red-fg',
              title: 'No pagues todavía' },
    yellow: { box: 'bg-yellow-tint border-yellow-line', Icon: ShieldAlert, icon: 'text-yellow-fg',
              title: 'Revisa la factura' },
    green:  { box: 'bg-green-tint border-green-line',   Icon: ShieldCheck, icon: 'text-green-fg',
              title: 'Coincide con tu proveedor' },
  }[color]
  return (
    <div className={clsx('rounded-md border p-3 flex items-start gap-3', cfg.box)}
         role="status" data-testid={`traffic-${color}`}>
      <cfg.Icon className={clsx('h-6 w-6 flex-shrink-0', cfg.icon)} aria-hidden="true" />
      <div className="min-w-0">
        <p className="text-body font-semibold text-fg">{cfg.title}</p>
        <p className="text-caption text-fg-2 mt-0.5">{shield.message}</p>
      </div>
    </div>
  )
}

function VerifyModal({ checkId, onClose, onDone }) {
  const [result, setResult] = useState('verified_by_call')
  const [notes, setNotes]   = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError]   = useState(null)

  const submit = async e => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      const { data } = await paymentShieldAPI.verifyCheck(checkId, { result, notes })
      onDone(data.status)
    } catch (err) {
      setError(err.response?.data?.error || err.response?.data?.detail
               || 'No se pudo registrar la verificación.')
      setSaving(false)
    }
  }

  return (
    <Modal title="Registrar verificación" onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <ErrorBanner message={error} onDismiss={() => setError(null)} />
        <div>
          <label htmlFor="verify-result" className="field-label">Resultado</label>
          <select id="verify-result" className="input" value={result}
                  onChange={e => setResult(e.target.value)}>
            <option value="verified_by_call">Llamé y el proveedor lo confirmó</option>
            <option value="rejected">Es un fraude: rechazar</option>
            <option value="approved">Aprobar el pago</option>
          </select>
        </div>
        <div>
          <label htmlFor="verify-notes" className="field-label">Notas</label>
          <textarea id="verify-notes" rows={3} className="input resize-y" value={notes}
                    placeholder="Con quién hablaste y qué te confirmó"
                    onChange={e => setNotes(e.target.value)} />
          <p className="field-hint">No escribas aquí números de cuenta completos.</p>
        </div>
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="btn-secondary">Cancelar</button>
          <button type="submit" disabled={saving} className="btn-primary">
            {saving && <Spinner size="sm" inverted />} Guardar
          </button>
        </div>
      </form>
    </Modal>
  )
}

export default function PaymentShieldPanel({ shield }) {
  const { isAnalyst } = useAuth()
  const [status, setStatus]       = useState(shield?.status)
  const [verifying, setVerifying] = useState(false)

  if (!shield) return null
  const { supplier, invoice } = shield
  const closed = status === 'rejected' || status === 'approved'

  return (
    <Section title="Escudo de pagos"
             description="Compara el correo con tu directorio de proveedores. No cambia el score del modelo.">
      <div className="space-y-4">
        <Traffic shield={shield} />

        <ul className="space-y-1.5" aria-label="Validaciones">
          {(shield.checks || []).map(check => {
            const cfg = CHECK_ICONS[check.status] || CHECK_ICONS.na
            return (
              <li key={check.key} className="flex items-start gap-2 text-body">
                <cfg.icon className={clsx('h-4 w-4 mt-0.5 flex-shrink-0', cfg.cls)}
                          aria-label={cfg.label} />
                <span className="min-w-0">
                  <span className="text-fg">{check.label}</span>
                  {check.detail && (
                    <span className="block text-caption text-fg-3 break-words">{check.detail}</span>
                  )}
                </span>
              </li>
            )
          })}
        </ul>

        {supplier ? (
          <div className="well px-3 py-2.5 space-y-1">
            <p className="text-body font-semibold text-fg">{supplier.name}</p>
            <p className="text-caption text-fg-3">NIT {supplier.nit}-{supplier.dv}</p>
            {supplier.bank_name && (
              <p className="text-caption text-fg-2 flex items-center gap-1.5">
                <Landmark className="h-3.5 w-3.5" aria-hidden="true" />
                {supplier.bank_name}
                {supplier.account_last4 && ` · ****${supplier.account_last4}`}
              </p>
            )}
            {supplier.contact_phone && (
              <a href={`tel:${supplier.contact_phone}`}
                 className="btn-secondary mt-2 w-full sm:w-auto">
                <Phone className="h-4 w-4" aria-hidden="true" />
                Llamar al número de confianza: {supplier.contact_phone}
              </a>
            )}
          </div>
        ) : (
          <p className="text-caption text-fg-3">
            Este remitente no está en tu directorio. Antes de pagar, confirma por un canal que ya conozcas.
          </p>
        )}

        {invoice?.dian_url && (
          <a href={invoice.dian_url} target="_blank" rel="noopener noreferrer"
             className="inline-flex items-center gap-1.5 text-body text-brand-fg hover:underline">
            <ExternalLink className="h-4 w-4" aria-hidden="true" />
            Consultar el CUFE en el catálogo de la DIAN
          </a>
        )}

        {shield.check_id && (
          <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
            <p className="text-caption text-fg-3">
              Estado: <span className="font-semibold text-fg-2">{STATUS_LABELS[status] || status}</span>
            </p>
            {isAnalyst && !closed && (
              <button type="button" onClick={() => setVerifying(true)} className="btn-primary">
                <Phone className="h-4 w-4" aria-hidden="true" />
                Registrar verificación telefónica
              </button>
            )}
          </div>
        )}
      </div>

      {verifying && (
        <VerifyModal checkId={shield.check_id} onClose={() => setVerifying(false)}
                     onDone={next => { setStatus(next); setVerifying(false) }} />
      )}
    </Section>
  )
}
