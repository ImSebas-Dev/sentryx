/**
 * Sentryx — Página de usuarios pendientes de aprobación.
 * Solo accesible para administradores.
 * Muestra las cuentas que verificaron su correo y esperan aprobación manual.
 * Móvil: los botones de aprobar/rechazar bajan debajo de los datos del usuario.
 */
import { useState } from 'react'
import { useFetch } from '../hooks/useFetch'
import {
  ErrorBanner, LoadingScreen, Spinner, PageHeader, EmptyState, MessageBar,
} from '../components/UI'
import { CheckCircle2, XCircle, Clock, RefreshCw, Users, Building2, UserCheck } from 'lucide-react'
import { authAPI } from '../services/api'

function UserCard({ user, onAction }) {
  const [loading, setLoading] = useState(null)   // 'approve' | 'reject' | null
  const [done, setDone]       = useState(null)
  const [error, setError]     = useState(null)

  const displayName = user.email || user.username || '?'

  const handle = async (approved) => {
    setLoading(approved ? 'approve' : 'reject')
    setError(null)
    try {
      await authAPI.approveUser({ user_id: user.id, approved })
      setDone(approved ? 'approved' : 'rejected')
      onAction()
    } catch (e) {
      setError(e.response?.data?.error || 'Error al procesar la solicitud.')
    } finally {
      setLoading(null)
    }
  }

  if (done) return (
    <MessageBar intent={done === 'approved' ? 'success' : 'error'} role="status"
                title={displayName}>
      <p className="text-caption text-fg-2">
        {done === 'approved'
          ? 'Cuenta aprobada — se envió un correo de notificación.'
          : 'Cuenta rechazada.'}
      </p>
    </MessageBar>
  )

  // Fecha de registro — puede venir como created_at o date_joined
  const registeredAt = user.created_at || user.date_joined
  const dateLabel = registeredAt
    ? new Date(registeredAt).toLocaleString('es-CO', {
        day: '2-digit', month: 'short', year: 'numeric',
        hour: '2-digit', minute: '2-digit',
      })
    : 'Fecha no disponible'

  return (
    <div className="card p-4 sm:p-5 space-y-3">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex items-center gap-3 min-w-0">
          <span className="h-10 w-10 rounded-full bg-brand-tint text-brand-fg ring-1 ring-brand-line
                           flex items-center justify-center flex-shrink-0 font-semibold uppercase"
                aria-hidden="true">
            {displayName[0]}
          </span>
          <div className="min-w-0">
            <p className="text-body font-semibold text-fg truncate">{displayName}</p>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 mt-0.5 text-caption text-fg-3">
              {user.organization && (
                <span className="inline-flex items-center gap-1">
                  <Building2 className="h-3.5 w-3.5" aria-hidden="true" />{user.organization}
                </span>
              )}
              <span className="inline-flex items-center gap-1">
                <Clock className="h-3.5 w-3.5" aria-hidden="true" />{dateLabel}
              </span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          <button onClick={() => handle(false)} disabled={!!loading}
            className="btn-danger flex-1 sm:flex-none"
            aria-label={`Rechazar cuenta de ${displayName}`}>
            {loading === 'reject' ? <Spinner size="sm" /> : <XCircle className="h-4 w-4" aria-hidden="true" />}
            Rechazar
          </button>
          <button onClick={() => handle(true)} disabled={!!loading}
            className="btn-success flex-1 sm:flex-none"
            aria-label={`Aprobar cuenta de ${displayName}`}>
            {loading === 'approve' ? <Spinner size="sm" inverted /> : <CheckCircle2 className="h-4 w-4" aria-hidden="true" />}
            Aprobar
          </button>
        </div>
      </div>
      <ErrorBanner message={error} onDismiss={() => setError(null)} />
    </div>
  )
}

export default function PendingUsersPage() {
  const { data, loading, error, refetch } = useFetch(() => authAPI.pendingUsers())

  // El endpoint puede devolver lista directa o paginada con results
  const users = Array.isArray(data) ? data : (data?.results || [])

  if (loading) return <LoadingScreen />

  return (
    <div className="page page-narrow">
      <PageHeader
        icon={Users}
        title="Usuarios pendientes"
        description="Revisa y aprueba las cuentas que ya verificaron su correo electrónico."
        actions={
          <button onClick={refetch} className="btn-secondary" aria-label="Actualizar lista de pendientes">
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            <span className="hidden sm:inline">Actualizar</span>
          </button>
        }
      />

      <ErrorBanner message={error} />

      {users.length === 0 ? (
        <div className="card">
          <EmptyState icon={UserCheck} title="Sin cuentas pendientes"
            description="Todas las solicitudes de registro han sido revisadas." />
        </div>
      ) : (
        <>
          <p className="text-caption text-fg-3" aria-live="polite">
            {users.length} cuenta{users.length !== 1 ? 's' : ''} pendiente{users.length !== 1 ? 's' : ''} de aprobación
          </p>
          <ul className="space-y-3" aria-label="Usuarios pendientes de aprobación">
            {users.map(user => (
              <li key={user.id}>
                <UserCard user={user} onAction={refetch} />
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}
