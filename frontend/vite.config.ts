import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const apiProxy = {'/api': {target: process.env.VITE_API_TARGET || 'http://127.0.0.1:8000', changeOrigin: true}}
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { host: '127.0.0.1', port: 5173, strictPort: true, proxy: apiProxy },
  preview: { host: '127.0.0.1', port: 4173, proxy: apiProxy },
})

