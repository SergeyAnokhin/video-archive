import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // 0.0.0.0 (post-V1, user request -- "connect from a phone on the same
    // network / hotspot"): listens on every local interface, not just
    // loopback, so a LAN device can reach it. Backend proxy target below
    // stays on 127.0.0.1 since that hop is same-machine regardless.
    host: '0.0.0.0',
    port: Number(process.env.PORT) || 5173,
    proxy: {
      '/api': {
        target: `http://127.0.0.1:${process.env.BACKEND_PORT || 8000}`,
        changeOrigin: true,
      },
    },
  },
})
