import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    {
      name: 'remove-crossorigin',
      enforce: 'post',
      transformIndexHtml(html: string) {
        // Remove crossorigin attribute from script/link tags (breaks CF Access)
        return html.replace(/ crossorigin/g, '')
      },
    },
  ],
  base: '/app/',
  build: {
    outDir: '../app/static',
    emptyOutDir: true,
    modulePreload: false,
  },
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/dl': 'http://localhost:8000',
    },
  },
})
