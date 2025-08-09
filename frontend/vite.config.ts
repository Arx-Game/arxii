import path from 'path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Use environment variable or default to Evennia's default web port
const djangoPort = process.env.DJANGO_PORT || '4001';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    proxy: {
      '/api': {
        target: `http://localhost:${djangoPort}`,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: '../src/web/static/dist',
    emptyOutDir: true,
    sourcemap: true, // Enable source maps for production builds
  },
  // Ensure source maps are enabled in development
  css: {
    devSourcemap: true,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.ts',
  },
});
