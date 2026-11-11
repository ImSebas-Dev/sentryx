/**
 * Sentryx v2 — Política de cuatro ojos (solo admin).
 * Interruptores, severidad mínima, aprobadores, vencimiento y exigencia de MFA.
 */
import { useCallback, useEffect, useState } from 'react'
import { ShieldCheck, Save } from 'lucide-react'
import { fourEyesAPI } from '../services/api'
import { useAuth } from '../store/AuthContext'
import {
  ErrorBanner, LoadingScreen, MessageBar, PageHeader, Section, Spinner,
} from '../components/UI'

const SWITCHES = [
  ['enabled', 'Activar el control de cuatro ojos', 'Bloquea los correos de riesgo hasta que otra persona los apruebe.'],
  ['require_for_payment', 'Correos que piden un pago', 'Cuando el Escudo de pagos encuentra datos que no coinciden.'],
  ['require_for_credentials', 'Correos que piden credenciales', 'Iniciar sesión, verificar la cuenta, formularios de acceso.'],
  ['require_for_attachments', 'Adjuntos de riesgo', 'Ejecutables, macros, HTML y comprimidos con contraseña.'],
  ['require_mfa_for_approval', 'Exigir código al aprobar', 'El aprobador confirma con su código de 6 dígitos en ese momento.'],
]

const SEVERITIES = [['MEDIUM', 'Media'], ['HIGH', 'Alta'], ['CRITICAL', 'Crítica']]

export default function FourEyesPolicyPage() {
  const { isAdmin } = useAuth()
  const [policy, setPolicy]     = useState(null)
  const [approvers, setApprovers] = useState([])
  const [loading, setLoading]   = useState(true)
  const [saving, setSaving]     = useState(false)
  const [error, setError]       = useState(null)
  const [saved, setSaved]       = useState(false)

  const load = useCallback(async () => {
    try {
      const { data } = await fourEyesAPI.policy()
      setPolicy(data)
      setApprovers(data.approvers.map(a => a.id))
    } catch (err) {
      setError(err.response?.data?.error || 'No se pudo cargar la política.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  if (loading) return <LoadingScreen />
  if (!policy) return <div className="page"><ErrorBanner message={error} /></div>

  const set = (key, value) => { setPolicy(p => ({ ...p, [key]: value })); setSaved(false) }
  const toggleApprover = id => {
    setApprovers(list => list.includes(id) ? list.filter(x => x !== id) : [...list, id])
    setSaved(false)
  }

  // Calcula el aviso con la selección en pantalla, antes de guardar
  const eligible = approvers.length
    ? approvers.length
    : policy.candidates.filter(c => c.role === 'admin').length

  const submit = async e => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      const { data } = await fourEyesAPI.updatePolicy({
        enabled: policy.enabled,
        min_severity: policy.min_severity,
        require_for_payment: policy.require_for_payment,
        require_for_credentials: policy.require_for_credentials,
        require_for_attachments: policy.require_for_attachments,
        require_mfa_for_approval: policy.require_mfa_for_approval,
        expiry_minutes: Number(policy.expiry_minutes),
        approver_ids: approvers,
      })
      setPolicy(data)
      setSaved(true)
    } catch (err) {
      const body = err.response?.data
      setError(body?.error || Object.values(body || {}).flat().join(' ') || 'No se pudo guardar.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="page">
      <PageHeader icon={ShieldCheck} title="Política de cuatro ojos" guide="four-eyes-policy"
        description="Define cuándo un correo necesita la aprobación de una segunda persona." />

      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
      {saved && <MessageBar intent="success" onDismiss={() => setSaved(false)}>Política guardada.</MessageBar>}
      {eligible < 2 && (
        <MessageBar intent="warning" title="Hacen falta al menos dos personas con permiso de aprobar">
          Nadie puede aprobar su propia solicitud. Con menos de dos aprobadores, los correos que
          reciba ese aprobador no tendrán quién los revise.
        </MessageBar>
      )}

      <form onSubmit={submit} className="space-y-4 sm:space-y-5">
        <Section title="Cuándo aplica">
          <div className="space-y-3">
            {SWITCHES.map(([key, label, hint]) => (
              <label key={key} className="flex items-start gap-3 cursor-pointer">
                <input type="checkbox" className="mt-1 h-4 w-4 flex-shrink-0" checked={policy[key]}
                       disabled={!isAdmin} onChange={e => set(key, e.target.checked)} />
                <span>
                  <span className="block text-body font-medium text-fg">{label}</span>
                  <span className="block text-caption text-fg-3">{hint}</span>
                </span>
              </label>
            ))}
          </div>
        </Section>

        <Section title="Severidad y vencimiento">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label htmlFor="p-severity" className="field-label">Severidad mínima</label>
              <select id="p-severity" className="input" value={policy.min_severity} disabled={!isAdmin}
                      onChange={e => set('min_severity', e.target.value)}>
                {SEVERITIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="p-expiry" className="field-label">Vencimiento (minutos)</label>
              <input id="p-expiry" type="number" min={5} max={10080} className="input" required
                     disabled={!isAdmin} value={policy.expiry_minutes}
                     onChange={e => set('expiry_minutes', e.target.value)} />
            </div>
          </div>
        </Section>

        <Section title="Aprobadores" description="Si no eliges a nadie, aprueban los administradores.">
          <ul className="space-y-2">
            {policy.candidates.map(candidate => (
              <li key={candidate.id}>
                <label className="flex items-center gap-3 cursor-pointer">
                  <input type="checkbox" className="h-4 w-4 flex-shrink-0"
                         checked={approvers.includes(candidate.id)}
                         onChange={() => toggleApprover(candidate.id)} />
                  <span className="min-w-0 flex-1">
                    <span className="block text-body text-fg truncate">{candidate.username}</span>
                    <span className="block text-caption text-fg-3 truncate">{candidate.email}</span>
                  </span>
                  {!candidate.mfa_enabled && policy.require_mfa_for_approval && (
                    <span className="badge bg-yellow-tint text-yellow-fg border-yellow-line">Sin 2FA</span>
                  )}
                </label>
              </li>
            ))}
          </ul>
        </Section>

        {isAdmin && (
          <div className="flex justify-end">
            <button type="submit" disabled={saving} className="btn-primary w-full sm:w-auto">
              {saving ? <Spinner size="sm" inverted /> : <Save className="h-4 w-4" aria-hidden="true" />}
              Guardar política
            </button>
          </div>
        )}
      </form>
    </div>
  )
}
