/**
 * Sentryx v2 — Documentos legales
 * WCAG 2.2 compliant: headings structure, lang, skip links, focus visible
 * Ley 1581/2012 (Colombia) + GDPR-compatible
 */
import { Link } from 'react-router-dom'
import { ShieldCheck, ArrowLeft } from 'lucide-react'
import ThemeMenu from '../components/ThemeMenu'

const LAST_UPDATED = '21 de septiembre de 2026'
const CONTACT_EMAIL = 'privacidad@sentryx.com'

function LegalLayout({ title, children }) {
  return (
    <div className="min-h-screen bg-canvas">
      {/* Skip link para accesibilidad WCAG 2.4.1 */}
      <a href="#main-content"
         className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 btn-primary">
        Saltar al contenido principal
      </a>

      <header className="sticky top-0 z-40 border-b border-stroke bg-nav/90 backdrop-blur">
        <div className="max-w-3xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between gap-3">
          <Link to="/" className="flex items-center gap-2.5 rounded-md" aria-label="Ir al inicio de Sentryx">
            <span className="h-7 w-7 rounded-md bg-brand text-on-brand flex items-center justify-center shadow-2">
              <ShieldCheck className="h-4 w-4" strokeWidth={2.25} aria-hidden="true" />
            </span>
            <span className="text-subtitle2 font-semibold text-fg">Sentryx</span>
          </Link>
          <div className="flex items-center gap-1">
            <ThemeMenu />
            <Link to="/login" className="btn-ghost">
              <ArrowLeft className="h-4 w-4" aria-hidden="true" /> Volver
            </Link>
          </div>
        </div>
      </header>

      <main id="main-content" className="max-w-3xl mx-auto px-4 sm:px-6 py-8 sm:py-12 animate-fade-in"
            tabIndex="-1">
        <h1 className="text-title2 font-semibold text-fg tracking-tight mb-2">{title}</h1>
        <p className="text-fg-3 text-body mb-8">
          Última actualización: {LAST_UPDATED}
        </p>
        <div className="card p-5 sm:p-8">
          {children}
        </div>
      </main>

      <footer className="border-t border-stroke py-6">
        <div className="max-w-3xl mx-auto px-4 sm:px-6 flex flex-wrap gap-4 text-caption text-fg-3">
          <Link to="/terms"         className="hover:text-fg hover:underline">Términos</Link>
          <Link to="/privacy"       className="hover:text-fg hover:underline">Privacidad</Link>
          <Link to="/accessibility" className="hover:text-fg hover:underline">Accesibilidad</Link>
          <span className="ml-auto">© 2026 Sentryx</span>
        </div>
      </footer>
    </div>
  )
}

function Section({ title, id, children }) {
  return (
    <section aria-labelledby={id} className="mb-8 last:mb-0 scroll-mt-20">
      <h2 id={id} className="text-subtitle2 font-semibold text-fg mb-3">
        {title}
      </h2>
      <div className="text-fg-2 text-body leading-relaxed space-y-3">
        {children}
      </div>
    </section>
  )
}

