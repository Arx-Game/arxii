# Frontend Development Guidelines

This file provides guidance for Claude Code when working with the React frontend.

## Code Standards

### Component Rules

- **Functional components only** - No class-based components allowed
- **Exception**: Error Boundaries must use `react-error-boundary` library for functional approach
- **TypeScript required** - All components must be properly typed
- **Props interfaces** - Define clear interface for all component props

### Import Rules

- **Relative imports preferred** - Use `../` instead of path aliases like `@/`
- **Explicit imports** - Avoid barrel exports, import specific functions/components
- **Group imports** - React imports first, then libraries, then local imports

### Error Handling

- **Error boundaries** - Wrap route components with `<ErrorBoundary>`
- **Loading states** - All async operations must show loading state
- **Error states** - All API calls must handle and display errors gracefully

### State Management

- **React Query** - For server state (API data)
- **Redux Toolkit** - For global client state only
- **Local state** - Use `useState` for component-specific state

## Architecture

### Directory Structure

```
src/
├── components/          # Reusable UI components
├── evennia_replacements/# Evennia-specific pages and logic
├── hooks/              # Custom React hooks
├── pages/              # Route-level page components
├── store/              # Redux store and slices
└── types/              # TypeScript type definitions
```

### Component Patterns

- **Single responsibility** - One component, one purpose
- **Composition over inheritance** - Use props and children
- **Custom hooks** - Extract logic from components into hooks
- **Error boundaries** - Wrap components that might fail

## Performance

### Bundle Optimization

- **Code splitting** - Use React.lazy() for route-level components
- **Tree shaking** - Import only what you need from libraries
- **Bundle analysis** - Use rollup-plugin-visualizer to check bundle size

### React Query Best Practices

- **Stale time** - Set appropriate cache duration
- **Error retry** - Limit retries for 404s, allow for network errors
- **Devtools** - Keep React Query devtools in development
