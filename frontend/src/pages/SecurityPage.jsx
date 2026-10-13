/**
 * Sentryx v2 — Seguridad de la cuenta (verificación en dos pasos, TOTP).
 *
 * Flujo de activación: generar QR → confirmar con un código → mostrar los
 * 8 códigos de recuperación una sola vez. El backend no los vuelve a entregar:
 * no guardarlos en el estado global ni en localStorage.
 */
import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  KeyRound, ShieldCheck, ShieldOff, Smartphone, Download, Copy, Check, AlertTriangle,
} from 'lucide-react'
import { clsx } from 'clsx'
import { format } from 'date-fns'
import { es } from 'date-fns/locale'
import { useAuth } from '../store/AuthContext'
import { authAPI } from '../services/api'
import { PageHeader, Section, ErrorBanner, MessageBar, Spinner } from '../components/UI'
import { PasswordInput } from '../components/AuthShell'
import MfaCodeField from '../components/MfaCodeField'

function apiError(err, fallback) {
  if (!err.response) return 'No se pudo conectar con el servidor. Revisa tu conexión.'
  if (err.response.status === 429) return 'Demasiados intentos. Espera un minuto e inténtalo de nuevo.'
  return err.response.data?.error || err.response.data?.detail || fallback
}

// Agrupar la clave en bloques de 4 para dictarla o copiarla a mano
const groupSecret = s => (s || '').match(/.{1,4}/g)?.join(' ') || ''

function CopyButton({ text, label }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch { /* Sin permiso de portapapeles: el texto sigue visible para copiarlo a mano */ }
  }
  return (
    <button type="button" onClick={copy} className="btn-secondary">
      {copied ? <Check className="h-4 w-4" aria-hidden="true" /> : <Copy className="h-4 w-4" aria-hidden="true" />}
      <span aria-live="polite">{copied ? 'Copiado' : label}</span>
    </button>
  )
}

function downloadCodes(codes, email) {
  const text = [
    'Sentryx — Códigos de recuperación de la verificación en dos pasos',
    `Cuenta: ${email}`,
    `Generados: ${format(new Date(), "d 'de' MMMM yyyy, HH:mm", { locale: es })}`,
    '',
    'Cada código sirve una sola vez. Guárdalos en un lugar seguro.',
    '',
    ...codes,
    '',
  ].join('\n')
  const url = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }))
  const a = document.createElement('a')
  a.href = url
  a.download = 'sentryx-codigos-recuperacion.txt'
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

