/**
 * Sentryx Extension — Popup Script
 *
 * Controla la interfaz del popup:
 *  1. Al abrir, pide al content script que extraiga el correo
 *  2. Muestra la preview del correo detectado
 *  3. Al hacer clic en "Analizar", envía a background.js
 *  4. Muestra el resultado con score, capas y tipo
 */

// ── Constantes ────────────────────────────────────────────
const BACKEND_URL_DEFAULT = 'http://localhost/api/v1';

const MAIL_HOSTS = [
  'mail.google.com',
  'outlook.live.com',
  'outlook.office.com',
  'outlook.office365.com',
];

const TYPE_LABELS = {
  bec:       'BEC',
  whaling:   'Whaling',
  spear:     'Spear',
  clone:     'Clone',
  vishing:   'Vishing',
  smishing:  'Smishing',
  generic:   'Genérico',
  unknown:   'Desconocido',
  legitimate:'Legítimo',
};

const CLASSIFICATION_LABELS = {
  legitimate: 'Correo legítimo',
  suspicious: 'Correo sospechoso',
  phishing:   'Phishing detectado',
  critical:   'Phishing crítico',
};

const STEP_NAMES = { headers: 'Encabezados', content: 'Contenido', urls: 'URLs' };

// ── Elementos del DOM ─────────────────────────────────────
const $ = id => document.getElementById(id);

let states           = {};
let currentEmailData = null;
let frontendUrl      = 'http://localhost';

// ── Mensajería con background.js ──────────────────────────
function sendToBackground(message) {
  return new Promise(resolve => {
    chrome.runtime.sendMessage(message, response => {
      if (chrome.runtime.lastError) {
        resolve({ success: false, error: chrome.runtime.lastError.message });
      } else {
        resolve(response);
      }
    });
  });
}

// ── Utilidades de UI ──────────────────────────────────────
function showView(viewId) {
  $('view-main').classList.toggle('hidden', viewId !== 'main');
  $('view-settings').classList.toggle('hidden', viewId !== 'settings');
}

function showState(stateName) {
  Object.entries(states).forEach(([key, el]) => {
    el.classList.toggle('hidden', key !== stateName);
  });
}

function scoreColor(score) {
  if (score >= 85) return 'critical';
  if (score >= 70) return 'phishing';
  if (score >= 40) return 'suspicious';
  return 'legitimate';
}

// Color de relleno según el score (tokens definidos en styles.css)
function barColor(score) {
  if (score >= 85) return 'var(--red-solid)';
  if (score >= 70) return 'var(--orange-solid)';
  if (score >= 40) return 'var(--yellow-solid)';
  return 'var(--green-solid)';
}

function animateBar(barEl, valueEl, score) {
  const pct = Math.min(Math.max(Number(score) || 0, 0), 100);
  barEl.style.width = '0%';
  setTimeout(() => {
    barEl.style.width           = `${pct}%`;
    barEl.style.backgroundColor = barColor(pct);
  }, 50);
  valueEl.textContent = Math.round(pct);
}

// Anillo del score: la circunferencia (2·π·42) coincide con styles.css
const RING_LENGTH = 263.89;
function animateRing(score) {
  const ring = $('result-ring');
  const pct  = Math.min(Math.max(score, 0), 100);
  ring.style.strokeDashoffset = RING_LENGTH;
  setTimeout(() => { ring.style.strokeDashoffset = RING_LENGTH * (1 - pct / 100); }, 50);
}

// Los indicadores (pendiente / en curso / hecho) los dibuja el CSS según la clase
function resetLoadingSteps() {
  Object.keys(STEP_NAMES).forEach(key => $(`step-${key}`).classList.remove('active', 'done'));
}

function setLoadingStep(step) {
  const order = Object.keys(STEP_NAMES);
  order.forEach((key, i) => {
    const el = $(`step-${key}`);
    if (key === step) {
      el.classList.add('active');
    } else if (i < order.indexOf(step)) {
      el.classList.remove('active');
      el.classList.add('done');
    }
  });
}

// ── Extraer correo del content script ────────────────────
function getActiveTab() {
  return new Promise(resolve => {
    chrome.tabs.query({ active: true, currentWindow: true }, tabs => resolve(tabs[0] || null));
  });
}

function requestExtraction(tabId) {
  return new Promise(resolve => {
    chrome.tabs.sendMessage(tabId, { type: 'EXTRACT_EMAIL' }, response => {
      if (chrome.runtime.lastError) {
        resolve({ reachable: false });
      } else {
        resolve({ reachable: true, response });
      }
    });
  });
}

