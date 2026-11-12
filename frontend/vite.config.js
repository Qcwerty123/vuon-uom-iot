import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Đích proxy khi chạy dev. Mặc định backend trên chính máy này.
// Làm trên máy khác (trong hotspot của máy chủ):
//   PowerShell: $env:BACKEND_URL = "http://192.168.137.1:8000"; ..\tools\node\npm.cmd run dev
const target = process.env.BACKEND_URL || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': { target, changeOrigin: true },
      '/ws': { target: target.replace(/^http/, 'ws'), ws: true },
    },
  },
  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 1500,
  },
})