/** Paso a paso para activar el 2FA. */
function EnableFlow({ onDone }) {
  const { user, refreshUser, replaceTokens } = useAuth()
  const [setup, setSetup]       = useState(null)   // { secret, otpauth_url, qr_code }
  const [code, setCode]         = useState('')
  const [codes, setCodes]       = useState(null)   // códigos de recuperación en claro
  const [saved, setSaved]       = useState(false)
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState(null)
  const stepRef = useRef(null)

  // Mover el foco al inicio de cada paso nuevo
  useEffect(() => { stepRef.current?.focus() }, [setup, codes])

  const start = async () => {
    setLoading(true); setError(null)
    try {
      const { data } = await authAPI.mfaSetup()
      setSetup(data)
    } catch (err) {
      setError(apiError(err, 'No se pudo generar el código QR.'))
    } finally { setLoading(false) }
  }

  const confirm = async e => {
    e.preventDefault()
    setLoading(true); setError(null)
    try {
      const { data } = await authAPI.mfaEnable(code)
      replaceTokens(data)
      setCodes(data.recovery_codes)
    } catch (err) {
      setError(apiError(err, 'El código no es válido.'))
      setCode('')
    } finally { setLoading(false) }
  }

  const finish = async () => {
    await refreshUser()
    onDone('La verificación en dos pasos quedó activada.')
  }

  if (codes) {
    return (
      <div className="space-y-4">
        <h3 ref={stepRef} tabIndex={-1} className="text-subtitle2 font-semibold text-fg focus:outline-none">
          Guarda tus códigos de recuperación
        </h3>
        <MessageBar intent="warning" title="Solo se muestran esta vez">
          Si pierdes el teléfono, cada código te permite entrar una vez. Descárgalos o cópialos
          y guárdalos fuera de este equipo.
        </MessageBar>
        <ul className="grid grid-cols-1 min-[360px]:grid-cols-2 gap-2 well p-4 font-mono text-body text-fg"
            aria-label="Códigos de recuperación">
          {codes.map(c => <li key={c} className="tabular-nums">{c}</li>)}
        </ul>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="btn-secondary" onClick={() => downloadCodes(codes, user?.email)}>
            <Download className="h-4 w-4" aria-hidden="true" /> Descargar .txt
          </button>
          <CopyButton text={codes.join('\n')} label="Copiar códigos" />
        </div>
        <label className="flex items-start gap-2.5 text-body text-fg-2 cursor-pointer min-h-[24px]">
          <input type="checkbox" checked={saved} onChange={e => setSaved(e.target.checked)}
                 className="mt-0.5 h-4 w-4 flex-shrink-0 accent-[rgb(var(--brand))]" />
          Guardé mis códigos de recuperación en un lugar seguro.
        </label>
        <button type="button" className="btn-primary" disabled={!saved} onClick={finish}>
          Terminar
        </button>
      </div>
    )
  }

  if (setup) {
    return (
      <form onSubmit={confirm} className="space-y-5">
        <h3 ref={stepRef} tabIndex={-1} className="text-subtitle2 font-semibold text-fg focus:outline-none">
          Escanea el código QR
        </h3>
        <ErrorBanner message={error} onDismiss={() => setError(null)} />
        <ol className="list-decimal pl-5 space-y-1.5 text-body text-fg-2">
          <li>Instala Google Authenticator o Microsoft Authenticator en tu teléfono.</li>
          <li>En la app, elige «Agregar cuenta» y escanea este código.</li>
          <li>Escribe el código de 6 dígitos que muestra la app para confirmar.</li>
        </ol>
        <div className="flex flex-col sm:flex-row gap-5 sm:items-start">
          {/* Fondo blanco fijo: las apps no leen bien el QR sobre el tema oscuro */}
          <img src={setup.qr_code} width={200} height={200}
               alt="Código QR para agregar Sentryx a tu app de autenticación"
               className="rounded-md bg-white p-2 ring-1 ring-stroke self-center sm:self-start" />
          <div className="min-w-0 space-y-2">
            <p className="text-body text-fg-2">¿No puedes escanearlo? Ingresa esta clave a mano:</p>
            <p className="font-mono text-body text-fg break-all well px-3 py-2" translate="no">
              {groupSecret(setup.secret)}
            </p>
            <CopyButton text={setup.secret} label="Copiar clave" />
          </div>
        </div>
        <div className="max-w-xs">
          <MfaCodeField id="enable-code" label="Código de la app"
                        hint="6 dígitos. Cambia cada 30 segundos."
                        value={code} onChange={setCode} />
        </div>
        <button type="submit" className="btn-primary" disabled={loading || code.length !== 6}>
          {loading ? <><Spinner size="sm" inverted /> Confirmando…</> : 'Activar'}
        </button>
      </form>
    )
  }

  return (
    <div className="space-y-4">
      <ErrorBanner message={error} onDismiss={() => setError(null)} />
      <p className="text-body text-fg-2">
        Además de la contraseña, Sentryx te pedirá un código de 6 dígitos de tu teléfono al
        iniciar sesión. Así nadie puede entrar solo con tu contraseña.
      </p>
      <button type="button" className="btn-primary" onClick={start} disabled={loading}>
        {loading
          ? <><Spinner size="sm" inverted /> Generando…</>
          : <><Smartphone className="h-4 w-4" aria-hidden="true" /> Activar la verificación en dos pasos</>}
      </button>
    </div>
  )
}

