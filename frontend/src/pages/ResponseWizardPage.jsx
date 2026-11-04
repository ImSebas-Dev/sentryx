/**
 * Sentryx v2 — Asistente "¿Caíste en un phishing?" a pantalla completa.
 * Tres pasos: qué pasó, qué hacer ahora (con temporizador de 15 minutos) y
 * descarga del paquete de denuncia. Se abre con ?alert=<id> para vincular la alerta.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  ArrowLeft, ArrowRight, Check, Download, ExternalLink, KeyRound, Landmark, Paperclip,
  Phone, Timer, Users, X,
} from 'lucide-react'
import { clsx } from 'clsx'
import { responseAPI } from '../services/api'
import { ErrorBanner, MessageBar, Spinner, LoadingScreen, Section } from '../components/UI'

const FIFTEEN_MINUTES = 15 * 60

const PLAYBOOK_ICONS = {
  password: KeyRound, attachment: Paperclip, payment: Landmark, data: Users,
}

const WHEN_OPTIONS = [
  'Hace menos de 15 minutos', 'Hace menos de 1 hora', 'Hoy, hace más de 1 hora', 'Antes de hoy',
]

function useCountdown(startedAt) {
  const [remaining, setRemaining] = useState(FIFTEEN_MINUTES)
  useEffect(() => {
    if (!startedAt) return undefined
    const tick = () => {
      const elapsed = Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000)
      setRemaining(Math.max(FIFTEEN_MINUTES - elapsed, 0))
    }
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [startedAt])
  return remaining
}

function CountdownBadge({ startedAt }) {
  const remaining = useCountdown(startedAt)
  const minutes = String(Math.floor(remaining / 60)).padStart(2, '0')
  const seconds = String(remaining % 60).padStart(2, '0')
  return (
    <span role="timer" aria-label={`Quedan ${minutes} minutos y ${seconds} segundos`}
          className={clsx('badge font-mono text-body h-7 px-3',
            remaining === 0 ? 'bg-red-tint text-red-fg border-red-line'
                            : 'bg-brand-tint text-brand-fg border-brand-line')}>
      <Timer className="h-4 w-4 mr-1" aria-hidden="true" />
      {minutes}:{seconds}
    </span>
  )
}

function ContactsPanel({ contacts, warning, caiUrl }) {
  return (
    <Section title="Contactos de emergencia" description={warning}>
      <ul className="space-y-2">
        {contacts.map(contact => (
          <li key={contact.id} className="well px-3 py-2.5">
            <p className="text-body font-medium text-fg">{contact.name}</p>
            {contact.is_placeholder && (
              <p className="text-caption text-yellow-fg">
                Falta completarlo: pide al administrador que registre este contacto.
              </p>
            )}
            <div className="flex flex-wrap gap-2 mt-1.5 empty:hidden">
              {contact.phone && (
                <a href={`tel:${contact.phone}`} className="btn-primary">
                  <Phone className="h-4 w-4" aria-hidden="true" /> Llamar: {contact.phone}
                </a>
              )}
              {contact.url && (
                <a href={contact.url} target="_blank" rel="noopener noreferrer" className="btn-secondary">
                  <ExternalLink className="h-4 w-4" aria-hidden="true" /> Abrir sitio
                </a>
              )}
            </div>
          </li>
        ))}
      </ul>
      {caiUrl && (
        <a href={caiUrl} target="_blank" rel="noopener noreferrer"
           className="inline-flex items-center gap-1.5 text-body text-brand-fg hover:underline mt-3">
          <ExternalLink className="h-4 w-4" aria-hidden="true" />
          Denunciar en el CAI Virtual de la Policía Nacional
        </a>
      )}
    </Section>
  )
}

function ChooseStep({ playbooks, starting, onStart, linkedAlert }) {
  const [when, setWhen] = useState(WHEN_OPTIONS[0])
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-page-title">Respira. Vamos paso a paso.</h1>
        <p className="text-fg-3 text-body mt-1">Cuéntanos qué pasó y te decimos qué hacer primero.</p>
      </div>
      {linkedAlert && <MessageBar intent="info">Esta respuesta quedará vinculada a la alerta del correo.</MessageBar>}
      <div>
        <label htmlFor="r-when" className="field-label">¿Cuándo pasó?</label>
        <select id="r-when" className="input" value={when} onChange={e => setWhen(e.target.value)}>
          {WHEN_OPTIONS.map(o => <option key={o}>{o}</option>)}
        </select>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {playbooks.map(playbook => {
          const Icon = PLAYBOOK_ICONS[playbook.key] || KeyRound
          return (
            <button key={playbook.key} type="button" disabled={starting}
                    onClick={() => onStart(playbook.key, { cuando: when })}
                    className="card-interactive p-4 text-left flex gap-3 items-start">
              <span className="h-10 w-10 rounded-md bg-red-tint text-red-fg flex items-center justify-center flex-shrink-0">
                <Icon className="h-5 w-5" aria-hidden="true" />
              </span>
              <span className="min-w-0">
                <span className="block text-body font-semibold text-fg">{playbook.title}</span>
                <span className="block text-caption text-fg-3 mt-0.5">{playbook.description}</span>
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}

function StepsStep({ session, contacts, warning, caiUrl, onSession, onFinish }) {
  const steps = session.playbook.steps
  const [index, setIndex]   = useState(0)
  const [note, setNote]     = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError]   = useState(null)
  const step  = steps[index]
  const state = session.steps_state[step.id] || {}

  useEffect(() => { setNote(session.steps_state[step.id]?.note || '') }, [step.id]) // eslint-disable-line

  const save = async done => {
    setSaving(true)
    setError(null)
    try {
      const { data } = await responseAPI.step(session.id, step.id, { done, note })
      onSession(data)
      return true
    } catch (err) {
      setError(err.response?.data?.error || 'No se pudo guardar el paso. Sigue con la lista igual.')
      return false
    } finally {
      setSaving(false)
    }
  }

  const doneCount = steps.filter(s => session.steps_state[s.id]?.done).length
  const isLast = index === steps.length - 1

  const next = async () => {
    // Guarda la nota al avanzar para no perderla si el usuario no marcó el paso
    if (note !== (state.note || '')) await save(!!state.done)
    if (isLast) onFinish()
    else setIndex(i => i + 1)
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-section">{session.playbook.title}</h1>
        <CountdownBadge startedAt={session.started_at} />
      </div>

      <div className="h-1.5 bg-fg/10 rounded-full overflow-hidden" role="progressbar"
           aria-valuemin={0} aria-valuemax={steps.length} aria-valuenow={doneCount}
           aria-label="Pasos completados">
        <div className="h-full bg-green-solid transition-[width] duration-300"
             style={{ width: `${doneCount / steps.length * 100}%` }} />
      </div>

      <ErrorBanner message={error} onDismiss={() => setError(null)} />

      <section className="card p-4 sm:p-5 space-y-3" aria-live="polite">
        <p className="text-caption text-fg-3">
          Paso {index + 1} de {steps.length}
          {step.critical && <span className="badge ml-2 bg-red-tint text-red-fg border-red-line">Urgente</span>}
        </p>
        <label className="flex items-start gap-3 cursor-pointer">
          <input type="checkbox" className="mt-1 h-5 w-5 flex-shrink-0" disabled={saving}
                 checked={!!state.done} onChange={e => save(e.target.checked)} />
          <span>
            <span className="block text-subtitle2 font-semibold text-fg">{step.title}</span>
            <span className="block text-body text-fg-2 mt-1">{step.detail}</span>
          </span>
        </label>
        <div>
          <label htmlFor="r-note" className="field-label">Notas (opcional)</label>
          <textarea id="r-note" rows={2} maxLength={1000} className="input resize-y" value={note}
                    onChange={e => setNote(e.target.value)} />
          <p className="field-hint">No escribas aquí contraseñas ni números de cuenta: esta nota va al informe.</p>
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={() => setIndex(i => i - 1)} disabled={index === 0}
                  className="btn-secondary">
            <ArrowLeft className="h-4 w-4" aria-hidden="true" /> Anterior
          </button>
          <button type="button" onClick={next} disabled={saving} className="btn-primary flex-1">
            {isLast ? 'Terminar' : 'Siguiente'}
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      </section>

      <ContactsPanel contacts={contacts} warning={warning} caiUrl={caiUrl} />
    </div>
  )
}

function DoneStep({ session, caiUrl, onExit }) {
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState(null)

  const download = async () => {
    setDownloading(true)
    setError(null)
    try {
      const { data } = await responseAPI.report(session.id)
      const url = URL.createObjectURL(data)
      const link = document.createElement('a')
      link.href = url
      link.download = `paquete-denuncia-${session.id.slice(0, 8)}.pdf`
      link.click()
      URL.revokeObjectURL(url)
    } catch {
      setError('No se pudo generar el PDF. Inténtalo de nuevo.')
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div className="space-y-4 text-center sm:text-left">
      <span className="inline-flex h-14 w-14 rounded-full bg-green-tint text-green-fg items-center justify-center">
        <Check className="h-7 w-7" aria-hidden="true" />
      </span>
      <h1 className="text-page-title">Hiciste lo correcto</h1>
      <p className="text-fg-2 text-body">
        Creamos un incidente y avisamos a los administradores. Descarga el paquete de denuncia:
        trae los hechos, la línea de tiempo y los indicadores para presentarlo ante las autoridades.
        Sentryx no envía nada por su cuenta.
      </p>
      <ErrorBanner message={error} onDismiss={() => setError(null)} />
      <div className="flex flex-col sm:flex-row gap-2">
        <button type="button" onClick={download} disabled={downloading} className="btn-primary btn-lg">
          {downloading ? <Spinner size="sm" inverted /> : <Download className="h-4 w-4" aria-hidden="true" />}
          Descargar paquete de denuncia (PDF)
        </button>
        {caiUrl && (
          <a href={caiUrl} target="_blank" rel="noopener noreferrer" className="btn-secondary btn-lg">
            <ExternalLink className="h-4 w-4" aria-hidden="true" /> Ir al CAI Virtual
          </a>
        )}
        <button type="button" onClick={onExit} className="btn-secondary btn-lg">Volver a Sentryx</button>
      </div>
    </div>
  )
}

export default function ResponseWizardPage() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const alertId  = params.get('alert')
  const topRef   = useRef(null)

  const [playbooks, setPlaybooks] = useState(null)
  const [contacts, setContacts]   = useState([])
  const [config, setConfig]       = useState({})
  const [session, setSession]     = useState(null)
  const [finished, setFinished]   = useState(false)
  const [starting, setStarting]   = useState(false)
  const [error, setError]         = useState(null)

  useEffect(() => {
    responseAPI.playbooks().then(r => setPlaybooks(r.data))
      .catch(() => setError('No se pudieron cargar las opciones. Revisa tu conexión.'))
    responseAPI.contacts().then(r => setContacts(r.data)).catch(() => {})
    responseAPI.config().then(r => setConfig(r.data)).catch(() => {})
  }, [])

  const start = useCallback(async (key, answers) => {
    setStarting(true)
    setError(null)
    try {
      const payload = { playbook_key: key, answers }
      if (alertId) payload.alert_id = alertId
      const { data } = await responseAPI.start(payload)
      setSession(data)
      topRef.current?.scrollTo?.(0, 0)
    } catch (err) {
      setError(err.response?.data?.error || 'No se pudo iniciar la respuesta.')
    } finally {
      setStarting(false)
    }
  }, [alertId])

  const finish = async () => {
    try {
      const { data } = await responseAPI.complete(session.id)
      setSession(data)
    } catch { /* El usuario igual puede descargar el paquete */ }
    setFinished(true)
    topRef.current?.scrollTo?.(0, 0)
  }

  const exit = () => navigate('/')

  return (
    <div ref={topRef} role="dialog" aria-modal="true" aria-label="Respuesta guiada"
         className="fixed inset-0 z-50 bg-canvas overflow-y-auto animate-fade-in
                    pt-[env(safe-area-inset-top)] pb-[env(safe-area-inset-bottom)]">
      <div className="max-w-2xl mx-auto p-4 sm:p-6 space-y-4">
        <div className="flex justify-end">
          <button type="button" onClick={exit} className="btn-ghost" aria-label="Salir del asistente">
            <X className="h-4 w-4" aria-hidden="true" /> Salir
          </button>
        </div>
        <ErrorBanner message={error} onDismiss={() => setError(null)} />

        {!session && !playbooks && !error && <LoadingScreen />}
        {!session && playbooks && (
          <ChooseStep playbooks={playbooks} starting={starting} onStart={start} linkedAlert={!!alertId} />
        )}
        {session && !finished && (
          <StepsStep session={session} contacts={contacts} warning={config.contact_warning}
                     caiUrl={config.cai_virtual_url} onSession={setSession} onFinish={finish} />
        )}
        {session && finished && <DoneStep session={session} caiUrl={config.cai_virtual_url} onExit={exit} />}
      </div>
    </div>
  )
}
