/**
 * Sentryx v2 — Páginas de Incidentes y Threat Intelligence (responsive).
 * Móvil: listas en formato tarjeta y formularios de una columna.
 * Desktop: tablas y formularios de dos columnas.
 */
import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  FolderOpen, Plus, Globe2, ShieldCheck, Search, ChevronRight,
  ShieldAlert, Database, X,
} from 'lucide-react'
import { clsx } from 'clsx'
import { incidentsAPI, threatIntelAPI } from '../services/api'
import { useFetch, useSubmit } from '../hooks/useFetch'
import { useIsDesktop } from '../hooks/useMediaQuery'
import { useAuth } from '../store/AuthContext'
import {
  SeverityBadge, StatusBadge, MitreBadge, LoadingScreen, EmptyState,
  ErrorBanner, Spinner, PageHeader, Pagination, MessageBar, tone,
} from '../components/UI'
import { format } from 'date-fns'
import { es } from 'date-fns/locale'

const SEVERITY_OPTIONS = [['CRITICAL', 'Crítica'], ['HIGH', 'Alta'], ['MEDIUM', 'Media'], ['LOW', 'Baja']]

// Panel de formulario desplegable con título y botón de cerrar
function FormPanel({ title, onClose, children }) {
  return (
    <section className="card animate-slide-up">
      <div className="card-header">
        <h2 className="text-section">{title}</h2>
        <button onClick={onClose} className="btn-ghost btn-icon" aria-label={`Cerrar: ${title}`}>
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
      <div className="p-4 sm:p-5">{children}</div>
    </section>
  )
}


// ═══════════════════════════════════════════════════════════
// IncidentsPage — lista y gestión de incidentes
// ═══════════════════════════════════════════════════════════
const EMPTY_INCIDENT = { title: '', severity: 'HIGH', description: '' }

