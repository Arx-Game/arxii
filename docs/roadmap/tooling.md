# Tooling

**Status:** in-progress
**Depends on:** Areas, Items, Combat, Stories (for GM tools)

## Built (2026-07-17, epic #2436 slice 1 / #2448 — grid foundation + export/import)

Staff world-building has a durable content pipeline now, ahead of any authoring UI:
`Area`/`RoomProfile` carry a permanent `slug`/`fixture_key` identity plus a
`GridOrigin` (AUTHORED/STORY/PLAYER) marking who built each row, and
`core_management.grid_export`/`grid_import` round-trip authored areas (with their
rooms, exits, and authored sidecar values) to the private lore repo as reviewable
per-area JSON bundles — see `docs/roadmap/rooms-and-estates.md`'s matching "Built"
entry and ADR-0140 for the format and rejected alternatives. No staff-facing canvas
exists yet (Django admin + `@dig`/`@open`/`@link` remain the only way to author grid
content); that's slice 2. The epic's remaining slices are filed as separate
sub-issues, not designed here: **#2449** (staff world-builder canvas — the drag/drop
authoring surface this document's "GM dashboard UI" / "Staff world management" items
below actually need), **#2450** (GM story areas — `STORY`-origin, never exported),
**#2451** (discovery/portal authoring — clue placement + portal anchors from the
canvas), **#2452** (player building via projects, `needs-design`).

## Built (2026-07-17, epic #2436 slice 2 / #2449 — staff world-builder canvas)

