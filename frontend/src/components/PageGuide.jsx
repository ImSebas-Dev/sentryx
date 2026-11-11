/**
 * Guía paso a paso de una pantalla, plegable y abierta la primera vez.
 * Recuerda por navegador si la persona la ocultó. Edita los textos en guides.js.
 */
import { useId, useState } from 'react'
import { ChevronDown, CircleHelp } from 'lucide-react'
import { clsx } from 'clsx'
import { GUIDES } from './guides'

const STORAGE_PREFIX = 'sentryx_guide_hidden_'

// El navegador puede bloquear localStorage: sin él, la guía solo se abre cada vez
function readHidden(id) {
  try {
    return localStorage.getItem(STORAGE_PREFIX + id) === '1'
  } catch {
    return false
  }
}

function saveHidden(id, hidden) {
  try {
    if (hidden) localStorage.setItem(STORAGE_PREFIX + id, '1')
    else localStorage.removeItem(STORAGE_PREFIX + id)
  } catch { /* sin persistencia */ }
}

export default function PageGuide({ id, className }) {
  const panelId = useId()
  const [open, setOpen] = useState(() => !readHidden(id))
  const guide = GUIDES[id]
  if (!guide) return null

  const toggle = () => {
    saveHidden(id, open)
    setOpen(!open)
  }

  return (
    <section className={clsx('rounded-lg border border-brand-line bg-brand-tint', className)}
             aria-label={guide.title || 'Cómo usar esta página'}>
      <button type="button" onClick={toggle} aria-expanded={open} aria-controls={panelId}
              className="w-full min-h-[44px] flex items-center gap-2 px-4 py-2.5 text-left rounded-lg">
        <CircleHelp className="h-4 w-4 text-brand-fg flex-shrink-0" aria-hidden="true" />
        <span className="flex-1 text-body font-semibold text-fg">
          {guide.title || 'Cómo usar esta página'}
        </span>
        <span className="text-caption text-fg-3">{open ? 'Ocultar' : 'Ver pasos'}</span>
        <ChevronDown className={clsx('h-4 w-4 text-fg-3 flex-shrink-0 transition-transform duration-150',
                                     open && 'rotate-180')}
                     aria-hidden="true" />
      </button>
      {open && (
        <ol id={panelId} className="px-4 pb-4 pt-1 space-y-2.5 text-left">
          {guide.steps.map((step, i) => (
            <li key={step} className="flex gap-2.5 items-start">
              {/* El número va por CSS: el <ol> ya lo anuncia a los lectores de pantalla */}
              <span data-step={i + 1} aria-hidden="true"
                    className="h-5 w-5 mt-px rounded-full bg-layer text-brand-fg ring-1 ring-brand-line text-caption
                               font-semibold flex items-center justify-center flex-shrink-0
                               before:content-[attr(data-step)]" />
              <span className="min-w-0 text-body text-fg-2">{step}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
