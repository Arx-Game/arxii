# Review evidence

- Reviewed revision: `8ca2627a21a08f029aa5df107ca81480ca347ace`
- Reviewer: implementing agent (Claude Code), comparing the rendered Atlas against the issue's stated outcome and the rooms-mode precedent (#3729) it mirrors
- Reviewer verdict: PASS
- Application/build identity: production bundle from `vite build` at the reviewed revision, served by `vite preview` on port 4173
- Environment: Linux devcontainer, Playwright 1.58.2 Chromium headless; the builder REST surface and the action dispatch are fixtures (no Django behind the preview build)
- Viewports/themes: 1280x1000, the Atlas's light theme (the page has one)
- Approved design: issue #4084 (lightweight lane, no demo page); the change mirrors the rooms-mode place-by-name path from #3729 and adds no element the map did not already have for rooms
- Visual review: Completed
- Visual verdict: PASS
- Screenshots: ![Before: ledger lists the unplaced neighborhood, map shows one tile](docs/reviews/4084/atlas-before-1280.png) ![The place dialog on a planned square](docs/reviews/4084/atlas-dialog-1280.png) ![After: the tile is on the square](docs/reviews/4084/atlas-after-1280.png)
- Comparison notes: compared the areas-mode dialog with the rooms-mode one it mirrors: a typed prefix shows a "place X here" suggestion, an exact match shows the note and turns the button to Place, the level fork and the door rows disappear because the area already has a level, and the field is labelled by the matched area's level ("Neighborhood name", the first capture had it as "Ward name", fixed in the reviewed revision). After Place the dispatch is `edit_area {area_id, grid_x: 1, grid_y: 0}`, the same call the map's drag makes, and the tile appears on the square east of the placed market.
- Tested interactions: open `/staff/world-builder` as staff, land on the root barony, read the ledger, plan a square (two clicks), type a prefix, click the suggestion, read the note, press Place, see the tile and the toast. No page errors were raised.
- Fixture/live boundary: the page, router, hooks, lattice, dialog and bundle are real. Every `/api/**` response is a fixture: one root barony with two neighborhoods shaped like the production placeholders, one placed and one not; the dispatch fixture records the call and writes the square onto the children fixture, so the invalidated children query returns the position the way the live server would.
- Overall outcome: PASS

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Ledger row for the unplaced area | listed with its level, no tile on the map | MATCH | docs/reviews/4084/atlas-before-1280.png |
| Suggestion under the name field | "place Dockside Warrens (neighborhood) here" | MATCH | docs/reviews/4084/atlas-dialog-1280.png |
| Note on an exact match | says the area exists without a place and Add puts it on this square | MATCH | docs/reviews/4084/atlas-dialog-1280.png |
| Level fork ("This square is") | hidden while placing | MATCH | docs/reviews/4084/atlas-dialog-1280.png |
| Field label | the matched area's level | MATCH | docs/reviews/4084/atlas-dialog-1280.png |
| Submit button | "Place" | MATCH | docs/reviews/4084/atlas-dialog-1280.png |
| Tile after Place | on the planned square, beside the placed neighborhood | MATCH | docs/reviews/4084/atlas-after-1280.png |
| Toast | the dispatch's message | MATCH | docs/reviews/4084/atlas-after-1280.png |

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| A01-place-by-name | PASS | `frontend/e2e/evidence/atlas-place-area-4084.spec.ts` asserts the dispatch and the tile; `Lattice.test.tsx` "areas mode: naming an unplaced child area places it via edit_area" | |
| A02-no-duplicate-created | PASS | the same tests assert `create_area` is never dispatched; `AddDialog.test.tsx` "a name that only resembles an unplaced area still creates a new one" covers the other side | |
| A03-no-level-fork-or-door-when-placing | PASS | `AddDialog.test.tsx` "names a child area with no position to place it"; docs/reviews/4084/atlas-dialog-1280.png | |
| A04-levels-half | PASS | shipped in #4087 (`AREA_LEVELS` regenerated and pinned to the schema by `areaLevels.test.ts`) | |

## Unresolved findings

- None
