/** Aviso de la Red de alerta: otras empresas reportaron este dominio o enlace. */
import { MessageBar } from './UI'

export default function CommunityNotice({ signal }) {
  if (!signal) return null
  return (
    <MessageBar intent="warning" title="⚠ Red de alerta">
      {signal.message}
      {signal.regions?.length > 0 && (
        <p className="text-caption text-fg-2 mt-0.5">Regiones: {signal.regions.join(', ')}.</p>
      )}
    </MessageBar>
  )
}
