/**
 * Sentryx — Componentes base (Fluent 2).
 *
 * Las clases de color se escriben completas en mapas (nunca con plantillas
 * como `text-${tono}-fg`) para que Tailwind las detecte al compilar.
 */
import { clsx } from 'clsx'
import {
  AlertCircle, CheckCircle2, Info, AlertTriangle, X, ChevronLeft, ChevronRight,
} from 'lucide-react'

// ── Tonos de color compartidos ────────────────────────────
const TONES = {
  red:    { badge: 'bg-red-tint text-red-fg border-red-line',          text: 'text-red-fg',    solid: 'bg-red-solid',    stroke: 'text-red-solid',    chip: 'bg-red-tint text-red-fg' },
  orange: { badge: 'bg-orange-tint text-orange-fg border-orange-line', text: 'text-orange-fg', solid: 'bg-orange-solid', stroke: 'text-orange-solid', chip: 'bg-orange-tint text-orange-fg' },
  yellow: { badge: 'bg-yellow-tint text-yellow-fg border-yellow-line', text: 'text-yellow-fg', solid: 'bg-yellow-solid', stroke: 'text-yellow-solid', chip: 'bg-yellow-tint text-yellow-fg' },
  green:  { badge: 'bg-green-tint text-green-fg border-green-line',    text: 'text-green-fg',  solid: 'bg-green-solid',  stroke: 'text-green-solid',  chip: 'bg-green-tint text-green-fg' },
  purple: { badge: 'bg-purple-tint text-purple-fg border-purple-line', text: 'text-purple-fg', solid: 'bg-purple-solid', stroke: 'text-purple-solid', chip: 'bg-purple-tint text-purple-fg' },
  teal:   { badge: 'bg-teal-tint text-teal-fg border-teal-line',       text: 'text-teal-fg',   solid: 'bg-teal-solid',   stroke: 'text-teal-solid',   chip: 'bg-teal-tint text-teal-fg' },
  pink:   { badge: 'bg-pink-tint text-pink-fg border-pink-line',       text: 'text-pink-fg',   solid: 'bg-pink-solid',   stroke: 'text-pink-solid',   chip: 'bg-pink-tint text-pink-fg' },
  blue:   { badge: 'bg-blue-tint text-blue-fg border-blue-line',       text: 'text-blue-fg',   solid: 'bg-blue-solid',   stroke: 'text-blue-solid',   chip: 'bg-brand-tint text-brand-fg' },
  gray:   { badge: 'bg-gray-tint text-gray-fg border-gray-line',       text: 'text-fg-3',      solid: 'bg-gray-solid',   stroke: 'text-gray-solid',   chip: 'bg-fg/[0.06] text-fg-2' },
}

export const tone = name => TONES[name] || TONES.gray

/** Tono según el score de riesgo (mismos umbrales que el backend). */
export function scoreTone(score) {
  if (score >= 85) return 'red'
  if (score >= 70) return 'orange'
  if (score >= 40) return 'yellow'
  return 'green'
}

export function scoreLabel(score) {
  if (score >= 85) return 'Crítico'
  if (score >= 70) return 'Phishing'
  if (score >= 40) return 'Sospechoso'
  return 'Legítimo'
}

// ── Badges ────────────────────────────────────────────────
const SEVERITY_TONES = { CRITICAL: 'red', HIGH: 'orange', MEDIUM: 'yellow', LOW: 'green' }

export const TYPE_LABELS = {
  bec:     'BEC',
  whaling: 'Whaling',
  spear:   'Spear',
  clone:   'Clone',
  vishing: 'Vishing',
  smishing:'Smishing',
  generic: 'Genérico',
  unknown: 'Sin clasificar',
  legitimate: 'Legítimo',
}

const TYPE_TONES = {
  bec: 'purple', whaling: 'red', spear: 'orange', clone: 'blue',
  vishing: 'pink', smishing: 'teal', generic: 'gray', unknown: 'gray',
  legitimate: 'green',
}

export function SeverityBadge({ severity }) {
  return (
    <span className={clsx('badge', tone(SEVERITY_TONES[severity] || 'green').badge)}>
      <span className="badge-dot" aria-hidden="true" />
      {severity}
    </span>
  )
}

export function TypeBadge({ type }) {
  return (
    <span className={clsx('badge', tone(TYPE_TONES[type] || 'gray').badge)}>
      {TYPE_LABELS[type] || type}
    </span>
  )
}

const STATUS = {
  // Alertas
  new:           { tone: 'blue',   label: 'Nueva' },
  acknowledged:  { tone: 'yellow', label: 'En revisión' },
  resolved:      { tone: 'green',  label: 'Resuelta' },
  false_pos:     { tone: 'gray',   label: 'Falso positivo' },
  // Incidentes
  investigating: { tone: 'yellow', label: 'En investigación' },
  contained:     { tone: 'purple', label: 'Contenido' },
  closed:        { tone: 'green',  label: 'Cerrado' },
}

