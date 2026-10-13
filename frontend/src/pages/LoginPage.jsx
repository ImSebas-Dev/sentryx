import { useState, useRef, useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { LogIn, ShieldCheck, ArrowLeft } from 'lucide-react'
import { useAuth } from '../store/AuthContext'
import { Spinner, ErrorBanner, MessageBar } from '../components/UI'
import AuthShell, { PasswordInput } from '../components/AuthShell'
import MfaCodeField from '../components/MfaCodeField'
import { SECURITY_PATH } from '../services/api'

function loginErrorMessage(err) {
  const status = err.response?.status
  const data   = err.response?.data
  if (status === 401) return 'Correo o contraseña incorrectos.'
  if (status === 429) return 'Demasiados intentos. Espera unos minutos e inténtalo de nuevo.'
  if (!err.response)  return 'No se pudo conectar con el servidor. Revisa tu conexión.'
  // 403: correo sin verificar o cuenta pendiente de aprobación
  return data?.error || data?.detail || 'No se pudo iniciar sesión.'
}

// Errores del segundo paso que obligan a volver a escribir la contraseña
const RESTART_CODES = ['mfa_token_expired', 'mfa_token_invalid', 'mfa_token_used', 'mfa_too_many_attempts']

function afterLoginPath(me) {
  return me?.mfa_setup_required ? SECURITY_PATH : '/'
}

/** Segundo paso: código de la app de autenticación o de recuperación. */
function MfaStep({ mfaToken, onRestart }) {
  const { verifyMfa } = useAuth()
  const navigate = useNavigate()
  const [useRecovery, setUseRecovery] = useState(false)
  const [code, setCode]       = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState(null)
  const headingRef = useRef(null)

  // Llevar el foco al título del paso para que el lector de pantalla anuncie el cambio
  useEffect(() => { headingRef.current?.focus() }, [])

  const toggleMode = () => {
    setUseRecovery(r => !r)
    setCode('')
    setError(null)
  }

  const handleSubmit = async e => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      const me = await verifyMfa(mfaToken, useRecovery ? { recovery_code: code } : { code })
      navigate(afterLoginPath(me))
    } catch (err) {
      const data = err.response?.data
      if (RESTART_CODES.includes(data?.code)) {
        onRestart(data.error)
        return
      }
      if (err.response?.status === 429) {
        setError(data?.error || 'Demasiados intentos. Espera unos minutos e inténtalo de nuevo.')
      } else if (!err.response) {
        setError('No se pudo conectar con el servidor. Revisa tu conexión.')
      } else {
        const left = data?.attempts_left
        setError(`El código no es válido.${left != null ? ` Te quedan ${left} ${left === 1 ? 'intento' : 'intentos'}.` : ''}`)
      }
      setCode('')
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5" noValidate={useRecovery}>
      <div>
        <h2 ref={headingRef} tabIndex={-1}
            className="flex items-center gap-2 text-subtitle2 font-semibold text-fg focus:outline-none">
          <ShieldCheck className="h-5 w-5 text-brand-fg" aria-hidden="true" />
          Verificación en dos pasos
        </h2>
        <p className="text-body text-fg-3 mt-1">
          {useRecovery
            ? 'Escribe uno de los códigos de recuperación que guardaste al activar la verificación.'
            : 'Abre Google Authenticator o Microsoft Authenticator y escribe el código de Sentryx.'}
        </p>
      </div>

      <ErrorBanner message={error} onDismiss={() => setError(null)} />

      <MfaCodeField
        key={useRecovery ? 'recovery' : 'totp'}
        id={useRecovery ? 'mfa-recovery' : 'mfa-code'}
        label={useRecovery ? 'Código de recuperación' : 'Código de verificación'}
        hint={useRecovery ? 'Cada código de recuperación sirve una sola vez.' : '6 dígitos. Cambia cada 30 segundos.'}
        value={code} onChange={setCode} recovery={useRecovery} autoFocus
      />

      <button type="submit" disabled={loading || (!useRecovery && code.length !== 6) || (useRecovery && !code)}
              className="btn-primary btn-lg w-full">
        {loading ? <><Spinner size="sm" inverted /> Verificando…</> : 'Verificar'}
      </button>

      <div className="flex flex-col sm:flex-row sm:justify-between gap-3 text-body">
        <button type="button" onClick={toggleMode} className="link text-left min-h-[24px]">
          {useRecovery ? 'Usar la app de autenticación' : 'Usar código de recuperación'}
        </button>
        <button type="button" onClick={() => onRestart(null)}
                className="link inline-flex items-center gap-1 text-left min-h-[24px]">
          <ArrowLeft className="h-4 w-4" aria-hidden="true" /> Volver
        </button>
      </div>
    </form>
  )
}

export default function LoginPage() {
  const { login }    = useAuth()
  const navigate     = useNavigate()
  const [form, setForm] = useState({ email: '', password: '' })
  const [showPass, setShowPass] = useState(false)
  const [loading, setLoading]   = useState(false)
  const [error,   setError]     = useState(null)
  const [notice,  setNotice]    = useState(null)
  const [mfaToken, setMfaToken] = useState(null)

  const handleSubmit = async e => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    setNotice(null)
    try {
      const result = await login(form.email, form.password)
      if (result?.mfaRequired) {
        setMfaToken(result.mfaToken)
        return
      }
      navigate(afterLoginPath(result))
    } catch (err) {
      setError(loginErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  const restart = message => {
    setMfaToken(null)
    setForm(f => ({ ...f, password: '' }))
    setNotice(message)
  }

  if (mfaToken) {
    return (
      <AuthShell tagline title="Iniciar sesión" subtitle={form.email}>
        <MfaStep mfaToken={mfaToken} onRestart={restart} />
      </AuthShell>
    )
  }

  return (
    <AuthShell
      tagline
      title="Iniciar sesión"
      subtitle="Usa tu correo y contraseña de Sentryx."
      footer={
        <p>
          ¿No tienes cuenta?{' '}
          <Link to="/register" className="link">Solicitar acceso</Link>
        </p>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-5">
        <ErrorBanner message={error} onDismiss={() => setError(null)} />
        {notice && (
          <MessageBar intent="warning" onDismiss={() => setNotice(null)}>{notice}</MessageBar>
        )}

        <div>
          <label htmlFor="login-email" className="field-label">Correo electrónico</label>
          <input
            id="login-email"
            type="email"
            required
            autoFocus
            autoComplete="username"
            inputMode="email"
            value={form.email}
            onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
            className="input input-lg"
            placeholder="usuario@empresa.com"
          />
        </div>

        <div>
          <div className="flex items-baseline justify-between mb-1.5">
            <label htmlFor="login-password" className="field-label mb-0">Contraseña</label>
            <Link to="/forgot-password" className="link text-caption">¿La olvidaste?</Link>
          </div>
          <PasswordInput
            id="login-password"
            required
            autoComplete="current-password"
            value={form.password}
            onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
            show={showPass}
            onToggle={() => setShowPass(s => !s)}
            placeholder="Tu contraseña"
          />
        </div>

        <button type="submit" disabled={loading} className="btn-primary btn-lg w-full">
          {loading
            ? <><Spinner size="sm" inverted /> Autenticando…</>
            : <><LogIn className="h-4 w-4" aria-hidden="true" /> Entrar</>}
        </button>
      </form>
    </AuthShell>
  )
}
