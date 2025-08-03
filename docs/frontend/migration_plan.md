# Frontend Migration Plan

These notes outline the process for replacing Evennia's server-rendered pages with a modern React application. The project uses Vite, TypeScript, and Tailwind CSS.

## Goals

- Duplicate the Evennia login and home pages as proof of concept.
- Expose functionality through the Django REST Framework API.
- Fetch data with React Query and manage shared state via Redux Toolkit.
- Style components using shadcn/ui and Tailwind CSS.
- Gradually migrate other pages and the webclient after the proof of concept.

## Progress

- Initial React scaffolding committed with routing and a Redux store.
- Build output configured to `src/web/static/dist/` for Django to serve.
- Architecture documentation added under `docs/frontend/`.
- Home and login pages implemented using React.
- Backend API endpoints `/api/homepage/` and `/api/login/` now provide the needed context.
- AuthProvider now fetches the current account and header displays login state with profile and logout options.
- `/api/login/` responses contain only account data and React Query hooks update the auth slice automatically.

## Migrating the default pages

To duplicate Evennia's starting templates we will:

1. Copy `evennia/web/templates/website/index.html` and `login.html` into React components.
2. Serve `dist/index.html` from a new Django view so `/` loads the React app.
3. Build a `/login` route with a form that posts to a DRF endpoint for authentication.
4. Create DRF serializers and views for login and for fetching the current user's info to populate the home page.
5. Ensure links from the old templates still work by keeping the same URLs and redirecting them to the React routes.
- React pages moved under `src/evennia_replacements` with typed API helpers.
- Django now serves the compiled React app for all non-admin routes.
- Added serializer returning account and player info used after login.
