import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiTarget = env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000'
  const isVercelBuild = env.VERCEL === '1' || process.env.VERCEL === '1'
  const apiUrl = env.VITE_API_URL || process.env.VITE_API_URL
  const configuredWsUrl = env.VITE_WS_URL || process.env.VITE_WS_URL
  const wsUrl = configuredWsUrl?.replace(/^https:/, 'wss:') || (apiUrl ? `${apiUrl.replace(/^https:/, 'wss:').replace(/\/$/, '')}/ws/dashboard` : undefined)
  if (isVercelBuild) {
    if (!apiUrl?.startsWith('https://')) {
      throw new Error('Vercel requires VITE_API_URL with the public HTTPS FastAPI base URL.')
    }
    if (!wsUrl?.startsWith('wss://')) throw new Error('Vercel requires a public secure WebSocket URL.')
  }
  return {
    base: mode === 'desktop' ? './' : '/',
    plugins: [react()],
    server: {
      proxy: {
        '/api': apiTarget,
        '/ws': {
          target: apiTarget.replace(/^http/, 'ws'),
          ws: true,
        },
      },
    },
  }
})
