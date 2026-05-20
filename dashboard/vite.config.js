import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import Icons from 'unplugin-icons/vite'
import path from 'node:path'

// Vite builds into ../barista/public/dist so that Frappe serves the bundle
// at /assets/barista/dist/.
export default defineConfig({
  plugins: [
    vue(),
    Icons({ compiler: 'vue3', autoInstall: false }),
  ],
  resolve: {
    alias: { '@': path.resolve(__dirname, 'src') },
  },
  build: {
    outDir: path.resolve(__dirname, '../barista/public/dist'),
    emptyOutDir: true,
    rollupOptions: {
      output: {
        entryFileNames: 'index.js',
        chunkFileNames: 'chunk-[hash].js',
        assetFileNames: (a) => (a.name && a.name.endsWith('.css') ? 'index.css' : 'asset-[hash][extname]'),
      },
    },
  },
  test: {
    environment: 'happy-dom',
    globals: true,
    setupFiles: ['./tests/setup.js'],
  },
  server: {
    port: 8080,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/assets': 'http://127.0.0.1:8000',
    },
  },
})
