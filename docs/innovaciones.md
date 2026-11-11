# Innovaciones de Sentryx v2 para pymes colombianas

Sentryx v2 agrega cuatro funciones al detector de phishing: **Escudo de pagos**, **Control de cuatro ojos**, **Respuesta guiada** y **Red de alerta**. Este documento explica para cada una qué problema resuelve, cómo funciona, sus decisiones de seguridad y privacidad, sus límites y cómo probarla en local.

## Principio común: capas de negocio separadas del modelo

Ninguna de estas funciones cambia los pesos, los umbrales ni los modelos del ensemble. Corren después de él, en [`risk_layers.py`](../backend/apps/alerts/risk_layers.py), y dejan su resultado en el campo `Alert.risk_signals`:

```json
{
  "payment_shield": { "verdict": "lookalike_domain", "supplier": { "name": "..." } },
  "community": { "company_count": 3, "sectors": ["H"], "regions": ["Cundinamarca"] },
  "four_eyes": { "required": true, "reasons": [{ "trigger": "payment", "detail": "..." }] },
  "severity_adjustments": [{ "layer": "payment_shield", "from": "LOW", "to": "HIGH", "reason": "..." }]
}
```

Tres consecuencias:

- `risk_score` y `classification` siguen siendo exactamente lo que dio el modelo. Las métricas del ensemble para la tesis no cambian.
- Una capa puede **crear una alerta aunque el score sea bajo**. Un BEC bien escrito engaña al modelo de contenido, y sin alerta no habría dónde elevar la severidad. Por eso puede existir una alerta `HIGH` con clasificación `legitimate`; la interfaz la muestra como «Requiere revisión».
- Si una capa falla, el análisis sigue: el error queda en el log.

### Separación por empresa

`ShieldUser.organization` es ahora la frontera entre empresas, así que dejó de poder editarse con `PATCH /auth/me/`. Dos usuarios sin organización **no** se consideran de la misma empresa. Un usuario sin organización puede analizar correos, pero no tiene proveedores ni control de cuatro ojos ni red de alerta.

El registro es abierto y solo exige verificar el correo. La primera persona que registra un nombre de organización lo toma. Si el nombre ya existe, sin distinguir mayúsculas, la cuenta se crea sin organización y la respuesta es la misma, para no revelar qué empresas usan el sistema. Un superusuario la agrega a su empresa desde `/admin/`. **No quites esta regla**: sin ella, escribir el nombre de otra empresa daría acceso a sus proveedores y solicitudes.

**Límite conocido.** Alguien puede registrar primero el nombre de una empresa que aún no usa Sentryx. No accede a datos de esa empresa, pero un superusuario debe corregir la organización de las cuentas afectadas.

---

## 1. Escudo de pagos

**Problema.** El fraude BEC es el que más dinero le cuesta a una pyme: un correo pide cambiar la cuenta de un proveedor y nadie lo verifica. Suele estar bien redactado y no traer enlaces, así que el modelo puede darle un score bajo.

**Cómo funciona.** Detecta la intención de pago, extrae las cuentas y los bancos, compara el remitente con un directorio de proveedores de confianza y valida la factura electrónica adjunta.

| Veredicto | Cuándo |
|---|---|
| `match` | Dominio autorizado, y cuenta y factura sin problemas |
| `lookalike_domain` | El dominio imita a uno registrado: otro TLD (`.co` frente a `.com.co`), Levenshtein ≤ 2, `rn→m`, `0→o`, `l→1`, caracteres cirílicos o `proveedor.co.evil.tk` |
| `domain_mismatch` | El NIT de la factura es de un proveedor, pero el dominio no está autorizado |
| `account_mismatch` | La cuenta no coincide con la registrada, o el proveedor no tiene cuenta con qué comparar |
| `invoice_inconsistent` | Falla un chequeo de la factura o el adjunto se bloqueó |
| `unknown_supplier` | No hay ningún proveedor relacionado |

Con intención de pago y un veredicto distinto de `match`, la severidad sube al menos a `HIGH`, y la alerta queda como `bec` con la técnica `T1566.002`.