function isMailTab(tab) {
  try {
    return MAIL_HOSTS.includes(new URL(tab.url).hostname);
  } catch {
    return false;
  }
}

/**
 * Devuelve { status, data } con status:
 *  'ok' | 'no-email' | 'unsupported'
 */
async function extractEmailFromTab() {
  const tab = await getActiveTab();
  if (!tab || !isMailTab(tab)) return { status: 'unsupported' };

  let result = await requestExtraction(tab.id);

  // La pestaña se abrió antes de instalar/recargar la extensión:
  // el content script no está cargado, así que lo inyectamos.
  if (!result.reachable) {
    try {
      await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        files:  ['content.js'],
      });
      result = await requestExtraction(tab.id);
    } catch (err) {
      console.error('[Sentryx] No se pudo inyectar el content script:', err);
      return { status: 'no-email' };
    }
  }

  const response = result.response;
  if (!result.reachable || !response?.success || !response.data) {
    return { status: 'no-email' };
  }
  return { status: 'ok', data: response.data };
}

// ── Mostrar resultado de análisis ─────────────────────────
function showResult(result) {
  const score  = Math.round(Number(result.risk_score) || 0);
  const level  = scoreColor(score);
  const cls    = result.classification || level;
  const type   = cls === 'legitimate' ? 'legitimate' : (result.phishing_type || 'unknown');
  const scores = result.scores_by_layer || {};

  if (result.frontend_url) frontendUrl = result.frontend_url;

  // Nivel de riesgo: define los colores del resultado en el CSS
  $('state-result').dataset.level = level;

  // Score principal
  $('result-score').textContent = score;
  animateRing(score);

  // Clasificación
  $('result-classification').textContent = CLASSIFICATION_LABELS[cls] || cls;

  // Badge de tipo (en un correo legítimo el título ya lo dice: se omite)
  $('result-type-badge').textContent = cls === 'legitimate' ? '' : (TYPE_LABELS[type] || type);
  $('result-type-badge').className   = `badge type-${type}`;

  // Barras por capa
  animateBar($('bar-headers'), $('val-headers'), scores.headers);
  animateBar($('bar-content'), $('val-content'), scores.content);
  animateBar($('bar-urls'),    $('val-urls'),    scores.urls);

  // MITRE: solo tiene sentido si hay un ataque
  $('result-mitre').textContent = cls === 'legitimate' ? '' : (result.mitre_technique || 'T1566');

  // Estado de alerta
  const alertStatus = $('result-alert-status');
  const btnAlert    = $('btn-view-alert');
  if (result.alert_created && result.alert_id) {
    alertStatus.textContent = 'Alerta guardada en Sentryx';
    alertStatus.className   = 'alert-status created';
    btnAlert.classList.remove('hidden');
    btnAlert.dataset.alertId = result.alert_id;
  } else {
    alertStatus.textContent = cls === 'legitimate' ? 'Correo legítimo: no se creó ninguna alerta' : '';
    alertStatus.className   = 'alert-status';
    btnAlert.classList.add('hidden');
    delete btnAlert.dataset.alertId;
  }

  showState('result');
}

// ── Flujo principal: analizar ─────────────────────────────
async function analyzeCurrentEmail() {
  if (!currentEmailData) {
    init();
    return;
  }

  resetLoadingSteps();
  showState('loading');

  // Progreso visual de las tres capas mientras responde el backend
  const timers = [
    setTimeout(() => setLoadingStep('headers'), 300),
    setTimeout(() => setLoadingStep('content'), 800),
    setTimeout(() => setLoadingStep('urls'),    1300),
  ];

  const response = await sendToBackground({ type: 'ANALYZE_EMAIL', emailData: currentEmailData });
  timers.forEach(clearTimeout);

  if (response?.success) {
    showResult(response.data);
  } else {
    showError(response?.error || 'Error desconocido al analizar el correo.');
  }
}

function showError(message) {
  $('error-message').textContent = message;
  showState('error');
}

// ── Settings ──────────────────────────────────────────────
let mfaRecoveryMode = false;

function setMfaStep(active, email) {
  $('mfa-group').classList.toggle('hidden', !active);
  // Mientras se pide el código, correo y contraseña ya no se pueden editar
  $('input-email').disabled    = active;
  $('input-password').disabled = active;
  $('input-backend-url').disabled = active;
  if (email) $('input-email').value = email;
  $('btn-save-settings').textContent = active ? 'Verificar' : 'Guardar y conectar';
  setMfaMode(false);
  if (active) $('input-mfa-code').focus();
}

