/**
 * Colores de las gráficas (Recharts) por tema.
 * Recharts escribe los colores como atributos SVG, que no aceptan var(),
 * así que se resuelven aquí según el tema activo (useTheme().theme).
 * Los valores coinciden con los tokens de src/index.css.
 */
const PALETTES = {
  light: {
    brand:   '#0f6cbd',
    grid:    '#e0e0e0',
    axis:    '#616161',
    cursor:  'rgba(15, 108, 189, 0.08)',
    tooltip: { background: '#ffffff', border: '#e0e0e0', text: '#242424', muted: '#616161' },
  },
  dark: {
    brand:   '#479ef5',
    grid:    '#3d3d3d',
    axis:    '#adadad',
    cursor:  'rgba(71, 158, 245, 0.12)',
    tooltip: { background: '#292929', border: '#3d3d3d', text: '#ffffff', muted: '#adadad' },
  },
}

// Tonos saturados de Fluent: legibles sobre fondo claro y oscuro
export const TYPE_COLORS = {
  bec:      '#8764b8',
  whaling:  '#d13438',
  spear:    '#da3b01',
  clone:    '#0f6cbd',
  vishing:  '#c239b3',
  smishing: '#038387',
  generic:  '#8a8a8a',
  unknown:  '#6e6e6e',
}

export const chartPalette = theme => PALETTES[theme] || PALETTES.light

export function tooltipStyle(theme) {
  const t = chartPalette(theme).tooltip
  return {
    contentStyle: {
      background: t.background, border: `1px solid ${t.border}`, borderRadius: 8,
      fontSize: 12, boxShadow: '0 8px 16px rgba(0,0,0,0.14)', padding: '8px 12px',
    },
    labelStyle: { color: t.muted, marginBottom: 2 },
    itemStyle:  { color: t.text, fontWeight: 600 },
  }
}