**Chequeos de la factura (UBL 2.1).** Acepta `Invoice` directo, `AttachedDocument` con el `Invoice` en CDATA y ZIP con el XML. Valida el dígito de verificación del NIT (módulo 11), el formato del CUFE (96 hexadecimales), que el NIT sea del proveedor, que el valor coincida con el del correo y que la cuenta coincida con la registrada.

**Seguridad y privacidad.**

- El número de cuenta se recibe una vez y se convierte en los últimos 4 dígitos más un HMAC-SHA256 con `PAYMENT_SHIELD_SECRET`. Nunca se guarda ni se devuelve completo.
- El XML se lee con `defusedxml` (bloquea XXE y expansión de entidades), también el que viene dentro del CDATA.
- El ZIP se lee en memoria, sin escribir a disco, con límites de archivos, de tamaño descomprimido y de relación de compresión.
- El dominio se toma de la dirección real: `"pagos@proveedor.co" <x@evil.tk>` da `evil.tk`. Antes el sistema tomaba el del nombre visible.
- Para no confundir un NIT o un celular con una cuenta, se mira la palabra más cercana al número. Nequi y Daviplata sí cuentan como cuenta.
- Los adjuntos no se guardan.
- No hay llamadas al portal de la DIAN: solo se genera el enlace para que el usuario consulte el CUFE a mano.

**Endpoints** (`/api/v1/payment-shield/`, analista o superior; solo el admin edita proveedores):

| Método y ruta | Uso |
|---|---|
| `GET, POST suppliers/` · `GET, PUT, PATCH, DELETE suppliers/{id}/` | Directorio de proveedores |
| `GET checks/` · `GET checks/{id}/` | Verificaciones de la organización |
| `POST checks/{id}/verify/` | Registrar la llamada, rechazar o aprobar |
| `POST checks/{id}/acknowledge-risk/` | «Entiendo el riesgo» desde la extensión, queda en la auditoría |
| `POST /api/v1/alerts/analyze/` | Ahora también acepta `multipart/form-data` con `attachments` |

**Modelos:** `Supplier`, `PaymentCheck`, más `Alert.risk_signals`.

**Limitaciones conocidas.**

- Si el directorio está vacío, todo correo que pida un pago se marca como `unknown_supplier` y sube a `HIGH`. Conviene cargar los proveedores antes de usarlo; de lo contrario habrá falsos positivos.
- Si el correo real de un proveedor fue comprometido y no trae un número de cuenta, el veredicto es `match`. La llamada de verificación sigue siendo el control de fondo.
- El CUFE se valida solo en formato: no se comprueba que la DIAN lo haya emitido.
- Registrar un dominio de correo gratuito (`gmail.com`) como autorizado hace que cualquier cuenta de ese dominio pase el chequeo de dominio.
- Si cambia `PAYMENT_SHIELD_SECRET`, hay que volver a registrar las cuentas.
- `analyze_email_task` de Celery no ejecuta estas capas porque no tiene un usuario asociado. Solo las ejecuta `POST /alerts/analyze/`.

---

## 2. Control de cuatro ojos

**Problema.** En una pyme, el fraude funciona porque una sola persona recibe el correo, lo cree y actúa. Este control aplica la separación de funciones al correo del día a día.

**Cómo funciona.** Si la severidad final alcanza el mínimo de la política (por defecto `HIGH`) y el correo pide un pago riesgoso, credenciales o abrir un adjunto de riesgo, queda bloqueado hasta que una segunda persona lo apruebe.

**Reglas de seguridad** (se validan en [`services.py`](../backend/apps/four_eyes/services.py), no en la vista):

- Nadie decide su propia solicitud, aunque sea admin. Si no hay otro aprobador, el error lo explica.
- El aprobador debe ser de la misma organización y estar en la lista de la política (o ser admin, si la lista está vacía).
- Con la política por defecto, el aprobador confirma con su código TOTP en ese momento. Sin 2FA activo no puede aprobar. Un código ya usado no vale dos veces.
- `select_for_update` impide dos decisiones simultáneas. Una solicitud decidida, cancelada o vencida no se vuelve a decidir.
- El rechazo exige una nota y ofrece «¿Ya hiciste clic o pagaste?», que abre la respuesta guiada.
- `verify` con `approved` solo se acepta si existe una solicitud aprobada para esa alerta. «Entiendo el riesgo» no sirve para saltarse una aprobación pendiente.
- El correo de aviso **no aprueba con un clic**: solo enlaza a una página que exige sesión, y no incluye el contenido del mensaje. Así, ni un prefetch del cliente de correo ni un reenvío pueden aprobar algo.
- Los intentos rechazados quedan en la auditoría como `FOUR_EYES_DENIED`, con su motivo. Se registran fuera de la transacción para que el rollback no los borre.

