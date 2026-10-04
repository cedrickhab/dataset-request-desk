// vitest/config re-exports defineConfig with the `test` block typed; the
// plain vite export does not know about it.
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

import pkg from './package.json' with { type: 'json' }

export default defineConfig({
  plugins: [react()],
  // The footer displays the version only when it comes from real project
  // metadata: this define reads package.json at build time and nothing else.
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
  server: {
    port: 5173,
    // Dev-only proxy. In the container the same single-origin arrangement is
    // provided by nginx, so application code never needs an API base URL and
    // never has to think about CORS.
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: false },
      '/health': { target: 'http://127.0.0.1:8000', changeOrigin: false },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    // Fail the build rather than ship a surprisingly large bundle: these
    // users are on metered mobile data.
    chunkSizeWarningLimit: 300,
  },
  test: {
    // Keep jsdom workers within the local Docker memory budget. Assertions
    // and timeouts stay unchanged; files run sequentially instead of competing.
    maxWorkers: 1,
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
})
