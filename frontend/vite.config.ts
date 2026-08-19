import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiTarget = env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000'
  const wsTarget = apiTarget.replace(/^http/, 'ws')
  return {
    plugins: [react()],
    server: {
      proxy: {
        '/api': apiTarget,
        '/ws': { target: wsTarget, ws: true },
      },
    },
  }
})
