import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { resolve } from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'index.html'),
        eval: resolve(__dirname, 'eval.html'),
      },
    },
  },
  server: {
    port: Number(process.env.PORT) || 5173,
    // Слушать на всех интерфейсах — иначе с другой машины по IP не зайти
    host: true,
    proxy: {
      // Относительные /api/* с любого IP идут на локальный backend
      '/api': {
        target: process.env.VITE_API_PROXY || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
