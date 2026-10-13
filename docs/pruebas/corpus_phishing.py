"""
Corpus de prueba — 60 correos de PHISHING en contexto colombiano.

Reconstruidos a partir de modalidades documentadas públicamente en Colombia
(ver docs/pruebas/README.md): suplantación de la DIAN (embargos, devoluciones),
falsas citaciones judiciales y fotomultas (Fiscalía, SIMIT), bancos y billeteras
(Bancolombia, Davivienda, Nequi, llaves Bre-B), mensajería, y fraudes BEC contra
el área de tesorería de una empresa de retail ficticia (Comercial Andina S.A.S.).

Los dominios de los remitentes y de los enlaces son parecidos a los reales
(typosquatting, subdominios, acortadores) como en las campañas reales. Este
archivo es solo un corpus de evaluación: no enviar estos correos a nadie.

Autenticación: un atacante que registra su propio dominio puede pasar SPF y
DKIM; por eso hay casos con spf=pass desde dominios parecidos y desde Gmail,
además de suplantaciones directas que fallan SPF/DMARC.
"""

TO = "laura.mendez@comercialandina.com.co"
FAIL = "spf=fail smtp.mailfrom={d}; dkim=none; dmarc=fail (p=REJECT) header.from={d}"
SOFT = "spf=softfail smtp.mailfrom={d}; dkim=none; dmarc=none header.from={d}"
PASS = "spf=pass smtp.mailfrom={d}; dkim=pass header.d={d}; dmarc=none header.from={d}"
GMAIL = "spf=pass smtp.mailfrom=gmail.com; dkim=pass header.d=gmail.com; dmarc=pass header.from=gmail.com"
OUTLOOK = "spf=pass smtp.mailfrom=outlook.com; dkim=pass header.d=outlook.com; dmarc=pass header.from=outlook.com"


def a(kind, dom=""):
    return {"fail": FAIL, "soft": SOFT, "pass": PASS}[kind].format(d=dom) if kind in ("fail", "soft", "pass") \
        else {"gmail": GMAIL, "outlook": OUTLOOK}[kind]


P = []


def add(id, type, frm, auth, subject, body, basis, reply_to="", hops=6):
    P.append(dict(id=id, label="phishing", type=type, frm=frm, to=TO, auth=auth,
                  subject=subject, body=body, basis=basis, reply_to=reply_to, hops=hops))


# ══ GENÉRICO (9) — masivo, sin personalizar ═══════════════════════
add("P01", "generic", "DIAN <notificaciones@dian-gov.com.co>", a("pass", "dian-gov.com.co"),
    "Notificación de embargo de cuentas - Proceso de cobro coactivo",
    "Estimado contribuyente: la Dirección de Impuestos y Aduanas Nacionales le informa que "
    "existe un proceso de cobro coactivo en su contra por obligaciones pendientes. Para evitar "
    "el embargo de sus cuentas bancarias consulte el expediente en el siguiente enlace: "
    "http://dian-gov.com.co/consulta-proceso?id=88213 . Tiene 48 horas para presentar sus "
    "descargos. Evite sanciones graves.",
    "Suplantación DIAN con embargo (alerta DIAN 2024, Infobae)")
add("P02", "generic", "Devoluciones DIAN <devoluciones@dian.devolucion-saldos.com>", a("soft", "dian.devolucion-saldos.com"),
    "Usted tiene un saldo a favor pendiente de devolución",
    "Apreciado ciudadano, según su última declaración de renta tiene un saldo a favor de "
    "$1.874.000. Para recibir la devolución actualice sus datos bancarios aquí: "
    "https://bit.ly/3DianDevol . Si no actualiza en 24 horas, el saldo será anulado.",
    "Suplantación DIAN con devolución de impuestos (Noticias RCN 2026)")
add("P03", "generic", "SIMIT <comparendos@simit-notificaciones.com>", a("fail", "simit-notificaciones.com"),
    "Notificación de fotomulta - Comparendo No. 05001000000048211934",
    "Se le informa que su vehículo registra una infracción C29 detectada por cámara "
    "salvavidas. Valor: $604.100. Si no regulariza la infracción en 10 días no podrá vender ni "
    "traspasar el vehículo. Descargue la evidencia fotográfica: "
    "http://simit-notificaciones.com/evidencia/Fotomulta_048211934.zip",
    "Falsa fotomulta (alertas SIMIT y Alcaldía de Cali)")
