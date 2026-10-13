import { useNavigate } from 'react-router-dom'
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid,
  ResponsiveContainer, PieChart, Pie, Cell,
} from 'recharts'
import {
  AlertTriangle, ShieldCheck, TrendingUp, RefreshCw,
  Target, Layers, FileSearch, ChevronRight,
} from 'lucide-react'
import { clsx } from 'clsx'
import { alertsAPI } from '../services/api'
import { useFetch, usePolling } from '../hooks/useFetch'
import { useTheme } from '../store/ThemeContext'
import {
  StatCard, LoadingScreen, ErrorBanner, TypeBadge, SeverityBadge,
  PageHeader, Section, TYPE_LABELS, tone,
} from '../components/UI'
import { chartPalette, tooltipStyle, TYPE_COLORS } from '../components/chartTheme'
import { format } from 'date-fns'
import { es } from 'date-fns/locale'

const SEVERITY_ROWS = [
  { key: 'CRITICAL', label: 'Crítica', tone: 'red' },
  { key: 'HIGH',     label: 'Alta',    tone: 'orange' },
  { key: 'MEDIUM',   label: 'Media',   tone: 'yellow' },
  { key: 'LOW',      label: 'Baja',    tone: 'green' },
]

function TrendTooltip({ active, payload, label, theme }) {
  if (!active || !payload?.length) return null
  const { contentStyle, labelStyle, itemStyle } = tooltipStyle(theme)
  return (
    <div style={contentStyle}>
      <p style={labelStyle}>{format(new Date(label + 'T12:00:00'), "EEEE d 'de' MMMM", { locale: es })}</p>
      <p style={itemStyle}>{payload[0].value} alertas</p>
    </div>
  )
}

