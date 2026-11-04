/**
 * Validación del NIT colombiano en el cliente (módulo 11 de la DIAN).
 * Mantén este cálculo igual al de backend/apps/payment_shield/invoice.py:
 * aquí solo sirve para avisar antes de enviar; el backend vuelve a validar.
 */
const WEIGHTS = [3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]

export function computeDv(nit) {
  const digits = String(nit).split('').reverse().map(Number)
  const total  = digits.reduce((sum, d, i) => sum + d * WEIGHTS[i], 0)
  const rest   = total % 11
  return String(rest < 2 ? rest : 11 - rest)
}

export function isValidNit(nit, dv) {
  return /^\d{5,15}$/.test(nit || '') && /^\d$/.test(dv || '') && computeDv(nit) === dv
}

/** Muestra una cuenta con solo los últimos 4 dígitos mientras el usuario escribe. */
export function maskAccount(value) {
  const digits = String(value || '').replace(/\D/g, '')
  if (digits.length <= 4) return digits
  return `${'•'.repeat(digits.length - 4)}${digits.slice(-4)}`
}