// ═══════════════════════════════════════════════════════════
// TÉRMINOS Y CONDICIONES
// ═══════════════════════════════════════════════════════════
export function TermsPage() {
  return (
    <LegalLayout title="Términos y Condiciones de Uso">

      <Section title="1. Aceptación de los términos" id="s-accept">
        <p>
          Al registrarte y usar Sentryx ("el Sistema", "la Plataforma"), aceptas
          estos Términos y Condiciones en su totalidad. Si no estás de acuerdo con
          alguno de ellos, no debes usar la Plataforma.
        </p>
        <p>
          Sentryx es una plataforma de detección de phishing por correo electrónico
          desarrollada como proyecto académico de grado en Ingeniería de Sistemas.
        </p>
      </Section>

      <Section title="2. Descripción del servicio" id="s-service">
        <p>
          Sentryx ofrece análisis automático de correos electrónicos para detectar
          intentos de phishing mediante modelos de aprendizaje automático. El Sistema
          clasifica los correos como legítimos, sospechosos, phishing o críticos,
          y genera alertas gestionables por los usuarios.
        </p>
        <p>
          <strong className="text-fg font-semibold">Limitación importante:</strong> Sentryx
          es una herramienta de apoyo a la decisión humana. Sus resultados no constituyen
          asesoría de seguridad profesional y no reemplazan el juicio del analista.
          La plataforma puede producir falsos positivos y falsos negativos.
        </p>
      </Section>

      <Section title="3. Registro y aprobación de cuentas" id="s-register">
        <p>Para usar el Sistema debes:</p>
        <ul className="list-disc list-inside space-y-1 pl-2">
          <li>Proporcionar un correo electrónico válido y verificarlo.</li>
          <li>Esperar la aprobación manual de un administrador.</li>
          <li>Mantener la confidencialidad de tus credenciales de acceso.</li>
          <li>Aceptar estos Términos y la Política de Privacidad.</li>
        </ul>
        <p>
          Nos reservamos el derecho de rechazar o revocar cuentas sin previo aviso
          en caso de uso indebido de la plataforma.
        </p>
      </Section>

      <Section title="4. Uso aceptable" id="s-use">
        <p>Al usar Sentryx, te comprometes a:</p>
        <ul className="list-disc list-inside space-y-1 pl-2">
          <li>Usar la plataforma únicamente para analizar correos de los cuales
              tienes autorización legítima.</li>
          <li>No intentar eludir los controles de seguridad del Sistema.</li>
          <li>No usar el Sistema para actividades ilegales o que violen derechos de terceros.</li>
          <li>No compartir tus credenciales con otras personas.</li>
        </ul>
        <p>
          El incumplimiento puede resultar en la suspensión inmediata de tu cuenta
          y, si aplica, en acciones legales.
        </p>
      </Section>

      <Section title="5. Tratamiento de datos personales" id="s-data">
        <p>
          Sentryx aplica seudonimización a todos los datos personales contenidos
          en los correos analizados (remitente, destinatario, asunto) antes de
          almacenarlos, conforme a la <strong className="text-fg font-semibold">Ley 1581 de 2012</strong>{' '}
          de Colombia y principios compatibles con el GDPR europeo.
        </p>
        <p>
          Los correos electrónicos en texto plano <strong className="text-fg font-semibold">no se almacenan</strong>.
          Solo se conservan métricas técnicas derivadas del análisis.
          Consulta nuestra <Link to="/privacy" className="link">
          Política de Privacidad</Link> para más detalles.
        </p>
      </Section>

      <Section title="6. Propiedad intelectual" id="s-ip">
        <p>
          Sentryx es un proyecto de grado de código abierto (open-source) bajo
          licencia MIT. Los modelos de machine learning entrenados con el dataset
          base son propiedad de los autores del proyecto académico.
        </p>
        <p>
          Los datos que tú introduces (correos analizados, correcciones de feedback)
          permanecen bajo tu control. Al proporcionar feedback de reentrenamiento,
          otorgas una licencia no exclusiva para usar esos datos en mejorar los
          modelos de detección de la plataforma.
        </p>
      </Section>

      <Section title="7. Limitación de responsabilidad" id="s-liability">
        <p>
          Sentryx se proporciona "tal cual" sin garantías de ningún tipo.
          Los autores no son responsables de:
        </p>
        <ul className="list-disc list-inside space-y-1 pl-2">
          <li>Pérdidas derivadas de falsos positivos o falsos negativos.</li>
          <li>Interrupciones del servicio o pérdida de datos.</li>
          <li>Daños indirectos, incidentales o consecuentes.</li>
        </ul>
      </Section>

      <Section title="8. Modificaciones" id="s-changes">
        <p>
          Nos reservamos el derecho de modificar estos Términos en cualquier momento.
          Los cambios entran en vigor al publicarse en esta página. El uso continuado
          de la plataforma después de los cambios implica su aceptación.
        </p>
      </Section>

      <Section title="9. Contacto" id="s-contact">
        <p>
          Para consultas sobre estos Términos, contacta a:{' '}
          <a href={`mailto:${CONTACT_EMAIL}`}
             className="link underline">
            {CONTACT_EMAIL}
          </a>
        </p>
      </Section>

    </LegalLayout>
  )
}