function DisableForm({ onDone }) {
  const { refreshUser } = useAuth()
  const [password, setPassword] = useState('')
  const [showPass, setShowPass] = useState(false)
  const [code, setCode]         = useState('')
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState(null)

  const submit = async e => {
    e.preventDefault()
    setLoading(true); setError(null)
    try {
      await authAPI.mfaDisable({ password, code })
      await refreshUser()
      onDone('La verificación en dos pasos quedó desactivada.')
    } catch (err) {
      setError(apiError(err, 'No se pudo desactivar.'))
      setCode('')
    } finally { setLoading(false) }
  }

  return (
    <form onSubmit={submit} className="space-y-4 max-w-sm">
      <ErrorBanner message={error} onDismiss={() => setError(null)} />
      <div>
        <label htmlFor="disable-password" className="field-label">Contraseña actual</label>
        <PasswordInput id="disable-password" required autoComplete="current-password"
                       value={password} onChange={e => setPassword(e.target.value)}
                       show={showPass} onToggle={() => setShowPass(s => !s)} />
      </div>
      <MfaCodeField id="disable-code" recovery
                    label="Código de la app o de recuperación"
                    hint="Escribe el código de 6 dígitos de la app o uno de tus códigos de recuperación."
                    value={code} onChange={setCode} />
      <button type="submit" className="btn-danger" disabled={loading || !password || !code}>
        {loading
          ? <><Spinner size="sm" inverted /> Desactivando…</>
          : <><ShieldOff className="h-4 w-4" aria-hidden="true" /> Desactivar</>}
      </button>
    </form>
  )
}

export default function SecurityPage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [message, setMessage] = useState(null)
  const [showDisable, setShowDisable] = useState(false)

  const enabled = !!user?.mfa_enabled
  const remaining = user?.mfa_recovery_codes_remaining ?? 0

  const handleDone = (text) => {
    setMessage(text)
    setShowDisable(false)
    // El admin que venía obligado a configurar el 2FA ya puede usar el resto
    if (user?.mfa_setup_required) navigate('/', { replace: true })
  }

  return (
    <div className="page">
      <PageHeader icon={KeyRound} title="Seguridad de la cuenta"
                  description="Protege tu acceso a Sentryx con la verificación en dos pasos." />

      {user?.mfa_setup_required && (
        <MessageBar intent="warning" title="Debes activar la verificación en dos pasos">
          La política de seguridad exige 2FA para las cuentas de administrador. Actívala para
          seguir usando Sentryx.
        </MessageBar>
      )}
      {message && <MessageBar intent="success" onDismiss={() => setMessage(null)}>{message}</MessageBar>}

      <Section title="Verificación en dos pasos"
               description="Compatible con Google Authenticator y Microsoft Authenticator."
               actions={
                 <span className={clsx('badge h-6 px-2.5',
                   enabled ? 'bg-green-tint text-green-fg' : 'bg-fg/5 text-fg-2')}>
                   {enabled
                     ? <><ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" /> Activada</>
                     : <><ShieldOff className="h-3.5 w-3.5" aria-hidden="true" /> Desactivada</>}
                 </span>
               }>
        {enabled ? (
          <div className="space-y-4">
            <dl className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="well p-3">
                <dt className="text-caption text-fg-3">Activada desde</dt>
                <dd className="text-body text-fg">
                  {user.mfa_enabled_at
                    ? format(new Date(user.mfa_enabled_at), "d 'de' MMMM yyyy", { locale: es })
                    : '—'}
                </dd>
              </div>
              <div className="well p-3">
                <dt className="text-caption text-fg-3">Códigos de recuperación sin usar</dt>
                <dd className="text-body text-fg tabular-nums">{remaining} de 8</dd>
              </div>
            </dl>
            {remaining <= 2 && (
              <MessageBar intent="warning" title="Te quedan pocos códigos de recuperación">
                Desactiva y vuelve a activar la verificación para generar códigos nuevos.
              </MessageBar>
            )}
            {showDisable ? (
              <DisableForm onDone={handleDone} />
            ) : (
              <div className="space-y-2">
                <p className="flex items-start gap-2 text-body text-fg-3">
                  <AlertTriangle className="h-4 w-4 mt-0.5 flex-shrink-0" aria-hidden="true" />
                  Desactivarla hace que tu cuenta dependa solo de la contraseña.
                </p>
                <button type="button" className="btn-secondary" onClick={() => setShowDisable(true)}>
                  Desactivar la verificación en dos pasos
                </button>
              </div>
            )}
          </div>
        ) : (
          <EnableFlow onDone={handleDone} />
        )}
      </Section>
    </div>
  )
}
