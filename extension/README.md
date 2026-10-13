# Sentryx — Extensión de navegador

Analiza el correo abierto en Gmail u Outlook con el motor de Sentryx y muestra el
puntaje de riesgo, el tipo de phishing, la técnica MITRE ATT&CK y el desglose por
capas (encabezados, contenido y URLs). Si el correo es sospechoso, la alerta queda
guardada en el dashboard.

Extensión Manifest V3 para Chrome y Edge (versión 110 o superior).

## Instalación

1. Abre `chrome://extensions/` (en Edge, `edge://extensions/`).
2. Activa el **Modo de desarrollador**.
3. Pulsa **Cargar descomprimida** y elige la carpeta `extension/` de este repositorio.
4. Fija el icono de Sentryx en la barra de herramientas.

Si Gmail u Outlook ya estaban abiertos, no hace falta recargar la pestaña: el popup
inyecta el script de lectura cuando lo necesita.

## Conectar con el backend

1. Pulsa el icono de Sentryx. La primera vez se abre la configuración.
2. Completa:
   - **URL del backend**: la URL de la API, terminada en `/api/v1`.
     - Desarrollo local con Docker Compose: `http://localhost/api/v1`.
     - Otro servidor: por ejemplo `https://sentryx.tu-empresa.com/api/v1`. Chrome te
       pedirá permiso para conectarte a ese servidor; acéptalo. El permiso se puede
       retirar después en los detalles de la extensión.
   - **Correo** y **contraseña** de tu cuenta de Sentryx (rol analista o administrador,
     con el correo verificado y la cuenta aprobada).
3. Pulsa **Guardar y conectar**.
4. Si tu cuenta tiene **verificación en dos pasos**, aparece el campo **Código de
   verificación**: escribe el código de 6 dígitos de Google Authenticator o Microsoft
   Authenticator y pulsa **Verificar**. Si no tienes el teléfono, usa **Usar código de
   recuperación**. Si cambias de ventana para mirar el código, el popup se cierra, pero
   al abrirlo de nuevo vuelve a ese mismo paso durante 5 minutos.

La contraseña no se guarda. La extensión conserva solo los tokens de sesión en el
almacenamiento local del navegador. Cuando la sesión caduca (por defecto, tras 1 día
sin uso, según `JWT_REFRESH_TOKEN_LIFETIME_DAYS`), la extensión pide iniciar sesión
otra vez. **Cerrar sesión** borra los tokens.

Las cuentas de administrador sin verificación en dos pasos no pueden analizar desde la
extensión cuando el backend tiene `MFA_REQUIRED_FOR_ADMINS=True`: primero hay que
activarla en el dashboard, en **Seguridad de la cuenta**.

## Uso

1. Abre un correo en Gmail u Outlook.
2. Pulsa el icono de Sentryx y luego **Analizar correo**.
3. El resultado muestra el puntaje de 0 a 100, la clasificación (legítimo, sospechoso,
   phishing o crítico), el tipo de phishing y la técnica MITRE. Si se creó una alerta,
   **Ver alerta** la abre en el dashboard.

## Privacidad

La extensión envía al backend el remitente, el asunto, los encabezados de
autenticación visibles y el cuerpo del correo abierto, solo cuando pulsas
**Analizar correo**. El backend guarda remitente, asunto y cuerpo únicamente como
hash SHA-256 con salt (Ley 1581 de 2012). La extensión no lee el destinatario, así que
en las alertas creadas desde aquí el hash del destinatario queda vacío.

## Archivos

```
extension/
├── manifest.json   Configuración (Manifest V3)
├── background.js   Sesión JWT, verificación en dos pasos y llamadas al backend
├── content.js      Lee el correo abierto en el DOM de Gmail u Outlook
├── popup.html      Interfaz del popup
├── popup.js        Lógica del popup y de la configuración
├── styles.css      Estilos (tema claro y oscuro)
└── icons/          Iconos de 16, 32, 48 y 128 px
```

## Cambios en la versión 1.2.0

- Inicio de sesión con verificación en dos pasos (código TOTP o de recuperación).
- La contraseña ya no se guarda; al actualizar desde la 1.1 se borra la que hubiera.
- Permiso opcional para conectarse a un backend distinto de `localhost`.
