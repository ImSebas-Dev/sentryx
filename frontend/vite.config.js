import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // Sin mapas de código en producción: no publicar el código fuente original
  build: { sourcemap: false },
  server: {
    host: '0.0.0.0',
    port: 5173,
    allowedHosts: ['frontend', 'localhost', '127.0.0.1'],
    // En Docker sobre carpetas de Windows no llegan los eventos de cambio de
    // archivo: sin polling, Vite seguiría sirviendo el código anterior.
    watch: { usePolling: true, interval: 300 },
    // Solo la API. El motor ML no se expone al navegador: lo llama el backend.
    proxy: {
      '/api': { target: 'http://backend:8000', changeOrigin: true },
    },
  },
  test: {
    globals:     true,
    environment: 'jsdom',
    // Mismo origen que la API simulada (http://localhost/api/v1): sin esto jsdom
    // trata las peticiones con X-Sentryx-Client como cross-origin y exige preflight.
    environmentOptions: { jsdom: { url: 'http://localhost/' } },
    setupFiles:  ['./src/test/setup.js'],
    coverage: {
      provider:   'v8',
      reporter:   ['text', 'lcov', 'html'],
      exclude:    ['node_modules/', 'src/test/', '*.config.*'],
      thresholds: { lines: 60, functions: 60, branches: 55, statements: 60 },
    },
    include: ['src/**/*.{test,spec}.{js,jsx}'],
  },
})
