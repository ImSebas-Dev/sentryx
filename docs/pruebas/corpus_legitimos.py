"""
Corpus de prueba — 40 correos LEGÍTIMOS en contexto colombiano.

Reconstruidos a partir de la forma de notificaciones reales de entidades y
comercios colombianos (bancos, DIAN, servicios públicos, comercio electrónico,
logística) y de correo interno de una empresa de retail ficticia
(Comercial Andina S.A.S., dominio comercialandina.com.co). Los nombres de
personas, números de cuenta, guías y montos son ficticios.

No reutilizar textos del dataset de entrenamiento (ml_engine/data/processed):
la prueba mide generalización.
"""

PASS = "spf=pass smtp.mailfrom={d}; dkim=pass header.d={d}; dmarc=pass (p=REJECT) header.from={d}"
TO = "laura.mendez@comercialandina.com.co"


def auth(domain):
    return PASS.format(d=domain)


LEGITIMOS = [
    # ── Banca y pagos ──────────────────────────────────────────────
    dict(id="L01", frm="Bancolombia <alertasynotificaciones@an.notificacionesbancolombia.com>",
         dom="an.notificacionesbancolombia.com", subject="Alertas y Notificaciones Bancolombia",
         body="Bancolombia le informa: Compra por $187.450,00 en ALMACENES EXITO ENVIGADO "
              "el 08/10/2026 a las 18:42 con su tarjeta débito *4417. Si no reconoce esta "
              "transacción comuníquese con la Sucursal Telefónica Bancolombia al 604 510 90 00. "
              "Este correo es informativo, por favor no lo responda.",
         basis="Alerta transaccional bancaria (formato de notificaciones de banca colombiana)"),
    dict(id="L02", frm="Davivienda <notificaciones@davivienda.com>", dom="davivienda.com",
         subject="Constancia de transferencia exitosa",
         body="Hola LAURA MENDEZ, realizaste una transferencia a otros bancos por $1.250.000 "
              "desde tu cuenta de ahorros terminada en 2290 hacia BANCO DE BOGOTA cuenta *8813 "
              "el 07 de octubre de 2026. Número de comprobante: 0045821773. Puedes consultar el "
              "detalle en la app Davivienda o en davivienda.com. Davivienda nunca te pedirá "
              "claves ni códigos por correo.",
         basis="Constancia de transferencia"),
    dict(id="L03", frm="Nequi <no-reply@nequi.com.co>", dom="nequi.com.co",
         subject="Tu extracto de septiembre ya está listo",
         body="¡Hola Laura! Ya puedes consultar el extracto de tu Nequi del mes de septiembre "
              "de 2026. Lo encuentras en la app, en la sección Movimientos > Extractos. Recuerda "
              "que en Nequi nunca te pediremos tu clave ni el código que te llega por mensaje.",
         basis="Aviso de extracto de billetera digital"),
    dict(id="L04", frm="Banco de Bogotá <extractos@bancodebogota.com.co>", dom="bancodebogota.com.co",
         subject="Extracto tarjeta de crédito Visa — corte 30 de septiembre",
         body="Señora Laura Méndez, adjuntamos el extracto de su tarjeta de crédito Visa terminada "
              "en 6021 con corte al 30 de septiembre de 2026. Pago mínimo: $412.300. Pago total: "
              "$2.184.900. Fecha límite de pago: 16 de octubre de 2026. El archivo PDF está "
              "protegido con su número de documento sin puntos ni espacios.",
         basis="Extracto de tarjeta con PDF protegido"),
    dict(id="L05", frm="PSE - ACH Colombia <notificaciones@achcolombia.com.co>", dom="achcolombia.com.co",
         subject="Comprobante de pago PSE - EPM",
         body="Transacción aprobada. Empresa: EMPRESAS PUBLICAS DE MEDELLIN E.S.P. Valor: $238.760. "
              "CUS: 1834402291. Banco: BANCOLOMBIA. Fecha: 06/10/2026 07:15 p. m. Conserve este "
              "comprobante como soporte de su pago.",
         basis="Comprobante de pago PSE"),
    dict(id="L06", frm="Daviplata <notificaciones@daviplata.com>", dom="daviplata.com",
         subject="Recibiste dinero en tu Daviplata",
         body="Hola, recibiste $95.000 de JUAN CARLOS RUIZ en tu Daviplata el 09/10/2026. Ya "
              "puedes usarlos para pagar, retirar sin tarjeta o transferir. Consulta tus "
              "movimientos en la app.",
         basis="Notificación de dinero recibido"),
    # ── Entidades públicas ─────────────────────────────────────────
    dict(id="L07", frm="DIAN <notificaciones@dian.gov.co>", dom="dian.gov.co",
         subject="Notificación electrónica - Acto administrativo No. 1001-2026-004512",
         body="Señor(a) COMERCIAL ANDINA S.A.S., NIT 901.234.567. La Dirección de Impuestos y "
              "Aduanas Nacionales le informa que se encuentra disponible un acto administrativo "
              "en el buzón de notificaciones electrónicas del portal www.dian.gov.co. Código de "
              "verificación de este correo: DN7K-2Q9R-55TA. Puede validarlo en la opción "
              "'Verificar correo DIAN'. La DIAN no solicita claves ni datos bancarios por correo.",
         basis="Notificación electrónica oficial de la DIAN (direcciones y código de verificación descritos por la DIAN)"),
    dict(id="L08", frm="DIAN <comunicaciones@dian.gov.co>", dom="dian.gov.co",
         subject="Recuerde: vencimientos de declaración de renta personas naturales",
         body="La DIAN recuerda que los plazos para presentar la declaración de renta de personas "
              "naturales del año gravable 2025 van hasta el 21 de octubre de 2026, según los dos "
              "últimos dígitos del NIT. Diligencie su declaración únicamente en www.dian.gov.co "
              "con su usuario y firma electrónica.",
         basis="Comunicación masiva oficial de la DIAN"),
    dict(id="L09", frm="RUNT <notificaciones@runt.com.co>", dom="runt.com.co",
         subject="Confirmación de registro en el RUNT",
         body="Su solicitud de inscripción como persona natural en el Registro Único Nacional de "
              "Tránsito fue aprobada. Puede consultar su información en www.runt.gov.co con su "
              "tipo y número de documento.",
         basis="Confirmación de trámite de tránsito"),
    dict(id="L10", frm="Mi Seguridad Social PILA <notificaciones@aportesenlinea.com>", dom="aportesenlinea.com",
         subject="Planilla PILA pagada - periodo 2026-09",
         body="La planilla No. 9483312 del aportante COMERCIAL ANDINA S.A.S. para el periodo "
              "2026-09 fue pagada exitosamente por $14.882.300. Número de cotizantes: 23. "
              "Descargue el soporte desde su sesión.",
         basis="Soporte de pago de seguridad social"),
    # ── Servicios públicos y telecomunicaciones ────────────────────
    dict(id="L11", frm="EPM <facturaelectronica@epm.com.co>", dom="epm.com.co",
         subject="Tu factura EPM de octubre está disponible",
         body="Hola, tu factura de servicios públicos del contrato 4410228 ya está disponible. "
              "Valor a pagar: $238.760. Fecha de pago oportuno: 20 de octubre de 2026. Puedes "
              "pagarla en la app EPM, en epm.com.co o en los puntos autorizados.",
         basis="Factura de servicios públicos"),
    dict(id="L12", frm="Claro Colombia <facturaelectronica@claro.com.co>", dom="claro.com.co",
         subject="Factura electrónica Claro Hogar - cuenta 82293104",
         body="Estimado cliente, adjuntamos la factura electrónica de su servicio Claro Hogar "
              "correspondiente al periodo septiembre-octubre 2026. Total a pagar: $129.900. "
              "Fecha límite: 25 de octubre. Consulte también en Mi Claro.",
         basis="Factura electrónica de operador"),
    dict(id="L13", frm="Vanti <notificaciones@grupovanti.com>", dom="grupovanti.com",
         subject="Programación de revisión periódica de gas",
         body="Le informamos que la revisión técnica reglamentaria de su instalación de gas está "
              "programada para el 22 de octubre de 2026 entre 8:00 a. m. y 12:00 m. El técnico "
              "portará carné de Vanti con código QR verificable. Si necesita reprogramar, use la "
              "Oficina Virtual o la línea 164.",
         basis="Aviso de visita técnica"),
    dict(id="L14", frm="Movistar <no-reply@movistar.com.co>", dom="movistar.com.co",
         subject="Tu plan cambió con éxito",
         body="Hola, confirmamos el cambio de tu plan móvil a Plan Ilimitado 30 GB a partir del "
              "próximo ciclo de facturación. Si no solicitaste este cambio, llama al *611 desde "
              "tu línea.",
         basis="Confirmación de cambio de plan"),
    # ── Comercio electrónico y logística ───────────────────────────
    dict(id="L15", frm="Mercado Libre <info@mercadolibre.com.co>", dom="mercadolibre.com.co",
         subject="¡Tu compra está en camino!",
         body="Hola Laura, tu compra 'Silla ergonómica oficina' ya va en camino. Llega entre el "
              "martes y el jueves. Puedes seguir el envío en Mis compras.",
         basis="Notificación de envío de marketplace"),
    dict(id="L16", frm="Rappi <hola@rappi.com>", dom="rappi.com",
         subject="Recibo de tu pedido #RP-77193845",
         body="Gracias por pedir en Rappi. Pedido: 2 almuerzos ejecutivos + bebidas. Total "
              "pagado: $58.400 con tarjeta *4417. Calificar tu experiencia nos ayuda a mejorar.",
         basis="Recibo de domicilio"),
    dict(id="L17", frm="Servientrega <notificaciones@servientrega.com>", dom="servientrega.com",
         subject="Tu envío guía 2109887733 fue entregado",
         body="El envío con guía No. 2109887733 fue entregado el 08/10/2026 a las 11:27 en "
              "CALLE 10 # 43A-30 MEDELLIN. Recibió: PORTERIA. Consulte el rastreo en "
              "servientrega.com.",
         basis="Confirmación de entrega de mensajería"),
    dict(id="L18", frm="Coordinadora <rastreo@coordinadora.com>", dom="coordinadora.com",
         subject="Guía 74021933411 - en reparto",
         body="Su envío de FALABELLA DE COLOMBIA S.A. con guía 74021933411 está en reparto en "
              "Medellín. Horario estimado: 2:00 p. m. a 6:00 p. m.",
         basis="Estado de envío"),
    dict(id="L19", frm="Falabella.com <noreply@falabella.com.co>", dom="falabella.com.co",
         subject="Confirmamos tu pedido 2018833901",
         body="¡Gracias por tu compra! Pedido 2018833901: Monitor 27 pulgadas QHD. Total: "
              "$1.099.900. Te avisaremos cuando sea despachado.",
         basis="Confirmación de pedido de retail"),
    dict(id="L20", frm="Avianca <noreply@avianca.com>", dom="avianca.com",
         subject="Confirmación de reserva - Código RXK7PQ",
         body="Hola LAURA MENDEZ, tu reserva RXK7PQ está confirmada. MDE - BOG, 24 de octubre de "
              "2026, vuelo AV9301, salida 6:05 a. m. Haz check-in en avianca.com desde 48 horas "
              "antes del vuelo.",
         basis="Confirmación de reserva aérea"),
    dict(id="L21", frm="Éxito <comunicaciones@exito.com>", dom="exito.com",
         subject="Laura, hasta 40% en tecnología este fin de semana",
         body="Aprovecha descuentos de hasta 40% en portátiles, celulares y televisores en "
              "exito.com y en nuestras tiendas. Válido del 17 al 19 de octubre de 2026 o hasta "
              "agotar existencias. Para dejar de recibir estos correos haz clic en cancelar "
              "suscripción.",
         basis="Correo promocional legítimo (marketing)"),
    dict(id="L22", frm="Siigo <notificaciones@siigo.com>", dom="siigo.com",
         subject="Documento soporte electrónico recibido - FV 33821",
         body="COMERCIAL ANDINA S.A.S., ha recibido la factura electrónica FV 33821 del "
              "proveedor DISTRIBUIDORA DEL VALLE S.A.S. por $4.320.000. Puede aceptarla o "
              "rechazarla desde su cuenta. CUFE: a8f1...c93d.",
         basis="Factura electrónica de proveedor (software contable)"),
    # ── Correo interno de la empresa (retail) ──────────────────────
    dict(id="L23", frm="Talento Humano <talentohumano@comercialandina.com.co>", dom="comercialandina.com.co",
         subject="Desprendible de nómina - segunda quincena de septiembre",
         body="Hola Laura, ya está disponible tu desprendible de pago de la segunda quincena de "
              "septiembre en el portal de autoservicio de nómina. Ingresa con tu usuario de "
              "red. Cualquier inquietud, escríbenos a este correo o a la extensión 1204.",
         basis="Comunicación interna de nómina"),
    dict(id="L24", frm="Mesa de Ayuda TI <mesadeayuda@comercialandina.com.co>", dom="comercialandina.com.co",
         subject="Ventana de mantenimiento ERP - sábado 18 de octubre",
         body="Equipo, el sábado 18 de octubre de 10:00 p. m. a 2:00 a. m. el ERP y el portal de "
              "proveedores no estarán disponibles por actualización. Las cajas de las tiendas "
              "operan normalmente en modo contingencia. Gracias por su comprensión.",
         basis="Aviso interno de TI"),
    dict(id="L25", frm="Andrés Gómez <andres.gomez@comercialandina.com.co>", dom="comercialandina.com.co",
         subject="Re: Inventario tienda Laureles",
         body="Laura, revisé el conteo cíclico de Laureles. La diferencia en la categoría de "
              "aseo es de 14 unidades, ya hice el ajuste en el sistema. Mañana te paso el "
              "informe completo de las otras tres tiendas.",
         basis="Correo de trabajo entre colegas"),
    dict(id="L26", frm="Natalia Ríos <natalia.rios@comercialandina.com.co>", dom="comercialandina.com.co",
         subject="Invitación: comité de compras jueves 3 p. m.",
         body="Hola a todos, los invito al comité de compras del jueves 16 a las 3:00 p. m. en la "
              "sala 2 o por Teams. Temas: temporada navideña, negociación con proveedores de "
              "juguetería y metas del cuarto trimestre.",
         basis="Invitación a reunión interna"),
    dict(id="L27", frm="Gerencia General <gerencia@comercialandina.com.co>", dom="comercialandina.com.co",
         subject="Resultados del tercer trimestre",
         body="Equipo, cerramos el tercer trimestre con ventas 8% por encima del año anterior y "
              "un crecimiento de 22% en el canal en línea. Gracias por el trabajo. El viernes "
              "compartiremos los detalles en la reunión general.",
         basis="Comunicado del gerente (legítimo, mismo dominio)"),
    dict(id="L28", frm="Tesorería <tesoreria@comercialandina.com.co>", dom="comercialandina.com.co",
         subject="Programación de pagos a proveedores - semana 42",
         body="Hola Laura, adjunto la programación de pagos a proveedores de la semana 42 "
              "aprobada por la Dirección Financiera. Los pagos se dispersan el viernes por el "
              "portal empresarial del banco, a las cuentas ya inscritas.",
         basis="Correo financiero interno legítimo (parecido a un BEC pero sin cambio de cuenta)"),
    dict(id="L29", frm="Seguridad de la Información <seguridad@comercialandina.com.co>", dom="comercialandina.com.co",
         subject="Cuidado: correos falsos a nombre de la DIAN",
         body="Equipo, están circulando correos falsos que suplantan a la DIAN con supuestos "
              "embargos y enlaces para 'consultar el proceso'. La DIAN solo escribe desde "
              "notificaciones@dian.gov.co y comunicaciones@dian.gov.co. Si reciben uno, no lo "
              "abran y repórtenlo a este buzón.",
         basis="Aviso interno de concienciación (menciona términos de phishing sin serlo)"),
    dict(id="L30", frm="Mesa de Ayuda TI <mesadeayuda@comercialandina.com.co>", dom="comercialandina.com.co",
         subject="Tu contraseña de red vence en 5 días",
         body="Hola Laura, tu contraseña de red vence el 17 de octubre. Cámbiala presionando "
              "Ctrl+Alt+Supr en tu equipo de la oficina y eligiendo 'Cambiar una contraseña'. "
              "Nunca te pediremos tu contraseña por correo ni por teléfono.",
         basis="Aviso real de vencimiento de contraseña (sin enlace)"),
    # ── Proveedores, educación y otros ─────────────────────────────
    dict(id="L31", frm="Distribuidora del Valle <cartera@distrivalle.com.co>", dom="distrivalle.com.co",
         subject="Estado de cuenta a 30 de septiembre",
         body="Buenas tardes, adjuntamos el estado de cuenta de COMERCIAL ANDINA S.A.S. con corte "
              "al 30 de septiembre. Saldo pendiente: $8.640.000 correspondiente a las facturas FV "
              "33790 y FV 33821. Los pagos se reciben en la cuenta corriente registrada en el "
              "RUT. Quedamos atentos.",
         basis="Correo de cartera de proveedor"),
    dict(id="L32", frm="Universidad EAFIT <noreply@eafit.edu.co>", dom="eafit.edu.co",
         subject="Certificado del curso Analítica de datos para retail",
         body="Felicitaciones, Laura. Completaste el curso de educación continua 'Analítica de "
              "datos para retail'. Descarga tu certificado desde el portal de estudiantes con tu "
              "usuario institucional.",
         basis="Correo académico"),
    dict(id="L33", frm="LinkedIn <messages-noreply@linkedin.com>", dom="linkedin.com",
         subject="Laura, tienes 3 invitaciones nuevas",
         body="Carlos Pérez, Gerente de Operaciones en Grupo Retail, y 2 personas más quieren "
              "conectar contigo. Ver invitaciones.",
         basis="Notificación de red social"),
    dict(id="L34", frm="Microsoft 365 <no-reply@microsoft.com>", dom="microsoft.com",
         subject="Resumen de actividad de tu cuenta de Microsoft",
         body="Este es el resumen semanal de la actividad de tu cuenta laura.mendez@... Inicios "
              "de sesión: Medellín, Colombia (Windows). Si no reconoces alguna actividad, revisa "
              "la configuración de seguridad en account.microsoft.com.",
         basis="Notificación de seguridad legítima (texto parecido a phishing de cuenta)"),
    dict(id="L35", frm="Google <no-reply@accounts.google.com>", dom="accounts.google.com",
         subject="Alerta de seguridad",
         body="Se accedió a tu cuenta de Google desde un nuevo dispositivo Android en Medellín. "
              "Si fuiste tú, no necesitas hacer nada. Si no, te ayudaremos a proteger tu cuenta. "
              "Puedes ver la actividad de seguridad en myaccount.google.com/notifications.",
         basis="Alerta de inicio de sesión legítima"),
    dict(id="L36", frm="Colsubsidio <notificaciones@colsubsidio.com>", dom="colsubsidio.com",
         subject="Tu subsidio monetario de octubre fue abonado",
         body="Hola Laura, el subsidio monetario de octubre por $64.000 fue abonado a tu tarjeta "
              "Colsubsidio. Consulta tu saldo en la app.",
         basis="Notificación de caja de compensación"),
    dict(id="L37", frm="Sura <notificaciones@segurossura.com.co>", dom="segurossura.com.co",
         subject="Renovación de tu póliza de vehículo",
         body="Tu póliza de autos No. 3200194477 vence el 30 de octubre de 2026. La renovaremos "
              "automáticamente con el mismo medio de pago. Si quieres cambiar coberturas, "
              "ingresa a segurossura.com.co o comunícate con tu asesor.",
         basis="Aviso de renovación de seguro"),
    dict(id="L38", frm="Cámara de Comercio de Medellín <notificaciones@camaramedellin.com.co>",
         dom="camaramedellin.com.co", subject="Certificado de existencia y representación legal",
         body="Adjuntamos el certificado de existencia y representación legal de COMERCIAL "
              "ANDINA S.A.S. solicitado el 09/10/2026. Puede verificar su autenticidad con el "
              "código de verificación impreso en el documento.",
         basis="Certificado mercantil solicitado"),
    dict(id="L39", frm="Zoom <no-reply@zoom.us>", dom="zoom.us",
         subject="Grabación en la nube disponible: Capacitación cajeros",
         body="La grabación de la reunión 'Capacitación cajeros nuevo POS' ya está disponible. "
              "Duración: 58 minutos. Compártela con tu equipo desde tu cuenta de Zoom.",
         basis="Notificación de plataforma de reuniones"),
    dict(id="L40", frm="Proveedor Juguetes Andes <ventas@juguetesandes.com>", dom="juguetesandes.com",
         subject="Cotización pedido temporada navideña",
         body="Laura, buen día. Como hablamos, adjunto la cotización para el pedido de temporada: "
              "1.200 unidades surtidas, entrega en dos despachos (1 y 15 de noviembre). Precios "
              "sostenidos hasta el 24 de octubre. Quedo atento a la orden de compra.",
         basis="Cotización comercial de proveedor"),
]

for e in LEGITIMOS:
    e.update(label="legitimate", type="legitimate", to=TO, auth=auth(e.pop("dom")),
             reply_to="", hops=4)
