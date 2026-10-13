import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, SlidersHorizontal, RefreshCw, Bell, X, ChevronRight } from 'lucide-react'
import { clsx } from 'clsx'
import { alertsAPI } from '../services/api'
import { useFetch } from '../hooks/useFetch'
import { useIsDesktop } from '../hooks/useMediaQuery'
import {
  SeverityBadge, TypeBadge, StatusBadge, ScoreNumber,
  MitreBadge, LoadingScreen, EmptyState, ErrorBanner,
  PageHeader, Pagination, tone, scoreTone,
} from '../components/UI'
import { format } from 'date-fns'
import { es } from 'date-fns/locale'

const PAGE_SIZE = 20

const SEVERITY_OPTIONS = [
  ['', 'Todas'], ['CRITICAL', 'Crítica'], ['HIGH', 'Alta'], ['MEDIUM', 'Media'], ['LOW', 'Baja'],
]
const TYPE_OPTIONS = [
  ['', 'Todos'], ['bec', 'BEC'], ['whaling', 'Whaling'], ['spear', 'Spear'], ['clone', 'Clone'],
  ['vishing', 'Vishing'], ['smishing', 'Smishing'], ['generic', 'Genérico'],
]
const STATUS_OPTIONS = [
  ['', 'Todos'], ['new', 'Nueva'], ['acknowledged', 'En revisión'],
  ['resolved', 'Resuelta'], ['false_pos', 'Falso positivo'],
]
const FILTER_LABELS = {
  severity:      ['Severidad', SEVERITY_OPTIONS],
  phishing_type: ['Tipo', TYPE_OPTIONS],
  status:        ['Estado', STATUS_OPTIONS],
  domain:        ['Dominio', null],
}
const EMPTY_FILTERS = { severity: '', phishing_type: '', status: '', domain: '' }

// Score con mini barra para la tabla
function ScoreCell({ score }) {
  return (
    <div className="flex items-center gap-2.5">
      <ScoreNumber score={score} className="text-body w-7" />
      <div className="w-14 h-1 bg-fg/10 rounded-full overflow-hidden" aria-hidden="true">
        <div className={clsx('h-full rounded-full', tone(scoreTone(score)).solid)}
             style={{ width: `${Math.min(score, 100)}%` }} />
      </div>
    </div>
  )
}

// Tarjeta de alerta para móvil
function AlertCard({ alert, onClick }) {
  return (
    <button onClick={onClick}
      className="w-full text-left px-4 py-3.5 hover:bg-fg/[0.03] active:bg-fg/[0.06] transition-colors">
      <div className="flex items-start justify-between gap-3 mb-2">
        <p className="text-body font-semibold text-fg leading-snug flex-1 min-w-0">{alert.title}</p>
        <ScoreNumber score={alert.risk_score} className="text-subtitle2 flex-shrink-0" />
      </div>
      <div className="flex flex-wrap gap-1.5 mb-2">
        <SeverityBadge severity={alert.severity} />
        <TypeBadge type={alert.phishing_type} />
        <StatusBadge status={alert.status} />
        <MitreBadge technique={alert.mitre_technique} />
      </div>
      <div className="flex items-center justify-between gap-2 text-caption text-fg-3">
        <span className="truncate font-mono">{alert.sender_domain || '—'}</span>
        <span className="whitespace-nowrap tabular-nums">
          {format(new Date(alert.detected_at), 'dd/MM HH:mm', { locale: es })}
        </span>
      </div>
    </button>
  )
}

