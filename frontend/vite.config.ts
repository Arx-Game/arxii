import path from 'path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Use environment variable or default to Evennia's webserver-proxy port
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
    port: 3000,
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
    rollupOptions: {
      output: {
        manualChunks: (id: string) => {
          // Core vendor libraries (rarely change, cache aggressively)
          if (
            ['react', 'react-dom', 'react-router-dom'].some((pkg) =>
              id.includes(`node_modules/${pkg}`)
            )
          ) {
            return 'vendor-react';
          }
          if (
            ['@reduxjs/toolkit', 'react-redux', '@tanstack/react-query'].some((pkg) =>
              id.includes(`node_modules/${pkg}`)
            )
          ) {
            return 'vendor-state';
          }
          if (
            [
              '@radix-ui/react-accordion',
              '@radix-ui/react-avatar',
              '@radix-ui/react-dialog',
              '@radix-ui/react-dropdown-menu',
              '@radix-ui/react-icons',
              '@radix-ui/react-navigation-menu',
              '@radix-ui/react-separator',
              '@radix-ui/react-slot',
              '@radix-ui/react-tabs',
              '@radix-ui/react-select',
              'sonner',
              'lucide-react',
            ].some((pkg) => id.includes(`node_modules/${pkg}`))
          ) {
            return 'vendor-ui';
          }
          if (
            [
              'clsx',
              'class-variance-authority',
              'tailwind-merge',
              'next-themes',
              'react-hook-form',
              'react-error-boundary',
            ].some((pkg) => id.includes(`node_modules/${pkg}`))
          ) {
            return 'vendor-utils';
          }

          // Feature-based chunks (load on-demand based on user activity)
          if (
            id.includes('/game/') ||
            id.includes('/hooks/useGameSocket') ||
            id.includes('/hooks/handleCommandPayload') ||
            id.includes('/hooks/handleRoomStatePayload') ||
            id.includes('/hooks/handleScenePayload') ||
            id.includes('/hooks/parseGameMessage')
          ) {
            return 'game-client';
          }
          if (
            id.includes('/roster/') ||
            id.includes('/components/character/') ||
            id.includes('/world/character_sheets/')
          ) {
            return 'character-roster';
          }
          if (id.includes('/scenes/')) {
            return 'scenes';
          }
          if (
            id.includes('LoginPage') ||
            id.includes('ProfilePage') ||
            id.includes('AuthProvider')
          ) {
            return 'auth-profile';
          }
          if (
            id.includes('HomePage') ||
            (id.includes('/evennia_replacements/') && !id.includes('LoginPage'))
          ) {
            return 'home-public';
          }

          // Default chunk for everything else
          return undefined;
        },
      },
    },
  },
  // Ensure source maps are enabled in development
  css: {
    devSourcemap: true,
  },
});
