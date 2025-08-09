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
        configure: (proxy) => {
          proxy.on('proxyReq', (proxyReq, req) => {
            // Forward cookies from the browser
            if (req.headers.cookie) {
              proxyReq.setHeader('cookie', req.headers.cookie);
            }
            // Set proper origin for CSRF validation
            proxyReq.setHeader('origin', `http://localhost:${djangoPort}`);
            proxyReq.setHeader('referer', `http://localhost:${djangoPort}/`);
          });
        },
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
});