add("P04", "generic", "Bancolombia <seguridad@bancolombia-seguridad.top>", a("pass", "bancolombia-seguridad.top"),
    "Su cuenta ha sido bloqueada temporalmente",
    "Estimado cliente, detectamos movimientos inusuales y por su seguridad su clave virtual fue "
    "bloqueada. Para desbloquearla ingrese a https://https.bancolombia-seguridad.top/personas "
    "y valide su identidad con su usuario, clave y los datos de su tarjeta. Si no lo hace hoy, "
    "su cuenta será cancelada.",
    "Cuenta bloqueada de Bancolombia con subdominio 'https' (ESET vía Colombia.com)")
add("P05", "generic", "Servientrega <envios@servientrega-co.info>", a("pass", "servientrega-co.info"),
    "Su paquete no pudo ser entregado",
    "Tenemos un paquete a su nombre retenido en bodega por dirección incompleta. Pague el "
    "reenvío de $6.900 para programar la entrega: http://servientrega-co.info/reprogramar . "
    "Después de 72 horas el paquete será devuelto al remitente.",
    "Falso aviso de mensajería con cobro pequeño")
add("P06", "generic", "Netflix <info@netflix-pagos.co>", a("pass", "netflix-pagos.co"),
    "Tu membresía está en espera",
    "No pudimos procesar el pago de tu suscripción. Actualiza tu método de pago para seguir "
    "viendo tus series: http://netflix-pagos.co/actualizar . Si no lo haces, tu cuenta se "
    "suspenderá hoy.",
    "Phishing de suscripción (masivo)")
add("P07", "generic", "Premios Éxito <premios.exito.colombia@gmail.com>", a("gmail"),
    "¡Felicidades! Ganaste un bono de $500.000",
    "Hola, tu correo fue seleccionado en el sorteo de aniversario de Almacenes Éxito. Ganaste un "
    "bono de $500.000. Para reclamarlo llena la encuesta y paga el envío de la tarjeta: "
    "https://forms.gle/x8KpQ2bonoExito . Solo para los primeros 100.",
    "Falso sorteo de marca de retail desde Gmail")
add("P08", "generic", "Microsoft 365 <no-reply@m365-mailbox-verify.com>", a("pass", "m365-mailbox-verify.com"),
    "Su buzón está lleno - acción requerida",
    "Su buzón de correo ha alcanzado el 99% de su capacidad. Los mensajes nuevos serán "
    "rechazados. Verifique su cuenta para obtener 50 GB adicionales gratis: "
    "https://m365-mailbox-verify.com/owa/login?user=laura.mendez",
    "Robo de credenciales de correo corporativo")
add("P09", "generic", "Fiscalía General de la Nación <citaciones@fiscalia-gov.net>", a("fail", "fiscalia-gov.net"),
    "Citación Judicial - Proceso No. 110016000049202600153",
    "Por medio de la presente se le cita a audiencia de imputación de cargos dentro del proceso "
    "de la referencia. Revise la documentación adscrita en el archivo adjunto. Contraseña del "
    "archivo: 2026. Descargar: http://fiscalia-gov.net/citacion/Citacion_Judicial.rar . La "
    "inasistencia generará orden de captura.",
    "Falsa citación judicial con adjunto comprimido (El Colombiano; Fiscalía 2023)")

# ══ SPEAR (9) — dirigido a la persona, con datos de su trabajo ════
add("P10", "spear", "Portal Proveedores <portal@comercialandina-proveedores.com>", a("pass", "comercialandina-proveedores.com"),
    "Laura, tienes 3 facturas pendientes de aprobación",
    "Hola Laura Méndez, como responsable de inventarios tienes 3 facturas de proveedores "
    "esperando tu aprobación en el portal antes del cierre de mes. Ingresa con tu usuario de "
    "red para revisarlas: https://comercialandina-proveedores.com/sso/login",
    "Spear con dominio parecido al de la empresa")
