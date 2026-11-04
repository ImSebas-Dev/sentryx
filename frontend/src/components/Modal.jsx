/**
 * Diálogo modal (patrón Fluent). Cierra con Escape o con el fondo.
 * En móvil ocupa el ancho disponible y se desplaza si el contenido no cabe.
 */
import { useEffect, useRef } from 'react'
import { X } from 'lucide-react'

export default function Modal({ title, onClose, children }) {
  const panelRef = useRef(null)

  useEffect(() => {
    const onKey = e => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    panelRef.current?.focus()
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 animate-fade-in">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} aria-hidden="true" />
      <div ref={panelRef} tabIndex={-1} role="dialog" aria-modal="true" aria-label={title}
           className="relative card w-full max-w-md max-h-[90vh] overflow-y-auto shadow-64
                      animate-scale-in focus:outline-none">
        <div className="card-header">
          <h2 className="text-section">{title}</h2>
          <button type="button" onClick={onClose} className="btn-ghost btn-icon"
                  aria-label={`Cerrar: ${title}`}>
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
        <div className="p-4 sm:p-5">{children}</div>
      </div>
    </div>
  )
}
