/**
 * Contenedor de las pantallas de acceso (login, registro, verificación…).
 * Desktop: panel de marca a la izquierda y formulario a la derecha.
 * Móvil:   solo el formulario, con la marca encima.
 */
import { Link } from 'react-router-dom'
import { ShieldCheck, ScanSearch, Layers3, LockKeyhole, Eye, EyeOff } from 'lucide-react'
import { clsx } from 'clsx'
import ThemeMenu from './ThemeMenu'
import { tone } from './UI'

const FEATURES = [
  { icon: Layers3,     title: 'Ensemble de tres modelos', text: 'Encabezados, contenido y URLs se analizan por separado y se combinan en un único score.' },
  { icon: ScanSearch,  title: 'Clasificación del ataque', text: 'Identifica BEC, whaling, spear phishing y más, con su técnica MITRE ATT&CK.' },
  { icon: LockKeyhole, title: 'Privacidad por diseño',    text: 'Los datos se seudonimizan antes de guardarse, conforme a la Ley 1581 de 2012.' },
]

function BrandPanel() {
  return (
    <aside className="hidden lg:flex relative overflow-hidden flex-col justify-between p-10 xl:p-14
                      text-white bg-[linear-gradient(140deg,#0f6cbd_0%,#0c4f8a_45%,#0a2e4d_100%)]">
      {/* Decoración: halos y escudo de fondo */}
      <div className="absolute -top-24 -right-24 h-96 w-96 rounded-full bg-white/10 blur-3xl" aria-hidden="true" />
      <div className="absolute bottom-0 left-0 h-72 w-72 rounded-full bg-[#479ef5]/20 blur-3xl" aria-hidden="true" />
      <ShieldCheck className="absolute -right-16 bottom-10 h-[420px] w-[420px] text-white/[0.05]"
                   strokeWidth={0.75} aria-hidden="true" />

      <div className="relative flex items-center gap-2 text-white/80 text-body font-semibold">
        <span className="h-2 w-2 rounded-full bg-[#54b054] shadow-[0_0_0_4px_rgba(84,176,84,0.25)]" aria-hidden="true" />
        Motor de detección activo
      </div>

      <div className="relative max-w-md">
        <h2 className="text-title1 xl:text-[40px] xl:leading-[52px] font-semibold tracking-tight">
          Detecta el phishing antes de que llegue a tu equipo.
        </h2>
        <ul className="mt-10 space-y-6">
          {FEATURES.map(({ icon: Icon, title, text }) => (
            <li key={title} className="flex gap-4">
              <span className="h-10 w-10 rounded-lg bg-white/10 ring-1 ring-white/20 flex items-center
                               justify-center flex-shrink-0">
                <Icon className="h-5 w-5" strokeWidth={1.75} aria-hidden="true" />
              </span>
              <div>
                <p className="font-semibold">{title}</p>
                <p className="text-white/75 text-body mt-0.5">{text}</p>
              </div>
            </li>
          ))}
        </ul>
      </div>

      <p className="relative text-caption text-white/60">Sentryx v2 · Proyecto de Grado · 2026</p>
    </aside>
  )
}

/**
 * @param title     Título de la tarjeta
 * @param subtitle  Texto bajo el título
 * @param status    Icono de estado grande (pantallas de éxito/error)
 * @param tagline   Muestra el eslogan bajo la marca (solo en el login)
 * @param footer    Contenido bajo la tarjeta (enlaces)
 */
export default function AuthShell({ title, subtitle, status, tagline = false, footer, children, wide = false }) {
  return (
    <div className="min-h-[100dvh] grid lg:grid-cols-[minmax(0,1fr)_minmax(480px,560px)] bg-canvas">
      <BrandPanel />

      <div className="relative flex flex-col min-h-[100dvh]">
        <div className="absolute top-3 right-3">
          <ThemeMenu />
        </div>

        <main className="flex-1 flex items-center justify-center px-4 py-14 sm:px-8">
          <div className={clsx('w-full animate-slide-up', wide ? 'max-w-md' : 'max-w-sm')}>
            {/* Marca */}
            <div className="flex flex-col items-center text-center mb-7">
              <Link to="/login" className="flex items-center gap-2.5 rounded-md">
                <span className="h-10 w-10 rounded-lg bg-brand text-on-brand flex items-center justify-center shadow-4">
                  <ShieldCheck className="h-6 w-6" strokeWidth={2} aria-hidden="true" />
                </span>
                <span className="text-title3 font-semibold text-fg tracking-tight">Sentryx</span>
              </Link>
              {tagline && (
                <p className="text-fg-3 text-body mt-2">Plataforma de detección de phishing</p>
              )}
            </div>

            <div className="card shadow-8 p-6 sm:p-8">
              {status && (
                <div className={clsx('h-14 w-14 rounded-full flex items-center justify-center mx-auto mb-4',
                                     tone(status.tone).chip)}>
                  <status.icon className="h-7 w-7" strokeWidth={1.75} aria-hidden="true" />
                </div>
              )}
              {title && (
                <h1 className={clsx('text-subtitle font-semibold text-fg', status && 'text-center')}>{title}</h1>
              )}
              {subtitle && (
                <p className={clsx('text-fg-3 text-body mt-1', status && 'text-center')}>{subtitle}</p>
              )}
              <div className={clsx((title || subtitle) && 'mt-6')}>{children}</div>
            </div>

            {footer && <div className="mt-6 text-center text-body text-fg-3">{footer}</div>}
          </div>
        </main>

        <footer className="pb-5 px-4 flex flex-wrap justify-center gap-x-4 gap-y-1 text-caption text-fg-4">
          <Link to="/terms" className="hover:text-fg-2 hover:underline">Términos</Link>
          <Link to="/privacy" className="hover:text-fg-2 hover:underline">Privacidad</Link>
          <Link to="/accessibility" className="hover:text-fg-2 hover:underline">Accesibilidad</Link>
        </footer>
      </div>
    </div>
  )
}

/** Campo de contraseña con botón para mostrar/ocultar. */
export function PasswordInput({ id, value, onChange, show, onToggle, ...props }) {
  return (
    <div className="relative">
      <input id={id} type={show ? 'text' : 'password'} value={value} onChange={onChange}
             className="input input-lg pr-11" {...props} />
      <button type="button" onClick={onToggle}
              className="absolute right-1 top-1/2 -translate-y-1/2 btn-ghost btn-icon h-8 text-fg-3"
              aria-label={show ? 'Ocultar contraseña' : 'Mostrar contraseña'}>
        {show
          ? <EyeOff className="h-4 w-4" aria-hidden="true" />
          : <Eye className="h-4 w-4" aria-hidden="true" />}
      </button>
    </div>
  )
}