export function StatusBadge({ status: s }) {
  const cfg = STATUS[s] || { tone: 'blue', label: s }
  return (
    <span className={clsx('badge', tone(cfg.tone).badge)}>
      {cfg.label}
    </span>
  )
}

export function MitreBadge({ technique }) {
  if (!technique) return null
  return (
    <span className="badge font-mono font-medium bg-subtle text-fg-2 border-stroke-strong"
          title="Técnica MITRE ATT&CK">
      {technique}
    </span>
  )
}

// ── Score visual 0–100 ────────────────────────────────────
export function ScoreBar({ score, size = 'md' }) {
  const pct = Math.min(Math.max(score, 0), 100)
  const h   = size === 'sm' ? 'h-1' : 'h-1.5'

  return (
    <div className="flex items-center gap-3">
      <div className={clsx('flex-1 bg-fg/10 rounded-full overflow-hidden', h)}
           role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(pct)}>
        <div
          className={clsx('h-full rounded-full transition-[width] duration-700 ease-decelerate',
                          tone(scoreTone(pct)).solid)}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-caption font-mono font-semibold text-fg-2 w-7 text-right tabular-nums">
        {Math.round(pct)}
      </span>
    </div>
  )
}

export function ScoreNumber({ score, className = '' }) {
  const pct = Math.round(score)
  return (
    <span className={clsx('font-mono font-semibold tabular-nums', tone(scoreTone(pct)).text, className)}>
      {pct}
    </span>
  )
}

/** Indicador circular del score (anillo de progreso). */
export function ScoreGauge({ score, size = 132, label }) {
  const pct    = Math.min(Math.max(score || 0, 0), 100)
  const stroke = 10
  const r      = (size - stroke) / 2
  const c      = 2 * Math.PI * r
  const t      = tone(scoreTone(pct))

  return (
    <div className="relative flex-shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}
           className="-rotate-90" aria-hidden="true">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth={stroke}
                className="stroke-fg/10" />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth={stroke}
                strokeLinecap="round" stroke="currentColor"
                strokeDasharray={c} strokeDashoffset={c * (1 - pct / 100)}
                className={clsx(t.stroke, 'transition-[stroke-dashoffset] duration-1000 ease-decelerate')} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center"
           role="img" aria-label={`Score de riesgo ${Math.round(pct)} de 100`}>
        <span className="text-title1 font-semibold text-fg tabular-nums leading-none">
          {Math.round(pct)}
        </span>
        <span className="text-caption text-fg-3 mt-1">{label ?? '/ 100'}</span>
      </div>
    </div>
  )
}

// ── Carga ─────────────────────────────────────────────────
/** inverted: spinner blanco para usar dentro de botones primarios. */
export function Spinner({ size = 'md', className = '', inverted = false }) {
  const s = { sm: 'h-4 w-4 border-2', md: 'h-6 w-6 border-[3px]', lg: 'h-9 w-9 border-[3px]' }[size]
  return (
    <div role="status" aria-label="Cargando" className={clsx(
      'animate-spin rounded-full flex-shrink-0',
      inverted ? 'border-white/30 border-t-white' : 'border-fg/15 border-t-brand-fg',
      s, className
    )} />
  )
}

export function LoadingScreen() {
  return (
    <div className="flex items-center justify-center h-64 animate-fade-in">
      <div className="flex flex-col items-center gap-3">
        <Spinner size="lg" />
        <p className="text-fg-3 text-body">Cargando…</p>
      </div>
    </div>
  )
}

// ── Estado vacío ──────────────────────────────────────────
export function EmptyState({ icon: Icon, title, description, action }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 sm:py-16 px-4 text-center">
      {Icon && (
        <div className="h-14 w-14 rounded-full bg-fg/[0.05] flex items-center justify-center mb-4">
          <Icon className="h-7 w-7 text-fg-3" strokeWidth={1.5} aria-hidden="true" />
        </div>
      )}
      <h3 className="text-subtitle2 font-semibold text-fg mb-1">{title}</h3>
      {description && <p className="text-fg-3 text-body max-w-sm mb-4">{description}</p>}
      {action}
    </div>
  )
}

// ── Message bar (Fluent) ──────────────────────────────────
const INTENTS = {
  info:    { cls: 'bg-brand-tint border-brand-line',   icon: Info,          iconCls: 'text-brand-fg' },
  success: { cls: 'bg-green-tint border-green-line',   icon: CheckCircle2,  iconCls: 'text-green-fg' },
  warning: { cls: 'bg-yellow-tint border-yellow-line', icon: AlertTriangle, iconCls: 'text-yellow-fg' },
  error:   { cls: 'bg-red-tint border-red-line',       icon: AlertCircle,   iconCls: 'text-red-fg' },
}

