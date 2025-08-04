# Frontend

This directory houses the React client built with Vite and TypeScript.

## Development

1. Install the project toolchain:
   ```bash
   mise install
   pnpm install
   ```
2. Start the Vite dev server which proxies API requests to Django:
   ```bash
   pnpm dev
   ```
   The application will be available at <http://localhost:5173>.

## Production Build

1. Create an optimized build:
   ```bash
   pnpm build
   ```
   Compiled assets will be written to `src/web/static/dist/` for Django or nginx to serve.
2. Optionally preview the build locally:
   ```bash
   pnpm preview
   ```

See `docs/frontend/architecture.md` for more details on the frontend stack.

## Bundle Analysis

To analyze your bundle size and optimize performance:

### Install Bundle Analyzer

```bash
pnpm add -D rollup-plugin-visualizer
```

### Add to vite.config.ts

```typescript
import { visualizer } from 'rollup-plugin-visualizer';

export default defineConfig({
  plugins: [
    react(),
    visualizer({
      filename: 'dist/stats.html',
      open: true,
      gzipSize: true,
      brotliSize: true,
    }),
  ],
  // ... rest of config
});
```

### Run Analysis

```bash
pnpm build
```

This will:

1. Build your app
2. Generate `dist/stats.html` with interactive bundle visualization
3. Automatically open the report in your browser

### Reading the Report

- **Large chunks**: Look for unexpectedly large dependencies
- **Duplicates**: Check if libraries are imported multiple times
- **Unused code**: Identify modules that might not be needed
- **Tree shaking**: Verify that unused exports are eliminated

### Common Optimizations

- Split vendor chunks: Separate React/libraries from your code
- Lazy load routes: Use `React.lazy()` for page components
- Import specific functions: Use `import { specific } from 'library'`
- Remove unused dependencies: Check package.json for unused packages

Example bundle optimization in vite.config.ts:

```typescript
build: {
  rollupOptions: {
    output: {
      manualChunks: {
        vendor: ['react', 'react-dom'],
        router: ['react-router-dom'],
        query: ['@tanstack/react-query'],
        redux: ['@reduxjs/toolkit', 'react-redux'],
      },
    },
  },
},
```

## Error Boundaries

We use functional error boundaries via `react-error-boundary`:

```bash
pnpm add react-error-boundary
```

Wrap components that might fail:

```typescript
import { ErrorBoundary } from './components/ErrorBoundary'

<ErrorBoundary>
  <ComponentThatMightFail />
</ErrorBoundary>
```

## Authentication

`AuthProvider` mounts a `useAccountQuery` that fetches `/api/login/` and updates
the Redux `auth` slice. Components access the current account through a
`useAccount` hook, and mutations such as `useLogin` and `useLogout` update the
slice automatically after completing. The API layer reads the `csrftoken`
cookie and sends it with login and logout requests.
