// ═══════════════════════════════════════════════════════════
// Páginas auxiliares de acceso: verificación de correo y
// recuperación de contraseña. Comparten AuthShell con el login.
// ═══════════════════════════════════════════════════════════
import { useEffect, useState } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { MailCheck, MailWarning, Send, KeyRound, CheckCircle2, ArrowLeft } from 'lucide-react'
import { authAPI } from '../services/api'
import { Spinner, ErrorBanner } from '../components/UI'
import AuthShell, { PasswordInput } from '../components/AuthShell'

const BackToLogin = () => (
  <Link to="/login" className="link inline-flex items-center gap-1.5">
    <ArrowLeft className="h-4 w-4" aria-hidden="true" /> Volver al inicio de sesión
  </Link>
)

// ═══════════════════════════════════════════════════════════
// VerifyEmailPage — confirmación del token del correo
// ═══════════════════════════════════════════════════════════
export function VerifyEmailPage() {
  const [params]  = useSearchParams()
  const [state, setState] = useState('loading') // loading | success | error | resent
  const [msg, setMsg]     = useState('')
  const [resending, setResending] = useState(false)

  useEffect(() => {
    const token = params.get('token')
    const email = params.get('email')
    if (!token || !email) { setState('error'); setMsg('Enlace inválido.'); return }

    authAPI.verifyEmail({ token, email })
      .then(() => setState('success'))
      .catch(err => {
        setMsg(err.response?.data?.error || 'Enlace inválido o expirado.')
        setState('error')
      })
  }, [])

  const resend = async () => {
    const email = params.get('email')
    if (!email) return
    setResending(true)
    await authAPI.resendVerification({ email }).catch(() => {})
    setResending(false)
    setState('resent')
  }

  if (state === 'loading') return (
    <AuthShell>
      <div className="flex flex-col items-center gap-4 py-6" aria-live="polite">
        <Spinner size="lg" />
        <p className="text-fg-2">Verificando tu correo…</p>
      </div>
    </AuthShell>
  )

  if (state === 'success') return (
    <AuthShell
      status={{ icon: MailCheck, tone: 'green' }}
      title="Correo verificado"
      subtitle="Tu cuenta está pendiente de aprobación por el administrador. Recibirás un correo cuando esté lista."
    >
      <Link to="/login" className="btn-primary btn-lg w-full">Ir al inicio de sesión</Link>
    </AuthShell>
  )

  if (state === 'resent') return (
    <AuthShell
      status={{ icon: Send, tone: 'blue' }}
      title="Correo reenviado"
      subtitle="Revisa tu bandeja de entrada y haz clic en el nuevo enlace de verificación."
    >
      <Link to="/login" className="btn-primary btn-lg w-full">Volver al inicio de sesión</Link>
    </AuthShell>
  )

  return (
    <AuthShell
      status={{ icon: MailWarning, tone: 'red' }}
      title="Enlace inválido"
      subtitle={msg}
    >
      <div className="space-y-3">
        <button onClick={resend} disabled={resending} className="btn-primary btn-lg w-full">
          {resending && <Spinner size="sm" inverted />}
          Reenviar correo de verificación
        </button>
        <Link to="/login" className="btn-secondary btn-lg w-full">Volver al inicio de sesión</Link>
      </div>
    </AuthShell>
  )
}


