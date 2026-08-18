import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    // 开发模式：/api 转发到本地 FastAPI，前端代码无需关心端口
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
