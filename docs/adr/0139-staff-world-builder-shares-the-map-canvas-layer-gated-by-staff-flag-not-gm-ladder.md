# Staff world-builder shares the map-canvas layer; authority is the staff flag, not the GM ladder

The staff world-builder canvas (#2449, epic #2436) is the third consumer of a drag-and-drop
room-grid canvas, after the owner-facing building Room Builder (#670) and the battle map
editor. Rather than a third parallel implementation, the frontend's canvas primitives
(`MapCanvasShell`, `useMapNodeInteraction`, `coords`, `edges`, ghost-cell placement via
`ghosts.ts`/`GhostNode.tsx`) were extracted into a shared `map-canvas/` package that all three
now depend on — a caller-supplied tooltip label (`"Dig <direction>"` for buildings vs. `"Dig
room here"` for the world-builder) is the only per-caller variation point. The backend mirrors
this: `world.areas.grid_services` extracts the area-generic room-graph core (room/exit/grid
CRUD, BFS reachability, `promote_to_authored`/`suggest_fixture_key`/
`ensure_slug_change_allowed`) out of `world.buildings.room_services`, so the owner-facing
Room Builder and the new `world_builder` staff actions call the same primitives instead of two
copies drifting apart.

The eleven `world_builder` REGISTRY actions (`src/actions/definitions/world_builder.py`) are
gated by `StaffOnlyPrerequisite` alone — `actor.db_account.is_staff` — with no
ownership/tenancy standing (unlike the owner-gated Room Builder) and, deliberately, no
GM-ladder trust check (unlike e.g. the battle-staging actions' `MinimumGMLevelPrerequisite`).
This is a conscious choice, not an oversight: the canvas edits the *canonical shared world
grid* (AUTHORED areas/rooms, the surface `core_management.grid_export` ships to the lore
repo), which is a different authority question than "is this GM trusted to run scenes." The
GM-trust ladder has no tier today that means "may permanently reshape canonical world
content," and building one prematurely — before GM-authored `STORY` areas (#2450) or
clue/portal layers (#2451) exist to give that tier a real shape — risks conflating two
distinct grants (scene-running trust vs. world-architecture authority) into one flag. The
staff account flag is therefore the whole authority boundary for this slice; the read API
(`WorldBuilderViewSet`, `src/world/areas/builder_views.py`) is staff-only for the same reason.
Rejected alternative: reusing `MinimumGMLevelPrerequisite` (or a new higher tier of it) now —
deferred to #2450, which will need to design what "trusted enough to edit the shared grid"
actually means once GM story-area authoring exists to compare it against, rather than
guessing at a ladder rung with only one consumer.

> Status: accepted · Source: epic #2436, issue #2449 (staff world-builder canvas) · Related:
> ADR-0140 (the grid-export bundle format this canvas's `promote_room`/`promote_area` verbs
> feed) · Follow-ups: #2450 (GM story areas — where the GM-ladder authority question gets
> revisited), #2451 (clue/portal layers), #2452
