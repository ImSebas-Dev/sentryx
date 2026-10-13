/**
 * Sentryx Extension — Content Script
 *
 * Se inyecta en Gmail y Outlook. Su única responsabilidad es
 * extraer los datos del correo actualmente abierto y responder
 * al mensaje "EXTRACT_EMAIL" que envía el popup.
 *
 * NO hace llamadas al backend — eso lo hace background.js.
 *
 * El popup puede volver a inyectar este archivo (chrome.scripting)
 * en pestañas abiertas antes de instalar la extensión, por lo que
 * se protege contra registrarse dos veces.
 */

if (!window.__sentryxContentLoaded) {
  window.__sentryxContentLoaded = true;

  const MAX_HTML = 50000;
  const MAX_TEXT = 20000;

  // ── Utilidades ──────────────────────────────────────────
  const text = el => (el ? (el.innerText || el.textContent || '').trim() : '');

  // Un elemento cuenta como visible si ocupa espacio en pantalla
  const isVisible = el => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));

  function lastVisible(selector, root = document) {
    const all = [...root.querySelectorAll(selector)].filter(isVisible);
    return all.length ? all[all.length - 1] : null;
  }

  function firstMatch(selectors, root = document) {
    for (const sel of selectors) {
      const el = lastVisible(sel, root);
      if (el) return el;
    }
    return null;
  }

  const EMAIL_RE = /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i;

  // ── Detectar servicio de correo ─────────────────────────
  function detectService() {
    const host = window.location.hostname;
    if (host === 'mail.google.com')           return 'Gmail';
    if (host.includes('outlook.live.com'))    return 'Outlook';
    if (host.includes('outlook.office.com'))  return 'Outlook 365';
    if (host.includes('outlook.office365.com')) return 'Outlook 365';
    return 'Desconocido';
  }

  // ════════════════════════════════════════════════════════
  // EXTRACTORES DE GMAIL
  // ════════════════════════════════════════════════════════
  function extractFromGmail() {
    // Cada mensaje expandido de la conversación es un ".adn.ads".
    // Tomamos el último visible (el más reciente).
    const message = lastVisible('.adn.ads');
    const bodyEl  = message
      ? message.querySelector('.a3s.aiL, .a3s')
      : lastVisible('.a3s.aiL, .a3s');

    if (!message && !bodyEl) return null;
    const scope = message || document;

    // ── Remitente ──────────────────────────────────────────
    // .gD lleva los atributos "email" y "name" del remitente
    let from = '';
    const senderEl = scope.querySelector('.gD[email]') || scope.querySelector('.gD');
    if (senderEl) {
      const email = senderEl.getAttribute('email') || '';
      const name  = senderEl.getAttribute('name')  || text(senderEl);
      from = email ? (name && name !== email ? `${name} <${email}>` : email) : name;
    }

    // ── Asunto ─────────────────────────────────────────────
    const subject = text(lastVisible('h2.hP'));

    // ── Cuerpo ─────────────────────────────────────────────
    const bodyHtml = bodyEl ? bodyEl.innerHTML : '';
    const bodyText = text(bodyEl);

    if (!from && !subject && !bodyText) return null;

    return {
      from,
      subject,
      reply_to:     '',
      body_html:    bodyHtml.substring(0, MAX_HTML),
      body_text:    bodyText.substring(0, MAX_TEXT),
      auth_results: extractGmailAuthResults(scope),
      service:      'Gmail',
    };
  }

  function extractGmailAuthResults(scope) {
    // Gmail no expone los encabezados en el DOM. Si el usuario abrió el
    // desplegable de detalles del remitente, aparecen "enviado por"
    // (mailed-by → SPF válido) y "firmado por" (signed-by → DKIM válido).
    // Solo se busca dentro de esa tabla para no confundir texto del cuerpo.
    const details = document.querySelector('.ajA table, .ajC') || scope.querySelector('.ajA');
    if (!details) return '';

    const detailsText = text(details).toLowerCase();
    const parts = [];

    const explicit = detailsText.match(/(spf|dkim|dmarc)=(pass|fail|softfail|neutral|none)/g);
    if (explicit) return [...new Set(explicit)].join(' ');

    if (/mailed-by|enviado por/.test(detailsText))  parts.push('spf=pass');
    if (/signed-by|firmado por/.test(detailsText))  parts.push('dkim=pass');
    return parts.join(' ');
  }

  // ════════════════════════════════════════════════════════
  // EXTRACTORES DE OUTLOOK
  // ════════════════════════════════════════════════════════
  function extractFromOutlook() {
    // Panel de lectura: Outlook (nuevo y clásico) usa role="main"
    const pane = document.querySelector('#ReadingPaneContainerId, [role="main"]') || document;

    // ── Cuerpo ─────────────────────────────────────────────
    const bodyEl = firstMatch([
      '[aria-label="Cuerpo del mensaje"]',
      '[aria-label="Message body"]',
      '[data-testid="messageBody"]',
      'div[role="document"]',
      '.allowTextSelection',
    ], pane);
    const bodyHtml = bodyEl ? bodyEl.innerHTML : '';
    const bodyText = text(bodyEl);

    // Buscar los encabezados cerca del cuerpo (mismo mensaje)
    const messageScope = (bodyEl && bodyEl.closest('[role="region"], [aria-label][tabindex], .wide-content-host')) || pane;

    // ── Remitente ──────────────────────────────────────────
    let from = '';
    const senderEl = firstMatch([
      '[data-testid="SenderPersona"]',
      '[data-testid="SenderField"]',
      'span[title*="@"]',
      'button[title*="@"]',
      '.ms-Persona-primaryText',
    ], messageScope) || firstMatch(['span[title*="@"]', 'button[title*="@"]'], pane);

    if (senderEl) {
      const title = senderEl.getAttribute('title') || '';
      const label = senderEl.getAttribute('aria-label') || '';
      const visible = text(senderEl);
      const email = (title.match(EMAIL_RE) || label.match(EMAIL_RE) || visible.match(EMAIL_RE) || [''])[0];
      const name  = visible.replace(/<[^>]*>/g, '').trim();
      from = email ? (name && !name.includes(email) ? `${name} <${email}>` : email) : name;
    }

    // ── Asunto ─────────────────────────────────────────────
    const subjectEl = firstMatch([
      '[data-testid="subject"]',
      '[id$="_SUBJECT"]',
      '[class*="SubjectLine"]',
      '[role="heading"][aria-level="2"]',
      '[role="heading"][aria-level="1"]',
    ], pane);
    const subject = text(subjectEl);

    if (!from && !subject && !bodyText) return null;

    return {
      from,
      subject,
      reply_to:     '',
      body_html:    bodyHtml.substring(0, MAX_HTML),
      body_text:    bodyText.substring(0, MAX_TEXT),
      auth_results: '', // Outlook no expone los encabezados en el DOM
      service:      detectService(),
    };
  }

  // ════════════════════════════════════════════════════════
  // FUNCIÓN PRINCIPAL DE EXTRACCIÓN
  // ════════════════════════════════════════════════════════
  function extractEmail() {
    const service = detectService();
    try {
      if (service === 'Gmail')          return extractFromGmail();
      if (service.includes('Outlook'))  return extractFromOutlook();
    } catch (err) {
      console.error('[Sentryx] Error extrayendo correo:', err);
    }
    return null;
  }

  // ════════════════════════════════════════════════════════
  // ESCUCHAR MENSAJES DEL POPUP
  // ════════════════════════════════════════════════════════
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message?.type !== 'EXTRACT_EMAIL') return false;

    const emailData = extractEmail();
    sendResponse({
      success: !!emailData,
      data:    emailData,
      service: detectService(),
      url:     window.location.href,
    });
    return false; // respuesta síncrona
  });
}
