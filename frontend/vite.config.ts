import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import path from 'node:path';

export default defineConfig({
  base: './',
  plugins: [react(), tailwindcss()],
  css: {
    postcss: {
      plugins: [],
    },
  },
  build: {
    outDir: path.resolve(__dirname, '../backend/web_dist'),
    emptyOutDir: true,
    sourcemap: false,
  },
});
