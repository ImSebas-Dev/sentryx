import { useState } from 'react'
import { Link } from 'react-router-dom'
import { MailCheck, Check } from 'lucide-react'
import { clsx } from 'clsx'
import { authAPI } from '../services/api'
import { Spinner, ErrorBanner } from '../components/UI'
import AuthShell, { PasswordInput } from '../components/AuthShell'

// Medidor de fortaleza sencillo: longitud mínima + variedad de caracteres
function passwordChecks(pw) {
  return [
    { ok: pw.length >= 10,                     label: 'Mínimo 10 caracteres' },
    { ok: /[a-z]/.test(pw) && /[A-Z]/.test(pw), label: 'Mayúsculas y minúsculas' },
    { ok: /\d/.test(pw),                       label: 'Al menos un número' },
    { ok: /[^A-Za-z0-9]/.test(pw),             label: 'Al menos un símbolo' },
  ]
}

const STRENGTH = [
  { label: 'Muy débil', bar: 'bg-red-solid',    text: 'text-red-fg' },
  { label: 'Débil',     bar: 'bg-orange-solid', text: 'text-orange-fg' },
  { label: 'Aceptable', bar: 'bg-yellow-solid', text: 'text-yellow-fg' },
  { label: 'Buena',     bar: 'bg-green-solid',  text: 'text-green-fg' },
  { label: 'Excelente', bar: 'bg-green-solid',  text: 'text-green-fg' },
]

