/**
 * Sentryx v2 — Contactos de emergencia de la empresa (solo admin edita).
 * Sentryx no trae números cargados: el admin debe verificar cada uno con su banco.
 */
import { useCallback, useEffect, useState } from 'react'
import { PhoneCall, Plus, Pencil, Trash2, Save } from 'lucide-react'
import { responseAPI } from '../services/api'
import {
  EmptyState, ErrorBanner, LoadingScreen, MessageBar, PageHeader, Spinner,
} from '../components/UI'
import Modal from '../components/Modal'
import PageGuide from '../components/PageGuide'

const KIND_LABELS = { bank: 'Banco', authority: 'Autoridad', internal: 'Interno' }
const EMPTY = { name: '', phone: '', url: '', kind: 'bank' }

function apiError(err) {
  const data = err.response?.data
  if (!data || typeof data !== 'object') return 'No se pudo guardar el contacto.'
  return data.error || data.detail || Object.values(data).flat().join(' ')
}

function ContactForm({ initial, onClose, onSaved }) {
  const [form, setForm]     = useState(initial || EMPTY)
  const [saving, setSaving] = useState(false)
  const [error, setError]   = useState(null)
  const set = key => e => setForm(f => ({ ...f, [key]: e.target.value }))

  const submit = async e => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    const payload = { name: form.name, phone: form.phone, url: form.url, kind: form.kind }
    try {
      if (initial) await responseAPI.updateContact(initial.id, payload)
      else         await responseAPI.createContact(payload)
      onSaved()
    } catch (err) {
      setError(apiError(err))
      setSaving(false)
    }
  }

  return (
    <Modal title={initial ? 'Editar contacto' : 'Nuevo contacto'} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <PageGuide id="contact-form" />
        <ErrorBanner message={error} onDismiss={() => setError(null)} />
        <div>
          <label htmlFor="c-name" className="field-label">Nombre</label>
          <input id="c-name" required className="input" value={form.name} onChange={set('name')}
                 placeholder="Línea de fraude de mi banco" />
        </div>
        <div>
          <label htmlFor="c-kind" className="field-label">Tipo</label>
          <select id="c-kind" className="input" value={form.kind} onChange={set('kind')}>
            {Object.entries(KIND_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="c-phone" className="field-label">Teléfono</label>
          <input id="c-phone" type="tel" className="input" value={form.phone} onChange={set('phone')} />
          <p className="field-hint">Cópialo de tu contrato o del respaldo de tu tarjeta.</p>
        </div>
        <div>
          <label htmlFor="c-url" className="field-label">Sitio web</label>
          <input id="c-url" type="url" className="input" value={form.url} onChange={set('url')}
                 placeholder="https://" />
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

export default function EmergencyContactsPage() {
  const [contacts, setContacts] = useState(null)
  const [error, setError]       = useState(null)
  const [warning, setWarning]   = useState('')
  const [editing, setEditing]   = useState(null) // null | 'new' | contacto

  const load = useCallback(async () => {
    try {
      const { data } = await responseAPI.contacts()
      setContacts(data)
    } catch (err) {
      setError(apiError(err))
      setContacts([])
    }
  }, [])

  useEffect(() => {
    load()
    responseAPI.config().then(r => setWarning(r.data.contact_warning)).catch(() => {})
  }, [load])

  const remove = async contact => {
    if (!window.confirm(`¿Borrar «${contact.name}»?`)) return
    try {
      await responseAPI.deleteContact(contact.id)
      load()
    } catch (err) {
      setError(apiError(err))
    }
  }

  return (
    <div className="page">
      <PageHeader icon={PhoneCall} title="Contactos de emergencia" guide="emergency-contacts"
        description="Aparecen en el asistente cuando alguien cae en un phishing."
        actions={(
          <button type="button" onClick={() => setEditing('new')} className="btn-primary">
            <Plus className="h-4 w-4" aria-hidden="true" /> Nuevo contacto
          </button>
        )} />

      {warning && <MessageBar intent="warning" title="Importante">{warning}</MessageBar>}
      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

      <div className="card overflow-hidden">
        {contacts === null ? <LoadingScreen /> : contacts.length === 0 ? (
          <EmptyState icon={PhoneCall} title="Sin contactos"
            description="Tu usuario necesita una organización para guardar contactos." />
        ) : (
          <ul className="divide-y divide-stroke">
            {contacts.map(contact => (
              <li key={contact.id} className="p-4 flex items-start gap-3">
                <div className="min-w-0 flex-1">
                  <p className="text-body font-semibold text-fg">{contact.name}</p>
                  <p className="text-caption text-fg-3">
                    {KIND_LABELS[contact.kind]}
                    {contact.phone && ` · ${contact.phone}`}
                    {contact.url && ` · ${contact.url}`}
                  </p>
                  {contact.is_placeholder && (
                    <span className="badge mt-1 bg-yellow-tint text-yellow-fg border-yellow-line">Por completar</span>
                  )}
                </div>
                <button type="button" onClick={() => setEditing(contact)} className="btn-ghost btn-icon"
                        aria-label={`Editar ${contact.name}`}>
                  <Pencil className="h-4 w-4" aria-hidden="true" />
                </button>
                <button type="button" onClick={() => remove(contact)}
                        className="btn-ghost btn-icon hover:text-red-fg" aria-label={`Borrar ${contact.name}`}>
                  <Trash2 className="h-4 w-4" aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {editing && (
        <ContactForm initial={editing === 'new' ? null : editing}
                     onClose={() => setEditing(null)}
                     onSaved={() => { setEditing(null); load() }} />
      )}
    </div>
  )
}
