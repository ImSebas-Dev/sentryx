/**
 * Sentryx — Tailwind con tokens de Fluent 2.
 *
 * Los colores no son fijos: apuntan a variables CSS (src/index.css) que
 * cambian entre tema claro y oscuro. Así una misma clase (bg-layer,
 * text-fg-2, text-red-fg…) funciona en ambos temas.
 *
 * Familias de estado (red, orange, yellow, green, purple, teal, pink,
 * blue, gray) siguen la paleta de Fluent:
 *   -fg    texto/icono con contraste AA sobre el fondo de la tarjeta
 *   -tint  fondo suave (badges, message bars)
 *   -line  borde de ese fondo suave
 *   -solid relleno saturado (barras, gráficas)
 */
const v = name => `rgb(var(--${name}) / <alpha-value>)`

const statusFamily = name => ({
  fg:    v(`${name}-fg`),
  tint:  v(`${name}-tint`),
  line:  v(`${name}-line`),
  solid: v(`${name}-solid`),
})

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // Superficies (de atrás hacia delante)
        canvas:  v('canvas'),     // fondo de la app
        nav:     v('nav'),        // panel de navegación y barra superior
        layer:   v('layer'),      // tarjetas, menús, diálogos
        subtle:  v('subtle'),     // zonas hundidas dentro de una tarjeta

        // Bordes
        stroke: {
          DEFAULT: v('stroke'),         // tarjetas y divisores
          strong:  v('stroke-strong'),  // controles (inputs, botones secundarios)
        },

        // Texto
        fg: {
          DEFAULT: v('fg'),     // títulos y texto principal
          2:       v('fg-2'),   // texto secundario
          3:       v('fg-3'),   // descripciones, etiquetas
          4:       v('fg-4'),   // placeholders, metadatos
        },

        // Marca (azul de comunicación de Fluent)
        brand: {
          DEFAULT: v('brand'),
          hover:   v('brand-hover'),
          pressed: v('brand-pressed'),
          fg:      v('brand-fg'),
          tint:    v('brand-tint'),
          line:    v('brand-line'),
        },
        'on-brand': v('on-brand'),
        focus:      v('focus'),

        red:    statusFamily('red'),
        orange: statusFamily('orange'),
        yellow: statusFamily('yellow'),
        green:  statusFamily('green'),
        purple: statusFamily('purple'),
        teal:   statusFamily('teal'),
        pink:   statusFamily('pink'),
        blue:   statusFamily('blue'),
        gray:   statusFamily('gray'),
      },

      fontFamily: {
        sans: [
          '"Segoe UI Variable Text"', '"Segoe UI"', '-apple-system',
          'BlinkMacSystemFont', 'Roboto', '"Helvetica Neue"', 'sans-serif',
        ],
        mono: ['"Cascadia Mono"', 'Consolas', '"SF Mono"', 'Menlo', 'monospace'],
      },

      // Rampa tipográfica de Fluent 2 (tamaño / interlineado)
      fontSize: {
        caption2: ['10px', '14px'],
        caption:  ['12px', '16px'],
        body:     ['14px', '20px'],
        subtitle2:['16px', '22px'],
        subtitle: ['20px', '28px'],
        title3:   ['24px', '32px'],
        title2:   ['28px', '36px'],
        title1:   ['32px', '40px'],
      },

      // Elevación de Fluent 2 (sombra ambiental + sombra clave)
      boxShadow: {
        2:  '0 0 2px rgb(0 0 0 / var(--shadow-ambient)), 0 1px 2px rgb(0 0 0 / var(--shadow-key))',
        4:  '0 0 2px rgb(0 0 0 / var(--shadow-ambient)), 0 2px 4px rgb(0 0 0 / var(--shadow-key))',
        8:  '0 0 2px rgb(0 0 0 / var(--shadow-ambient)), 0 4px 8px rgb(0 0 0 / var(--shadow-key))',
        16: '0 0 2px rgb(0 0 0 / var(--shadow-ambient)), 0 8px 16px rgb(0 0 0 / var(--shadow-key))',
        28: '0 0 8px rgb(0 0 0 / var(--shadow-ambient)), 0 14px 28px rgb(0 0 0 / var(--shadow-key))',
        64: '0 0 8px rgb(0 0 0 / var(--shadow-ambient)), 0 32px 64px rgb(0 0 0 / var(--shadow-key))',
      },

      // Curvas de movimiento de Fluent 2
      transitionTimingFunction: {
        fluent:     'cubic-bezier(0.33, 0, 0.67, 1)',
        decelerate: 'cubic-bezier(0.1, 0.9, 0.2, 1)',
        accelerate: 'cubic-bezier(0.9, 0.1, 1, 0.2)',
      },

      keyframes: {
        'fade-in':  { from: { opacity: 0 }, to: { opacity: 1 } },
        'slide-up': {
          from: { opacity: 0, transform: 'translateY(8px)' },
          to:   { opacity: 1, transform: 'translateY(0)' },
        },
        'scale-in': {
          from: { opacity: 0, transform: 'scale(0.96)' },
          to:   { opacity: 1, transform: 'scale(1)' },
        },
        'drawer-in': {
          from: { transform: 'translateX(-100%)' },
          to:   { transform: 'translateX(0)' },
        },
      },
      animation: {
        'drawer-in': 'drawer-in 250ms cubic-bezier(0.1, 0.9, 0.2, 1) both',
        'fade-in':  'fade-in 200ms cubic-bezier(0.33, 0, 0.67, 1) both',
        'slide-up': 'slide-up 300ms cubic-bezier(0.1, 0.9, 0.2, 1) both',
        'scale-in': 'scale-in 150ms cubic-bezier(0.1, 0.9, 0.2, 1) both',
      },
    },
  },
  plugins: [],
}