export default function RegisterPage() {
  const [form, setForm] = useState({
    email: '', password: '', confirmPassword: '',
    organization: '', accepted_terms: false,
  })
  const [showPass, setShowPass]   = useState(false)
  const [loading, setLoading]     = useState(false)
  const [error,   setError]       = useState(null)
  const [success, setSuccess]     = useState(false)

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))
  const checks   = passwordChecks(form.password)
  const score    = checks.filter(c => c.ok).length
  const strength = STRENGTH[score]
  const mismatch = form.confirmPassword && form.password !== form.confirmPassword

  const validate = () => {
    if (!form.email)           return 'El correo es obligatorio.'
    if (form.password.length < 10) return 'La contraseña debe tener al menos 10 caracteres.'
    if (form.password !== form.confirmPassword) return 'Las contraseñas no coinciden.'
    if (!form.accepted_terms)  return 'Debes aceptar los Términos y Condiciones.'
    return null
  }

  const handleSubmit = async e => {
    e.preventDefault()
    const err = validate()
    if (err) { setError(err); return }

    setLoading(true); setError(null)
    try {
      await authAPI.register({
        email:          form.email,
        password:       form.password,
        organization:   form.organization,
        accepted_terms: form.accepted_terms,
      })
      setSuccess(true)
    } catch (err) {
      const data = err.response?.data
      setError(
        data?.email?.[0] || data?.password?.[0] ||
        data?.detail     || data?.error ||
        'Error al crear la cuenta. Inténtalo de nuevo.'
      )
    } finally { setLoading(false) }
  }

  if (success) return (
    <AuthShell
      status={{ icon: MailCheck, tone: 'green' }}
      title="Revisa tu correo"
      subtitle={<>Enviamos un enlace de verificación a <strong className="text-fg">{form.email}</strong>.</>}
    >
      <ol className="space-y-3 mb-6">
        {[
          'Abre el correo y haz clic en el enlace para confirmar tu dirección.',
          'Un administrador revisará y aprobará tu solicitud.',
          'Recibirás otro correo cuando tu cuenta esté lista.',
        ].map((text, i) => (
          <li key={i} className="flex gap-3 text-body text-fg-2">
            <span className="h-6 w-6 rounded-full bg-brand-tint text-brand-fg text-caption font-semibold
                             flex items-center justify-center flex-shrink-0">{i + 1}</span>
            {text}
          </li>
        ))}
      </ol>
      <Link to="/login" className="btn-primary btn-lg w-full">Volver al inicio de sesión</Link>
    </AuthShell>
  )

  return (
    <AuthShell
      wide
      title="Solicitar acceso"
      subtitle="Crea tu cuenta. Un administrador la aprobará después de verificar tu correo."
      footer={
        <p>¿Ya tienes cuenta?{' '}<Link to="/login" className="link">Iniciar sesión</Link></p>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-5" noValidate>
        <ErrorBanner message={error} onDismiss={() => setError(null)} />

        <div>
          <label htmlFor="email" className="field-label">
            Correo electrónico <span className="text-red-fg" aria-hidden="true">*</span>
          </label>
          <input id="email" type="email" required autoFocus autoComplete="email"
                 className="input input-lg" placeholder="usuario@empresa.com"
                 value={form.email}
                 onChange={e => set('email', e.target.value)}
                 aria-required="true" />
        </div>

        <div>
          <label htmlFor="organization" className="field-label">
            Organización <span className="font-normal text-fg-3">(opcional)</span>
          </label>
          <input id="organization" type="text" autoComplete="organization"
                 className="input input-lg" placeholder="Mi empresa S.A.S."
                 value={form.organization}
                 onChange={e => set('organization', e.target.value)} />
        </div>

        <div>
          <label htmlFor="password" className="field-label">
            Contraseña <span className="text-red-fg" aria-hidden="true">*</span>
          </label>
          <PasswordInput id="password" required autoComplete="new-password"
                         placeholder="Mínimo 10 caracteres"
                         value={form.password}
                         onChange={e => set('password', e.target.value)}
                         show={showPass} onToggle={() => setShowPass(s => !s)}
                         aria-required="true" aria-describedby="password-hint" />
          {form.password ? (
            <div id="password-hint" className="mt-2.5 space-y-2" aria-live="polite">
              <div className="flex items-center gap-3">
                <div className="flex-1 grid grid-cols-4 gap-1" aria-hidden="true">
                  {[0, 1, 2, 3].map(i => (
                    <span key={i} className={clsx('h-1 rounded-full transition-colors duration-200',
                                                  i < score ? strength.bar : 'bg-fg/10')} />
                  ))}
                </div>
                <span className={clsx('text-caption font-semibold w-20 text-right', strength.text)}>
                  {strength.label}
                </span>
              </div>
              <ul className="grid grid-cols-2 gap-x-3 gap-y-1">
                {checks.map(c => (
                  <li key={c.label} className={clsx('flex items-center gap-1.5 text-caption',
                                                    c.ok ? 'text-green-fg' : 'text-fg-3')}>
                    <Check className={clsx('h-3.5 w-3.5', !c.ok && 'opacity-30')} aria-hidden="true" />
                    {c.label}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p id="password-hint" className="field-hint">
              Mínimo 10 caracteres. Usa letras, números y símbolos.
            </p>
          )}
        </div>

        <div>
          <label htmlFor="confirmPassword" className="field-label">
            Confirmar contraseña <span className="text-red-fg" aria-hidden="true">*</span>
          </label>
          <input id="confirmPassword" type={showPass ? 'text' : 'password'} required
                 autoComplete="new-password"
                 className={clsx('input input-lg', mismatch && 'border-red-line border-b-red-fg')}
                 placeholder="Repite tu contraseña"
                 value={form.confirmPassword}
                 onChange={e => set('confirmPassword', e.target.value)}
                 aria-required="true" aria-invalid={!!mismatch}
                 aria-describedby={mismatch ? 'confirm-error' : undefined} />
          {mismatch && (
            <p id="confirm-error" className="text-caption text-red-fg mt-1.5">Las contraseñas no coinciden.</p>
          )}
        </div>

        {/* Términos y condiciones */}
        <label className="flex items-start gap-3 cursor-pointer well p-3">
          <input type="checkbox" required id="accepted_terms"
                 className="mt-0.5 h-4 w-4 rounded-sm accent-[rgb(var(--brand))] cursor-pointer flex-shrink-0"
                 checked={form.accepted_terms}
                 onChange={e => set('accepted_terms', e.target.checked)}
                 aria-required="true" />
          <span className="text-caption text-fg-2 leading-relaxed">
            He leído y acepto los{' '}
            <Link to="/terms" target="_blank" className="link">Términos y Condiciones</Link>{' '}y la{' '}
            <Link to="/privacy" target="_blank" className="link">Política de Privacidad</Link>{' '}
            de Sentryx, incluyendo el tratamiento de mis datos personales
            conforme a la Ley 1581 de 2012.
          </span>
        </label>

        <button type="submit" disabled={loading} className="btn-primary btn-lg w-full">
          {loading
            ? <><Spinner size="sm" inverted /> Creando cuenta…</>
            : 'Crear cuenta'}
        </button>
      </form>
    </AuthShell>
  )
}