add("P11", "spear", "Recursos Humanos <rrhh.comercialandina@gmail.com>", a("gmail"),
    "Laura - actualización de datos para el pago de la prima",
    "Hola Laura, para incluirte en el pago de la prima de diciembre necesitamos que confirmes tu "
    "número de cuenta y tu cédula en este formulario antes del viernes: "
    "https://forms.gle/PrimaAndina2026 . Gracias, Talento Humano.",
    "Suplantación de RR. HH. desde Gmail para robar datos personales")
add("P12", "spear", "SharePoint <share@sharepoint-comercialandina.com>", a("pass", "sharepoint-comercialandina.com"),
    "Andrés Gómez compartió 'Inventario_Laureles_Oct.xlsx' contigo",
    "Andrés Gómez ha compartido un archivo contigo: Inventario_Laureles_Oct.xlsx. Este enlace "
    "solo funciona para laura.mendez@comercialandina.com.co. Abrir: "
    "https://sharepoint-comercialandina.com/:x:/g/personal/inventario?e=Lr9",
    "Falso archivo compartido usando el nombre de un colega real")
add("P13", "spear", "Mesa de Ayuda <mesadeayuda@comercialandina-ti.com>", a("pass", "comercialandina-ti.com"),
    "Laura, tu contraseña vence hoy",
    "Hola Laura, tu contraseña de red vence hoy a las 6:00 p. m. Para conservar el acceso al ERP "
    "y al correo, mantenla aquí: https://comercialandina-ti.com/password/keep?u=lmendez . "
    "Equipo de TI.",
    "Spear que imita el aviso real de vencimiento de contraseña")
add("P14", "spear", "Universidad EAFIT <certificados@eafit-edu.co>", a("pass", "eafit-edu.co"),
    "Laura, tu certificado requiere validación",
    "Hola Laura, para emitir tu certificado del curso 'Analítica de datos para retail' debes "
    "validar tu identidad e iniciar sesión con tu cuenta de Microsoft: "
    "http://eafit-edu.co/certificados/validar",
    "Spear apoyado en un evento real de la víctima")
add("P15", "spear", "LinkedIn <invitaciones@linkedln-mail.com>", a("pass", "linkedln-mail.com"),
    "Carlos Pérez te envió un mensaje sobre una vacante",
    "Laura, vi tu perfil de jefe de inventarios y tenemos una vacante de Gerente de Operaciones "
    "en Grupo Retail. Revisa la descripción del cargo aquí: "
    "http://linkedln-mail.com/jobs/view/GerenteOps.docm",
    "Oferta laboral falsa con typosquatting (linkedln)")
add("P16", "spear", "Juguetes Andes <ventas@juguetes-andes.com>", a("pass", "juguetes-andes.com"),
    "Re: Cotización pedido temporada navideña",
    "Laura, buen día. Te comparto la cotización actualizada del pedido de temporada con los "
    "nuevos precios. Por el tamaño del archivo lo subí a la nube: "
    "https://juguetes-andes.com/docs/Cotizacion_Navidad.html",
    "Spear que continúa una conversación real con un proveedor")
add("P17", "spear", "Siigo <facturacion@siigo-documentos.com>", a("pass", "siigo-documentos.com"),
    "Factura electrónica FV 33822 rechazada - COMERCIAL ANDINA S.A.S.",
    "COMERCIAL ANDINA S.A.S., la factura FV 33822 fue rechazada por inconsistencias en el NIT. "
    "Ingrese con su usuario y contraseña de Siigo para corregirla: "
    "https://siigo-documentos.com/login",
    "Spear con plataforma contable que usa la víctima")
add("P18", "spear", "DocuSign <dse@docusign-andina.net>", a("pass", "docusign-andina.net"),
    "Laura, revisa y firma: Acuerdo de confidencialidad proveedores 2027",
    "Natalia Ríos te envió un documento para firmar: Acuerdo de confidencialidad proveedores "
    "2027. REVISAR DOCUMENTO: https://docusign-andina.net/signing/Doc?id=a77f",
    "Falso flujo de firma electrónica")

