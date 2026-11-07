import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import { execFileSync } from 'node:child_process'

const buildId = process.env.VITE_BUILD_VERSION || execFileSync('git', ['rev-parse', '--short=12', 'HEAD'], { cwd: __dirname, encoding: 'utf8' }).trim()

export default defineConfig({
  base: './',
  plugins: [react()],
  define: { 'import.meta.env.VITE_BUILD_VERSION': JSON.stringify(buildId) },
  resolve: {
    alias: {
      '@core': path.resolve(__dirname, '../core/core'),
      '@models': path.resolve(__dirname, '../core/models'),
    },
  },
  server: {
    fs: {
      allow: [path.resolve(__dirname, '..')],
    },
  },
  optimizeDeps: { },
})
