/**
 * Sentryx v2 — Directorio de proveedores de confianza (Escudo de pagos).
 * Móvil: tarjetas. Desktop: tabla. Solo el admin crea, edita y borra.
 */
import { useState, useCallback } from 'react'
import { Building2, Plus, Pencil, Trash2, Phone, Save } from 'lucide-react'
import { paymentShieldAPI } from '../services/api'
import { useFetch } from '../hooks/useFetch'
import { useIsDesktop } from '../hooks/useMediaQuery'
import { useAuth } from '../store/AuthContext'
import {
  LoadingScreen, EmptyState, ErrorBanner, MessageBar, PageHeader, Spinner,
} from '../components/UI'
import Modal from '../components/Modal'
import PageGuide from '../components/PageGuide'
import { computeDv, isValidNit, maskAccount } from '../utils/nit'

const EMPTY = {
  name: '', nit: '', dv: '', email_domains: '', contact_phone: '', bank_name: '', account_number: '',
}

function apiError(err) {
  const data = err.response?.data
  if (!data || typeof data !== 'object') return 'No se pudo guardar el proveedor.'
  return data.error || data.detail || Object.values(data).flat().join(' ')
}

function SupplierForm({ initial, onClose, onSaved }) {
  const [form, setForm] = useState(initial
    ? { ...EMPTY, ...initial, email_domains: (initial.email_domains || []).join(', '), account_number: '' }
    : EMPTY)
  const [saving, setSaving]  = useState(false)
  const [error, setError]    = useState(null)
  const [showAccount, setShowAccount] = useState(false)

  const set = key => e => setForm(f => ({ ...f, [key]: e.target.value }))
  const nitOk = isValidNit(form.nit, form.dv)

  const submit = async e => {
    e.preventDefault()
    if (!nitOk) {
      setError(`El dígito de verificación no corresponde al NIT${
        /^\d{5,15}$/.test(form.nit) ? ` (debería ser ${computeDv(form.nit)})` : ''}.`)
      return
    }
    setSaving(true)
    setError(null)
    const payload = {
      name: form.name, nit: form.nit, dv: form.dv,
      email_domains: form.email_domains.split(/[\s,;]+/).filter(Boolean),
      contact_phone: form.contact_phone, bank_name: form.bank_name,
    }
    // Envía la cuenta solo si la escribieron: vacía conserva la registrada
    if (form.account_number) payload.account_number = form.account_number
    try {
      if (initial) await paymentShieldAPI.updateSupplier(initial.id, payload)
      else         await paymentShieldAPI.createSupplier(payload)
      onSaved()
    } catch (err) {
      setError(apiError(err))
      setSaving(false)
    }
  }

  return (
    <Modal title={initial ? 'Editar proveedor' : 'Nuevo proveedor'} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <PageGuide id="supplier-form" />
        <ErrorBanner message={error} onDismiss={() => setError(null)} />
        <div>
          <label htmlFor="s-name" className="field-label">Nombre</label>
          <input id="s-name" required className="input" value={form.name} onChange={set('name')} />
        </div>
        <div className="grid grid-cols-[1fr_5rem] gap-3">
          <div>
            <label htmlFor="s-nit" className="field-label">NIT (sin DV)</label>
            <input id="s-nit" required inputMode="numeric" className="input font-mono"
                   value={form.nit}
                   onChange={e => setForm(f => ({ ...f, nit: e.target.value.replace(/\D/g, '') }))} />
          </div>
          <div>
            <label htmlFor="s-dv" className="field-label">DV</label>
            <input id="s-dv" required inputMode="numeric" maxLength={1} className="input font-mono"
                   value={form.dv}
                   onChange={e => setForm(f => ({ ...f, dv: e.target.value.replace(/\D/g, '') }))} />
          </div>
        </div>
        {form.nit && form.dv && !nitOk && (
          <p className="field-hint text-red-fg" role="alert">
            El dígito de verificación no corresponde a este NIT.
          </p>
        )}
        <div>
          <label htmlFor="s-domains" className="field-label">Dominios autorizados</label>
          <input id="s-domains" required className="input" autoCapitalize="none"
                 placeholder="proveedor.com.co, proveedor.co"
                 value={form.email_domains} onChange={set('email_domains')} />
          <p className="field-hint">Separados por coma. Incluye todos los dominios desde los que escribe.</p>
        </div>
        <div>
          <label htmlFor="s-phone" className="field-label">Teléfono de confianza</label>
          <input id="s-phone" type="tel" className="input" value={form.contact_phone}
                 onChange={set('contact_phone')} />
          <p className="field-hint">Tómalo de un contrato o de tu agenda, nunca de un correo.</p>
        </div>
        <div>
          <label htmlFor="s-bank" className="field-label">Banco</label>
          <input id="s-bank" className="input" value={form.bank_name} onChange={set('bank_name')} />
        </div>
        <div>
          <label htmlFor="s-account" className="field-label">Número de cuenta</label>
          <input id="s-account" inputMode="numeric" autoComplete="off" className="input font-mono"
                 value={showAccount ? form.account_number : maskAccount(form.account_number)}
                 onFocus={() => setShowAccount(true)} onBlur={() => setShowAccount(false)}
                 onChange={set('account_number')}
                 placeholder={initial?.account_masked || 'Se guarda cifrado; solo verás los últimos 4'} />
          <p className="field-hint">
            No se guarda completo: Sentryx conserva los últimos 4 dígitos y una huella para comparar.
            {initial?.account_masked && ' Déjalo vacío para conservar la cuenta actual.'}
          </p>
        </div>
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="btn-secondary">Cancelar</button>
          <button type="submit" disabled={saving} className="btn-primary">
            {saving ? <Spinner size="sm" inverted /> : <Save className="h-4 w-4" aria-hidden="true" />}
            Guardar
          </button>
        </div>
      </form>
    </Modal>
  )
}