# ══ WHALING (8) — dirigido a directivos ═══════════════════════════
for i, (subj, body, frm, auth, basis) in enumerate([
    ("Demanda laboral contra Comercial Andina S.A.S. - notificación al representante legal",
     "Señor Gerente General: se notifica al representante legal la admisión de una demanda "
     "laboral en su contra. Debe consultar el auto admisorio y los anexos en el portal de la "
     "Rama Judicial: http://ramajudicial-notificaciones.com/proceso/2026-00417",
     "Rama Judicial <notificaciones@ramajudicial-notificaciones.com>", a("pass", "ramajudicial-notificaciones.com"),
     "Falsa demanda al representante legal"),
    ("Junta Directiva: documentos confidenciales para la sesión del jueves",
     "Dr. Fernando Arango, por instrucción de la presidencia de la Junta, comparto los estados "
     "financieros preliminares y la propuesta de fusión. Son confidenciales; acceda con su "
     "cuenta corporativa: https://boardroom-docs.net/andina/junta",
     "Secretaría de Junta <secretaria.junta@boardroom-docs.net>", a("pass", "boardroom-docs.net"),
     "Documentos de junta directiva falsos"),
    ("Superintendencia de Industria y Comercio - Requerimiento al Gerente",
     "Señor Gerente, la SIC adelanta una investigación por presunta publicidad engañosa en sus "
     "promociones en línea. Debe responder el requerimiento en 5 días hábiles en "
     "http://sic-requerimientos.co/radicar . La omisión acarrea multas de hasta 2.000 SMMLV.",
     "SIC <requerimientos@sic-requerimientos.co>", a("fail", "sic-requerimientos.co"),
     "Requerimiento regulatorio falso al gerente"),
    ("Invitación personal: Foro de Líderes del Retail 2026",
     "Estimado Fernando, por su liderazgo en Comercial Andina ha sido seleccionado como panelista "
     "del Foro de Líderes del Retail 2026. Confirme su participación y datos para el contrato en "
     "https://foroliderretail.com/panelistas/registro",
     "Foro Retail <invitaciones@foroliderretail.com>", a("pass", "foroliderretail.com"),
     "Invitación halagadora a un directivo"),
    ("CFO - Aprobación urgente de inversión en CDT",
     "Dra. Patricia Lozano, el asesor de banca empresarial requiere su aprobación hoy para "
     "constituir el CDT a 180 días a tasa preferencial. Firme la autorización con el token del "
     "banco en https://bancaempresas-bancolombia.com/aprobaciones",
     "Banca Empresarial <asesor@bancaempresas-bancolombia.com>", a("pass", "bancaempresas-bancolombia.com"),
     "Whaling a la directora financiera con banca empresarial falsa"),
    ("Su declaración de renta como persona natural presenta inconsistencias",
     "Señor Fernando Arango Restrepo, la DIAN detectó inconsistencias en sus ingresos por "
     "dividendos del año gravable 2025. Descargue el emplazamiento para corregir: "
     "http://dian-fiscalizacion.co/emplazamiento/FA-2025.pdf.exe",
     "DIAN Fiscalización <fiscalizacion@dian-fiscalizacion.co>", a("soft", "dian-fiscalizacion.co"),
     "DIAN dirigida a un directivo con ejecutable disfrazado"),
    ("Entrevista con Revista Dinero - preguntas previas",
     "Buenas tardes, Dr. Arango. Le envío el cuestionario previo para la entrevista sobre el "
     "crecimiento del canal en línea de Comercial Andina. Lo encuentra aquí (requiere inicio de "
     "sesión con su correo): https://dinero-entrevistas.com/cuestionario",
     "Revista Dinero <editorial@dinero-entrevistas.com>", a("pass", "dinero-entrevistas.com"),
     "Falso periodista a un directivo"),
    ("Firma pendiente: acta de asamblea extraordinaria",
     "Señor Fernando Arango, el acta de la asamblea extraordinaria de accionistas está pendiente "
     "de su firma como representante legal antes de radicarla en Cámara de Comercio. Firmar: "
     "https://camaramedellin-firmas.com/acta",
     "Cámara de Comercio <firmas@camaramedellin-firmas.com>", a("pass", "camaramedellin-firmas.com"),
     "Trámite mercantil falso al representante legal"),
], start=19):
    add(f"P{i}", "whaling", frm, auth, subj, body, basis)
for e in P[-8:]:
    e["to"] = "fernando.arango@comercialandina.com.co"