**Vencimiento.** Una tarea de Beat vence las solicitudes cada 5 minutos, avisa al solicitante y escala a los admins.

**Endpoints** (`/api/v1/four-eyes/`):

| Método y ruta | Uso |
|---|---|
| `GET, PUT policy/` | Política (solo el admin edita) |
| `POST requests/` | Pedir aprobación |
| `GET requests/?mine=true&to_approve=true&status=&alert=` | Listar |
| `GET requests/{id}/` | Detalle |
| `POST requests/{id}/approve/` · `reject/` | Decidir con `{totp_code, note}` |
| `POST requests/{id}/cancel/` | Cancelar, solo quien la pidió |
| `GET requests/{id}/status/` | Estado liviano para el polling, con throttle propio |
| `GET stats/` | Métricas del mes para el dashboard |

**Modelos:** `FourEyesPolicy`, `ApprovalRequest`.

**Limitaciones conocidas.**

- **El control es preventivo en la extensión y la web.** No hay botón para saltarse el bloqueo, pero nada impide abrir el correo desde otro cliente (celular, Outlook de escritorio) o un navegador sin la extensión.
- Los selectores de Gmail y Outlook pueden cambiar sin aviso. La capa se probó contra un DOM simulado, no contra las aplicaciones reales.
- Una empresa con un solo aprobador no puede usar el control para los correos que reciba esa persona. La página de política lo advierte.
- Las detecciones son reglas de palabras clave: pueden tener falsos positivos y negativos. Se amplían en [`detectors.py`](../backend/apps/four_eyes/detectors.py).
- Un RAR con contraseña no se abre: se reconoce porque el correo menciona una clave.

---

## 3. Respuesta guiada: «Hice clic, ¿y ahora qué?»

**Problema.** Una pyme sin área de TI no sabe qué hacer cuando alguien cae en un phishing, y los primeros minutos importan, sobre todo si hubo una transferencia.

**Cómo funciona.** Un botón rojo visible en todas las páginas abre un asistente a pantalla completa:

1. Pregunta qué pasó y cuándo. Hay 4 playbooks: contraseña, adjunto, pago y datos.
2. Muestra los pasos uno a uno, con temporizador de 15 minutos, contactos de emergencia con botón de llamar y notas opcionales.
3. Ofrece descargar el **paquete de denuncia** en PDF.

Al iniciar crea un `Incident` con su timeline y avisa a los admins de la organización.

**Paquete de denuncia.** Trae el resumen de los hechos, la línea de tiempo con la hora de cada paso, los IOC con enlaces desactivados (`hxxp://ejemplo[.]com`), el score y la técnica MITRE, los hashes SHA-256 de la evidencia y los próximos pasos: CAI Virtual y evaluación del reporte ante la SIC.

**Seguridad y privacidad.**

- **No hay números telefónicos inventados.** Cada empresa arranca con contactos por completar y una advertencia visible. El enlace del CAI Virtual se configura con `CAI_VIRTUAL_URL`; si falta, el PDF indica cómo buscarlo en el sitio oficial.
- Nada se envía automáticamente a las autoridades.
- El PDF no incluye remitente, destinatario, asunto ni cuerpo. Las notas del usuario sí van en el informe: la interfaz advierte no escribir contraseñas ni números de cuenta.
- Los teléfonos y URL de los contactos se validan: terminan en enlaces `tel:` y `https:`.

**Endpoints** (`/api/v1/response/`):

| Método y ruta | Uso |
|---|---|
| `GET playbooks/` · `GET config/` | Opciones del asistente y enlace del CAI |
| `POST start/` | Crea la sesión y el incidente |
| `GET {id}/` | Consultar la sesión |
| `POST {id}/steps/{step_id}/` | Marcar un paso |
| `POST {id}/complete/` | Terminar |
| `GET {id}/report.pdf` | Paquete de denuncia |
| `GET, POST contacts/` · `GET, PUT, PATCH, DELETE contacts/{id}/` | Contactos: todos leen para poder llamar; solo el admin edita |

