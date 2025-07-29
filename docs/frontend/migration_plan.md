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
- Planning to implement login and home pages next using DRF endpoints.

## Migrating the default pages

To duplicate Evennia's starting templates we will:

1. Copy `evennia/web/templates/website/index.html` and `login.html` into React components.
2. Serve `dist/index.html` from a new Django view so `/` loads the React app.
3. Build a `/login` route with a form that posts to a DRF endpoint for authentication.
4. Create DRF serializers and views for login and for fetching the current user's info to populate the home page.
5. Ensure links from the old templates still work by keeping the same URLs and redirecting them to the React routes.
