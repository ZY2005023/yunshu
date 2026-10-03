import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:1236',
        changeOrigin: true
      },
      // 上传文件由后端的 /files/** 静态映射提供。
      // 不代理这一条的话，开发环境里所有封面/头像都会打到 vite 上变成 404。
      '/files': {
        target: 'http://127.0.0.1:1236',
        changeOrigin: true
      }
    }
  }
})
