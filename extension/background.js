/**
 * Sentryx Extension — Background Service Worker
 *
 * Responsabilidades:
 *  1. Gestionar el token JWT (obtenerlo, renovarlo, guardarlo)
 *  2. Hacer las llamadas al backend de Sentryx
 *  3. Responder a los mensajes del popup
 *
 * Notas sobre el backend (sentryx_v2):
 *  - El modelo de usuario usa USERNAME_FIELD = "email", por lo que
 *    POST /auth/token/ espera { email, password } (no "username").
 *  - Los errores de la API pueden venir como { detail }, { error } o
 *    como errores de validación de DRF { campo: [mensajes] }.
 *  - ROTATE_REFRESH_TOKENS = True: cada refresh devuelve un refresh nuevo.
 *  - Si la cuenta tiene verificación en dos pasos, /auth/token/ devuelve
 *    { mfa_required, mfa_token } y el JWT se obtiene en /auth/mfa/verify/.
 *
 * La contraseña NO se guarda: solo el par JWT. Cuando el refresh token
 * caduca, el usuario vuelve a iniciar sesión desde la configuración.
 * No volver a guardar la contraseña para re-autenticar en silencio: con 2FA
 * eso no funciona y deja la contraseña en claro en chrome.storage.
 */

const DEFAULT_BACKEND  = 'http://localhost/api/v1';
const REQUEST_TIMEOUT  = 20000; // ms — el backend espera hasta 10 s al motor ML

// ── Helpers de storage ────────────────────────────────────
async function getConfig() {
  const data = await chrome.storage.local.get(
    ['backendUrl', 'email', 'username', 'accessToken', 'refreshToken']
  );
  // Compatibilidad con versiones anteriores que guardaban "username"
  if (!data.email && data.username) data.email = data.username;
  data.backendUrl = normalizeBackendUrl(data.backendUrl || DEFAULT_BACKEND);
  return data;
}

async function saveTokens(access, refresh) {
  const values = { accessToken: access };
  if (refresh) values.refreshToken = refresh;
  await chrome.storage.local.set(values);
}

async function clearTokens() {
  await chrome.storage.local.remove(['accessToken', 'refreshToken']);
}

function normalizeBackendUrl(url) {
  return (url || DEFAULT_BACKEND).trim().replace(/\/+$/, '');
}

// URL del frontend (dashboard) a partir de la URL de la API:
// http://localhost/api/v1 → http://localhost
function frontendUrlFrom(backendUrl) {
  return normalizeBackendUrl(backendUrl).replace(/\/api\/v\d+$/, '');
}

// ── Helpers HTTP ──────────────────────────────────────────
async function fetchWithTimeout(url, options = {}, timeout = REQUEST_TIMEOUT) {
  try {
    return await fetch(url, { ...options, signal: AbortSignal.timeout(timeout) });
  } catch (err) {
    if (err.name === 'TimeoutError' || err.name === 'AbortError') {
      throw new Error(`El backend no respondió a tiempo (${url}).`);
    }
    // TypeError: Failed to fetch → servidor caído o URL incorrecta
    throw new Error(`No se pudo conectar con Sentryx en ${url}. ¿Está corriendo el backend?`);
  }
}

// Extrae un mensaje legible de cualquier formato de error de la API
async function extractError(res, fallback) {
  const body = await res.json().catch(() => null);
  if (!body || typeof body !== 'object') return `${fallback} (${res.status})`;
  if (typeof body.error  === 'string') return body.error;
  if (typeof body.detail === 'string') return body.detail;

  // Errores de validación DRF: { campo: ["msg"] } o { non_field_errors: ["msg"] }
  const messages = [];
  for (const [field, value] of Object.entries(body)) {
    const text = Array.isArray(value) ? value.join(' ') : String(value);
    messages.push(field === 'non_field_errors' ? text : `${field}: ${text}`);
  }
  return messages.length ? messages.join(' | ') : `${fallback} (${res.status})`;
}

// Las versiones 1.x guardaban la contraseña: borrarla al actualizar
chrome.runtime.onInstalled.addListener(async () => {
  await chrome.storage.local.remove('password');
});