**Modelos:** `Playbook`, `EmergencyContact`, `ResponseSession`.

**Limitaciones conocidas.**

- El contenido legal es orientativo: los plazos y requisitos deben verificarse con la normativa vigente y un asesor legal. El PDF lo advierte.
- Los hashes de evidencia usan el salt de la instalación: sirven para reconocer un correo dentro de Sentryx, no para probarlo ante un tercero sin ese salt.
- El estado `abandoned` existe en el modelo, pero nada lo asigna todavía: una sesión sin terminar queda `in_progress`.

---

## 4. Red de alerta entre pymes

**Problema.** Cuando una campaña ataca a un sector, cada pyme la enfrenta sola. Con un aviso temprano, las demás pueden estar prevenidas.

**Arquitectura.** Cada instalación es un **nodo**. El servicio `community_hub` (FastAPI con PostgreSQL propio) se levanta solo con el perfil `hub` y no afecta la instalación normal.

```
Nodo (apps.community)                     community_hub
  analizar correo ── guarda huellas ─┐
  tarea cada 15 min ── POST /indicators ──▶ guarda reportes por nodo
                     ◀── GET /feed ─────── publica solo si hay K nodos
  analizar correo ── busca en la copia local (sin llamar al hub)
```

**Qué se comparte.** Por cada indicador de una alerta con score ≥ 70 o resuelta por un analista: el tipo (`domain` o `url`), un HMAC-SHA256 del valor normalizado, el tipo de phishing, la técnica, la severidad, la sección CIIU, el departamento y la fecha sin hora.

**Qué nunca se comparte.** Cuerpo, asunto, remitentes, destinatarios, nombre de la empresa ni usuarios. El hub rechaza con 422 cualquier campo que no esté en su esquema.

**Decisiones de privacidad y seguridad.**

- **Opt-in explícito**, apagado por defecto. Solo un admin lo activa, aceptando un texto que queda versionado, con quién y cuándo.
- Solo se comparte lo detectado **después** del consentimiento.
- **Revocable:** al desactivar se deja de enviar y se pide borrar los aportes. Si el hub está caído, se reintenta en cada sincronización.
- **k-anonimato:** un indicador solo aparece con al menos K nodos distintos, y el feed nunca revela cuáles.
- **Antienvenenamiento:** un nodo nuevo cuenta como medio reporte durante 7 días, la reputación baja si nadie confirma sus reportes y el operador puede suspender nodos.
- **Dominios excluidos:** `gmail.com`, `outlook.com` y similares nunca se comparten ni coinciden; de lo contrario, un phishing enviado desde Gmail marcaría todo Gmail como campaña. Tampoco se reportan los dominios de los proveedores propios.
- Los falsos positivos marcados por un analista no se envían.
- Las keys de los nodos se guardan solo como hash y se entregan una sola vez. Se generan al reclamarlas, así que ni el operador llega a verlas.
- El nombre del nodo lo escribe quien se registra, sin autenticarse: el panel del operador lo pinta como texto y las acciones exigen un encabezado propio contra CSRF.
- El análisis nunca llama al hub: un hub lento o caído no retrasa la detección.

**Efecto en el análisis.** Si hay coincidencia, se agrega `risk_signals.community` y un aviso en lenguaje sencillo. Con `company_count ≥ 2`, la severidad sube al menos a `HIGH` sin tocar el score.

**Endpoints del nodo** (`/api/v1/community/`):

| Método y ruta | Uso |
|---|---|
| `GET, PUT settings/` | Estado, consentimiento, sector y departamento (admin) |
| `POST enable/` · `POST disable/` | Activar con `{accept_consent, sector, region}` o desactivar (admin) |
| `POST sync/` | Sincronizar ahora (admin) |
| `GET summary/` | Tarjeta del dashboard |

**Endpoints del hub** (puerto 8100):

