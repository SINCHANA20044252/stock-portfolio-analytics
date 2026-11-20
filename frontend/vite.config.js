import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In development the browser talks to /api on the Vite server, which forwards to FastAPI.
// That keeps the login cookie first-party (same origin), which is what makes httpOnly cookies work.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true, rewrite: (p) => p.replace(/^\/api/, '') },
    },
  },
})
