/**
 * Sentryx — Campo para el código de verificación en dos pasos.
 *
 * Un solo <input type="text">: no usar type="number" (quita ceros a la
 * izquierda) ni separar los dígitos en varias casillas (rompe el autocompletado
 * one-time-code y el pegado). La ayuda va encima del campo para que el teclado
 * móvil no la tape.
 *
 * Con recovery=true acepta un código de recuperación (letras y números).
 */
export default function MfaCodeField({
  id, label, hint, value, onChange, recovery = false, autoFocus = false, required = true,
}) {
  const hintId = `${id}-hint`
  const handleChange = e => {
    const raw = e.target.value
    // Quitar espacios y, en modo TOTP, todo lo que no sea dígito (al pegar "123 456")
    onChange(recovery ? raw.replace(/\s+/g, '') : raw.replace(/\D/g, '').slice(0, 6))
  }

  return (
    <div>
      <label htmlFor={id} className="field-label">{label}</label>
      {hint && <p id={hintId} className="field-hint mb-1.5">{hint}</p>}
      {recovery ? (
        <input
          id={id} type="text" value={value} onChange={handleChange}
          required={required} autoFocus={autoFocus}
          autoComplete="off" autoCapitalize="none" autoCorrect="off" spellCheck={false}
          maxLength={20} placeholder="xxxxx-xxxxx"
          aria-describedby={hint ? hintId : undefined}
          className="input input-lg font-mono tracking-wider"
        />
      ) : (
        <input
          id={id} type="text" value={value} onChange={handleChange}
          required={required} autoFocus={autoFocus}
          inputMode="numeric" autoComplete="one-time-code" pattern="\d{6}" maxLength={6}
          placeholder="000000"
          aria-describedby={hint ? hintId : undefined}
          className="input input-lg font-mono text-center text-title3 tracking-[0.5em]"
        />
      )}
    </div>
  )
}
