# Frontend Testing

The frontend uses [Vitest](https://vitest.dev/) with [React Testing Library](https://testing-library.com/docs/react-testing-library/intro/) for unit tests.

## Running tests

```bash
pnpm test
```

This runs all Vitest unit tests under `frontend/src`.

## Mocks

Reusable mock data lives in `frontend/src/test/mocks`. Update or extend these files when adding tests that need mocked backend data or store state.

## Utilities

Shared testing helpers are in `frontend/src/test/utils`. Use `renderWithProviders` to render components with the Redux store, React Query client, and React Router.