export function IncidentsPage() {
  const navigate      = useNavigate()
  const { isAnalyst } = useAuth()
  const [page, setPage]             = useState(1)
  const [showCreate, setShowCreate] = useState(false)
  const [newIncident, setNewIncident] = useState(EMPTY_INCIDENT)

  const fetchInc = useCallback(() => incidentsAPI.list({ page, page_size: 20 }), [page])
  const { data, loading, error, refetch } = useFetch(fetchInc, [page])

  const { submit: createInc, submitting, error: createError } = useSubmit(
    useCallback(d => incidentsAPI.create(d), [])
  )

  const incidents = data?.results || []
  const count     = data?.count   || 0
  const pages     = Math.ceil(count / 20)

  const handleCreate = async e => {
    e.preventDefault()
    try {
      await createInc(newIncident)
      setShowCreate(false)
      setNewIncident(EMPTY_INCIDENT)
      refetch()
    } catch { /* useSubmit ya expone el error */ }
  }

  const set = key => e => setNewIncident(n => ({ ...n, [key]: e.target.value }))

  return (
    <div className="page">
      <PageHeader
        icon={FolderOpen}
        title="Incidentes"
        description={`${count} incidentes en total`}
        actions={isAnalyst && !showCreate && (
          <button onClick={() => setShowCreate(true)} className="btn-primary">
            <Plus className="h-4 w-4" aria-hidden="true" />
            Nuevo incidente
          </button>
        )}
      />

      {error && <ErrorBanner message={error} />}

      {showCreate && (
        <FormPanel title="Crear incidente" onClose={() => setShowCreate(false)}>
          <form onSubmit={handleCreate} className="space-y-4">
            {createError && <ErrorBanner message={createError} />}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="sm:col-span-2">
                <label htmlFor="inc-title" className="field-label">Título</label>
                <input id="inc-title" required className="input"
                  placeholder="Campaña de BEC contra el área financiera"
                  value={newIncident.title} onChange={set('title')} />
              </div>
              <div>
                <label htmlFor="inc-severity" className="field-label">Severidad</label>
                <select id="inc-severity" className="input"
                  value={newIncident.severity} onChange={set('severity')}>
                  {SEVERITY_OPTIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </div>
            </div>
            <div>
              <label htmlFor="inc-description" className="field-label">Descripción</label>
              <textarea id="inc-description" rows={3} className="input resize-y"
                placeholder="Qué se detectó, alcance y primeras acciones…"
                value={newIncident.description} onChange={set('description')} />
            </div>
            <div className="flex gap-2 justify-end">
              <button type="button" onClick={() => setShowCreate(false)} className="btn-secondary">
                Cancelar
              </button>
              <button type="submit" disabled={submitting} className="btn-primary">
                {submitting && <Spinner size="sm" inverted />} Crear incidente
              </button>
            </div>
          </form>
        </FormPanel>
      )}

      <div className="card overflow-hidden">
        {loading ? <LoadingScreen /> : incidents.length === 0 ? (
          <EmptyState icon={FolderOpen} title="Sin incidentes"
            description="Crea un incidente para agrupar alertas relacionadas." />
        ) : (
          <ul className="divide-y divide-stroke">
            {incidents.map(inc => (
              <li key={inc.id}>
                <button onClick={() => navigate(`/incidents/${inc.id}`)}
                  className="w-full px-4 sm:px-5 py-3.5 hover:bg-fg/[0.03] transition-colors text-left group
                             flex items-center gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-1.5 mb-1.5">
                      <SeverityBadge severity={inc.severity} />
                      <StatusBadge status={inc.status} />
                      {inc.mitre_technique && <MitreBadge technique={inc.mitre_technique} />}
                    </div>
                    <p className="text-body font-semibold text-fg truncate">{inc.title}</p>
                    <p className="text-caption text-fg-3">
                      {inc.alert_count} alerta{inc.alert_count !== 1 ? 's' : ''} relacionada{inc.alert_count !== 1 ? 's' : ''}
                    </p>
                  </div>
                  <span className="text-caption text-fg-3 whitespace-nowrap tabular-nums">
                    {format(new Date(inc.created_at), 'dd/MM HH:mm', { locale: es })}
                  </span>
                  <ChevronRight className="h-4 w-4 text-fg-4 group-hover:text-fg-2 flex-shrink-0"
                                aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        )}
        <Pagination page={page} pages={pages} count={count} onChange={setPage} noun="incidentes" />
      </div>
    </div>
  )
}


// ═══════════════════════════════════════════════════════════
// ThreatIntelPage — IOCs y estadísticas de Threat Intelligence
// ═══════════════════════════════════════════════════════════
const SOURCE_TONES = {
  phishtank: 'blue', openphish: 'teal', misp: 'purple', virustotal: 'orange', manual: 'gray',
}

const EMPTY_IOC = { ioc_type: 'url', value: '', threat_level: 'HIGH', description: '' }

function SourceTag({ source }) {
  const t = tone(SOURCE_TONES[source] || 'gray')
  return (
    <span className={clsx('inline-flex items-center gap-1.5 text-caption font-semibold capitalize', t.text)}>
      <span className={clsx('h-2 w-2 rounded-full', t.solid)} aria-hidden="true" />
      {source}
    </span>
  )
}

export function ThreatIntelPage() {
  const { isAnalyst } = useAuth()
  const isDesktop     = useIsDesktop()
  const [checkVal, setCheckVal]       = useState('')
  const [checkResult, setCheckResult] = useState(null)
  const [checking, setChecking]       = useState(false)
  const [checkError, setCheckError]   = useState(null)
  const [page, setPage]               = useState(1)
  const [showAddIOC, setShowAddIOC]   = useState(false)
  const [newIOC, setNewIOC]           = useState(EMPTY_IOC)

  const { data: stats } = useFetch(() => threatIntelAPI.stats())
  const fetchIOCs = useCallback(() => threatIntelAPI.iocs({ page, page_size: 20 }), [page])
  const { data: iocsData, refetch } = useFetch(fetchIOCs, [page])
  const { submit: addIOC, submitting: addingIOC, error: addError } = useSubmit(
    useCallback(d => threatIntelAPI.addIOC(d), [])
  )

  const iocs  = iocsData?.results || []
  const count = iocsData?.count   || 0
  const pages = Math.ceil(count / 20)

  const handleCheck = async e => {
    e.preventDefault()
    if (!checkVal.trim()) return
    setChecking(true)
    setCheckError(null)
    try {
      const r = await threatIntelAPI.check({ value: checkVal.trim() })
      setCheckResult(r.data)
    } catch {
      setCheckError('No se pudo consultar la reputación. Intenta de nuevo.')
    } finally {
      setChecking(false)
    }
  }

  const handleAddIOC = async e => {
    e.preventDefault()
    try {
      await addIOC(newIOC)
      setShowAddIOC(false)
      setNewIOC(EMPTY_IOC)
      refetch()
    } catch { /* useSubmit ya expone el error */ }
  }

  const setIOC = key => e => setNewIOC(n => ({ ...n, [key]: e.target.value }))

  return (
    <div className="page">
      <PageHeader
        icon={Globe2}
        title="Threat Intelligence"
        description={`IOCs activos: ${stats?.total_active ?? '…'}`}
        actions={isAnalyst && !showAddIOC && (
          <button onClick={() => setShowAddIOC(true)} className="btn-primary">
            <Plus className="h-4 w-4" aria-hidden="true" />
            Añadir IOC manual
          </button>
        )}
      />

      {/* IOCs por fuente */}
      {stats && Object.keys(stats.by_source || {}).length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
          {Object.entries(stats.by_source).map(([src, cnt]) => (
            <div key={src} className="card p-4">
              <SourceTag source={src} />
              <p className="text-title3 font-semibold text-fg tabular-nums mt-1">{cnt}</p>
            </div>
          ))}
        </div>
      )}

      {/* Consulta rápida */}
      <section className="card p-4 sm:p-5">
        <h2 className="text-section">Consulta rápida de reputación</h2>
        <p className="text-caption text-fg-3 mt-0.5 mb-4">
          Busca una URL, dominio o IP en todos los feeds activos.
        </p>
        <form onSubmit={handleCheck} className="flex flex-col sm:flex-row gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-fg-3"
                    aria-hidden="true" />
            <input className="input input-lg pl-9" autoCapitalize="none" autoComplete="off"
              placeholder="URL, dominio o IP a consultar…" aria-label="Valor a consultar"
              value={checkVal} onChange={e => setCheckVal(e.target.value)} />
          </div>
          <button type="submit" disabled={checking || !checkVal.trim()} className="btn-primary btn-lg">
            {checking ? <Spinner size="sm" inverted /> : <ShieldCheck className="h-4 w-4" aria-hidden="true" />}
            Verificar
          </button>
        </form>

        {checkError && <div className="mt-3"><ErrorBanner message={checkError} /></div>}

        {checkResult && (
          <div className="mt-4" aria-live="polite">
            {checkResult.found ? (
              <MessageBar intent="error" title="IOC encontrado en la lista negra" role="status">
                <div className="flex flex-wrap gap-x-4 gap-y-1 mt-1 text-caption text-fg-2">
                  <span>Tipo: <strong className="text-fg">{checkResult.ioc_type}</strong></span>
                  <span>Nivel: <strong className="text-fg">{checkResult.threat_level}</strong></span>
                  <span>Fuente: <strong className="text-fg">{checkResult.source}</strong></span>
                  {checkResult.mitre_technique && <span>MITRE: <strong className="text-fg font-mono">{checkResult.mitre_technique}</strong></span>}
                  {checkResult.brand_targeted && <span>Marca suplantada: <strong className="text-fg">{checkResult.brand_targeted}</strong></span>}
                </div>
              </MessageBar>
            ) : (
              <MessageBar intent="success" title="No encontrado en ningún feed activo" />
            )}
          </div>
        )}
      </section>

      {/* Añadir IOC manual */}
      {showAddIOC && (
        <FormPanel title="Añadir IOC manual" onClose={() => setShowAddIOC(false)}>
          <form onSubmit={handleAddIOC} className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {addError && <div className="sm:col-span-2"><ErrorBanner message={addError} /></div>}
            <div>
              <label htmlFor="ioc-type" className="field-label">Tipo de IOC</label>
              <select id="ioc-type" className="input" value={newIOC.ioc_type} onChange={setIOC('ioc_type')}>
                <option value="url">URL</option>
                <option value="domain">Dominio</option>
                <option value="ip">IP</option>
                <option value="sender">Remitente (hash)</option>
              </select>
            </div>
            <div>
              <label htmlFor="ioc-level" className="field-label">Nivel de amenaza</label>
              <select id="ioc-level" className="input" value={newIOC.threat_level} onChange={setIOC('threat_level')}>
                {SEVERITY_OPTIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </div>
            <div className="sm:col-span-2">
              <label htmlFor="ioc-value" className="field-label">Valor</label>
              <input id="ioc-value" required className="input font-mono"
                autoCapitalize="none" autoComplete="off"
                placeholder="https://banco-seguro.tk/login"
                value={newIOC.value} onChange={setIOC('value')} />
            </div>
            <div className="sm:col-span-2">
              <label htmlFor="ioc-description" className="field-label">
                Descripción <span className="font-normal text-fg-3">(opcional)</span>
              </label>
              <input id="ioc-description" className="input"
                placeholder="Suplantación de banco detectada en campaña…"
                value={newIOC.description} onChange={setIOC('description')} />
            </div>
            <div className="sm:col-span-2 flex gap-2 justify-end">
              <button type="button" onClick={() => setShowAddIOC(false)} className="btn-secondary">
                Cancelar
              </button>
              <button type="submit" disabled={addingIOC} className="btn-primary">
                {addingIOC ? <><Spinner size="sm" inverted /> Guardando…</> : 'Añadir IOC'}
              </button>
            </div>
          </form>
        </FormPanel>
      )}

      {/* Lista de IOCs */}
      <section className="card overflow-hidden">
        <div className="card-header">
          <h2 className="text-section">Indicadores de compromiso</h2>
          <span className="text-caption text-fg-3 tabular-nums">{count} IOCs</span>
        </div>
        {iocs.length === 0 ? (
          <EmptyState icon={Database} title="Sin IOCs"
            description="Añade un IOC manual o espera la sincronización de los feeds." />
        ) : isDesktop ? (
          <div className="overflow-x-auto max-h-[480px] overflow-y-auto">
            <table className="w-full min-w-[720px]">
              <thead className="sticky top-0 z-10">
                <tr>
                  <th scope="col" className="table-head pl-5">Valor</th>
                  <th scope="col" className="table-head">Tipo</th>
                  <th scope="col" className="table-head">Nivel</th>
                  <th scope="col" className="table-head">Fuente</th>
                  <th scope="col" className="table-head">Descripción</th>
                </tr>
              </thead>
              <tbody>
                {iocs.map(ioc => (
                  <tr key={ioc.id} className="border-b border-stroke last:border-0 hover:bg-fg/[0.03]">
                    <td className="px-4 pl-5 py-2.5 max-w-[320px]">
                      <span className="block font-mono text-caption text-fg truncate" title={ioc.value}>{ioc.value}</span>
                    </td>
                    <td className="px-4 py-2.5 text-caption text-fg-2 uppercase font-semibold">{ioc.ioc_type}</td>
                    <td className="px-4 py-2.5"><SeverityBadge severity={ioc.threat_level} /></td>
                    <td className="px-4 py-2.5"><SourceTag source={ioc.source} /></td>
                    <td className="px-4 py-2.5 text-caption text-fg-3 max-w-[260px] truncate">
                      {ioc.brand_targeted || ioc.description || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <ul className="divide-y divide-stroke">
            {iocs.map(ioc => (
              <li key={ioc.id} className="px-4 py-3 space-y-2">
                <p className="font-mono text-caption text-fg break-all">{ioc.value}</p>
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
                  <SeverityBadge severity={ioc.threat_level} />
                  <span className="text-caption text-fg-2 uppercase font-semibold">{ioc.ioc_type}</span>
                  <SourceTag source={ioc.source} />
                </div>
                {(ioc.brand_targeted || ioc.description) && (
                  <p className="text-caption text-fg-3">{ioc.brand_targeted || ioc.description}</p>
                )}
              </li>
            ))}
          </ul>
        )}
        <Pagination page={page} pages={pages} count={count} onChange={setPage} noun="IOCs" />
      </section>

      {!isAnalyst && (
        <p className="flex items-center gap-2 text-caption text-fg-3">
          <ShieldAlert className="h-4 w-4" aria-hidden="true" />
          Solo analistas y administradores pueden añadir IOCs.
        </p>
      )}
    </div>
  )
}
