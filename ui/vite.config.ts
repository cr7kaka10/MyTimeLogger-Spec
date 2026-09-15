import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  base: './',
  plugins: [react()],
  resolve: {
    alias: {
      '@core': path.resolve(__dirname, '../core/core'),
      '@models': path.resolve(__dirname, '../core/models'),
    },
  },
  optimizeDeps: { },
})