Slice 1's grid foundation now has an authoring surface: a staff-only drag-and-drop
canvas at `/staff/world-builder` (linked from the profile dropdown + Game Setup hub)
backed by eleven `world_builder`-category REGISTRY actions
(`create_area`/`edit_area`/`staff_dig_room`/`staff_edit_room`/`staff_link_rooms`/
`staff_unlink_rooms`/`staff_rename_exit`/`staff_place_room`/`staff_remove_room`/
`promote_room`/`promote_area`, `src/actions/definitions/world_builder.py`) and a
read-only `WorldBuilderViewSet` (`/api/world-builder/areas/`, `IsAdminUser`-gated).
Authority is the staff account flag alone — deliberately not a GM-ladder trust tier
(see ADR-0139); GM-level world-shaping (this document's "GM tools" section below)
stays a separate, still-unbuilt question. Backend substrate
(`world.areas.grid_services`) and frontend canvas primitives (`map-canvas/`) were
both extracted from the pre-existing building Room Builder (#670) so all three
canvas consumers (buildings, battles, this one) share one implementation — see
`docs/systems/INDEX.md`'s "Areas" section for the full surface and
`src/world/areas/tests/test_world_builder_journey.py` for the create-area →
dig → link → place → promote → export journey proving the canvas actually feeds
slice 1's `export_grid_bundles()` pipeline. Not built this slice: an `edit_area`
UI (the action exists; no canvas panel calls it yet), GM story areas
(#2450, see "Built" below), clue/portal layers (#2451) — the latter remains
filed as its own sub-issue.

## Built (2026-07-18, epic #2436 slice 3 / #2450 — GM story areas & story rooms)

The first GM-trust-gated (not staff-flag-gated) consumer of slice 1/2's grid
substrate: a GM can author their own private `STORY`-origin area, dig/link/place/
remove rooms in it (mirroring the staff canvas's verb set, scoped to areas they
own via `StoryArea`), and grant specific characters consent-first access to join
(`StoryRoomGrant` — gates the join only; walking inside rides ordinary exits, see
ADR-0141) — or spin up a disposable temp scene room (`InstancedRoom.gm_owner`) for
a one-off beat and close it out afterward, returning every joined character. Caps
are per-`GMLevel` (`GMLevelCap.max_story_areas`/`max_story_rooms_per_area`,
staff-tunable). 13 GM-authored REGISTRY actions
(`category="story_builder"`, `src/actions/definitions/story_builder.py`) plus 2
player-side join/leave actions (`category="story_rooms"`, no GM standing
required); telnet play verbs only (`sceneroom`/`joinroom`/`leaveroom`,
`src/commands/story_rooms.py`) — canvas authoring stays web-only (epic Decision
2), landing on the `/gm/story-builder` frontend page and the read-only
`StoryBuilderViewSet` (`/api/gm/story-areas/`, `IsGMOrStaff`). Story areas/rooms
are excluded from the player-facing `AreaViewSet`/`RoomProfileViewSet` and never
publicly listed regardless of a room's own `is_public` flag — see
`docs/systems/INDEX.md`'s GM section ("Story areas & story rooms") for the full
model/service/action/API rundown. Remaining: clue/portal layers (#2451), player
building via projects (#2452, `needs-design`).

## Overview
Tools for players, GMs, and staff to interact with and manage the game world. Player tools focus on building and customizing spaces. GM tools are granular and level-gated — GMs can only do what their trust level allows. Staff tools are unrestricted for the one staffer coordinating the entire game.

## Key Design Points
- **Player building tools:** Room creation, decoration, furnishing. Economic cost of construction (buying and building rooms IC). Decorations give room statistics and bonuses. Everything from a cozy apartment to a massive fortress with research labs
- **GM tools (level-gated):** NPC creation within limits, combat management for encounters they run, reward distribution within a scaled range based on GM level. Newbie GMs get basic tools; veteran GMs get powerful world-shaping abilities
- **Staff tools:** Unrestricted "do anything" capability. The general-purpose commands that only the coordinating staffer needs. Creating areas, setting world state, managing GM promotions, overriding any system
- **Room building:** Both the mechanical creation of rooms (exits, descriptions, properties) and the player-facing economic version (purchasing land, commissioning construction, decorating)
- **NPC management:** GMs creating, placing, and controlling NPCs for their stories and adventures
- **Reward tools:** GMs granting XP, items, codex entries, legend — all within their level-appropriate caps
- **World state tools:** Staff-level tools for managing the living grid, triggering world events, updating canon time

## What Exists
- **Commands:** Room building commands (door creation, exit commands, room descriptors), movement commands, perception commands, character switching/sheet commands
- **Staff frontend:** Staff application detail page, extensive Django admin configuration
- **Areas system:** Room creation infrastructure exists through the areas app;
  authored/runtime identity + grid export/import round-trip now exists (#2436/#2448,
  see "Built" above), and a staff-only drag-and-drop authoring canvas now sits on
  top of it (#2449, see "Built" above); a GM-trust-gated variant of that same
  canvas (story areas + story rooms, #2450) now sits alongside it, see "Built" above
- **GM dashboard** — see `docs/roadmap/gm-system.md` for GM-specific tooling
  (level-gated commands, story areas/rooms, the scenario catalog); this document's
  "GM tools" section below describes the still-open NPC/combat/reward tooling gap

## What's Needed for MVP
- GM command framework — level-gated command permissions scaling with GM trust
- GM NPC tools — creating, placing, customizing, and controlling NPCs within level limits
- GM combat tools — initiating encounters, managing combat flow, controlling enemy actions
- GM reward tools — granting XP, items, codex, legend within scaled caps
- Player room purchase flow — economic room acquisition with IC construction
- Decoration system — furnishing rooms with items that provide stats and bonuses
- Room stat calculation — how decorations and upgrades translate to room properties
- ~~Staff world management — tools for the coordinating staffer to manage world state~~
  built (#2449, staff world-builder canvas — see "Built" above)
- GM dashboard UI — web interface for GMs to manage their tables, NPCs, and active sessions
- Player building UI — web interface for room customization and decoration (#2452, needs-design)
- Builder documentation — in-game help for room creation and management

## Testing Infrastructure

### What Exists
- **Backend unit tests** — Django TestCase + DRF APITestCase per app, run via `arx test`
- **Frontend unit tests** — Vitest with React Testing Library, run via `pnpm test`
- **Production build smoke tests** — Playwright e2e tests that verify the built frontend loads,
  key routes render, no JS exceptions, and all chunks load. Run via `pnpm test:e2e`
- **Manual integration tests** — `arx integration-test` scaffolding for email verification flow
  (starts servers, creates test accounts, but human does the clicking)
- **Pre-commit hooks** — ruff, prettier, typecheck, custom linters

### What's Needed
- **Automated integration tests** — Replace the manual `arx integration-test` flow with Playwright
  tests that run the full stack (Django + frontend), log in, and exercise key user flows:
  - Registration and email verification
  - Character creation
  - Scene participation and interaction
  - Event creation and lifecycle
  - Codex browsing
- **CI pipeline** — Run backend tests, frontend tests, and e2e smoke tests on every PR.
  Integration tests can run on a schedule (nightly) since they need the full stack

### Coverage by System
| System | Backend Tests | Frontend Tests | E2E Smoke | Integration |
|--------|:---:|:---:|:---:|:---:|
| Events | yes | - | yes (route renders) | no |
| Scenes | yes | - | - | no |
| Roster/Characters | yes | - | - | no |
| Auth/Registration | yes | - | yes (login renders) | manual |
| Codex | yes | - | - | no |
| Stories | yes | - | - | no |

## Notes