# ══ BEC (10) — fraude de pago, casi siempre sin enlaces ═══════════
add("P27", "bec", "Fernando Arango <gerencia@comercia1andina.com.co>", a("pass", "comercia1andina.com.co"),
    "Transferencia urgente y confidencial",
    "Laura, necesito que hoy mismo hagas una transferencia de $48.500.000 a un proveedor nuevo "
    "para cerrar una negociación confidencial. No lo comentes con nadie hasta que se anuncie. "
    "Te envío los datos bancarios en el siguiente correo. Estoy en reunión, responde solo por "
    "aquí. Fernando",
    "Fraude del CEO con dominio parecido (l → 1)", reply_to="f.arango.gerencia@gmail.com")
add("P28", "bec", "Distribuidora del Valle <cartera@distrivalle.com.co>", a("fail", "distrivalle.com.co"),
    "Cambio de cuenta bancaria para pagos",
    "Buenas tardes, les informamos que por cambio de entidad bancaria los pagos de las facturas "
    "FV 33790 y FV 33821 ($8.640.000) deben hacerse a partir de hoy a la cuenta de ahorros "
    "Davivienda No. 0570-1882-4417 a nombre de DISTRIBUIDORA DEL VALLE. Favor confirmar la "
    "programación del pago.",
    "Cambio de cuenta de proveedor real suplantado (SPF falla)", reply_to="cartera.distrivalle@outlook.com")
add("P29", "bec", "Distribuidora del Valle <cartera@distrivaIle.com.co>", a("pass", "distrivaIle.com.co"),
    "Re: Estado de cuenta a 30 de septiembre",
    "Laura, gracias por la confirmación. Te recuerdo que la cuenta anterior quedó inactivada. "
    "Para no generar intereses de mora, por favor realiza el pago de $8.640.000 hoy a la nueva "
    "cuenta Bancolombia ahorros 1027-559-8812. Adjunto certificación bancaria.",
    "Secuestro de hilo con dominio homógrafo (l mayúscula → I)")
add("P30", "bec", "Patricia Lozano <patricia.lozano.cfo@gmail.com>", a("gmail"),
    "Pago de anticipo hoy",
    "Laura, estoy fuera de la oficina sin acceso al portal. Por favor programa hoy un anticipo "
    "de $23.000.000 para el proveedor de juguetería a la cuenta que te dejo abajo. Yo lo apruebo "
    "en el sistema mañana. Banco de Bogotá, cuenta corriente 384-11920-6, NIT 901.882.104.",
    "Fraude de directiva desde correo personal")
add("P31", "bec", "Andrés Gómez <andres.gomez@comercialandina.com.co>", a("fail", "comercialandina.com.co"),
    "Favor con tarjetas de regalo",
    "Laura, ¿estás en la oficina? Necesito un favor rápido: compra 10 tarjetas de regalo de "
    "Google Play de $200.000 para un detalle a clientes. Envíame las fotos de los códigos por "
    "WhatsApp al 312 448 9021. Luego te reembolso.",
    "Fraude de tarjetas de regalo suplantando a un colega (spoofing, SPF falla)")
add("P32", "bec", "Nómina <nomina@comercialandina.com.co>", a("soft", "comercialandina.com.co"),
    "Cambio de cuenta de nómina - Natalia Ríos",
    "Hola, soy Natalia Ríos. Cambié de banco y necesito que mi nómina de esta quincena se "
    "consigne en mi nueva cuenta Nequi 3104482291. Por favor hazlo antes del corte del viernes. "
    "Gracias.",
    "Desvío de nómina", reply_to="natalia.rios.andina@outlook.com")
add("P33", "bec", "Juguetes Andes <ventas@juguetesandes.co>", a("pass", "juguetesandes.co"),
    "Orden de compra y datos para el anticipo",
    "Laura, recibimos la aprobación verbal del pedido. Para separar las 1.200 unidades necesitamos "
    "un anticipo del 50% ($31.700.000) hoy. Nuestra cuenta cambió: Davivienda corriente "
    "0090-2231-7790. Si no se consigna hoy perdemos el cupo de producción.",
    "Proveedor suplantado con otro TLD (.co en lugar de .com)")
add("P34", "bec", "Revisoría Fiscal <revisoria@kpmg-auditoria.co>", a("pass", "kpmg-auditoria.co"),
    "Confirmación de saldos con proveedores",
    "Estimada Laura, como parte de la auditoría anual necesitamos la relación de pagos a "
    "proveedores con números de cuenta y los soportes de las últimas 10 transferencias. Envíelos "
    "respondiendo este correo antes del miércoles.",
    "Falsa auditoría para obtener información financiera")
