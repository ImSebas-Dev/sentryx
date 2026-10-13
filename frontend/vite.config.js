import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    allowedHosts: ['frontend', 'localhost', '127.0.0.1'],
    // En Docker sobre carpetas de Windows no llegan los eventos de cambio de
    // archivo: sin polling, Vite seguiría sirviendo el código anterior.
    watch: { usePolling: true, interval: 300 },
    proxy: {
      '/api': { target: 'http://backend:8000', changeOrigin: true },
      '/ml':  { target: 'http://ml_engine:8001', changeOrigin: true,
                rewrite: path => path.replace(/^\/ml/, '') },
    },
  },
  test: {
    globals:     true,
    environment: 'jsdom',
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
