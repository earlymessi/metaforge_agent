import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      // 前端开发时，API 走后端（避免 CORS、保持路径一致）
      '/api': process.env.VITE_API_PROXY || 'http://127.0.0.1:8008', // 与 METAFORGE_PORT 一致
    },
  },
  build: {
    // 生产构建输出到后端可直接托管的位置
    outDir: '../tests/templates/dist',
    emptyOutDir: true,
  },
})
