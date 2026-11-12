import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/video_feed': 'http://127.0.0.1:8000',
      '/cameras': 'http://127.0.0.1:8000',
      '/logs': 'http://127.0.0.1:8000',
      '/stats': 'http://127.0.0.1:8000',
      '/amfv_status': 'http://127.0.0.1:8000',
      '/system_info': 'http://127.0.0.1:8000',
      '/settings': 'http://127.0.0.1:8000',
      '/analytics': 'http://127.0.0.1:8000',
      '/snapshots_list': 'http://127.0.0.1:8000',
      '/snapshots': 'http://127.0.0.1:8000',
      '/export': 'http://127.0.0.1:8000',
      '/clear_logs': 'http://127.0.0.1:8000',
      '/violations': 'http://127.0.0.1:8000',
    }
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  }
})
