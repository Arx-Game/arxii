# Character Sheets Plan

The roster and character sheet system will let players browse available characters, review public information, apply for characters they can play, and view their own sheets. This plan outlines the initial implementation for a modern SPA.

## Goals

- List characters grouped by roster with search and filtering.
- Display an individual character sheet with public data such as biography, hooks, and images.
- Allow logged-in players to view private fields on their own characters.
- Provide an application workflow for characters on the Available roster.
- Let players view and manage their pending character applications.
- Link character names in chat and other UI to their sheets.

## Backend requirements

- `GET /api/roster/` returns active rosters and each character's public summary, portrait URL, roster type, and availability status. Endpoint supports pagination and django-filter query parameters for searching or filtering by availability, gender, class, and other fields that may be stubbed until full data exists.
- `GET /api/roster/<id>/` returns a full character sheet. Response includes secret sections only if the viewer controls the character or has staff permission.
- `POST /api/roster/<id>/apply/` submits an application to play a roster character.
- `GET /api/roster/mine/` lists the viewer's characters, providing ids and names so the frontend can link to sheets.
- `GET /api/accounts/me/applications/` lists the viewer's unprocessed applications. `PUT` or `PATCH` updates an application, and `DELETE` removes it as long as it has not yet been processed.
- API responses expose Cloudinary image data for portraits and gallery images.

## Frontend approach

- React Router routes:
  - `/roster` for the roster listing page.
  - `/characters/:id` for individual sheets.
- React Query handles data fetching and caching. Redux stores minimal derived state such as the active character.
- Roster list page shows cards with portrait, name, roster label, and an **Apply** button when available.
- Character sheet page displays portrait, summary, hooks, and other sections returned by the API. When the viewer owns the character, private fields render in an "Owner" tab.
- From the game client, clicking a character name opens the sheet in a side panel using the same route.
- Profile page lists pending applications with options to edit or delete.
- Profile dropdown lists the viewer's characters for quick access.

## Prototyping steps

1. Implement stubbed DRF viewsets for roster and character detail endpoints.
2. Create basic React pages with mock API hooks using React Query.
3. Wire character links from chat messages to open the sheet route.
4. Add application form that posts to `/apply/` and displays serializer errors.
5. Prototype endpoints and UI for viewing, editing, and deleting pending applications.
6. Expand API responses and UI iteratively as new data becomes available.

This document will evolve alongside the prototype implementation.
