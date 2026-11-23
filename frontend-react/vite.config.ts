import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  // Em `npm run dev` o frontend chama o caminho relativo /api/v1 e o Vite
  // encaminha ao backend local: sem CORS, e o SSE do sync (EventSource, que
  // não manda header) fala com a mesma origem. Antes, o dev chamava o backend
  // de produção no Railway — que nem existe mais.
  const backend = env.VITE_DEV_BACKEND || 'http://localhost:8000'
  // Build do app nativo (npm run build:mobile): o app não tem proxy, então a
  // API precisa ser uma URL absoluta e https — sem isso, recusa o build em vez
  // de gerar um app que fala com lugar nenhum (ou em texto puro).
  if (mode === 'mobile' && !/^https:\/\/[^/]+/.test(env.VITE_API_URL || '')) {
    throw new Error('build mobile: defina VITE_API_URL=https://<sua-api>/api/v1 no .env.mobile')
  }
  return {
    plugins: [react()],
    server: {
      port: 3000,
      host: true,
      watch: {
        usePolling: true,
        interval: 300,
      },
      proxy: {
        '/api': { target: backend, changeOrigin: true },
      },
    },
    resolve: {
      alias: {
        '@': '/src',
      },
    },
  }
})
