import path from 'path';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  // Load env file based on `mode` in the current working directory.
  // Set the third parameter to '' to load all env regardless of the `VITE_` prefix.
  const env = loadEnv(mode, process.cwd(), '');

  // Use environment variable or default to Evennia's webserver-proxy port
  const djangoPort = env.DJANGO_PORT || '4001';

  // Parse allowed hosts from environment variable (comma-separated list)
  // Example: VITE_ALLOWED_HOSTS="abc123.ngrok-free.app,xyz456.ngrok.io"
  const allowedHostsEnv = env.VITE_ALLOWED_HOSTS || '';
  const allowedHosts = allowedHostsEnv ? allowedHostsEnv.split(',').map((host) => host.trim()) : [];

  console.log('[vite.config] Allowed hosts:', allowedHosts);

  return {
    plugins: [react()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      port: 3000,
      // Allow specific hosts from environment variable for ngrok/tunneling
      // Set VITE_ALLOWED_HOSTS="your-ngrok-domain.ngrok-free.app" when using ngrok
      ...(allowedHosts.length > 0 && { allowedHosts }),
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

            // Log responses to debug error truncation issues
            proxy.on('proxyRes', (proxyRes, req) => {
              if (proxyRes.statusCode && proxyRes.statusCode >= 400) {
                let body = '';
                proxyRes.on('data', (chunk) => {
                  body += chunk.toString();
                });
                proxyRes.on('end', () => {
                  console.error(`[PROXY] ${req.method} ${req.url} -> ${proxyRes.statusCode}`);
                  console.error(`[PROXY] Response body:`, body);
                });
              }
            });
          },
        },
      },
    },
    build: {
      outDir: '../src/web/static/dist',
      emptyOutDir: true,
      sourcemap: true, // Enable source maps for production builds
      chunkSizeWarningLimit: 700, // App code is in one chunk; split with React.lazy later
      rollupOptions: {
        output: {
          manualChunks: (id: string) => {
            // Only split vendor libraries into manual chunks.
            // Feature-based splitting is left to Rollup's automatic chunking
            // to avoid circular chunk dependencies between app code and vendors.
            if (!id.includes('node_modules')) return undefined;

            if (
              ['react', 'react-dom', 'react-router-dom'].some((pkg) =>
                id.includes(`node_modules/${pkg}/`)
              )
            ) {
              return 'vendor-react';
            }
            if (
              ['@reduxjs/toolkit', 'react-redux', '@tanstack/react-query'].some((pkg) =>
                id.includes(`node_modules/${pkg}/`)
              )
            ) {
              return 'vendor-state';
            }
            if (
              ['@radix-ui/', 'sonner', 'lucide-react'].some((pkg) =>
                id.includes(`node_modules/${pkg}`)
              )
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
              ].some((pkg) => id.includes(`node_modules/${pkg}/`))
            ) {
              return 'vendor-utils';
            }

            return undefined;
          },
        },
      },
    },
    // Ensure source maps are enabled in development
    css: {
      devSourcemap: true,
    },
  };
});
