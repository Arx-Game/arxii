# Frontend Development Guidelines

This file provides guidance for Claude Code when working with the React frontend.

## React Frontend Architecture

Modern React application with TypeScript, Vite, and Tailwind CSS serving as the web interface for Arx II.

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

### Development

```bash
pnpm dev      # Start development server with Django API proxy
pnpm build    # Build production assets to src/web/static/dist/
pnpm test     # Run Vitest tests
```
