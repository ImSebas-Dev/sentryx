/**
 * Textos de las guías paso a paso que muestra PageGuide, una por pantalla.
 *
 * Al cambiar una pantalla, actualiza aquí su guía y cita los botones con el
 * mismo texto que tienen en la interfaz, entre comillas «». Escribe para alguien
 * que nunca ha usado el sistema: sin siglas sin explicar y con máximo 7 pasos.
 * No describas pasos que la pantalla no permita a todos los roles sin aclararlo.
 */
const FORM_TITLE = 'Cómo llenar este formulario'

export const GUIDES = {
  // ── Acceso ───────────────────────────────────────────────
  login: {
    steps: [
      'Escribe el correo y la contraseña de tu cuenta de Sentryx. El ícono del ojo muestra lo que escribiste.',
      'Pulsa «Entrar».',
      'Si activaste la verificación en dos pasos, escribe también el código de tu teléfono.',
      '¿Aún no tienes cuenta? Pulsa «Crear cuenta». ¿Olvidaste la contraseña? Pulsa «¿La olvidaste?».',
    ],
  },
  'login-mfa': {
    title: 'Cómo completar el ingreso',
    steps: [
      'Abre Google Authenticator o Microsoft Authenticator en tu teléfono y busca Sentryx.',
      'Escribe el código de 6 dígitos que aparece. Cambia cada 30 segundos.',
      'Pulsa «Verificar».',
      '¿No tienes el teléfono? Pulsa «Usar código de recuperación» y escribe uno de los códigos que guardaste.',
    ],
  },
  register: {
    title: 'Cómo crear tu cuenta',
    steps: [
      'Escribe tu correo de trabajo. Ahí te llegará un enlace de confirmación.',
      'Escribe el nombre de tu empresa. Si ya usa Sentryx, déjalo vacío y pide a su administrador que te agregue.',
      'Crea una contraseña de al menos 10 caracteres y repítela.',
      'Lee y acepta los términos, y pulsa «Crear cuenta».',
      'Abre el correo que te enviamos y pulsa el enlace. Después, inicia sesión con tu correo y tu contraseña.',
    ],
  },
  'forgot-password': {
    title: 'Cómo recuperar tu contraseña',
    steps: [
      'Escribe el correo de tu cuenta y pulsa «Enviar enlace de recuperación».',
      'Abre el correo que te enviamos. Revisa también la carpeta de spam.',
      'Pulsa el enlace y elige una contraseña nueva.',
    ],
  },
  'reset-password': {
    title: 'Cómo crear tu nueva contraseña',
    steps: [
      'Escribe una contraseña de al menos 10 caracteres.',
      'Repítela en «Confirmar contraseña».',
      'Pulsa «Restablecer contraseña» y vuelve a iniciar sesión con ella.',
    ],
  },
  'verify-email-error': {
    title: 'Qué hacer ahora',
    steps: [
      'Pulsa «Reenviar correo de verificación» para recibir un enlace nuevo.',
      'Abre el correo más reciente y pulsa su enlace: los anteriores pueden haber vencido.',
    ],
  },

  // ── Monitoreo ────────────────────────────────────────────
  dashboard: {
    title: 'Cómo empezar con Sentryx',
    steps: [
      'Usa el menú para moverte entre pantallas. En el teléfono se abre con el botón de las tres líneas, arriba a la izquierda.',
      'Las tarjetas de arriba resumen cuántas alertas hay. Las críticas son las primeras que debes atender.',
      '¿Recibiste un correo que te parece raro? Pulsa «Analizar correo» antes de abrir sus enlaces o adjuntos.',
      'En «Alertas recientes» ves lo último detectado. Pulsa «Ver todas» para revisar la lista completa.',
      'Si ya caíste en un correo falso, pulsa el botón rojo «¿Caíste en un phishing?». Está disponible en todas las pantallas.',
      'Primera vez: activa la verificación en dos pasos en «Seguridad de la cuenta». Si eres administrador, registra también tus proveedores y contactos de emergencia.',
    ],
  },
  alerts: {
    steps: [
      'Cada fila es un correo que Sentryx marcó como riesgoso. Un puntaje más alto significa más riesgo.',
      'Para encontrar una alerta, pulsa «Filtros» y elige severidad, tipo, estado o dominio del remitente.',
      'Quita un filtro con la X de su etiqueta, o todos con «Limpiar todo».',
      'Pulsa una alerta para ver su detalle y decidir qué hacer.',
      'Si hay muchas, usa las flechas del final de la lista para cambiar de página.',
    ],
  },
  'alert-detail': {
    title: 'Cómo revisar esta alerta',
    steps: [
      'Lee primero los avisos de arriba: explican por qué este correo es riesgoso.',
      'Si aparece «Requiere aprobación de una segunda persona», no actúes todavía y pide la aprobación.',
      'Revisa el puntaje y las URL sospechosas. No abras esos enlaces.',
      'Analistas: en «Acciones», elige el estado y pulsa «Guardar cambio». Usa «En revisión» mientras investigas y «Resuelta» al terminar.',
      'Si Sentryx se equivocó, elige «Falso positivo». Esa corrección ayuda a mejorar el modelo.',
      'Si ya abriste un enlace o un adjunto de este correo, pulsa «Hice clic en este correo».',
    ],
  },
  analyze: {
    title: 'Cómo analizar un correo',
    steps: [
      '¿Quieres probar primero? Pulsa «Cargar ejemplo» para llenar el formulario con un correo de muestra.',
      'Copia del correo el remitente, el destinatario y el asunto. Son opcionales, pero mejoran el resultado.',
      'Si lo tienes, pega «Authentication-Results». En Gmail está en el menú de los tres puntos, opción «Mostrar original».',
      'Pega el texto del correo en «Contenido». Es el único campo obligatorio.',
      'Si el correo trae una factura electrónica, súbela con «Elegir archivo .xml o .zip».',
      'Pulsa «Analizar correo». Un puntaje más alto significa más riesgo. Sigue las indicaciones que aparezcan junto al resultado.',
      'Para revisar otro correo, pulsa «Limpiar». En el teléfono es el botón de la flecha circular.',
    ],
  },
  'payment-shield-panel': {
    title: 'Qué hacer con este resultado',
    steps: [
      'Revisa la lista de validaciones: te muestra qué coincide con los datos de tu proveedor y qué no.',
      'Antes de pagar, llama al número de confianza que aparece aquí. Nunca uses un teléfono que venga en el correo.',
      'Si el correo trae un enlace a la DIAN, abre la consulta y compara los datos de la factura.',
      'Analistas: cuando termines la llamada, pulsa «Registrar verificación telefónica» y anota el resultado.',
    ],
  },
  'verify-payment': {
    title: FORM_TITLE,
    steps: [
      'En «Resultado», elige lo que pasó: el proveedor lo confirmó, es un fraude, o apruebas el pago.',
      'En «Notas», escribe con quién hablaste y qué te confirmó. No escribas números de cuenta completos.',
      'Pulsa «Guardar». Si el correo requiere una segunda persona, no podrás aprobar el pago hasta que ella lo apruebe.',
    ],
  },
  'four-eyes-panel': {
    title: 'Qué hacer con este correo',
    steps: [
      'No pagues, no entregues claves ni abras adjuntos por ahora.',
      'Si quieres, escribe una nota para explicar el contexto a quien va a revisar.',
      'Pulsa «Pedir aprobación». Los aprobadores de tu empresa recibirán el aviso.',
      'Sigue la respuesta en «Aprobaciones», en la pestaña «Mis solicitudes». Continúa solo si la aprueban.',
    ],
  },
  approvals: {
    steps: [
      'Si te toca revisar, abre la pestaña «Por aprobar». Para aprobar o rechazar necesitas tener activa la verificación en dos pasos.',
      'Lee los motivos y confirma con el proveedor o el remitente por un canal que ya conozcas, no por el correo.',
      'Pulsa «Aprobar» o «Rechazar» y escribe el código de tu app de autenticación. Nadie puede aprobar su propia solicitud.',
      'Si pediste una revisión, ábrela en la pestaña «Mis solicitudes» para ver si sigue pendiente, aprobada o rechazada.',
      '¿Ya no la necesitas? Pulsa «Cancelar solicitud» mientras siga pendiente.',
    ],
  },
  'approval-decision': {
    title: FORM_TITLE,
    steps: [
      'Si se te pide, escribe el código de 6 dígitos de tu app de autenticación.',
      'Escribe una nota. Es opcional al aprobar y obligatoria al rechazar.',
      'Pulsa «Aprobar» o «Rechazar» para confirmar. Quien pidió la revisión verá tu decisión.',
    ],
  },

  // ── Respuesta ────────────────────────────────────────────
  incidents: {
    steps: [
      'Un incidente agrupa lo que pasó y lo que se hizo. La etiqueta «Respuesta guiada» indica que nació del asistente de emergencia.',
      'Analistas: para registrar uno, pulsa «Nuevo incidente».',
      'Escribe un título claro, elige la severidad y describe qué se detectó y qué se ha hecho.',
      'Pulsa «Crear incidente». Aparecerá en esta lista.',
    ],
  },
  'threat-intel': {
    steps: [
      'Escribe una URL, un dominio o una IP en «Consulta rápida de reputación» y pulsa «Verificar».',
      'Un aviso rojo significa que está en una lista de sitios maliciosos: no lo abras.',
      'Un aviso verde solo significa que no está en esas listas. No garantiza que sea seguro.',
      'Analistas: si descubres un sitio malicioso, pulsa «Añadir IOC manual». IOC significa indicador de compromiso.',
      'Elige el tipo y el nivel, escribe el valor y pulsa «Añadir IOC».',
    ],
  },
  suppliers: {
    steps: [
      'Este directorio es la lista de proveedores de confianza. Sentryx compara con ella cada correo que pide un pago.',
      'Administradores: pulsa «Nuevo proveedor» y llena sus datos. Carga aquí a todos los proveedores a los que les pagas.',
      'Si un proveedor cambia de datos, usa el lápiz para editarlo. La papelera lo quita del directorio.',
      'Analistas: consulta aquí el teléfono de confianza antes de confirmar un pago.',
    ],
  },
  'supplier-form': {
    title: FORM_TITLE,
    steps: [
      'Escribe el nombre, el NIT sin dígito de verificación y el DV. Sentryx avisa si no corresponden.',
      'En «Dominios autorizados», escribe todos los dominios desde los que te escribe, separados por coma.',
      'Escribe un teléfono que ya conozcas por tu contrato o tus facturas. No lo copies de un correo.',
      'Escribe el banco y la cuenta. Después solo verás los últimos 4 dígitos.',
      'Pulsa «Guardar».',
    ],
  },
  'respond-choose': {
    title: 'Cómo usar este asistente',
    steps: [
      'Elige cuándo pasó.',
      'Pulsa la opción que mejor describe lo que hiciste. Esto abre el reloj y crea un incidente.',
      'Sigue los pasos en orden y marca cada uno al terminarlo.',
    ],
  },
  'respond-steps': {
    title: 'Cómo avanzar',
    steps: [
      'Haz lo que indica el paso y marca su casilla. Empieza por los que dicen «Urgente».',
      'Pulsa «Siguiente». Si no puedes hacer un paso ahora, continúa y vuelve con «Anterior».',
      'Debajo de esta guía tienes los contactos de emergencia para llamar.',
      'Al final pulsa «Terminar». Nunca escribas contraseñas ni números de cuenta en las notas.',
    ],
  },
  'respond-done': {
    title: 'Qué sigue',
    steps: [
      'Pulsa «Descargar paquete de denuncia (PDF)» y guárdalo.',
      'Si vas a denunciar, presenta ese archivo ante las autoridades. Sentryx no lo envía por ti.',
      'Pulsa «Volver a Sentryx». Tu administrador ya recibió el aviso y podrá ayudarte.',
    ],
  },

  // ── Gestión ──────────────────────────────────────────────
  reports: {
    steps: [
      'Elige «Semanal» o «Mensual».',
      'Selecciona la semana o el mes en la lista. Los periodos «en curso» todavía tienen datos parciales.',
      'Revisa la vista previa, más abajo en esta página.',
      'Pulsa «Descargar PDF» para un informe listo para compartir o «CSV (Excel)» para trabajar el listado.',
    ],
  },
  retraining: {
    steps: [
      'Abre «Alertas» y entra a las que Sentryx clasificó mal.',
      'Analistas: en «Acciones», elige «Falso positivo» y pulsa «Guardar cambio». Cada una suma una corrección.',
      'Mira aquí la barra «Mínimo para reentrenar» para saber cuántas faltan.',
      'Administradores: al llegar al mínimo, pulsa el botón «Reentrenar» y espera. Esta página se actualiza sola.',
      'Revisa el resultado en «Último reentrenamiento».',
    ],
  },
  'four-eyes-policy': {
    steps: [
      'En «Cuándo aplica», marca los casos en los que un correo debe esperar a una segunda persona.',
      'Elige la «Severidad mínima» y cuántos minutos tiene el aprobador antes de que la solicitud venza.',
      'En «Aprobadores», marca quién puede aprobar. Si no marcas a nadie, aprueban los administradores.',
      'Revisa la etiqueta «Sin 2FA»: esa persona debe activar la verificación en dos pasos para poder aprobar.',
      'Deja al menos dos aprobadores, porque nadie puede aprobar su propia solicitud. Después pulsa «Guardar política».',
    ],
  },
  'emergency-contacts': {
    steps: [
      'Estos contactos aparecen en el asistente cuando alguien cae en un phishing. Déjalos listos antes de necesitarlos.',
      'Busca los que dicen «Por completar» y edítalos con el lápiz.',
      'Pulsa «Nuevo contacto» para agregar otros, como tu gerencia o tu soporte técnico.',
      'La papelera borra un contacto que ya no sirva.',
    ],
  },
  'contact-form': {
    title: FORM_TITLE,
    steps: [
      'Escribe un nombre fácil de reconocer en plena emergencia y elige el tipo.',
      'Copia el teléfono de tu contrato o del respaldo de tu tarjeta, nunca de un correo.',
      'Si tiene sitio web, agrégalo con https://.',
      'Pulsa «Guardar».',
    ],
  },
  community: {
    steps: [
      'Elige el sector y el departamento de tu empresa. Las alertas se muestran según esos datos.',
      'Lee «Qué se comparte y qué no»: Sentryx nunca comparte el contenido de tus correos.',
      'Si estás de acuerdo, marca la casilla de aceptación y pulsa «Activar la Red de alerta».',
      'Revisa el «Estado del nodo». «Sincronizar ahora» trae las alertas de la red sin esperar.',
      '¿Cambiaste de datos? Pulsa «Guardar cambios». ¿Quieres salir? Pulsa «Desactivar la red» y pediremos borrar tus aportes.',
    ],
  },

  // ── Cuenta ───────────────────────────────────────────────
  security: {
    steps: [
      'Instala Google Authenticator o Microsoft Authenticator en tu teléfono.',
      'Pulsa «Activar la verificación en dos pasos» y escanea el código QR con la app.',
      'Escribe el código de 6 dígitos que muestra la app y pulsa «Activar».',
      'Descarga o copia tus códigos de recuperación y guárdalos fuera de este equipo. Solo se muestran una vez.',
      'Marca la casilla de confirmación y pulsa «Terminar».',
      'Para apagarla, pulsa «Desactivar la verificación en dos pasos». Necesitarás tu contraseña y un código.',
    ],
  },
}
