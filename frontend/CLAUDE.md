# Frontend Development Guidelines

This file provides guidance for Claude Code when working with the React frontend.

**This is the game.** The frontend is not a companion to a text-based MUD - it is the primary and intended way players experience Arx II. Every feature should be designed as a first-class web experience: interactive UI components, visual feedback, rich layouts. Think modern web RPG, not terminal emulator with a coat of paint.

## React Frontend Architecture

Modern React application with TypeScript, Vite, and Tailwind CSS powering the Arx II game experience.

### Core Stack

- **React 18** with functional components and hooks
- **TypeScript** for type safety
- **Vite** for development and builds
- **Redux Toolkit** for global state
- **React Query** for server state
- **Tailwind CSS** + **Radix UI** for styling

### Key Patterns

- **Functional components only** with TypeScript interfaces
- **React Query** for server state, **Redux** for global client state only
- **Custom hooks** for WebSocket management and game logic
- **Error boundaries** for graceful error handling

### Build & Code Splitting

- **Never use file path patterns in `manualChunks` for app code** — only split `node_modules` into vendor chunks. App code splitting creates circular chunk dependencies that work in Vite dev mode but crash in production (`Cannot access 'x' before initialization`). For feature-based splitting, use `React.lazy(() => import('./SomePage'))` at the route level instead
- **After any Vite config change, test the production build end-to-end** — run `pnpm build`, then verify the app loads on the Django/TwistedWeb server (port 4001). Vite dev mode (port 3000) resolves ESM imports differently and will not catch circular chunk dependencies or static file serving issues
- **`pnpm build` succeeding does not mean the app works** — the build only checks that code compiles. Module evaluation order, CORS on static files, and asset path rewriting are only testable against the production server

### Development

```bash
pnpm dev          # Start development server with Django API proxy
pnpm build        # Build production assets to src/web/static/dist/
pnpm test         # Run Vitest unit tests
pnpm test:e2e     # Run Playwright smoke tests against the production build
```

### E2E Smoke Tests

Playwright tests in `e2e/` verify the production build actually loads and works. They run against Vite's preview server (serves the same built bundle as Django). Run `pnpm build` first, then `pnpm test:e2e`. These catch issues that only appear in production builds — circular chunk dependencies, broken module loading, asset serving failures. Run these after any Vite config change or dependency update.
