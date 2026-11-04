/**
 * Sentryx v2 — Red de alerta entre pymes (solo admin).
 * Activar exige leer y aceptar el texto de consentimiento. Apagada por defecto.
 */
import { useCallback, useEffect, useState } from 'react'
import { format } from 'date-fns'
import { es } from 'date-fns/locale'
import { Network, RefreshCw, Save } from 'lucide-react'
import { clsx } from 'clsx'
import { communityAPI } from '../services/api'
import {
  ErrorBanner, LoadingScreen, MessageBar, PageHeader, Section, Spinner, tone,
} from '../components/UI'

const NODE_STATUS = {
  disabled:       { label: 'Red desactivada', tone: 'gray' },
  not_configured: { label: 'Falta configurar el servidor', tone: 'yellow' },
  active:         { label: 'Conectado', tone: 'green' },
  unreachable:    { label: 'El hub no responde', tone: 'orange' },
  suspended:      { label: 'Nodo rechazado por el hub', tone: 'red' },
}

function apiError(err, fallback) {
  const data = err.response?.data
  if (!data || typeof data !== 'object') return fallback
  return data.error || data.detail || Object.values(data).flat().join(' ') || fallback
}

export default function CommunityPage() {
  const [settings, setSettings] = useState(null)
  const [sector, setSector]     = useState('')
  const [region, setRegion]     = useState('')
  const [accepted, setAccepted] = useState(false)
  const [busy, setBusy]         = useState(false)
  const [error, setError]       = useState(null)
  const [notice, setNotice]     = useState(null)

  const apply = useCallback(data => {
    setSettings(data)
    setSector(data.sector || '')
    setRegion(data.region || '')
    setAccepted(false)
  }, [])

  useEffect(() => {
    communityAPI.settings().then(r => apply(r.data))
      .catch(err => setError(apiError(err, 'No se pudo cargar la configuración.')))
  }, [apply])

  const run = async (action, message) => {
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      const { data } = await action()
      if (data.organization) apply(data)
      setNotice(message(data))
    } catch (err) {
      setError(apiError(err, 'No se pudo completar la acción.'))
    } finally {
      setBusy(false)
    }
  }

  if (!settings) {
    return <div className="page">{error ? <ErrorBanner message={error} /> : <LoadingScreen />}</div>
  }

  const status = NODE_STATUS[settings.node_status] || NODE_STATUS.disabled

  const enable = e => {
    e.preventDefault()
    run(() => communityAPI.enable({ accept_consent: accepted, sector, region }),
        () => 'La Red de alerta quedó activa.')
  }

  const disable = () => {
    if (!window.confirm('¿Desactivar la red? Dejaremos de enviar datos y pediremos borrar tus aportes.')) return
    run(() => communityAPI.disable(), data => (data.deletion_pending
      ? 'Red desactivada. El hub no respondió: reintentaremos borrar tus aportes.'
      : 'Red desactivada. Tus aportes se pidieron borrar.'))
  }

  const saveLocation = () => run(() => communityAPI.update({ sector, region }), () => 'Datos guardados.')

  const sync = async () => {
    await run(() => communityAPI.sync(), () => 'Sincronización terminada.')
    communityAPI.settings().then(r => apply(r.data)).catch(() => {})
  }

  return (
    <div className="page">
      <PageHeader icon={Network} title="Red de alerta"
        description="Recibe avisos tempranos cuando otras pymes de tu sector y región reciben una campaña." />

      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
      {notice && <MessageBar intent="success" onDismiss={() => setNotice(null)}>{notice}</MessageBar>}
      {!settings.configured && (
        <MessageBar intent="warning" title="El servidor aún no está conectado a un hub">
          Puedes dar tu consentimiento, pero no se enviará ni recibirá nada hasta configurar
          COMMUNITY_HUB_URL, COMMUNITY_NODE_API_KEY y COMMUNITY_NETWORK_KEY.
        </MessageBar>
      )}
      {settings.deletion_pending && (
        <MessageBar intent="warning">Sigue pendiente pedirle al hub que borre tus aportes. Reintentaremos en cada sincronización.</MessageBar>
      )}

      <Section title="Estado del nodo" actions={settings.enabled && (
        <button type="button" onClick={sync} disabled={busy} className="btn-secondary">
          <RefreshCw className="h-4 w-4" aria-hidden="true" /> Sincronizar ahora
        </button>
      )}>
        <dl className="space-y-1.5 text-body">
          <div className="flex flex-wrap gap-2 items-center">
            <dt className="text-fg-3">Estado:</dt>
            <dd><span className={clsx('badge', tone(status.tone).badge)}>{status.label}</span></dd>
          </div>
          <div className="flex flex-wrap gap-2">
            <dt className="text-fg-3">Última sincronización:</dt>
            <dd className="text-fg-2">
              {settings.last_sync_at
                ? format(new Date(settings.last_sync_at), "d MMM yyyy 'a las' HH:mm", { locale: es })
                : 'Todavía no'}
            </dd>
          </div>
          {settings.last_error && <p className="text-caption text-red-fg">{settings.last_error}</p>}
          {settings.consent_accepted_at && (
            <p className="text-caption text-fg-3">
              Consentimiento aceptado por {settings.consent_accepted_by_name || 'un administrador'} el{' '}
              {format(new Date(settings.consent_accepted_at), "d MMM yyyy", { locale: es })}.
            </p>
          )}
        </dl>
      </Section>

      <form onSubmit={enable} className="space-y-4 sm:space-y-5">
        <Section title="Tu sector y región">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label htmlFor="c-sector" className="field-label">Sector (sección CIIU)</label>
              <select id="c-sector" required className="input" value={sector}
                      onChange={e => setSector(e.target.value)}>
                <option value="">Selecciona…</option>
                {settings.sector_options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="c-region" className="field-label">Departamento</label>
              <select id="c-region" required className="input" value={region}
                      onChange={e => setRegion(e.target.value)}>
                <option value="">Selecciona…</option>
                {settings.region_options.map(o => <option key={o}>{o}</option>)}
              </select>
            </div>
          </div>
        </Section>

        {!settings.enabled && (
          <Section title="Qué se comparte y qué no">
            <p className="text-body text-fg-2 whitespace-pre-line">{settings.consent_text}</p>
            <label className="flex items-start gap-3 cursor-pointer mt-4">
              <input type="checkbox" className="mt-1 h-4 w-4 flex-shrink-0" checked={accepted}
                     onChange={e => setAccepted(e.target.checked)} />
              <span className="text-body font-medium text-fg">
                Leí el texto y acepto en nombre de mi empresa
              </span>
            </label>
          </Section>
        )}

        <div className="flex flex-col sm:flex-row justify-end gap-2">
          {settings.enabled ? (
            <>
              <button type="button" onClick={disable} disabled={busy} className="btn-secondary">
                Desactivar la red
              </button>
              <button type="button" onClick={saveLocation} disabled={busy || !sector || !region} className="btn-primary">
                <Save className="h-4 w-4" aria-hidden="true" /> Guardar cambios
              </button>
            </>
          ) : (
            <button type="submit" disabled={busy || !accepted || !sector || !region} className="btn-primary">
              {busy && <Spinner size="sm" inverted />} Activar la Red de alerta
            </button>
          )}
        </div>
      </form>
    </div>
  )
}
