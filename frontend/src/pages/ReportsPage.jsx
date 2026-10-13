/**
 * Sentryx v2 — Página de informes semanales y mensuales.
 *
 * Flujo:
 *   1. El usuario elige el tipo de informe (semanal o mensual).
 *   2. Elige el periodo (la semana o mes actual, o uno anterior).
 *   3. Ve una vista previa con las métricas principales.
 *   4. Descarga el informe en PDF (formal) o CSV (para Excel).
 *
 * Cada analista solo recibe sus propias alertas; el admin recibe las de todos.
 * Ese filtro lo aplica el backend, aquí no se debe filtrar nada.
 */
import { useState, useCallback } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer } from 'recharts'
import {
  FileText, Download, FileSpreadsheet, CalendarDays, CalendarRange,
  TrendingUp, TrendingDown, Minus, Layers, AlertTriangle, Gauge, CheckCheck,
} from 'lucide-react'
import { reportsAPI } from '../services/api'
import { useFetch } from '../hooks/useFetch'
import { useAuth } from '../store/AuthContext'
import { useTheme } from '../store/ThemeContext'
import {
  ErrorBanner, LoadingScreen, Spinner, StatCard, PageHeader, Section, MessageBar, tone,
} from '../components/UI'
import { chartPalette, tooltipStyle } from '../components/chartTheme'
import { clsx } from 'clsx'

const DAY_NAMES = ['Dom', 'Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb']

const SEVERITIES = [
  { key: 'CRITICAL', label: 'Crítica', tone: 'red' },
  { key: 'HIGH',     label: 'Alta',    tone: 'orange' },
  { key: 'MEDIUM',   label: 'Media',   tone: 'yellow' },
  { key: 'LOW',      label: 'Baja',    tone: 'green' },
]

const TYPE_LABELS = {
  bec: 'BEC', whaling: 'Whaling', spear: 'Spear phishing', clone: 'Clone phishing',
  vishing: 'Vishing', smishing: 'Smishing', generic: 'Genérico', unknown: 'Sin clasificar',
}

/**
 * Descargar el archivo recibido como blob.
 * Se crea un enlace temporal porque es la forma compatible con Chrome,
 * Firefox, Safari de iPhone y navegadores de Android.
 */
function saveBlob(blob, filename) {
  const url  = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href     = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  // Liberar la memoria después de que el navegador inicie la descarga
  setTimeout(() => URL.revokeObjectURL(url), 10000)
}

/**
 * Cuando la petición pide un blob, los errores del backend también llegan
 * como blob. Hay que leerlo como texto para sacar el mensaje en JSON.
 */
async function readBlobError(err) {
  const data = err.response?.data
  if (data instanceof Blob) {
    try {
      const json = JSON.parse(await data.text())
      return json.error || json.detail || 'No se pudo generar el informe.'
    } catch {
      return 'No se pudo generar el informe.'
    }
  }
  return err.response?.data?.error || err.message || 'No se pudo generar el informe.'
}

function ChangeIndicator({ pct, prevLabel }) {
  if (pct === null || pct === undefined) {
    return <p className="text-caption text-fg-3">Sin datos del periodo anterior</p>
  }
  // Para phishing, que suban las alertas es una mala noticia (rojo)
  const Icon = pct > 0 ? TrendingUp : pct < 0 ? TrendingDown : Minus
  const cls  = pct > 0 ? tone('red').badge : pct < 0 ? tone('green').badge : tone('gray').badge
  return (
    <p className={clsx('badge h-6 px-2.5', cls)}>
      <Icon className="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" />
      {pct > 0 ? '+' : ''}{pct}% frente a {prevLabel?.toLowerCase()}
    </p>
  )
}

