/**
 * Sentryx Extension — Banner de riesgo sobre el correo.
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

  let current = null; // { body, host, shadow }

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

  function clear() {
    if (!current) return;
    current.host.remove();
    current = null;
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

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message?.type !== 'SHOW_RISK') return false;
    const body = window.__sentryxDom?.currentBodyElement();
    const { result } = message;
    if (body?.parentElement && result?.payment_shield?.risky && result.payment_shield.check_id) {
      showPaymentBanner(body, result.payment_shield);
    }
    sendResponse({ success: !!body });
    return false;
  });
}
