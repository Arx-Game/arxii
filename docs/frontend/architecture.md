# Frontend Architecture

Arx II is migrating from server-rendered templates to a modern React application. The frontend uses Vite for bundling, React Router for routing, React Query for API access, Redux Toolkit for state management and the shadcn/ui component library styled with Tailwind CSS. All code is written in TypeScript.

## Local development

Nginx is not required when developing locally. Run the Vite dev server to serve the application and proxy API requests to Django running at `http://localhost:8000`:

```bash
pnpm dev
```

## Build process

Production builds output static files to `src/web/static/dist/` so Django or nginx can serve them:

```bash
pnpm build
```

## Setup with mise

The `mise.toml` file manages our binary dependencies. Node and pnpm versions are defined so everyone uses the same tooling. After cloning the repository, install the tools with:

```bash
mise install
```

## Authentication flow

The application loads the current account on startup. `AuthProvider` mounts a
`useAccountQuery` that calls `/api/login/` with cookies included and dispatches
the result to the Redux `auth` slice. Components read this state through a
`useAccount` hook so they never handle store updates directly. The header uses
this hook to display a **Log in** link for anonymous visitors or a dropdown with
profile and logout actions for authenticated users. `useLogin` and `useLogout`
mutations likewise update the slice automatically.