export default function DashboardPage() {
  const navigate  = useNavigate()
  const { theme } = useTheme()
  const palette   = chartPalette(theme)

  const { data: stats, loading, error, refetch } =
    usePolling(() => alertsAPI.stats(), 30000)
  const { data: alertsData } =
    useFetch(() => alertsAPI.list({ page_size: 5, ordering: '-detected_at' }))

  if (loading) return <LoadingScreen />

  const daily  = stats?.daily_last_7_days || []
  const byType = Object.entries(stats?.by_type || {})
    .filter(([k]) => k !== 'legitimate')
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value)
  const typeTotal = byType.reduce((acc, t) => acc + t.value, 0) || 1

  const recent = alertsData?.results || []

  return (
    <div className="page">
      <PageHeader
        title="Dashboard"
        description="Resumen de la actividad de phishing · se actualiza cada 30 s"
        actions={<>
          <button onClick={refetch} className="btn-secondary">
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            Actualizar
          </button>
          <button onClick={() => navigate('/analyze')} className="btn-primary">
            <FileSearch className="h-4 w-4" aria-hidden="true" />
            Analizar correo
          </button>
        </>}
      />

      {error && <ErrorBanner message={error} />}

      {/* KPIs — 2 columnas en móvil, 4 en desktop */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        <StatCard label="Total alertas"    value={stats?.total ?? 0}
                  sub={stats?.new != null ? `${stats.new} nuevas sin revisar` : undefined}
                  icon={Layers}        color="blue" />
        <StatCard label="Críticas"         value={stats?.critical ?? 0}
                  sub="Acción inmediata"
                  icon={AlertTriangle} color="red" />
        <StatCard label="Esta semana"      value={stats?.week_total ?? 0}
                  sub="Últimos 7 días"
                  icon={TrendingUp}    color="orange" />
        <StatCard label="Campañas activas" value={stats?.active_campaigns ?? 0}
                  sub="Mismo dominio en 1 h"
                  icon={Target}        color="purple" />
      </div>

      {/* Gráficas — apiladas en móvil, lado a lado en desktop */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-5">
        <Section title="Alertas — últimos 7 días" className="lg:col-span-2" bodyClassName="pt-4 pb-3 pl-1 pr-4">
          <ResponsiveContainer width="100%" height={232}>
            <AreaChart data={daily} margin={{ top: 8, right: 4, bottom: 0, left: -16 }}>
              <defs>
                <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%"   stopColor={palette.brand} stopOpacity={0.28} />
                  <stop offset="100%" stopColor={palette.brand} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid vertical={false} stroke={palette.grid} strokeDasharray="3 3" />
              <XAxis dataKey="date" tick={{ fill: palette.axis, fontSize: 12 }}
                     axisLine={false} tickLine={false} dy={6}
                     tickFormatter={d => format(new Date(d + 'T12:00:00'), 'd MMM', { locale: es })} />
              <YAxis tick={{ fill: palette.axis, fontSize: 12 }} allowDecimals={false}
                     axisLine={false} tickLine={false} />
              <Tooltip content={<TrendTooltip theme={theme} />}
                       cursor={{ stroke: palette.brand, strokeWidth: 1, strokeDasharray: '4 4' }} />
              <Area type="monotone" dataKey="count" stroke={palette.brand} strokeWidth={2.5}
                    fill="url(#areaGrad)"
                    activeDot={{ r: 5, strokeWidth: 2, stroke: theme === 'dark' ? '#292929' : '#fff' }} />
            </AreaChart>
          </ResponsiveContainer>
        </Section>

        <Section title="Por tipo de phishing">
          {byType.length > 0 ? (
            <div className="flex flex-col sm:flex-row items-center gap-5">
              <div className="w-[168px] flex-shrink-0">
                <ResponsiveContainer width="100%" height={168}>
                  <PieChart>
                    <Pie data={byType} dataKey="value" nameKey="name"
                         cx="50%" cy="50%" outerRadius={78} innerRadius={52}
                         paddingAngle={2} stroke="none">
                      {byType.map(entry => (
                        <Cell key={entry.name} fill={TYPE_COLORS[entry.name] || '#8a8a8a'} />
                      ))}
                    </Pie>
                    <Tooltip {...tooltipStyle(theme)}
                             formatter={(v, name) => [`${v} alertas`, TYPE_LABELS[name] || name]} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <ul className="w-full min-w-0 flex-1 space-y-1.5" aria-label="Leyenda por tipo">
                {byType.map(t => (
                  <li key={t.name} className="flex items-center gap-2.5 text-body">
                    <span className="h-2.5 w-2.5 rounded-sm flex-shrink-0"
                          style={{ background: TYPE_COLORS[t.name] || '#8a8a8a' }} aria-hidden="true" />
                    <span className="flex-1 text-fg-2 truncate">{TYPE_LABELS[t.name] || t.name}</span>
                    <span className="text-fg-3 text-caption tabular-nums">
                      {Math.round(t.value / typeTotal * 100)}%
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-40 text-center">
              <ShieldCheck className="h-8 w-8 text-fg-4 mb-2" strokeWidth={1.5} aria-hidden="true" />
              <p className="text-fg-3 text-body">Sin datos aún</p>
            </div>
          )}
        </Section>
      </div>

      {/* Severidad */}
      <Section title="Distribución por severidad">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {SEVERITY_ROWS.map(({ key, label, tone: t }) => {
            const count = stats?.by_severity?.[key] || 0
            const total = stats?.total || 1
            const pct   = Math.round(count / total * 100)
            return (
              <div key={key} className="well p-3.5">
                <div className="flex items-center gap-2 mb-1">
                  <span className={clsx('h-2 w-2 rounded-full', tone(t).solid)} aria-hidden="true" />
                  <p className="text-caption font-semibold text-fg-2">{label}</p>
                </div>
                <p className="text-title3 font-semibold text-fg tabular-nums">{count}</p>
                <div className="h-1 bg-fg/10 rounded-full overflow-hidden mt-2.5">
                  <div className={clsx('h-full rounded-full transition-[width] duration-700 ease-decelerate',
                                       tone(t).solid)}
                       style={{ width: `${pct}%` }} />
                </div>
                <p className="text-caption text-fg-3 mt-1.5">{pct}% del total</p>
              </div>
            )
          })}
        </div>
      </Section>

      {/* Alertas recientes */}
      <Section
        title="Alertas recientes"
        bodyClassName="p-0"
        actions={
          <button onClick={() => navigate('/alerts')} className="btn-ghost text-brand-fg hover:text-brand-fg">
            Ver todas <ChevronRight className="h-4 w-4" aria-hidden="true" />
          </button>
        }
      >
        {recent.length === 0 ? (
          <div className="px-4 py-10 text-center">
            <ShieldCheck className="h-8 w-8 text-fg-4 mx-auto mb-2" strokeWidth={1.5} aria-hidden="true" />
            <p className="text-fg-3 text-body">Sin alertas recientes</p>
          </div>
        ) : (
          <ul className="divide-y divide-stroke">
            {recent.map(alert => (
              <li key={alert.id}>
                <button
                  onClick={() => navigate(`/alerts/${alert.id}`)}
                  className="w-full flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4
                             px-4 sm:px-5 py-3 hover:bg-fg/[0.03] transition-colors text-left group"
                >
                  <p className="flex-1 text-body font-medium text-fg truncate min-w-0 order-1 sm:order-2">
                    {alert.title}
                  </p>
                  <div className="flex gap-1.5 flex-shrink-0 order-2 sm:order-1 sm:w-48">
                    <SeverityBadge severity={alert.severity} />
                    <TypeBadge type={alert.phishing_type} />
                  </div>
                  <span className="text-caption text-fg-3 whitespace-nowrap flex-shrink-0 order-3 tabular-nums">
                    {format(new Date(alert.detected_at), 'HH:mm · d MMM', { locale: es })}
                  </span>
                  <ChevronRight className="hidden sm:block h-4 w-4 text-fg-4 group-hover:text-fg-2
                                           transition-colors order-4" aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  )
}