// ── Autenticación ─────────────────────────────────────────
// Devuelve { mfaRequired: true, mfaToken } o { mfaRequired: false } (tokens guardados)
async function login(backendUrl, email, password) {
  const res = await fetchWithTimeout(`${backendUrl}/auth/token/`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ email, password }),
  });

  if (!res.ok) {
    if (res.status === 401) {
      throw new Error('Correo o contraseña incorrectos.');
    }
    if (res.status === 429) {
      throw new Error('Demasiados intentos fallidos. Espera un momento e inténtalo de nuevo.');
    }
    throw new Error(await extractError(res, 'Error de autenticación'));
  }

  const data = await res.json();
  if (data.mfa_required) {
    return { mfaRequired: true, mfaToken: data.mfa_token, expiresIn: data.expires_in };
  }
  await saveTokens(data.access, data.refresh);
  return { mfaRequired: false };
}

// Segundo paso del login: payload = { code } o { recovery_code }
async function verifyMfa(backendUrl, mfaToken, payload) {
  const res = await fetchWithTimeout(`${backendUrl}/auth/mfa/verify/`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ mfa_token: mfaToken, ...payload }),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const err  = new Error(body.error || `Error de verificación (${res.status})`);
    // Estos códigos invalidan el mfa_token: hay que volver a escribir la contraseña
    err.restart = ['mfa_token_expired', 'mfa_token_invalid', 'mfa_token_used',
                   'mfa_too_many_attempts'].includes(body.code);
    if (body.code === 'mfa_invalid_code' && body.attempts_left != null) {
      err.message = `El código no es válido. Te quedan ${body.attempts_left} intentos.`;
    }
    throw err;
  }

  const data = await res.json();
  await saveTokens(data.access, data.refresh);
}

async function refreshAccessToken(backendUrl, refreshToken) {
  const res = await fetchWithTimeout(`${backendUrl}/auth/token/refresh/`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ refresh: refreshToken }),
  });

  if (!res.ok) {
    await clearTokens();
    return null;
  }

  const data = await res.json();
  // Con ROTATE_REFRESH_TOKENS el backend entrega un refresh nuevo
  await saveTokens(data.access, data.refresh || refreshToken);
  return data.access;
}

const SESSION_EXPIRED = 'Tu sesión expiró. Abre la configuración y vuelve a iniciar sesión.';

// Obtiene un access token nuevo con el refresh token
async function renewToken(config) {
  if (config.refreshToken) {
    const token = await refreshAccessToken(config.backendUrl, config.refreshToken);
    if (token) return token;
  }
  throw new Error(SESSION_EXPIRED);
}

async function getValidToken(config) {
  if (config.accessToken) return config.accessToken;
  if (config.refreshToken) return renewToken(config);
  throw new Error('No has iniciado sesión. Abre la configuración de la extensión.');
}

// ── Llamada al endpoint de análisis ──────────────────────
function buildPayload(emailData) {
  const bodyText = (emailData.body_text || '').trim();
  const bodyHtml = (emailData.body_html || '').trim();

  if (!bodyText && !bodyHtml) {
    throw new Error('No se pudo leer el cuerpo del correo. Ábrelo completamente e inténtalo de nuevo.');
  }

  // Coincide con EmailAnalysisRequestSerializer / EmailHeadersInputSerializer
  return {
    headers: {
      from_addr:              emailData.from         || '',
      subject:                emailData.subject      || '',
      reply_to:               emailData.reply_to     || '',
      authentication_results: emailData.auth_results || '',
    },
    body_text: bodyText || bodyHtml,
    body_html: bodyHtml || bodyText,
  };
}

