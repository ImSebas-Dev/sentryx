import { useState, useEffect, useCallback } from 'react'

/**
 * Hook genérico para peticiones con loading/error/refetch.
 * refetch(true) hace una actualización silenciosa: mantiene los datos
 * en pantalla y no muestra el estado de carga (lo usa el polling).
 */
export function useFetch(fetchFn, deps = []) {
  const [data,    setData]    = useState(null)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)

  const execute = useCallback(async (silent) => {
    // Cuando refetch se usa como onClick recibe un evento, no un booleano
    const isSilent = silent === true
    if (!isSilent) setLoading(true)
    setError(null)
    try {
      const res = await fetchFn()
      setData(res.data)
    } catch (err) {
      if (err.name !== 'CanceledError')
        setError(err.response?.data?.detail || err.message || 'Error desconocido')
    } finally {
      if (!isSilent) setLoading(false)
    }
  }, deps) // eslint-disable-line

  useEffect(() => { execute() }, [execute])

  return { data, loading, error, refetch: execute }
}

/**
 * Hook para polling automático cada N milisegundos.
 * Las actualizaciones periódicas son silenciosas para no hacer parpadear la vista.
 * Se pausa cuando la pestaña está oculta (ahorra batería y datos en el celular).
 */
export function usePolling(fetchFn, intervalMs = 30000, deps = []) {
  const { data, loading, error, refetch } = useFetch(fetchFn, deps)

  useEffect(() => {
    const tick = () => {
      if (document.visibilityState === 'visible') refetch(true)
    }
    const id = setInterval(tick, intervalMs)
    // Al volver a la pestaña, actualizar de inmediato
    const onVisible = () => {
      if (document.visibilityState === 'visible') refetch(true)
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      clearInterval(id)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [refetch, intervalMs])

  return { data, loading, error, refetch }
}

/**
 * Hook para manejar el envío de un formulario con estado.
 */
export function useSubmit(submitFn) {
  const [submitting, setSubmitting] = useState(false)
  const [error,      setError]      = useState(null)
  const [success,    setSuccess]    = useState(false)

  const submit = useCallback(async (...args) => {
    setSubmitting(true)
    setError(null)
    setSuccess(false)
    try {
      const result = await submitFn(...args)
      setSuccess(true)
      return result
    } catch (err) {
      const msg = err.response?.data?.detail
        || err.response?.data?.error
        || Object.values(err.response?.data || {})[0]
        || err.message
        || 'Error inesperado'
      setError(typeof msg === 'string' ? msg : JSON.stringify(msg))
      throw err
    } finally {
      setSubmitting(false)
    }
  }, [submitFn])

  return { submit, submitting, error, success, setError, setSuccess }
}