add("P35", "bec", "Fernando Arango <fernando.arango@comercialandina.com.co>", a("fail", "comercialandina.com.co"),
    "¿Estás disponible?",
    "Laura, ¿estás disponible? Necesito que me ayudes con un pago confidencial antes de las 3. "
    "Respóndeme apenas puedas. Enviado desde mi iPhone",
    "Primer contacto típico de fraude del CEO", reply_to="fernando.arango.ceo@outlook.com")
add("P36", "bec", "Abogado externo <dr.camilo.vargas@vargas-abogados.com>", a("pass", "vargas-abogados.com"),
    "Adquisición confidencial - instrucciones del Dr. Arango",
    "Señora Méndez, represento a la compañía en una adquisición que el Dr. Arango me pidió "
    "manejar con total reserva. Debe girar hoy $120.000.000 de depósito en garantía a la cuenta "
    "fiduciaria que le indicaré. No mencione esta operación a nadie del equipo financiero.",
    "Fraude del abogado (variante del fraude del CEO)")

# ══ CLONE (8) — copia de un correo legítimo con enlace cambiado ═══
add("P37", "clone", "Bancolombia <alertasynotificaciones@notificacionesbancolombia.co>",
    a("pass", "notificacionesbancolombia.co"), "Alertas y Notificaciones Bancolombia",
    "Bancolombia le informa: Compra por $1.187.450,00 en ALKOSTO EN LINEA el 08/10/2026 a las "
    "02:14 con su tarjeta débito *4417. Si no reconoce esta transacción cancélela aquí: "
    "http://notificacionesbancolombia.co/cancelar-compra . Este correo es informativo.",
    "Clon de alerta transaccional con enlace de 'cancelar'")
add("P38", "clone", "Davivienda <notificaciones@davivienda-co.com>", a("pass", "davivienda-co.com"),
    "Constancia de transferencia exitosa",
    "Hola LAURA MENDEZ, realizaste una transferencia a otros bancos por $3.250.000 desde tu "
    "cuenta de ahorros terminada en 2290. Si no realizaste esta operación, revierte la "
    "transacción ingresando a https://davivienda-co.com/revertir con tu clave.",
    "Clon de constancia de transferencia")
add("P39", "clone", "EPM <facturaelectronica@epm-facturas.com>", a("pass", "epm-facturas.com"),
    "Tu factura EPM de octubre está disponible",
    "Hola, tu factura de servicios públicos del contrato 4410228 ya está disponible. Valor a "
    "pagar: $238.760. Para evitar la suspensión del servicio, págala con tarjeta en "
    "http://epm-facturas.com/pagar-factura",
    "Clon de factura de servicios con amenaza de suspensión")
add("P40", "clone", "Mercado Libre <info@mercadolibre-envios.com>", a("pass", "mercadolibre-envios.com"),
    "¡Tu compra está en camino!",
    "Hola Laura, tu compra 'Silla ergonómica oficina' tiene un problema con la dirección de "
    "entrega. Confírmala e inicia sesión para que llegue a tiempo: "
    "http://mercadolibre-envios.com/mis-compras/confirmar",
    "Clon de notificación de envío")
add("P41", "clone", "Servientrega <notificaciones@servientrega.com>", a("fail", "servientrega.com"),
    "Tu envío guía 2109887733 no pudo ser entregado",
    "El envío con guía No. 2109887733 no pudo ser entregado el 08/10/2026. Descargue la "
    "constancia de visita y reprograme la entrega: "
    "http://45.133.182.20/servientrega/constancia_2109887733.zip",
    "Clon de mensajería con remitente real suplantado y URL por IP")
add("P42", "clone", "Zoom <no-reply@zoom-us.co>", a("pass", "zoom-us.co"),
    "Grabación en la nube disponible: Capacitación cajeros",
    "La grabación de la reunión 'Capacitación cajeros nuevo POS' ya está disponible. Para verla "
    "inicia sesión con tu cuenta corporativa: https://zoom-us.co/rec/share/capacitacion",
    "Clon de notificación de grabación")
