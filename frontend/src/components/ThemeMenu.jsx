/**
 * Selector de tema: claro, oscuro o el del sistema.
 * Menú accesible (menuitemradio): se abre con clic/Enter, se navega con
 * flechas, se cierra con Escape o al hacer clic fuera.
 */
import { useEffect, useRef, useState } from 'react'
import { Sun, Moon, Monitor, Check } from 'lucide-react'
import { clsx } from 'clsx'
import { useTheme } from '../store/ThemeContext'

const OPTIONS = [
  { value: 'light',  label: 'Claro',              icon: Sun },
  { value: 'dark',   label: 'Oscuro',             icon: Moon },
  { value: 'system', label: 'Usar el del sistema', icon: Monitor },
]

export default function ThemeMenu({ className }) {
  const { mode, theme, setMode } = useTheme()
  const [open, setOpen] = useState(false)
  const rootRef  = useRef(null)
  const itemsRef = useRef([])

  useEffect(() => {
    if (!open) return
    const onDown = e => { if (!rootRef.current?.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', onDown)
    // Enfocar la opción activa al abrir
    const idx = OPTIONS.findIndex(o => o.value === mode)
    itemsRef.current[idx >= 0 ? idx : 0]?.focus()
    return () => document.removeEventListener('mousedown', onDown)
  }, [open, mode])

  const onMenuKey = e => {
    const idx = itemsRef.current.indexOf(document.activeElement)
    if (e.key === 'Escape') { e.stopPropagation(); setOpen(false); rootRef.current?.querySelector('button')?.focus() }
    if (e.key === 'ArrowDown') { e.preventDefault(); itemsRef.current[(idx + 1) % OPTIONS.length]?.focus() }
    if (e.key === 'ArrowUp')   { e.preventDefault(); itemsRef.current[(idx - 1 + OPTIONS.length) % OPTIONS.length]?.focus() }
  }

  const TriggerIcon = theme === 'dark' ? Moon : Sun

  return (
    <div ref={rootRef} className={clsx('relative', className)}>
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="btn-ghost btn-icon"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Cambiar tema de color"
        title="Tema de color"
      >
        <TriggerIcon className="h-[18px] w-[18px]" aria-hidden="true" />
      </button>

      {open && (
        <div role="menu" aria-label="Tema de color" onKeyDown={onMenuKey}
             className="absolute right-0 top-full mt-1 z-50 w-56 p-1 rounded-lg bg-layer
                        border border-stroke shadow-16 animate-scale-in origin-top-right">
          {OPTIONS.map(({ value, label, icon: Icon }, i) => (
            <button
              key={value}
              ref={el => { itemsRef.current[i] = el }}
              role="menuitemradio"
              aria-checked={mode === value}
              onClick={() => { setMode(value); setOpen(false) }}
              className="w-full flex items-center gap-3 h-9 px-2.5 rounded text-body text-fg
                         hover:bg-fg/[0.06] focus-visible:bg-fg/[0.06]"
            >
              <Icon className="h-4 w-4 text-fg-2" aria-hidden="true" />
              <span className="flex-1 text-left">{label}</span>
              {mode === value && <Check className="h-4 w-4 text-brand-fg" aria-hidden="true" />}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