export function MessageBar({
  intent = 'info', title, children, onDismiss, dismissLabel = 'Cerrar mensaje',
  action, className, role,
}) {
  const cfg  = INTENTS[intent] || INTENTS.info
  const Icon = cfg.icon
  return (
    <div role={role || (intent === 'error' ? 'alert' : 'status')}
         className={clsx('flex items-start gap-3 rounded-md border px-3 py-2.5 animate-fade-in',
                         cfg.cls, className)}>
      <Icon className={clsx('h-[18px] w-[18px] flex-shrink-0 mt-px', cfg.iconCls)} aria-hidden="true" />
      <div className="flex-1 min-w-0 text-body text-fg break-words">
        {title && <p className="font-semibold">{title}</p>}
        {children}
      </div>
      {action}
      {onDismiss && (
        // Mantener type="button": el mensaje suele ir dentro de un <form> y un
        // botón sin tipo lo enviaría de nuevo al cerrarlo.
        <button type="button" onClick={onDismiss} aria-label={dismissLabel}
          className="btn-ghost btn-icon h-6 w-6 -my-0.5 -mr-1 text-fg-2">
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      )}
    </div>
  )
}

export function ErrorBanner({ message, onDismiss }) {
  if (!message) return null
  return (
    <MessageBar intent="error" onDismiss={onDismiss} dismissLabel="Cerrar mensaje de error">
      {message}
    </MessageBar>
  )
}

// ── Encabezado de página ──────────────────────────────────
export function PageHeader({ title, description, icon: Icon, actions, meta }) {
  return (
    <header className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3 sm:gap-4">
      <div className="flex items-start gap-3 min-w-0">
        {Icon && (
          <div className="hidden sm:flex h-10 w-10 rounded-lg bg-brand-tint text-brand-fg
                          items-center justify-center flex-shrink-0">
            <Icon className="h-5 w-5" strokeWidth={1.75} aria-hidden="true" />
          </div>
        )}
        <div className="min-w-0">
          <h1 className="text-page-title">{title}</h1>
          {description && <p className="text-fg-3 text-body mt-0.5">{description}</p>}
          {meta}
        </div>
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2 flex-shrink-0">{actions}</div>}
    </header>
  )
}

/** Tarjeta con encabezado (título + acciones opcionales). */
export function Section({ title, description, actions, children, className, bodyClassName }) {
  return (
    <section className={clsx('card', className)}>
      {(title || actions) && (
        <div className="card-header">
          <div className="min-w-0">
            {title && <h2 className="text-section">{title}</h2>}
            {description && <p className="text-caption text-fg-3 mt-0.5">{description}</p>}
          </div>
          {actions}
        </div>
      )}
      <div className={clsx('p-4 sm:p-5', bodyClassName)}>{children}</div>
    </section>
  )
}

// ── Paginación ────────────────────────────────────────────
export function Pagination({ page, pages, count, onChange, noun = 'resultados' }) {
  if (pages <= 1) return null
  return (
    <nav className="flex items-center justify-between gap-3 px-4 sm:px-5 py-3 border-t border-stroke"
         aria-label="Paginación">
      <p className="text-caption text-fg-3 tabular-nums">
        Página {page} de {pages}{count != null && ` · ${count} ${noun}`}
      </p>
      <div className="flex gap-1">
        <button disabled={page <= 1} onClick={() => onChange(page - 1)}
          className="btn-secondary btn-icon" aria-label="Página anterior">
          <ChevronLeft className="h-4 w-4" aria-hidden="true" />
        </button>
        <button disabled={page >= pages} onClick={() => onChange(page + 1)}
          className="btn-secondary btn-icon" aria-label="Página siguiente">
          <ChevronRight className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
    </nav>
  )
}

// ── KPI ───────────────────────────────────────────────────
export function StatCard({ label, value, sub, color = 'blue', icon: Icon }) {
  return (
    <div className="card p-4 min-w-0">
      <div className="flex items-start justify-between gap-2">
        <p className="text-caption font-semibold text-fg-3 leading-tight">{label}</p>
        {Icon && (
          <span className={clsx('h-8 w-8 rounded-md flex items-center justify-center flex-shrink-0 -mt-1',
                                tone(color).chip)}>
            <Icon className="h-4 w-4" strokeWidth={2} aria-hidden="true" />
          </span>
        )}
      </div>
      <p className="text-title2 font-semibold text-fg tabular-nums mt-1">{value ?? '—'}</p>
      {sub && <p className="text-caption text-fg-3 mt-1 truncate">{sub}</p>}
    </div>
  )
}