async function postAnalyze(backendUrl, token, payload) {
  return fetchWithTimeout(`${backendUrl}/alerts/analyze/`, {
    method:  'POST',
    headers: {
      'Content-Type':  'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });
}

async function analyzeEmail(emailData) {
  const config  = await getConfig();
  const payload = buildPayload(emailData);
  let token     = await getValidToken(config);
  let res       = await postAnalyze(config.backendUrl, token, payload);

  // Token expirado — renovar una sola vez y reintentar
  if (res.status === 401) {
    await chrome.storage.local.remove('accessToken');
    token = await renewToken(await getConfig());
    res   = await postAnalyze(config.backendUrl, token, payload);
  }

  if (res.status === 401) {
    await clearTokens();
    throw new Error(SESSION_EXPIRED);
  }
  if (res.status === 403) {
    const body = await res.clone().json().catch(() => ({}));
    if (body.code === 'mfa_setup_required') {
      throw new Error('Tu cuenta de administrador debe activar la verificación en dos pasos. '
                    + 'Hazlo en Sentryx → Seguridad de la cuenta y vuelve a iniciar sesión aquí.');
    }
    throw new Error('Tu usuario no tiene permiso para analizar correos (se requiere rol analista o administrador).');
  }
  if (res.status === 429) {
    throw new Error('Has superado el límite de análisis por hora. Inténtalo más tarde.');
  }
  if (res.status === 503) {
    throw new Error('El motor ML no está disponible. Verifica que el servicio ml_engine de Sentryx esté corriendo.');
  }
  if (!res.ok) {
    throw new Error(await extractError(res, 'Error del servidor'));
  }

  const result = await res.json();
  result.frontend_url = frontendUrlFrom(config.backendUrl);
  return result;
}

// ── Test de conexión ──────────────────────────────────────
async function testConnection(backendUrl, email, password) {
  // 1. Verificar que el backend responde
  const healthRes = await fetchWithTimeout(`${backendUrl}/health/`, {}, 5000);
  if (!healthRes.ok) {
    throw new Error(`El backend respondió con error (${healthRes.status}). Revisa la URL: debe terminar en /api/v1`);
  }

  // 2. Verificar credenciales (guarda los tokens si no hace falta 2FA)
  await clearTokens();
  return login(backendUrl, email, password);
}

// ══════════════════════════════════════════════════════════
// ROUTER DE MENSAJES
// ══════════════════════════════════════════════════════════
const handlers = {
  // ── Analizar correo ────────────────────────────────────
  async ANALYZE_EMAIL(message) {
    const result = await analyzeEmail(message.emailData);
    return { success: true, data: result };
  },

  // ── Guardar configuración y verificar conexión ─────────
  async SAVE_CONFIG(message) {
    const backendUrl = normalizeBackendUrl(message.config.backendUrl);
    const email      = (message.config.email || '').trim().toLowerCase();
    const password   = message.config.password || '';

    const result = await testConnection(backendUrl, email, password);
    if (result.mfaRequired) {
      // Guardar el desafío en storage.session: el popup se cierra si el
      // usuario cambia de ventana para mirar la app de autenticación.
      await chrome.storage.session.set({
        pendingMfa: { backendUrl, email, mfaToken: result.mfaToken,
                      expiresAt: Date.now() + (result.expiresIn || 300) * 1000 },
      });
      return { success: true, mfaRequired: true };
    }
    await chrome.storage.local.set({ backendUrl, email });
    await chrome.storage.local.remove(['username', 'password']);
    return { success: true };
  },

  // ── Segundo paso del login (código TOTP o de recuperación) ──
  async VERIFY_MFA(message) {
    const { pendingMfa } = await chrome.storage.session.get('pendingMfa');
    if (!pendingMfa || pendingMfa.expiresAt < Date.now()) {
      await chrome.storage.session.remove('pendingMfa');
      return { success: false, restart: true,
               error: 'La verificación expiró. Vuelve a escribir tu contraseña.' };
    }
    try {
      await verifyMfa(pendingMfa.backendUrl, pendingMfa.mfaToken, message.payload);
    } catch (err) {
      if (err.restart) await chrome.storage.session.remove('pendingMfa');
      return { success: false, restart: !!err.restart, error: err.message };
    }
    await chrome.storage.session.remove('pendingMfa');
    await chrome.storage.local.set({ backendUrl: pendingMfa.backendUrl, email: pendingMfa.email });
    await chrome.storage.local.remove(['username', 'password']);
    return { success: true, backendUrl: pendingMfa.backendUrl };
  },

  async GET_PENDING_MFA() {
    const { pendingMfa } = await chrome.storage.session.get('pendingMfa');
    const active = !!pendingMfa && pendingMfa.expiresAt > Date.now();
    return { pending: active, email: active ? pendingMfa.email : null,
             backendUrl: active ? pendingMfa.backendUrl : null };
  },

  async CANCEL_MFA() {
    await chrome.storage.session.remove('pendingMfa');
    return { success: true };
  },

  // ── Verificar estado de configuración ─────────────────
  async CHECK_CONFIG() {
    const config = await getConfig();
    return {
      configured:  !!(config.email && (config.accessToken || config.refreshToken)),
      hasToken:    !!config.accessToken,
      backendUrl:  config.backendUrl,
      frontendUrl: frontendUrlFrom(config.backendUrl),
    };
  },

  // ── Cerrar sesión / borrar credenciales ───────────────
  async LOGOUT() {
    await chrome.storage.local.remove(['email', 'username', 'password', 'accessToken', 'refreshToken']);
    await chrome.storage.session.remove('pendingMfa');
    return { success: true };
  },
};

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const handler = handlers[message?.type];
  if (!handler) return false;

  handler(message)
    .then(sendResponse)
    .catch(err => sendResponse({ success: false, error: err.message || String(err) }));
  return true; // mantener canal abierto para respuesta asíncrona
});