function setMfaMode(recovery) {
  mfaRecoveryMode = recovery;
  const input = $('input-mfa-code');
  input.value = '';
  $('mfa-label').textContent = recovery ? 'Código de recuperación' : 'Código de verificación';
  $('mfa-hint').textContent  = recovery
    ? 'Escribe uno de los códigos de recuperación que guardaste. Cada uno sirve una sola vez.'
    : 'Escribe el código de 6 dígitos de Google Authenticator o Microsoft Authenticator.';
  $('btn-mfa-mode').textContent = recovery ? 'Usar la app de autenticación' : 'Usar código de recuperación';
  if (recovery) {
    input.removeAttribute('pattern');
    input.setAttribute('inputmode', 'text');
    input.setAttribute('autocomplete', 'off');
    input.maxLength = 20;
  } else {
    input.setAttribute('pattern', '\\d{6}');
    input.setAttribute('inputmode', 'numeric');
    input.setAttribute('autocomplete', 'one-time-code');
    input.maxLength = 6;
  }
}

async function openSettings() {
  showView('settings');
  $('settings-status').classList.add('hidden');
  $('connection-info').classList.add('hidden');

  const data = await chrome.storage.local.get(['backendUrl', 'email', 'username', 'accessToken', 'refreshToken']);
  $('input-backend-url').value = data.backendUrl || BACKEND_URL_DEFAULT;
  $('input-email').value       = data.email || data.username || '';
  $('input-password').value    = '';
  $('btn-logout').classList.toggle('hidden', !(data.accessToken || data.refreshToken));

  // Retomar un segundo paso pendiente (el popup se cierra al cambiar de ventana)
  const pending = await sendToBackground({ type: 'GET_PENDING_MFA' });
  if (pending?.pending) {
    $('input-backend-url').value = pending.backendUrl;
    setMfaStep(true, pending.email);
  } else {
    setMfaStep(false);
  }
}

// Origen al que hay que pedir permiso (localhost ya viene en host_permissions)
function originPattern(url) {
  try {
    const u = new URL(url);
    if (['localhost', '127.0.0.1'].includes(u.hostname)) return null;
    return `${u.protocol}//${u.hostname}/*`;
  } catch {
    return null;
  }
}

let saving = false;

async function saveSettings() {
  if (saving) return;
  if (!$('mfa-group').classList.contains('hidden')) return verifyMfaCode();

  const backendUrl = $('input-backend-url').value.trim() || BACKEND_URL_DEFAULT;
  const email      = $('input-email').value.trim();
  const password   = $('input-password').value;

  if (!/^https?:\/\//i.test(backendUrl)) {
    showSettingsStatus('La URL debe empezar por http:// o https://', 'error');
    return;
  }

  // Pedir el permiso del servidor antes de cualquier await: Chrome solo lo
  // permite dentro del gesto del usuario (el clic en «Guardar y conectar»).
  const origin = originPattern(backendUrl);
  if (origin) {
    const granted = await chrome.permissions.request({ origins: [origin] });
    if (!granted) {
      showSettingsStatus(`Sin permiso para conectarse a ${new URL(backendUrl).host}.`, 'error');
      return;
    }
  }

  if (!email || !password) {
    showSettingsStatus('Ingresa correo y contraseña.', 'error');
    return;
  }

  const btn = $('btn-save-settings');
  saving          = true;
  btn.textContent = 'Conectando...';
  btn.disabled    = true;

  const response = await sendToBackground({
    type: 'SAVE_CONFIG',
    config: { backendUrl, email, password },
  });

  saving       = false;
  btn.disabled = false;
  $('input-password').value = '';

  if (response?.success && response.mfaRequired) {
    $('settings-status').classList.add('hidden');
    setMfaStep(true);
  } else if (response?.success) {
    btn.textContent = 'Guardar y conectar';
    connected(backendUrl);
  } else {
    btn.textContent = 'Guardar y conectar';
    showSettingsStatus(response?.error || 'Error al conectar.', 'error');
    showConnectionInfo(false, backendUrl);
  }
}