// ═══════════════════════════════════════════════════════════
// POLÍTICA DE PRIVACIDAD — Ley 1581/2012 + GDPR compatible
// ═══════════════════════════════════════════════════════════
export function PrivacyPage() {
  return (
    <LegalLayout title="Política de Privacidad y Tratamiento de Datos Personales">

      <div className="bg-brand-tint border border-brand-line rounded-md px-4 py-3 mb-8">
        <p className="text-fg text-body">
          🔒 Esta política cumple con la <strong>Ley 1581 de 2012</strong> (Colombia),
          el <strong>Decreto 1377 de 2013</strong> y los principios del{' '}
          <strong>GDPR europeo</strong> (Reglamento UE 2016/679).
        </p>
      </div>

      <Section title="1. Responsable del tratamiento" id="p-responsible">
        <p>
          <strong className="text-fg font-semibold">Sentryx</strong> — Proyecto de grado,
          Ingeniería de Sistemas, 2026.<br />
          Contacto de privacidad:{' '}
          <a href={`mailto:${CONTACT_EMAIL}`}
             className="link underline">
            {CONTACT_EMAIL}
          </a>
        </p>
      </Section>

      <Section title="2. Datos que recopilamos" id="p-data-collected">
        <p><strong className="text-fg font-semibold">Datos de cuenta:</strong></p>
        <ul className="list-disc list-inside space-y-1 pl-2">
          <li>Correo electrónico (identificación y comunicaciones)</li>
          <li>Nombre de la organización (opcional)</li>
          <li>Hash de la dirección IP en el log de auditoría</li>
        </ul>
        <p className="mt-3">
          <strong className="text-fg font-semibold">Datos de los correos analizados:</strong>
        </p>
        <ul className="list-disc list-inside space-y-1 pl-2">
          <li>
            <strong>No almacenamos</strong> el texto del correo ni las direcciones
            de remitente/destinatario en texto plano.
          </li>
          <li>
            Almacenamos: hash SHA-256 del remitente, hash del asunto, dominio del
            remitente (no personal), scores numéricos del análisis ML y metadatos
            técnicos derivados.
          </li>
        </ul>
      </Section>

      <Section title="3. Finalidad del tratamiento" id="p-purpose">
        <ul className="list-disc list-inside space-y-1 pl-2">
          <li>Proveer el servicio de detección de phishing.</li>
          <li>Gestionar tu cuenta y comunicarnos contigo.</li>
          <li>Mejorar los modelos de ML mediante feedback anonimizado.</li>
          <li>Cumplir obligaciones legales y de seguridad.</li>
        </ul>
      </Section>

      <Section title="4. Base legal del tratamiento" id="p-legal-basis">
        <ul className="list-disc list-inside space-y-1 pl-2">
          <li><strong className="text-fg font-semibold">Consentimiento:</strong> requerido y explícito al registrarte.</li>
          <li><strong className="text-fg font-semibold">Ejecución del contrato:</strong> necesario para proveer el servicio.</li>
          <li><strong className="text-fg font-semibold">Interés legítimo:</strong> seguridad del sistema y prevención de fraude.</li>
          <li><strong className="text-fg font-semibold">Obligación legal:</strong> registros de auditoría requeridos por ley.</li>
        </ul>
      </Section>

      <Section title="5. Seudonimización y seguridad" id="p-security">
        <p>
          Aplicamos <strong className="text-fg font-semibold">seudonimización irreversible</strong>{' '}
          (SHA-256 + salt único por despliegue) a todos los datos personales presentes
          en los correos analizados antes de almacenarlos. Esto significa:
        </p>
        <ul className="list-disc list-inside space-y-1 pl-2">
          <li>El email del remitente se convierte en un hash de 64 caracteres.</li>
          <li>Sin el salt, es imposible recuperar el dato original.</li>
          <li>El salt se genera automáticamente al instalar el sistema y nunca se comparte.</li>
        </ul>
        <p>
          Adicionalmente, usamos HTTPS, autenticación JWT, control de acceso basado
          en roles (RBAC) y log de auditoría inmutable.
        </p>
      </Section>

      <Section title="6. Período de retención" id="p-retention">
        <ul className="list-disc list-inside space-y-1 pl-2">
          <li>Alertas resueltas/cerradas: <strong className="text-fg font-semibold">90 días</strong></li>
          <li>Logs de auditoría: <strong className="text-fg font-semibold">365 días</strong></li>
          <li>Datos de cuenta: mientras la cuenta esté activa</li>
          <li>Tras la eliminación de la cuenta: eliminación dentro de 30 días</li>
        </ul>
      </Section>

      <Section title="7. Tus derechos (ARCO + adicionales)" id="p-rights">
        <p>
          Conforme a la Ley 1581 de 2012 y el GDPR, tienes los siguientes derechos:
        </p>
        <ul className="list-disc list-inside space-y-1 pl-2">
          <li><strong className="text-fg font-semibold">Acceso:</strong> conocer qué datos tenemos sobre ti.</li>
          <li><strong className="text-fg font-semibold">Rectificación:</strong> corregir datos inexactos.</li>
          <li><strong className="text-fg font-semibold">Cancelación/Supresión:</strong> solicitar la eliminación de tus datos.</li>
          <li><strong className="text-fg font-semibold">Oposición:</strong> oponerte a ciertos tratamientos.</li>
          <li><strong className="text-fg font-semibold">Portabilidad:</strong> recibir tus datos en formato legible.</li>
          <li><strong className="text-fg font-semibold">Retirar el consentimiento</strong> en cualquier momento.</li>
        </ul>
        <p>
          Para ejercer tus derechos, escríbenos a{' '}
          <a href={`mailto:${CONTACT_EMAIL}`}
             className="link underline">
            {CONTACT_EMAIL}
          </a>.
          Responderemos en un plazo máximo de <strong className="text-fg font-semibold">15 días hábiles</strong>.
        </p>
      </Section>

      <Section title="8. Transferencias internacionales" id="p-transfers">
        <p>
          Los correos de verificación y recuperación de contraseña se envían a través
          de <strong className="text-fg font-semibold">SendGrid</strong> (Twilio Inc., EE. UU.),
          que cumple con el Marco de Privacidad de Datos UE-EE. UU. y cuenta con
          Cláusulas Contractuales Estándar aprobadas por la Comisión Europea.
          No transferimos tus datos a ningún otro tercero.
        </p>
      </Section>

      <Section title="9. Cookies" id="p-cookies">
        <p>
          Sentryx <strong className="text-fg font-semibold">no usa cookies de rastreo</strong>.
          Usamos exclusivamente el almacenamiento local del navegador (localStorage)
          para guardar el token JWT de sesión. Este dato no se comparte con terceros
          y se elimina al cerrar sesión.
        </p>
      </Section>

      <Section title="10. Contacto y reclamaciones" id="p-complaints">
        <p>
          Si consideras que el tratamiento de tus datos vulnera la normativa aplicable,
          puedes presentar una reclamación ante la{' '}
          <strong className="text-fg font-semibold">
            Superintendencia de Industria y Comercio (SIC)
          </strong>{' '}
          de Colombia a través de{' '}
          <a href="https://www.sic.gov.co" target="_blank" rel="noopener noreferrer"
             className="link underline">
            www.sic.gov.co
          </a>.
        </p>
      </Section>

    </LegalLayout>
  )
}