function RowActions({ supplier, onEdit, onDelete }) {
  return (
    <div className="flex gap-1 justify-end">
      <button type="button" onClick={() => onEdit(supplier)} className="btn-ghost btn-icon"
              aria-label={`Editar ${supplier.name}`}>
        <Pencil className="h-4 w-4" aria-hidden="true" />
      </button>
      <button type="button" onClick={() => onDelete(supplier)}
              className="btn-ghost btn-icon hover:text-red-fg" aria-label={`Borrar ${supplier.name}`}>
        <Trash2 className="h-4 w-4" aria-hidden="true" />
      </button>
    </div>
  )
}

export default function SuppliersPage() {
  const { isAdmin, user } = useAuth()
  const isDesktop = useIsDesktop()
  const fetchSuppliers = useCallback(() => paymentShieldAPI.suppliers({ page_size: 200 }), [])
  const { data, loading, error, refetch } = useFetch(fetchSuppliers, [])
  const [editing, setEditing] = useState(null) // null | 'new' | proveedor
  const [actionError, setActionError] = useState(null)

  const suppliers = data?.results || []

  const handleDelete = async supplier => {
    if (!window.confirm(`¿Borrar a ${supplier.name} del directorio?`)) return
    try {
      await paymentShieldAPI.deleteSupplier(supplier.id)
      refetch()
    } catch (err) {
      setActionError(apiError(err))
    }
  }

  return (
    <div className="page">
      <PageHeader
        icon={Building2}
        title="Proveedores"
        guide="suppliers"
        description="Directorio de confianza con el que el Escudo de pagos compara cada correo."
        actions={isAdmin && (
          <button type="button" onClick={() => setEditing('new')} className="btn-primary">
            <Plus className="h-4 w-4" aria-hidden="true" />
            Nuevo proveedor
          </button>
        )}
      />

      {!user?.organization && (
        <MessageBar intent="warning" title="Tu usuario no tiene organización">
          Pide a un administrador que te la asigne: el directorio se guarda por empresa.
        </MessageBar>
      )}
      {error && <ErrorBanner message={error} />}
      <ErrorBanner message={actionError} onDismiss={() => setActionError(null)} />

      <div className="card overflow-hidden">
        {loading ? <LoadingScreen /> : suppliers.length === 0 ? (
          <EmptyState icon={Building2} title="Aún no hay proveedores"
            description="Mientras el directorio esté vacío, todo correo que pida un pago se marcará como proveedor desconocido." />
        ) : isDesktop ? (
          <div className="overflow-x-auto">
            <table className="w-full text-body">
              <thead>
                <tr className="border-b border-stroke text-left text-caption text-fg-3">
                  <th scope="col" className="px-5 py-2.5 font-semibold">Proveedor</th>
                  <th scope="col" className="px-3 py-2.5 font-semibold">NIT</th>
                  <th scope="col" className="px-3 py-2.5 font-semibold">Dominios</th>
                  <th scope="col" className="px-3 py-2.5 font-semibold">Teléfono</th>
                  <th scope="col" className="px-3 py-2.5 font-semibold">Banco y cuenta</th>
                  {isAdmin && <th scope="col" className="px-5 py-2.5"><span className="sr-only">Acciones</span></th>}
                </tr>
              </thead>
              <tbody className="divide-y divide-stroke">
                {suppliers.map(s => (
                  <tr key={s.id}>
                    <td className="px-5 py-3 font-medium text-fg">{s.name}</td>
                    <td className="px-3 py-3 font-mono text-caption text-fg-2">{s.nit}-{s.dv}</td>
                    <td className="px-3 py-3 text-caption text-fg-2">{s.email_domains.join(', ')}</td>
                    <td className="px-3 py-3 text-caption text-fg-2">{s.contact_phone || '—'}</td>
                    <td className="px-3 py-3 text-caption text-fg-2">
                      {s.bank_name || '—'} {s.account_masked && <span className="font-mono">{s.account_masked}</span>}
                    </td>
                    {isAdmin && (
                      <td className="px-5 py-3">
                        <RowActions supplier={s} onEdit={setEditing} onDelete={handleDelete} />
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <ul className="divide-y divide-stroke">
            {suppliers.map(s => (
              <li key={s.id} className="p-4 space-y-1.5">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-body font-semibold text-fg">{s.name}</p>
                    <p className="text-caption font-mono text-fg-3">NIT {s.nit}-{s.dv}</p>
                  </div>
                  {isAdmin && <RowActions supplier={s} onEdit={setEditing} onDelete={handleDelete} />}
                </div>
                <p className="text-caption text-fg-2 break-words">{s.email_domains.join(', ')}</p>
                <p className="text-caption text-fg-2">
                  {s.bank_name || 'Sin banco'} {s.account_masked && <span className="font-mono">{s.account_masked}</span>}
                </p>
                {s.contact_phone && (
                  <a href={`tel:${s.contact_phone}`} className="btn-secondary w-full">
                    <Phone className="h-4 w-4" aria-hidden="true" /> {s.contact_phone}
                  </a>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      {editing && (
        <SupplierForm initial={editing === 'new' ? null : editing}
                      onClose={() => setEditing(null)}
                      onSaved={() => { setEditing(null); refetch() }} />
      )}
    </div>
  )
}
