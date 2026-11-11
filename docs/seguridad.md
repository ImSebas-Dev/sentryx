# Seguridad de Sentryx — despliegue y operación

Guía para poner Sentryx en un servidor sin abrir huecos y para mantenerlo. Qué protege cada
pieza está en el código, junto a la protección; aquí solo lo que tienes que hacer tú.

## 1. Antes del primer despliegue

1. **Secretos nuevos.** Nunca copies `.env.example` a mano ni reutilices el `.env` de desarrollo:

   ```bash
   python scripts/dev/generate_env.py --production --domain sentryx.miempresa.co
   ```

   Genera `DJANGO_SECRET_KEY`, contraseñas de PostgreSQL y Redis, `ML_ENGINE_API_KEY`,
   `PSEUDONYMIZATION_SALT`, `MFA_ENCRYPTION_KEY`, `PAYMENT_SHIELD_SECRET` y una ruta aleatoria para
   `/admin/`. El backend se niega a arrancar en producción si falta alguno o si conserva un valor
   publicado en el repositorio (`config/settings/production.py`).
2. **Correo.** Pon `SENDGRID_API_KEY`: sin él no llegan los enlaces de verificación ni de recuperación.
3. **Certificado TLS.** Copia `fullchain.pem` y `privkey.pem` (Let's Encrypt) a `infra/nginx/certs/`.
   Esa carpeta no se versiona.
4. **Dominio.** Cambia `server_name` en `infra/nginx/nginx.prod.conf`. Si cambiaste
   `DJANGO_ADMIN_URL`, cambia también `location /admin/` en ese archivo (o restringe esa ruta a la IP
   de tu oficina con `allow`/`deny`).
5. **Levantar:**

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
   docker compose exec backend python manage.py check --deploy
   ```

6. **Cuenta de administrador.** Crea el superusuario con `createsuperuser`, entra al panel web y
   activa la verificación en dos pasos. En producción `MFA_REQUIRED_FOR_ADMINS=True`: un admin sin
   2FA solo puede configurarlo, y el login de `/admin/` también pide el código.

## 2. Qué queda expuesto

| Servicio | Desarrollo | Producción |
|---|---|---|
| nginx | `:80` | `:80` (solo redirige) y `:443` |
| Backend, motor ML, PostgreSQL, Redis | solo `127.0.0.1` | no se publican |
| Hub de la Red de alerta | `127.0.0.1:8100` | publícalo solo detrás de HTTPS |

El motor ML ya no se publica por `/ml/`: solo lo llama el backend, con `X-API-Key`.

## 3. Sesiones

- El panel web guarda el access token (15 min) **solo en memoria**. El refresh token va en la cookie
  `sentryx_refresh`: HttpOnly, `SameSite=Strict`, `Secure` con HTTPS, limitada a `/api/v1/auth/`.
- La cookie solo se acepta con la cabecera `X-Sentryx-Client: web`, que otro sitio no puede añadir
  sin pasar el preflight de CORS (defensa CSRF).
- Cada refresh rota el token y revoca el anterior. Cerrar sesión o restablecer la contraseña revoca
  todos los refresh de la cuenta.
- La extensión del navegador no envía esa cabecera y recibe el par en el cuerpo, como antes.

## 4. Vigilar actividad sospechosa

- El logger `sentryx.security` escribe en la salida del contenedor los logins fallidos, bloqueos de
  cuenta, tokens rechazados, respuestas 401/403/429 y fallos de 2FA en `/admin/`. Envía esa salida a
  tu sistema de logs y crea una alerta para `event=account_locked` y para muchos `login_failed`
  desde la misma IP.
- El log de auditoría (`/api/v1/audit/`, solo admins de la empresa) guarda logins, fallos, cierres
  de sesión, recuperaciones de contraseña y cambios de configuración. Las IP y los correos
  intentados van seudonimizados.
- django-axes bloquea una cuenta o IP tras `AXES_FAILURE_LIMIT` fallos durante `AXES_COOLOFF_TIME`
  horas. Para desbloquear: `docker compose exec backend python manage.py axes_reset_username <correo>`.

## 5. Rotar una clave comprometida

| Clave | Cómo rotarla | Efecto |
|---|---|---|
| `DJANGO_SECRET_KEY` | Valor nuevo y reiniciar | Cierra todas las sesiones (JWT y `/admin/`) |
| `POSTGRES_PASSWORD` | `ALTER USER sentryx WITH PASSWORD '...'` en la BD, luego `.env` y reiniciar | Ninguno |
| `REDIS_PASSWORD` | Cambiarla junto con `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` y reiniciar | Se pierden tareas en cola y caché |
| `ML_ENGINE_API_KEY` | Valor nuevo y reiniciar backend y motor | Ninguno |
| `PSEUDONYMIZATION_SALT` | Valor nuevo y reiniciar | Los hashes nuevos no coinciden con los antiguos (correlación histórica) |
| `MFA_ENCRYPTION_KEY` | Solo si se filtró: cada usuario debe reactivar el 2FA | Los secretos TOTP guardados dejan de descifrarse |
| `PAYMENT_SHIELD_SECRET` | Solo si se filtró: volver a registrar las cuentas de los proveedores | Las cuentas guardadas dejan de compararse |
| `SENDGRID_API_KEY` | Revocarla en SendGrid y crear otra | Ninguno |

Si un secreto llegó a Git, rotarlo es obligatorio: borrarlo del historial no basta, porque ya
pudo copiarse.

## 6. Mantenimiento

- Dependencias: `pip-audit -r backend/requirements.txt` (y `ml_engine`, `community_hub`) y
  `npm audit` en `frontend/` antes de cada despliegue.
- Django 5.2 LTS tiene parches hasta abril de 2028.
- Pruebas de seguridad: `backend/tests/test_security.py` y `ml_engine/tests/test_api_security.py`.