// ═══════════════════════════════════════════════════════════
// DECLARACIÓN DE ACCESIBILIDAD — WCAG 2.2
// ═══════════════════════════════════════════════════════════
export function AccessibilityPage() {
  return (
    <LegalLayout title="Declaración de Accesibilidad">

      <div className="bg-green-tint border border-green-line rounded-md px-4 py-3 mb-8">
        <p className="text-fg text-body">
          Sentryx aspira a cumplir con las{' '}
          <strong>Pautas de Accesibilidad para el Contenido Web (WCAG) 2.2</strong>{' '}
          al nivel <strong>AA</strong>.
        </p>
      </div>

      <Section title="Estado de conformidad" id="a-status">
        <p>
          Sentryx está <strong className="text-fg font-semibold">parcialmente conforme</strong> con
          WCAG 2.2 nivel AA. Las áreas que cumplen y las que están en mejora continua
          se detallan a continuación.
        </p>
      </Section>

      <Section title="Medidas de accesibilidad implementadas" id="a-implemented">
        <ul className="list-disc list-inside space-y-1 pl-2">
          <li>Enlace "Saltar al contenido principal" en todas las páginas.</li>
          <li>Estructura de encabezados jerárquica (H1 → H2 → H3).</li>
          <li>Atributos <code className="text-brand-fg text-caption font-mono bg-subtle border border-stroke px-1 rounded">aria-label</code>,{' '}
              <code className="text-brand-fg text-caption font-mono bg-subtle border border-stroke px-1 rounded">aria-required</code> y{' '}
              <code className="text-brand-fg text-caption font-mono bg-subtle border border-stroke px-1 rounded">aria-describedby</code>{' '}
              en todos los formularios.</li>
          <li>Contraste de color mínimo 4.5:1 en texto normal (WCAG 1.4.3).</li>
          <li>Focus visible en todos los elementos interactivos (WCAG 2.4.11).</li>
          <li>Iconos con <code className="text-brand-fg text-caption font-mono bg-subtle border border-stroke px-1 rounded">aria-hidden="true"</code>{' '}
              cuando son decorativos.</li>
          <li>Textos alternativos en todas las imágenes funcionales.</li>
          <li>Idioma de la página declarado (<code className="text-brand-fg text-caption font-mono bg-subtle border border-stroke px-1 rounded">lang="es"</code>).</li>
          <li>No se usa el color como único medio de transmitir información.</li>
          <li>Navegación completa por teclado en todos los flujos principales.</li>
        </ul>
      </Section>

      <Section title="Limitaciones conocidas" id="a-limitations">
        <ul className="list-disc list-inside space-y-1 pl-2">
          <li>
            <strong className="text-fg font-semibold">Gráficas del dashboard:</strong> las gráficas
            de área y dona (Recharts) no incluyen descripción textual alternativa completa.
            Estamos trabajando en añadir tablas de datos alternativas.
          </li>
          <li>
            <strong className="text-fg font-semibold">Mensajes de estado en tiempo real:</strong>{' '}
            algunas actualizaciones automáticas (polling del dashboard) no anuncian
            los cambios a lectores de pantalla. Estamos implementando aria-live regions.
          </li>
        </ul>
      </Section>

      <Section title="Tecnologías de asistencia compatibles" id="a-assistive">
        <ul className="list-disc list-inside space-y-1 pl-2">
          <li>NVDA + Firefox (Windows)</li>
          <li>VoiceOver + Safari (macOS / iOS)</li>
          <li>TalkBack + Chrome (Android)</li>
        </ul>
      </Section>

      <Section title="Cómo reportar problemas de accesibilidad" id="a-report">
        <p>
          Si encuentras alguna barrera de accesibilidad en Sentryx, por favor
          contacta a:{' '}
          <a href={`mailto:${CONTACT_EMAIL}`}
              className="link underline">
            {CONTACT_EMAIL}
          </a>
        </p>
        <p>
          Describe el problema, la página donde ocurre y la tecnología de asistencia
          que usas. Nos comprometemos a responder en <strong className="text-fg font-semibold">5 días hábiles</strong>.
        </p>
      </Section>

      <Section title="Fecha de revisión" id="a-review">
        <p>
          Esta declaración fue revisada el {LAST_UPDATED} y se actualiza
          semestralmente o ante cambios significativos en la plataforma.
        </p>
      </Section>

    </LegalLayout>
  )
}
