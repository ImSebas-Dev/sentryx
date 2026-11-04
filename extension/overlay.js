/**
 * Sentryx Extension — Banner de riesgo y capa de bloqueo sobre el correo.
 *
 * Recibe el resultado del análisis desde el popup (mensaje SHOW_RISK).
 * Dibuja dentro de un Shadow DOM para no heredar ni alterar los estilos de
 * Gmail u Outlook. Escribe siempre con textContent: los motivos traen nombres
 * de proveedores y notas de otras personas, y nada de eso debe interpretarse como HTML.
 */
if (!window.__sentryxOverlayLoaded) {
  window.__sentryxOverlayLoaded = true;

  const HOST_ID   = 'sentryx-risk-host';
  const HREF_ATTR = 'data-sentryx-href';
  const POLL_MS     = 20000;
  const POLL_MAX_MS = 300000;

  let current = null; // { body, host, shadow }
  let pollTimer = null;
  let hiddenAreas = [];

  function send(message) {
    return new Promise(resolve => {
      chrome.runtime.sendMessage(message, response => {
        if (chrome.runtime.lastError) {
          resolve({ success: false, error: chrome.runtime.lastError.message });
        } else {
          resolve(response || { success: false, error: 'Sin respuesta.' });
        }
      });
    });
  }

  // ── Enlaces ─────────────────────────────────────────────
  // Quita el href en vez de ocultar el enlace: así tampoco se abre con clic
  // derecho o con el teclado. Guárdalo en el atributo para poder restaurarlo.
  function disableLinks(body) {
    body.querySelectorAll('a[href]').forEach(link => {
      link.setAttribute(HREF_ATTR, link.getAttribute('href'));
      link.removeAttribute('href');
      link.style.pointerEvents = 'none';
      link.style.textDecoration = 'line-through';
    });
  }

  function restoreLinks(body) {
    body.querySelectorAll(`a[${HREF_ATTR}]`).forEach(link => {
      link.setAttribute('href', link.getAttribute(HREF_ATTR));
      link.removeAttribute(HREF_ATTR);
      link.style.pointerEvents = '';
      link.style.textDecoration = '';
    });
  }

  // ── Elementos ───────────────────────────────────────────
  const STYLES = `
    :host { all: initial; display: block; margin: 0 0 12px; }
    .box { font: 14px/20px "Segoe UI", Roboto, Arial, sans-serif; color: #fff;
           background: #b3261e; border-radius: 8px; padding: 14px 16px; }
    .box.warn { background: #9a5b00; }
    .box.ok   { background: #0e700e; }
    h2 { font-size: 16px; line-height: 22px; margin: 0 0 6px; font-weight: 600; }
    p  { margin: 0 0 8px; }
    ul { margin: 0 0 10px; padding-left: 20px; }
    textarea { width: 100%; box-sizing: border-box; border-radius: 4px; border: 0;
               padding: 6px 8px; font: inherit; margin-bottom: 8px; color: #242424; }
    button { font: inherit; font-weight: 600; padding: 6px 12px; border-radius: 4px;
             border: 1px solid #fff; background: #fff; color: #b3261e; cursor: pointer;
             margin: 0 6px 6px 0; }
    button.ghost { background: transparent; color: #fff; }
    button:disabled { opacity: .6; cursor: default; }
  `;

  function el(tag, props = {}, ...children) {
    const node = document.createElement(tag);
    Object.entries(props).forEach(([k, v]) => {
      if (k === 'onClick') node.addEventListener('click', v);
      else if (k === 'className') node.className = v;
      else node.setAttribute(k, v);
    });
    children.flat().forEach(c => node.append(c));
    return node;
  }

  function stopPolling() {
    if (pollTimer) clearTimeout(pollTimer);
    pollTimer = null;
  }

  function clear() {
    stopPolling();
    if (!current) return;
    current.host.remove();
    current = null;
  }

  // ── Bloqueo del cuerpo y de los adjuntos ────────────────
  function hideAttachments() {
    const selectors = window.__sentryxDom?.attachmentAreas() || [];
    selectors.forEach(selector => {
      document.querySelectorAll(selector).forEach(area => {
        if (area.style.display === 'none') return;
        area.style.display = 'none';
        hiddenAreas.push(area);
      });
    });
  }

  function lockEmail(body) {
    disableLinks(body);
    hideAttachments();
    body.style.visibility = 'hidden';
    body.style.maxHeight = '0';
    body.style.overflow = 'hidden';
  }

  function unlockEmail(body) {
    restoreLinks(body);
    body.style.visibility = '';
    body.style.maxHeight = '';
    body.style.overflow = '';
    hiddenAreas.forEach(area => { area.style.display = ''; });
    hiddenAreas = [];
  }

  function mount(body) {
    clear();
    const host = el('div', { id: HOST_ID });
    const shadow = host.attachShadow({ mode: 'closed' });
    shadow.append(el('style', {}, STYLES));
    body.parentElement.insertBefore(host, body);
    current = { body, host, shadow };
    return current;
  }

  function render(node) {
    const { shadow } = current;
    [...shadow.children].filter(c => c.tagName !== 'STYLE').forEach(c => c.remove());
    shadow.append(node);
  }

  // ── Banner del Escudo de pagos ──────────────────────────
  function showPaymentBanner(body, shield) {
    mount(body);
    disableLinks(body);
    const phone = shield.supplier?.contact_phone;
    const callText = phone
      ? `Antes de pagar, llama al número que tienes registrado: ${phone}.`
      : 'Antes de pagar, llama a tu proveedor a un número que ya conozcas, no al del correo.';

    const ack = el('button', { onClick: async () => {
      ack.disabled = true;
      const res = await send({ type: 'ACK_PAYMENT_RISK', checkId: shield.check_id });
      if (res.success) {
        restoreLinks(body);
        clear();
      } else {
        ack.disabled = false;
        status.textContent = res.error || 'No se pudo registrar. Inténtalo de nuevo.';
      }
    } }, 'Entiendo el riesgo');
    const status = el('p', { role: 'status' });

    render(el('div', { className: 'box', role: 'alert' },
      el('h2', {}, 'Este correo pide un pago y no coincide con los datos de tu proveedor'),
      el('p', {}, shield.message || ''),
      el('p', {}, callText),
      status,
      ack,
    ));
  }

  // ── Capa de bloqueo de cuatro ojos ──────────────────────
  // No agregues aquí un botón para saltarse el bloqueo: la decisión es de la
  // segunda persona. Ver la limitación en extension/README.md.
  function reasonList(reasons) {
    return el('ul', {}, (reasons || []).map(r => el('li', {}, r.detail || '')));
  }

  function renderRequestForm(state) {
    const note = el('textarea', { rows: '2', maxlength: '1000',
                                  placeholder: 'Nota para quien aprueba (opcional)',
                                  'aria-label': 'Nota para quien aprueba' });
    const status = el('p', { role: 'status' });
    const button = el('button', { onClick: async () => {
      button.disabled = true;
      const res = await send({ type: 'CREATE_APPROVAL', alertId: state.alertId, note: note.value });
      if (res.success) {
        renderRequest(state, res.data);
      } else {
        button.disabled = false;
        status.textContent = res.error || 'No se pudo pedir la aprobación.';
      }
    } }, 'Pedir aprobación');
    render(el('div', { className: 'box', role: 'alert' },
      el('h2', {}, 'Este correo está bloqueado hasta que otra persona lo apruebe'),
      reasonList(state.reasons), note, status, button));
  }

  function renderRequest(state, request) {
    const status = request.status === 'pending' || request.effective_status === 'pending'
      ? 'pending' : (request.effective_status || request.status);
    stopPolling();
    if (status === 'pending') {
      render(el('div', { className: 'box warn', role: 'status' },
        el('h2', {}, 'Esperando la aprobación de una segunda persona'),
        reasonList(state.reasons),
        el('p', {}, 'Puedes seguir trabajando; este aviso se actualiza solo.')));
      schedulePoll(state, request.id, POLL_MS);
    } else if (status === 'approved') {
      unlockEmail(state.body);
      render(el('div', { className: 'box ok', role: 'status' },
        el('h2', {}, 'Correo aprobado'),
        el('p', {}, `Lo aprobó ${request.decided_by_name || 'una segunda persona'}.`),
        el('button', { className: 'ghost', onClick: clear }, 'Cerrar')));
    } else if (status === 'rejected') {
      const guided = `${state.frontendUrl}/respond?alert=${encodeURIComponent(state.alertId)}`;
      render(el('div', { className: 'box', role: 'alert' },
        el('h2', {}, 'La aprobación fue rechazada: no continúes'),
        request.decision_note ? el('p', {}, `Nota: ${request.decision_note}`) : '',
        el('button', { onClick: () => window.open(guided, '_blank', 'noopener') },
           '¿Ya hiciste clic?')));
    } else {
      // Vencida o cancelada: el correo sigue bloqueado y se puede pedir de nuevo
      renderRequestForm(state);
    }
  }

  // Consulta el estado cada 20 s; si falla, espera el doble hasta 5 minutos.
  // Detente cuando el correo ya no esté en pantalla.
  function schedulePoll(state, requestId, delay) {
    pollTimer = setTimeout(async () => {
      if (!state.body.isConnected || !current) {
        clear();
        return;
      }
      if (document.hidden) {
        schedulePoll(state, requestId, delay);
        return;
      }
      const res = await send({ type: 'APPROVAL_STATUS', requestId });
      if (!current) return;
      if (res.success) renderRequest(state, res.data);
      else schedulePoll(state, requestId, Math.min(delay * 2, POLL_MAX_MS));
    }, delay);
  }

  async function showFourEyesLock(body, result) {
    mount(body);
    lockEmail(body);
    const state = { body, alertId: result.alert_id, reasons: result.four_eyes_reasons,
                    frontendUrl: result.frontend_url || '' };
    const existing = await send({ type: 'FIND_APPROVAL', alertId: result.alert_id });
    if (existing.success && existing.data) renderRequest(state, existing.data);
    else renderRequestForm(state);
  }

  window.addEventListener('hashchange', () => {
    if (current && !current.body.isConnected) clear();
  });

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message?.type !== 'SHOW_RISK') return false;
    const body = window.__sentryxDom?.currentBodyElement();
    const { result } = message;
    // La capa de cuatro ojos reemplaza al banner: no hay "Entiendo el riesgo" en ella
    if (body?.parentElement && result?.four_eyes_required && result.alert_id) {
      showFourEyesLock(body, result);
    } else if (body?.parentElement && result?.payment_shield?.risky && result.payment_shield.check_id) {
      showPaymentBanner(body, result.payment_shield);
    }
    sendResponse({ success: !!body });
    return false;
  });
}
