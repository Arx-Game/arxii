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
mutations likewise update the slice automatically and attach the CSRF token from
cookies so session authentication works without extra boilerplate.

Both mutations also write through to the React Query `['account']` entry, which
is what the route guards (`ProtectedRoute`, `StaffRoute`, `GMRoute`,
`GuestOnlyRoute`) read via `useAuthStatus`. `useLogout` navigates to `/` itself
after clearing the cache and writing `null` into `['account']` (#3592). Nothing
else would leave the current page: most routes (`/characters/create`, the
roster, character sheets) have no guard at all, a mounted guard never re-renders
on a cache clear, and a guard's own redirect goes to `/login`, which is the wrong
destination for a deliberate logout. Logging out from any page lands on the
logged-out home view.


## Same-connection room-state recovery (#3824)

Room recovery stays on the existing authenticated websocket. The client sends
`request_room_state` with a canonical UUID; the server resolves the current
puppet and location, serializes the same viewer-relative `room_state` used by
ordinary pushes, and sends it only to the requesting Session. A
`state_resync` acknowledgement follows the snapshot. `state_epoch` plus
per-character `state_sequence` lets Redux reject lower or equal stale frames.

The browser keeps recovery records by character, socket generation, and UUID.
It coalesces clicks, times out after six seconds, and reports a missing
acknowledgement after an accepted snapshot as partial success. Socket close
cannot settle a newer generation. Recovery does not reload, reconnect, emit
prose, clear feeds/drafts/interactions, or broadcast to another session.

Acknowledgement metadata drives exact viewer-scoped React Query invalidation:
`['scene-interactions', sceneId, characterName]` and, for an active scene,
`['scene-places', roomId, characterName]`. `/game` PlaceBar is controlled by
Redux `viewer_place_id`; the legacy SceneDetailPage keeps its historical key.
