import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Builds straight into ../static so FastAPI's existing "/" (FileResponse of
// static/index.html) and "/static" (StaticFiles mount) routes work unchanged
// - no app.py routing changes needed for this to slot in. Only the build
// needs base:'/static/' (so the built index.html references
// /static/assets/...); the dev server keeps base:'/' so `npm run dev` works
// at the plain root like a normal Vite app.
export default defineConfig(({ command }) => ({
  plugins: [react()],
  base: command === 'build' ? '/static/' : '/',
  build: {
    outDir: '../static',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
}))