function Preview({ data, period }) {
  const { theme } = useTheme()
  const palette   = chartPalette(theme)
  const s     = data.summary
  const total = s.total || 1

  const chartData = data.daily.map(d => {
    const date = new Date(d.date + 'T12:00:00')
    return {
      name:  period === 'weekly' ? `${DAY_NAMES[date.getDay()]} ${date.getDate()}` : `${date.getDate()}`,
      count: d.count,
    }
  })

  const types   = Object.entries(data.by_type || {}).slice(0, 4)
  const typeMax = Math.max(1, ...types.map(([, c]) => c))

  return (
    <div className="space-y-4 sm:space-y-5">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        <StatCard label="Alertas"        value={s.total}             color="blue"   icon={Layers} />
        <StatCard label="Críticas"       value={s.critical}          color="red"    icon={AlertTriangle}
                  sub={`${s.high} de severidad alta`} />
        <StatCard label="Score promedio" value={s.avg_score}         color="orange" icon={Gauge}
                  sub={`Máximo ${s.max_score}`} />
        <StatCard label="Gestionadas"    value={`${s.review_rate}%`} color="green"  icon={CheckCheck}
                  sub={`${s.pending} pendientes`} />
      </div>

      <ChangeIndicator pct={s.change_pct} prevLabel={s.prev_label} />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-5">
        <Section title="Alertas por día" className="lg:col-span-2" bodyClassName="pt-4 pb-3 pl-1 pr-4">
          {s.total === 0 ? (
            <div className="h-44 flex items-center justify-center text-fg-3 text-body">
              Sin alertas en este periodo
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={190}>
              <BarChart data={chartData} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
                <CartesianGrid vertical={false} stroke={palette.grid} strokeDasharray="3 3" />
                <XAxis dataKey="name" tick={{ fill: palette.axis, fontSize: 12 }}
                       axisLine={false} tickLine={false}
                       interval={period === 'weekly' ? 0 : 'preserveStartEnd'} />
                <YAxis tick={{ fill: palette.axis, fontSize: 12 }} allowDecimals={false}
                       axisLine={false} tickLine={false} />
                <Tooltip cursor={{ fill: palette.cursor }} {...tooltipStyle(theme)}
                         formatter={v => [`${v} alertas`, '']} separator="" />
                <Bar dataKey="count" fill={palette.brand} radius={[4, 4, 0, 0]} maxBarSize={36} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </Section>

        <Section title="Composición">
          <div className="space-y-5">
            <div>
              <h3 className="text-overline mb-2.5">Por severidad</h3>
              <div className="space-y-2.5">
                {SEVERITIES.map(({ key, label, tone: t }) => {
                  const count = data.by_severity?.[key] || 0
                  return (
                    <div key={key} className="flex items-center gap-3 text-caption">
                      <span className="text-fg-2 w-14 flex-shrink-0">{label}</span>
                      <div className="flex-1 h-1.5 bg-fg/10 rounded-full overflow-hidden">
                        <div className={clsx('h-full rounded-full', tone(t).solid)}
                             style={{ width: `${Math.round(count / total * 100)}%` }} />
                      </div>
                      <span className="text-fg font-mono font-semibold w-6 text-right tabular-nums">{count}</span>
                    </div>
                  )
                })}
              </div>
            </div>
            {types.length > 0 && (
              <div>
                <h3 className="text-overline mb-2.5">Tipos más frecuentes</h3>
                <ul className="space-y-2">
                  {types.map(([type, count]) => (
                    <li key={type} className="text-caption">
                      <div className="flex justify-between mb-1">
                        <span className="text-fg-2">{TYPE_LABELS[type] || type}</span>
                        <span className="text-fg font-mono font-semibold tabular-nums">{count}</span>
                      </div>
                      <div className="h-1 bg-fg/10 rounded-full overflow-hidden">
                        <div className="h-full rounded-full bg-brand-fg"
                             style={{ width: `${count / typeMax * 100}%` }} />
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </Section>
      </div>
    </div>
  )
}

export default function ReportsPage() {
  const { user } = useAuth()
  const [period, setPeriod]       = useState('weekly')
  const [offset, setOffset]       = useState(0)
  const [downloading, setDownloading] = useState(null)   // 'pdf' | 'csv' | null
  const [downloadError, setDownloadError] = useState(null)
  const [lastDownload, setLastDownload]   = useState(null)

  const { data: optionsData } = useFetch(
    useCallback(() => reportsAPI.options(period), [period]), [period]
  )
  const { data: preview, loading, error } = useFetch(
    useCallback(() => reportsAPI.preview(period, offset), [period, offset]), [period, offset]
  )

  const options = optionsData?.options || []

  // Al cambiar entre semanal y mensual, volver al periodo actual en el mismo render
  const changePeriod = value => {
    if (value === period) return
    setPeriod(value)
    setOffset(0)
    setLastDownload(null)
    setDownloadError(null)
  }

  const handleDownload = async exportType => {
    setDownloading(exportType)
    setDownloadError(null)
    setLastDownload(null)
    try {
      const res = await reportsAPI.download(period, offset, exportType)
      const disposition = res.headers['content-disposition'] || ''
      const match    = /filename="([^"]+)"/.exec(disposition)
      const filename = match?.[1] || `sentryx_informe_${period}.${exportType}`
      saveBlob(res.data, filename)
      setLastDownload(filename)
    } catch (err) {
      setDownloadError(await readBlobError(err))
    } finally {
      setDownloading(null)
    }
  }

  return (
    <div className="page">
      <PageHeader
        icon={FileText}
        title="Informes"
        description="Descarga un resumen semanal o mensual de las alertas que has generado."
      />

      {user?.role === 'admin' && (
        <MessageBar intent="info">
          Como administrador, tu informe incluye las alertas de todos los usuarios.
        </MessageBar>
      )}

      {/* Selección del periodo y descarga */}
      <div className="card p-4 sm:p-5">
        <div className="grid grid-cols-1 lg:grid-cols-[auto_minmax(0,1fr)_auto] gap-4 lg:items-end">
          <div>
            <p className="field-label" id="report-type-label">Tipo de informe</p>
            <div role="radiogroup" aria-labelledby="report-type-label" className="segmented w-full sm:w-auto">
              {[
                { value: 'weekly',  label: 'Semanal', icon: CalendarDays  },
                { value: 'monthly', label: 'Mensual', icon: CalendarRange },
              ].map(({ value, label, icon: Icon }) => (
                <button key={value} role="radio" aria-checked={period === value}
                        onClick={() => changePeriod(value)} className="segmented-item">
                  <Icon className="h-4 w-4" aria-hidden="true" />
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label htmlFor="report-period" className="field-label">
              {period === 'weekly' ? 'Semana (lunes a domingo)' : 'Mes'}
            </label>
            <select
              id="report-period"
              className="input input-lg"
              value={offset}
              onChange={e => { setOffset(Number(e.target.value)); setLastDownload(null) }}
              disabled={options.length === 0}
            >
              {options.length === 0 && <option>Cargando periodos…</option>}
              {options.map(o => (
                <option key={o.offset} value={o.offset}>
                  {o.label}{o.in_progress ? ' (en curso)' : ''}
                </option>
              ))}
            </select>
          </div>

          <div className="flex flex-col sm:flex-row gap-2">
            <button onClick={() => handleDownload('pdf')} disabled={!!downloading || loading}
                    className="btn-primary btn-lg">
              {downloading === 'pdf'
                ? <><Spinner size="sm" inverted /> Generando PDF…</>
                : <><Download className="h-4 w-4" aria-hidden="true" /> Descargar PDF</>}
            </button>
            <button onClick={() => handleDownload('csv')} disabled={!!downloading || loading}
                    className="btn-secondary btn-lg">
              {downloading === 'csv'
                ? <><Spinner size="sm" /> Generando CSV…</>
                : <><FileSpreadsheet className="h-4 w-4" aria-hidden="true" /> CSV (Excel)</>}
            </button>
          </div>
        </div>

        {(downloadError || lastDownload) && (
          <div className="mt-4 space-y-2">
            <ErrorBanner message={downloadError} onDismiss={() => setDownloadError(null)} />
            {lastDownload && (
              <MessageBar intent="success" onDismiss={() => setLastDownload(null)}>
                <span className="break-all">Descargado: {lastDownload}</span>
              </MessageBar>
            )}
          </div>
        )}

        <p className="text-caption text-fg-3 leading-relaxed mt-4 pt-4 border-t border-stroke">
          El PDF incluye resumen ejecutivo, gráficas, indicadores, incidentes y el detalle de
          alertas. El CSV trae el listado completo para analizarlo en Excel. Ninguno contiene
          datos personales y cada descarga queda registrada en el log de auditoría.
        </p>
      </div>

      {/* Vista previa */}
      <section aria-labelledby="preview-title" className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <h2 id="preview-title" className="text-subtitle font-semibold text-fg">
            Vista previa{preview ? ` — ${preview.label}` : ''}
          </h2>
          {preview?.in_progress && (
            <span className={clsx('badge', tone('yellow').badge)}>
              Periodo en curso · datos parciales
            </span>
          )}
        </div>

        {error && <ErrorBanner message={error} />}
        {loading ? <LoadingScreen /> : preview && <Preview data={preview} period={period} />}
      </section>
    </div>
  )
}
