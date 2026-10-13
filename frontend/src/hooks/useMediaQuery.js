import { useEffect, useState } from 'react'

/**
 * true si la media query se cumple; se actualiza al cambiar el tamaño.
 * Permite montar solo la vista adecuada (tabla o tarjetas) en lugar de
 * renderizar ambas y ocultar una con CSS.
 */
export function useMediaQuery(query) {
  const get = () => typeof window !== 'undefined' && !!window.matchMedia?.(query)?.matches
  const [matches, setMatches] = useState(get)

  useEffect(() => {
    const mq = window.matchMedia?.(query)
    if (!mq) return
    const onChange = e => setMatches(e.matches)
    setMatches(mq.matches)
    mq.addEventListener?.('change', onChange)
    return () => mq.removeEventListener?.('change', onChange)
  }, [query])

  return matches
}

/** Breakpoint md de Tailwind (≥ 768px). */
export const useIsDesktop = () => useMediaQuery('(min-width: 768px)')
