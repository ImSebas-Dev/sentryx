// Aplica el tema antes del primer pintado (evita el destello claro/oscuro).
// Debe coincidir con la lógica de src/store/ThemeContext.jsx.
// Está en un archivo y no inline en index.html para que la Content-Security-Policy
// pueda prohibir los scripts inline (script-src 'self').
(function () {
  var mode = 'system'
  try { mode = localStorage.getItem('sentryx-theme') || 'system' } catch (e) {}
  var dark = mode === 'dark' ||
    (mode === 'system' && window.matchMedia &&
     window.matchMedia('(prefers-color-scheme: dark)').matches)
  var theme = dark ? 'dark' : 'light'
  document.documentElement.setAttribute('data-theme', theme)
  var meta = document.querySelector('meta[name="theme-color"]')
  if (meta) meta.setAttribute('content', dark ? '#141414' : '#fafafa')
})()
