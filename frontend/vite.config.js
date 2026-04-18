import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        // changeOrigin intentionally off — keeps the request's Host header
        // (e.g. 192.168.0.133:5173) so FastAPI's trailing-slash 307 redirects
        // Location back through the proxy instead of cross-origin to localhost:8000.
        changeOrigin: false,
      },
    },
  },
})