| Método y ruta | Autenticación |
|---|---|
| `POST /nodes/register` · `POST /nodes/claim` | Pública, con token de registro para reclamar |
| `POST /indicators` · `GET /feed?since=` | `X-Node-Key` de un nodo activo |
| `DELETE /nodes/me/indicators` | `X-Node-Key`, también si está suspendido |
| `GET /operator` · `GET /operator/nodes` · `GET /operator/metrics` | Basic Auth con la clave de operador |
| `POST /operator/nodes/{id}/approve?established=` · `suspend` | Basic Auth más el encabezado `X-Operator-Action: 1` |

**Modelos:** `CommunitySettings`, `CommunityIndicator` y `OutboxEntry` en el nodo; `Node`, `Report` y `DailyCount` en el hub.

**Limitaciones conocidas.**

- La clave de la red es común: un miembro puede comprobar si un dominio concreto está en el feed calculando su HMAC. Las huellas protegen frente a terceros y al operador, no frente a un miembro curioso.
- Con K=2, cada empresa que reportó un indicador sabe que al menos otra también lo hizo. Sube K si la red crece.
- El operador conoce el nombre registrado de cada nodo y podría relacionarlo con sus reportes. Por eso hay que confiar en el operador o usar nombres genéricos.
- Un remitente falsificado puede hacer que se reporte un dominio inocente. K y la exclusión de dominios masivos reducen el riesgo, pero no lo eliminan.
- Marcar una alerta como falso positivo **después** de enviarla no la retira del hub. Hoy solo se retira con la revocación completa.
- Una instalación es un solo nodo aunque tenga varias empresas: cuentan como una en K, y al revocar una se borra todo lo del nodo y se reenvían los aportes de las demás.
- Las tablas del hub se crean con `create_all`, sin migraciones. El compose del hub no trae TLS: en producción va detrás de un proxy con HTTPS.
- La `feed` usa fechas sin hora, así que «últimas 24 h» en el dashboard significa hoy y ayer.
- Los umbrales de reputación son criterios razonables, no calibrados con datos reales.

---

## Cómo probar en local

### Preparación

1. Levanta el sistema: `docker compose up -d --build`.
2. Agrega al `.env` y reinicia con `docker compose up -d`. Sin `MFA_ENCRYPTION_KEY` nadie puede activar 2FA ni aprobar con la política por defecto.

   ```
   MFA_ENCRYPTION_KEY=una-clave-larga-de-prueba
   PAYMENT_SHIELD_SECRET=otra-clave-larga-de-prueba
   ```

3. Asigna una organización a los usuarios. `setup.sh` ya lo hace en instalaciones nuevas; en una existente:

   ```bash
   docker compose exec backend python manage.py shell -c "from apps.users.models import ShieldUser as U; print(U.objects.filter(email__in=['admin@sentryx.local','analista@sentryx.local']).update(organization='Sentryx Demo'))"
   ```

4. Con `admin@sentryx.local`, activa 2FA en *Seguridad de la cuenta*.

### Escudo de pagos

1. Como admin, en **Proveedores**, registra: NIT `900999991`, DV `6`, dominio `transandes.com.co`, teléfono `6015550100`, cuenta `12345678901`. Prueba también un DV incorrecto: el formulario lo rechaza.
2. Como analista, en **Analizar correo**, usa los ejemplos de abajo. Para el de la factura, sube [`factura_ficticia.xml`](pruebas/factura_ficticia.xml).

| Remitente | Cuerpo | Esperado |
|---|---|---|
| `pagos@transandes.com.co` | `Adjunto la factura por $ 1.500.000.` + XML | Semáforo verde, `match` |
| `pagos@transandes.com.co` | `Adjunto la factura por $ 2.000.000.` + XML | `invoice_inconsistent` |
| `pagos@transandes.co` | `Actualizamos nuestros datos bancarios. Consignar a la nueva cuenta 99988877766.` | `lookalike_domain`, alerta `HIGH` y BEC |
| `pagos@transandes.com.co` | `Nueva cuenta de ahorros 99988877766 en Davivienda.` | `account_mismatch` |
| `pagos@otra-empresa.org` | `Tiene una factura vencida. Debe transferir hoy.` | `unknown_supplier` |
| `pagos@transandes.com.co` | `Nos vemos el lunes en la reunión.` | Sin panel de escudo |

Comprueba en la base de datos o en la respuesta que `99988877766` no aparece completo en ninguna parte.