function FilterSelect({ id, label, value, options, onChange }) {
  return (
    <div>
      <label htmlFor={id} className="field-label">{label}</label>
      <select id={id} className="input" value={value} onChange={e => onChange(e.target.value)}>
        {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </div>
  )
}

export default function AlertsPage() {
  const navigate  = useNavigate()
  const isDesktop = useIsDesktop()
  const [page,    setPage]    = useState(1)
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [showFilters, setShowFilters] = useState(false)

  const fetchAlerts = useCallback(() =>
    alertsAPI.list({
      page, page_size: PAGE_SIZE, ordering: '-detected_at',
      ...(filters.severity      && { severity:      filters.severity }),
      ...(filters.phishing_type && { phishing_type: filters.phishing_type }),
      ...(filters.status        && { status:        filters.status }),
      ...(filters.domain        && { domain:        filters.domain }),
    }), [page, filters])

  const { data, loading, error, refetch } = useFetch(fetchAlerts, [page, filters])
  const alerts = data?.results || []
  const count  = data?.count   || 0
  const pages  = Math.ceil(count / PAGE_SIZE)

  const setFilter = (key, val) => {
    setFilters(f => ({ ...f, [key]: val }))
    setPage(1)
  }

  const activeFilters = Object.entries(filters).filter(([, v]) => v)
  const openAlert = id => navigate(`/alerts/${id}`)

  return (
    <div className="page">
      <PageHeader
        icon={Bell}
        title="Alertas"
        description={`${count} alertas en total`}
        actions={<>
          <button onClick={() => setShowFilters(s => !s)}
            className={clsx('btn-secondary', showFilters && 'bg-fg/[0.06]')}
            aria-expanded={showFilters} aria-controls="alert-filters">
            <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />
            Filtros
            {activeFilters.length > 0 && (
              <span className="h-5 min-w-[20px] px-1.5 rounded-full bg-brand text-on-brand text-caption
                               font-semibold flex items-center justify-center">
                {activeFilters.length}
              </span>
            )}
          </button>
          <button onClick={refetch} className="btn-secondary">
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            Actualizar
          </button>
        </>}
      />

      {error && <ErrorBanner message={error} />}

      {/* Filtros */}
      {showFilters && (
        <div id="alert-filters" className="card p-4 sm:p-5 animate-slide-up">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <FilterSelect id="f-severity" label="Severidad" value={filters.severity}
                          options={SEVERITY_OPTIONS} onChange={v => setFilter('severity', v)} />
            <FilterSelect id="f-type" label="Tipo de phishing" value={filters.phishing_type}
                          options={TYPE_OPTIONS} onChange={v => setFilter('phishing_type', v)} />
            <FilterSelect id="f-status" label="Estado" value={filters.status}
                          options={STATUS_OPTIONS} onChange={v => setFilter('status', v)} />
            <div>
              <label htmlFor="f-domain" className="field-label">Dominio remitente</label>
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-fg-3"
                        aria-hidden="true" />
                <input id="f-domain" className="input pl-8" placeholder="evil.tk"
                  autoCapitalize="none" autoComplete="off"
                  value={filters.domain}
                  onChange={e => setFilter('domain', e.target.value)} />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Filtros activos como chips */}
      {activeFilters.length > 0 && (
        <div className="flex flex-wrap items-center gap-2" aria-label="Filtros activos">
          {activeFilters.map(([key, value]) => {
            const [label, options] = FILTER_LABELS[key]
            const display = options ? options.find(([v]) => v === value)?.[1] : value
            return (
              <span key={key}
                    className="inline-flex items-center gap-1 h-7 pl-2.5 pr-1 rounded-full bg-brand-tint
                               border border-brand-line text-caption text-fg">
                <span className="text-fg-3">{label}:</span>
                <span className="font-semibold">{display}</span>
                <button onClick={() => setFilter(key, '')}
                        className="h-5 w-5 rounded-full flex items-center justify-center hover:bg-fg/10"
                        aria-label={`Quitar filtro ${label}`}>
                  <X className="h-3 w-3" aria-hidden="true" />
                </button>
              </span>
            )
          })}
          <button onClick={() => { setFilters(EMPTY_FILTERS); setPage(1) }}
                  className="btn-ghost h-7 text-caption">
            Limpiar todo
          </button>
        </div>
      )}

      {/* Lista */}
      <div className="card overflow-hidden">
        {loading ? <LoadingScreen /> : alerts.length === 0 ? (
          <EmptyState
            icon={Bell}
            title="Sin alertas"
            description="No hay alertas que coincidan con los filtros."
          />
        ) : (
          <>
            {isDesktop ? (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[760px]">
                  <thead>
                    <tr>
                      <th scope="col" className="table-head pl-5">Alerta</th>
                      <th scope="col" className="table-head">Severidad</th>
                      <th scope="col" className="table-head">Tipo</th>
                      <th scope="col" className="table-head">Estado</th>
                      <th scope="col" className="table-head">Score</th>
                      <th scope="col" className="table-head">MITRE</th>
                      <th scope="col" className="table-head">Detectada</th>
                      <th scope="col" className="table-head w-8"><span className="sr-only">Abrir</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    {alerts.map(alert => (
                      <tr key={alert.id}
                          onClick={() => openAlert(alert.id)}
                          onKeyDown={e => { if (e.key === 'Enter') openAlert(alert.id) }}
                          tabIndex={0}
                          className="table-row group focus-visible:bg-fg/[0.04]">
                        <td className="px-4 pl-5 py-3">
                          <p className="text-body font-semibold text-fg truncate max-w-xs">{alert.title}</p>
                          {alert.sender_domain && (
                            <p className="text-caption text-fg-3 font-mono truncate mt-0.5">{alert.sender_domain}</p>
                          )}
                        </td>
                        <td className="px-4 py-3"><SeverityBadge severity={alert.severity} /></td>
                        <td className="px-4 py-3"><TypeBadge type={alert.phishing_type} /></td>
                        <td className="px-4 py-3"><StatusBadge status={alert.status} /></td>
                        <td className="px-4 py-3"><ScoreCell score={alert.risk_score} /></td>
                        <td className="px-4 py-3"><MitreBadge technique={alert.mitre_technique} /></td>
                        <td className="px-4 py-3 text-caption text-fg-3 whitespace-nowrap tabular-nums">
                          {format(new Date(alert.detected_at), 'dd/MM HH:mm', { locale: es })}
                        </td>
                        <td className="pr-4 py-3">
                          <ChevronRight className="h-4 w-4 text-fg-4 group-hover:text-fg-2 transition-colors"
                                        aria-hidden="true" />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="divide-y divide-stroke">
                {alerts.map(alert => (
                  <AlertCard key={alert.id} alert={alert} onClick={() => openAlert(alert.id)} />
                ))}
              </div>
            )}

            <Pagination page={page} pages={pages} count={count} onChange={setPage} />
          </>
        )}
      </div>
    </div>
  )
}