add("P43", "clone", "Claro Colombia <facturaelectronica@claro-facturacion.com.co>",
    a("pass", "claro-facturacion.com.co"), "Factura electrónica Claro Hogar - cuenta 82293104",
    "Estimado cliente, su factura del periodo septiembre-octubre 2026 presenta mora. Total a "
    "pagar: $129.900. Evite el corte del servicio pagando en línea: "
    "https://claro-facturacion.com.co/pago-express",
    "Clon de factura de operador")
add("P44", "clone", "DocuSign <dse@docusign.net>", a("fail", "docusign.net"),
    "Completado: Programación de pagos a proveedores - semana 42",
    "Tesorería completó el documento 'Programación de pagos a proveedores - semana 42'. Ver el "
    "documento completado: http://docs-sign-view.com/envelope/9921 . No comparta este correo.",
    "Clon de flujo real interno con remitente suplantado")

# ══ VISHING (8) — llevan a una llamada ════════════════════════════
add("P45", "vishing", "Bancolombia <alertas@bancolombia-alertas.co>", a("pass", "bancolombia-alertas.co"),
    "Compra no reconocida por $2.849.000",
    "Se registró una compra internacional por $2.849.000 con su tarjeta *4417. Si usted no la "
    "realizó, comuníquese de inmediato con nuestra línea de fraudes 601 508 4471 para bloquear "
    "la tarjeta. Un asesor validará su identidad.",
    "Falsa compra con número de 'línea de fraudes'")
add("P46", "vishing", "DIAN <cobranzas@dian-cobro.co>", a("soft", "dian-cobro.co"),
    "Último aviso de cobro persuasivo",
    "Usted tiene una obligación tributaria vencida por $3.420.000. Para acordar un plan de pago "
    "y evitar el embargo, comuníquese hoy con el funcionario asignado al 315 882 0193 (WhatsApp "
    "o llamada). Horario: 8 a. m. a 5 p. m.",
    "DIAN con número de 'funcionario'")
add("P47", "vishing", "Soporte Microsoft <soporte.tecnico.microsoft@outlook.com>", a("outlook"),
    "Su licencia de Windows fue suspendida",
    "Detectamos que la licencia de Windows de su equipo fue usada en otro dispositivo y será "
    "suspendida. Llame al soporte técnico autorizado al 01 8000 519 233 para reactivarla y "
    "evitar la pérdida de sus archivos.",
    "Falso soporte técnico")
add("P48", "vishing", "Nequi <seguridad@nequi-colombia.com>", a("pass", "nequi-colombia.com"),
    "Intento de acceso a tu Nequi desde otro celular",
    "Hola, alguien intentó entrar a tu Nequi desde un celular en Bogotá. Para proteger tu plata, "
    "un asesor te llamará en los próximos minutos desde el 601 744 9132. Ten a la mano el código "
    "que te llegará por SMS para confirmar que eres tú.",
    "Aviso para robar el código de verificación por teléfono")
add("P49", "vishing", "Tránsito de Medellín <cobro.coactivo@transito-medellin.co>", a("fail", "transito-medellin.co"),
    "Comparendo en cobro jurídico - posible embargo",
    "Su comparendo No. 05001000000039218 pasó a cobro jurídico. Puede acogerse a un descuento "
    "del 50% si paga hoy. Llame a la línea de conciliación 604 322 1890 opción 2.",
    "Multa en cobro jurídico con línea falsa (occidente.co 2026)")
add("P50", "vishing", "Sura <servicioalcliente@sura-polizas.com>", a("pass", "sura-polizas.com"),
    "Tu póliza será cancelada por falta de pago",
    "Tu póliza de autos No. 3200194477 será cancelada hoy por un pago rechazado. Para mantener "
    "la cobertura llama a tu asesor al 324 118 7720 y paga con tarjeta por teléfono.",
    "Cobro de póliza por teléfono")
add("P51", "vishing", "Recursos Humanos <rrhh@comercialandina-rrhh.com>", a("pass", "comercialandina-rrhh.com"),
    "Llamada pendiente sobre tu liquidación",
    "Laura, necesitamos hablar contigo sobre un error en tu liquidación de cesantías. Llama hoy "
    "a la extensión externa 604 448 3021 y ten a mano tu cédula y tu clave del banco para "
    "verificar el abono.",
    "Vishing interno")