### Control de cuatro ojos

1. Como analista, analiza el correo de `lookalike_domain`. Aparece «Requiere aprobación de una segunda persona». Pulsa **Pedir aprobación**.
2. Como admin, ve a **Aprobaciones**: la insignia muestra 1. Prueba un código TOTP incorrecto y luego el correcto.
3. Comprueba en la auditoría los eventos `FOUR_EYES_APPROVED` y `FOUR_EYES_DENIED`.
4. Repite con otro correo y **Rechaza**: la solicitud ofrece «¿Ya hiciste clic o pagaste?».
5. Otros disparadores, con correos de score alto:
   - **Credenciales:** `URGENTE: tu cuenta sera suspendida. Verifica tu cuenta en http://login-seguro.tk/verify`, con `spf=fail dkim=fail dmarc=fail`.
   - **Adjuntos:** desde la API, con `"attachment_names": ["orden.docm"]`.
6. Vencimiento: pon 5 minutos en **Política de cuatro ojos** y espera a que corra la tarea. Sin SendGrid, los avisos quedan en el log: `docker compose logs backend celery_worker | grep "\[Email\]"`.

### Respuesta guiada

1. Pulsa **¿Caíste en un phishing?** y elige «Hice un pago o transferencia». Prueba el temporizador, un paso y una nota.
2. Al terminar, descarga el PDF y comprueba que las URL salen como `hxxp://...[.]...`. Para ver IOC, entra desde una alerta con **Hice clic en este correo**.
3. En **Incidentes** aparece la etiqueta «Respuesta guiada».
4. Como admin, completa **Contactos de emergencia** y vuelve al asistente: aparece el botón de llamar.

### Red de alerta

1. Agrega al `.env` una clave de operador y levanta el hub:

   ```
   COMMUNITY_HUB_OPERATOR_KEY=clave-del-operador
   ```

   ```bash
   docker compose --profile hub up -d
   ```

2. Corre la simulación. Muestra que el dominio compartido aparece en el feed y que el único no:

   ```bash
   python scripts/dev/simulate_network.py --operator-key clave-del-operador --local
   ```

3. Abre el panel en http://localhost:8100/operator (usuario `operator`, la clave de arriba).
4. Copia al `.env` las tres líneas que imprime el script (`COMMUNITY_HUB_URL`, `COMMUNITY_NODE_API_KEY`, `COMMUNITY_NETWORK_KEY`) y ejecuta `docker compose up -d`.
5. Como admin, en **Red de alerta**, elige un sector y un departamento, acepta el texto y activa. Pulsa **Sincronizar ahora**.
6. Analiza un correo de `pagos@pagos-falsos-demo.example` con el texto `Hola, adjunto información de la reunión.` Debe mostrar el aviso con 3 empresas y severidad `HIGH`, con el score intacto.
7. Desactiva la red y comprueba en las métricas del panel que bajan los reportes, si se habían compartido.

Para apagar el hub: `docker compose --profile hub stop community_hub community_db`.

### Tests automáticos

```bash
docker compose exec backend pytest
docker compose exec ml_engine pytest
docker compose exec frontend npx vitest run
make test-hub
```

### Extensión

Recarga la extensión en `chrome://extensions/` para tomar la versión 1.3.0. Analiza un correo que contenga el texto del BEC: si aplica cuatro ojos verás la capa de bloqueo con **Pedir aprobación**; si no, el banner rojo con **Entiendo el riesgo**. Ver [`extension/README.md`](../extension/README.md).

## Guías paso a paso

Cada pantalla donde se puede interactuar muestra sus pasos, para que una persona nueva sepa qué hacer sin ayuda.

- **Aplicación web:** `frontend/src/components/PageGuide.jsx` pinta la guía. Los textos están en `frontend/src/components/guides.js`.
- **Comportamiento:** la guía aparece abierta la primera vez. Si la persona la oculta, ese navegador lo recuerda solo para esa pantalla.
- **Extensión y panel del operador:** tienen sus pasos en `extension/popup.html`, `extension/overlay.js` y `community_hub/app/operator_panel.py`.

Al cambiar una pantalla, actualiza también su guía y cita los botones con el mismo texto que tienen en la interfaz.