async function verifyMfaCode() {
  const raw  = $('input-mfa-code').value.replace(/\s+/g, '');
  const code = mfaRecoveryMode ? raw : raw.replace(/\D/g, '');
  if (mfaRecoveryMode ? !code : code.length !== 6) {
    showSettingsStatus(mfaRecoveryMode ? 'Escribe un código de recuperación.' : 'El código tiene 6 dígitos.', 'error');
    return;
  }

  const btn = $('btn-save-settings');
  saving          = true;
  btn.textContent = 'Verificando...';
  btn.disabled    = true;

  const response = await sendToBackground({
    type: 'VERIFY_MFA',
    payload: mfaRecoveryMode ? { recovery_code: code } : { code },
  });

  saving       = false;
  btn.disabled = false;

  if (response?.success) {
    setMfaStep(false);
    connected(response.backendUrl);
  } else {
    if (response?.restart) setMfaStep(false);
    else btn.textContent = 'Verificar';
    $('input-mfa-code').value = '';
    showSettingsStatus(response?.error || 'No se pudo verificar el código.', 'error');
  }
}

function connected(backendUrl) {
  showSettingsStatus('Conexión exitosa. Sesión iniciada.', 'ok');
  showConnectionInfo(true, backendUrl);
  $('btn-logout').classList.remove('hidden');
  setTimeout(init, 1200);
}

async function cancelMfa() {
  await sendToBackground({ type: 'CANCEL_MFA' });
  setMfaStep(false);
  $('settings-status').classList.add('hidden');
  $('input-password').focus();
}

async function logout() {
  await sendToBackground({ type: 'LOGOUT' });
  $('input-password').value = '';
  $('btn-logout').classList.add('hidden');
  setMfaStep(false);
  showSettingsStatus('Sesión cerrada.', 'ok');
  $('connection-info').classList.add('hidden');
}

function showSettingsStatus(message, type) {
  const el = $('settings-status');
  el.textContent = message;
  el.className   = `settings-status ${type}`;
}

function showConnectionInfo(connected, url) {
  $('connection-dot').className = `dot ${connected ? 'green' : 'red'}`;
  $('connection-text').textContent = connected ? `Conectado a ${url}` : `Sin conexión a ${url}`;
  $('connection-info').classList.remove('hidden');
}

// ── Inicialización ────────────────────────────────────────
async function init() {
  showView('main');
  currentEmailData = null;

  // Verificar configuración
  const configStatus = await sendToBackground({ type: 'CHECK_CONFIG' });
  if (configStatus?.frontendUrl) frontendUrl = configStatus.frontendUrl;

  if (!configStatus?.configured) {
    // Sin configuración → ir directamente a settings
    openSettings();
    return;
  }

  // Intentar extraer correo de la pestaña activa
  const { status, data } = await extractEmailFromTab();

  if (status !== 'ok') {
    $('no-email-desc').innerHTML = status === 'unsupported'
      ? 'Esta pestaña no es Gmail ni Outlook.<br>Abre un correo allí y vuelve a hacer clic.'
      : 'Abre un correo en Gmail u Outlook<br>y vuelve a hacer clic aquí.';
    showState('noEmail');
    return;
  }

  currentEmailData = data;

  // Mostrar preview
  $('preview-from').textContent    = data.from    || '(no detectado)';
  $('preview-subject').textContent = data.subject || '(sin asunto)';
  $('preview-service').textContent = data.service || 'Correo';
  showState('ready');
}

// ── Event listeners ───────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  states = {
    noEmail: $('state-no-email'),
    ready:   $('state-ready'),
    loading: $('state-loading'),
    result:  $('state-result'),
    error:   $('state-error'),
  };

  // Navegación
  $('btn-settings').addEventListener('click', openSettings);
  $('btn-back').addEventListener('click', init);
  $('btn-logout').addEventListener('click', logout);

  // Analizar
  $('btn-analyze').addEventListener('click', analyzeCurrentEmail);

  // Reintentar / Analizar de nuevo (vuelve a leer el correo abierto)
  $('btn-retry').addEventListener('click', analyzeCurrentEmail);
  $('btn-analyze-again').addEventListener('click', init);

  // Ver alerta en el dashboard de Sentryx
  $('btn-view-alert').addEventListener('click', () => {
    const alertId = $('btn-view-alert').dataset.alertId;
    if (alertId) {
      chrome.tabs.create({ url: `${frontendUrl}/alerts/${alertId}` });
    }
  });

  // Guardar configuración
  $('btn-save-settings').addEventListener('click', saveSettings);

  // Verificación en dos pasos
  $('btn-mfa-mode').addEventListener('click', () => setMfaMode(!mfaRecoveryMode));
  $('btn-mfa-cancel').addEventListener('click', cancelMfa);

  // Enter en los campos de settings
  [$('input-backend-url'), $('input-email'), $('input-password'), $('input-mfa-code')].forEach(input => {
    input.addEventListener('keydown', e => {
      if (e.key === 'Enter') saveSettings();
    });
  });

  // Iniciar
  init();
});