add("P52", "vishing", "Fiscalía <unidad.delitos.informaticos@gmail.com>", a("gmail"),
    "Su cuenta bancaria fue usada en un fraude",
    "Señora Laura Méndez, su cuenta aparece vinculada a una investigación por lavado de activos. "
    "Comuníquese con el investigador asignado al 310 229 4417 antes de las 4 p. m. para evitar "
    "la orden de captura. Este caso es reservado.",
    "Falsa investigación de la Fiscalía con número telefónico")

# ══ SMISHING (8) — llevan a SMS o WhatsApp ════════════════════════
add("P53", "smishing", "Bre-B Colombia <registro@llaves-breb.com>", a("pass", "llaves-breb.com"),
    "Tu llave Bre-B está pendiente de registro",
    "Tu llave digital Bre-B aún no está registrada y tienes una transferencia esperando "
    "aceptación. Escríbenos por WhatsApp al +57 321 448 1290 o responde con un SMS con tu número "
    "de cédula para activarla hoy: https://cutt.ly/breb-activa",
    "Llaves Bre-B con enlace acortado (Kaspersky vía DPL News, 2025)")
add("P54", "smishing", "Bancolombia <info@bancolombia-puntos.com>", a("pass", "bancolombia-puntos.com"),
    "Tus Puntos Colombia vencen hoy",
    "Tienes 48.200 Puntos Colombia que vencen hoy. Te enviaremos un SMS con el enlace para "
    "redimirlos; si no te llega, escríbenos por WhatsApp al 300 912 4471 con la palabra PUNTOS.",
    "Redención de puntos que lleva a SMS/WhatsApp")
add("P55", "smishing", "Servientrega <whatsapp@servientrega-whatsapp.com>", a("pass", "servientrega-whatsapp.com"),
    "Confirma tu entrega por WhatsApp",
    "Tu paquete está listo para entrega. Para confirmar la dirección escribe 'CONFIRMAR' al "
    "WhatsApp +57 302 551 8890 y sigue el enlace que te enviaremos por SMS.",
    "Mensajería que lleva a WhatsApp")
add("P56", "smishing", "Nequi <premios@nequi-bonos.co>", a("pass", "nequi-bonos.co"),
    "Recibiste un bono de $200.000 en tu Nequi",
    "¡Felicidades! Recibiste un bono por ser cliente frecuente. Para cargarlo responde el SMS "
    "que te llegará con el código de 6 dígitos o escríbenos al WhatsApp 318 220 9014.",
    "Bono falso para robar el código de verificación")
add("P57", "smishing", "Oferta laboral <empleos.colombia2026@gmail.com>", a("gmail"),
    "Trabajo desde casa $180.000 diarios",
    "Hola, buscamos personas para calificar productos en línea desde el celular. Pago diario de "
    "$180.000. Escribe 'QUIERO' al WhatsApp +57 316 448 0021 para recibir las instrucciones.",
    "Estafa de empleo por WhatsApp")
add("P58", "smishing", "Movistar <beneficios@movistar-premios.com>", a("pass", "movistar-premios.com"),
    "Ganaste un celular por tu antigüedad",
    "Por tu antigüedad como cliente ganaste un Samsung Galaxy. Para reclamarlo envía un SMS con "
    "la palabra GANADOR al 89922 y paga solo el envío.",
    "Premio falso con SMS de tarificación")
add("P59", "smishing", "Davivienda <seguridad@davivienda-sms.com>", a("pass", "davivienda-sms.com"),
    "Actualiza tu Daviplata por mensaje de texto",
    "Por la nueva normativa debes actualizar tu Daviplata. Te enviamos un SMS con el enlace; "
    "ábrelo desde tu celular e ingresa tu clave de 4 dígitos para no perder tu saldo.",
    "Actualización de billetera por SMS")
add("P60", "smishing", "Rappi <promos@rappi-pay.co>", a("pass", "rappi-pay.co"),
    "Tu RappiCard tiene un cupo preaprobado",
    "Tienes un cupo preaprobado de $4.000.000 en tu RappiCard. Actívalo escribiendo al WhatsApp "
    "+57 301 228 7741; un asesor te pedirá los datos para el desembolso.",
    "Crédito preaprobado que lleva a WhatsApp")

PHISHING = P
assert len(P) == 60, len(P)