// ═══════════════════════════════════════════════════════════
// ForgotPasswordPage — solicitar recuperación de contraseña
// ═══════════════════════════════════════════════════════════
export function ForgotPasswordPage() {
  const [email,   setEmail]   = useState('')
  const [loading, setLoading] = useState(false)
  const [sent,    setSent]    = useState(false)
  const [error,   setError]   = useState(null)

  const handleSubmit = async e => {
    e.preventDefault()
    if (!email) { setError('Ingresa tu correo.'); return }
    setLoading(true); setError(null)
    try {
      await authAPI.passwordReset({ email })
      setSent(true)
    } catch { setSent(true) } // No revelar si el email existe
    finally { setLoading(false) }
  }

  if (sent) return (
    <AuthShell
      status={{ icon: Send, tone: 'blue' }}
      title="Revisa tu correo"
      subtitle="Si el correo está registrado y verificado, recibirás un enlace para restablecer tu contraseña en los próximos minutos."
      footer={<BackToLogin />}
    >
      <Link to="/login" className="btn-primary btn-lg w-full">Volver al inicio de sesión</Link>
    </AuthShell>
  )

  return (
    <AuthShell
      title="Recuperar contraseña"
      subtitle="Ingresa tu correo y te enviaremos un enlace para restablecerla."
      footer={<BackToLogin />}
    >
      <form onSubmit={handleSubmit} className="space-y-5">
        <ErrorBanner message={error} onDismiss={() => setError(null)} />
        <div>
          <label htmlFor="fp-email" className="field-label">Correo electrónico</label>
          <input id="fp-email" type="email" required autoFocus autoComplete="email"
                 className="input input-lg" placeholder="usuario@empresa.com"
                 value={email} onChange={e => setEmail(e.target.value)} />
        </div>
        <button type="submit" disabled={loading} className="btn-primary btn-lg w-full">
          {loading
            ? <><Spinner size="sm" inverted /> Enviando…</>
            : 'Enviar enlace de recuperación'}
        </button>
      </form>
    </AuthShell>
  )
}


// ═══════════════════════════════════════════════════════════
// ResetPasswordPage — confirmar nueva contraseña
// ═══════════════════════════════════════════════════════════
export function ResetPasswordPage() {
  const [params]  = useSearchParams()
  const [form, setForm]   = useState({ password: '', confirm: '' })
  const [showPass, setShowPass] = useState(false)
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState(false)
  const [error,   setError]   = useState(null)

  const handleSubmit = async e => {
    e.preventDefault()
    if (form.password.length < 10) { setError('Mínimo 10 caracteres.'); return }
    if (form.password !== form.confirm) { setError('Las contraseñas no coinciden.'); return }

    setLoading(true); setError(null)
    try {
      await authAPI.passwordResetConfirm({
        email:        params.get('email'),
        token:        params.get('token'),
        new_password: form.password,
      })
      setSuccess(true)
    } catch (err) {
      setError(err.response?.data?.error || 'Enlace inválido o expirado.')
    } finally { setLoading(false) }
  }

  if (success) return (
    <AuthShell
      status={{ icon: CheckCircle2, tone: 'green' }}
      title="Contraseña restablecida"
      subtitle="Ya puedes iniciar sesión con tu nueva contraseña."
    >
      <Link to="/login" className="btn-primary btn-lg w-full">Iniciar sesión</Link>
    </AuthShell>
  )

  return (
    <AuthShell
      status={{ icon: KeyRound, tone: 'blue' }}
      title="Nueva contraseña"
      subtitle="Elige una contraseña de al menos 10 caracteres."
      footer={<BackToLogin />}
    >
      <form onSubmit={handleSubmit} className="space-y-5">
        <ErrorBanner message={error} onDismiss={() => setError(null)} />
        <div>
          <label htmlFor="rp-pass" className="field-label">Nueva contraseña</label>
          <PasswordInput id="rp-pass" required autoFocus autoComplete="new-password"
                         placeholder="Mínimo 10 caracteres"
                         value={form.password}
                         onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                         show={showPass} onToggle={() => setShowPass(s => !s)} />
        </div>
        <div>
          <label htmlFor="rp-confirm" className="field-label">Confirmar contraseña</label>
          <input id="rp-confirm" type={showPass ? 'text' : 'password'} required
                 autoComplete="new-password"
                 className="input input-lg" placeholder="Repite tu contraseña"
                 value={form.confirm}
                 onChange={e => setForm(f => ({ ...f, confirm: e.target.value }))} />
        </div>
        <button type="submit" disabled={loading} className="btn-primary btn-lg w-full">
          {loading
            ? <><Spinner size="sm" inverted /> Guardando…</>
            : 'Restablecer contraseña'}
        </button>
      </form>
    </AuthShell>
  )
}
