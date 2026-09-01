# Tooling

**Status:** in-progress
**Depends on:** Areas, Items, Combat, Stories (for GM tools)

## Built (2026-08-31, #3477 Tasks 3–7 — the Atlas and the documents)

The grid-first canvas front door is replaced by the two-surface builder the
spec ratified (`frontend/src/world-builder/atlas/` + `document/`; `AtlasPage`
is the routed page). **Atlas** (navigation): warrant-scoped index rail with
pins/recents (`IndexRail`, `useAtlasState`), folio ancestry crumb, `AreaPage`
ledger rows + the `Lattice` — one snapped grid at every altitude with
plot-then-realize planning squares, right-click carving/voids, edge growth,
drag-to-swap arranging (`staff_move_room`'s first dispatch), and WIP dimming
from `published_at`. Cross-world search lands on the hit's parent grid with
the room highlighted. **Room Document** (`RoomDocument`): full-width drafted
name/prose (`useDraft`, per-room localStorage), Save/Publish/delete savebar
("Next unpublished" trance loop included), seasonal/day-night `VariantsPanel`
wiring the #3291 backend's first UI, exits band + `ExitEditorDialog`
(`staff_set_exit_detail`), the dig-trinity exit `AddDialog`, a 3×3 `Compass`,
and read-only `Marginalia` panels fed by the payload. **Area Document**
(`AreaDocument`): the same manuscript pattern per Dan's every-altitude ruling —
drafted area prose via `edit_area`, area marginalia, the reused #3269
`EditAreaDialog` as the metadata door, delete via `staff_remove_area` (its
first button). Room/area art resolves most-specific-wins up the ancestor chain
(`resolve_area_art`, Task 3) and ambient lines carry authorable conditions.
Art *authoring* landed in #3535: `art_id` on `staff_edit_room` (the room's
`ObjectDisplayData.thumbnail`) and `edit_area` (`Area.art`) — falsy takes it
down, absent leaves it untouched — with the `ArtDialog` door on both
documents' marginalia (library + upload reuse the roster media machinery).
Marginalia phase 2 (#3534) delivered the doors: Ambience (with the full
condition editor), People, Places & Things, Law & Danger, and Secrets &
Story headers open their systems' editors (the reused #3269 Phase B
sections via `CategoryDoorDialog`); the Resonance panels carry real cascade
readings (`room_resonance_readings`/`area_resonance_readings` +
`dominant_affinity`); builder reads opened to grant holders scoped to their
subtrees (`IsStaffOrGrantHolder` + `_covered_area_ids` + the `grants`
endpoint) and the atlas wears the warrant (grant rooting, ceiling-absent
planning, "3 of 8 rooms" budgets). Not built (later phases per the spec):
the Ownership door (the payload still carries no deed/tenancy fields), the
rest of the appendix gap-list burndown, the visitor lens, player permits.

## Built (2026-08-31, #3477 Task 2 — publish lifecycle)

A canvas-dug (`origin=AUTHORED`) room is now born unpublished:
`RoomProfile.published_at` defaults to `now()` (an ordinary PLAYER room, and
every pre-existing room via the migration backfill, is live immediately) but
`world.areas.grid_services.create_room` sets it to `NULL` for `origin=AUTHORED`.
An unpublished room does not exist in the live world — `ExitState.can_traverse`
refuses entry through any exit leading to one, and
`RoomStatePayloadSerializer` omits such an exit from the room-state payload
entirely — for anyone except a story-runner (GM/Staff, the `is_story_runner`
typeclass attribute); a story-runner can walk in and see the exit to review the
room before it goes live. The new `staff_publish_room` REGISTRY action
(kwarg `room_id`, gated by the same `BuildWarrantPrerequisite` as its siblings)
stamps `published_at=now()`; idempotent (a re-publish just refreshes the
stamp) — no unpublish verb, no separate "done" flag. The staff area-manager
payload (`WorldBuilderRoomSerializer`) gains a `published_at` field so the
canvas can show unpublished rooms distinctly. Not built this task: a canvas
UI affordance for the Publish action itself (a later task in the #3477 arc).

## Built (2026-08-31, #3478 — GM onboarding moves to the Hall; mint banner removed)

The staff-mint form the world-builder actor banner grew below (#3283) is gone.
`POST /api/world-builder/areas/mint-builder-character/` and its frontend caller
(`mintBuilderCharacter`, `frontend/src/world-builder/api.ts`) are deleted; a
role-aware `mint_gm_character` (`world.roster.services.staff_characters`) replaced
it at `POST /api/gm/profiles/character/`, onboarding both staff and approved GMs
(not staff alone) through the Hall's GM slot instead. The world-builder page's
no-actor banner (`WorldBuilderPage`, `data-testid="world-builder-actor-banner"`)
now just points at the Hall ("set up your GM Profile from the Hall" + a Link to
`/`) rather than minting inline. See `docs/roadmap/gm-system.md`'s Phase 9 for the
full rundown.

## Built (2026-08-20, #3283 — field feedback: staff mint, breadcrumbs, room editor page)

First real authoring session on the deployed builder produced three fixes.
**Staff character mint**: `POST /api/world-builder/areas/mint-builder-character/`
(`world.roster.services.staff_characters.mint_staff_character`) creates the
whole working set — character + sheet + PRIMARY persona + NPC-shelf roster
entry + active tenure — in one transaction, skipping the CG wizard entirely;
the world-builder actor banner grew the create form, and actor resolution
falls back to the account's first owned character (dispatch checks ownership,
not puppeting), so the minted character works immediately. Player-GM OOC
characters ride the same service gated on GMProfile later; sheet free-editing
stays on the admin. **Hierarchy at a glance**: the manager payload and
room-detail endpoint carry an `ancestors` breadcrumb chain, rendered on the
canvas header and the room editor. **Full-page room editor**:
`/staff/world-builder/rooms/:id` gives one room the full width (identity +
every authoring section in responsive columns), deep-linkable via the
self-sufficient room-detail payload; the canvas side panel keeps an "Open
full editor" link for quick jumps.

## Built (2026-08-18, #3269 Phases B+C — full room authoring + area metadata)

Rooms are no longer hollow: the staff panel gained sections for ambient stats
(authored zero-decay modifiers by default; pin = the rare cascade-cutting
override, warned loudly), places, atmosphere (entry lines + gated linger
emits with minted keys), feature install/dissolve by fiat (the identical
per-kind strategy handlers, run through an instantly-completed audit
project; VAULT/SANCTUM refused), functionary staffing (web mirror of telnet
`functionary`), travel-hub flags, default tactical blueprints
(`PositionBlueprint` + nodes/edges join `CONTENT_MODELS` with natural keys +
credits), starting-room bindings (the last admin-only step before characters
could enter a new grid), exit kind/openness/alias editing (a WINDOW switch
auto-opens so a kind flip can't sever a live link), cross-area room
duplication, and corridor batch-digs. Grid bundles round-trip every one of
those surfaces (credited ambient emits freeze rather than overwrite, ADR-0201
pattern), so a live-server build is durable content. Phase C: `edit_area`
finally has a UI — realm/climate/dominant-society/description/colour/ward
permits, with effective-climate display and a below-REGION warning — plus
the "Arrange children" canvas: child areas drag-to-place on the same grid,
one level up (the city map of wards). `PlaceViewSet`'s player-reachable POST
was removed (staff authoring only); `AmbientEmit` gained admin parity.

## Built (2026-08-18, #3269 Phase A — grid bootstrap, recoverability, navigation)

The world builder can now bootstrap a first grid and recover from mistakes.
**Relational dig** is the primary flow: a ghost-cell click passes its anchor +
direction to `staff_dig_room`, which derives the cell and auto-creates the
aliased exit pair (the `Direction` spec moved to `world.areas.constants`,
shared with buildings); an empty AUTHORED area offers "Dig first room" at the
origin; a `like` exemplar copies size + description cross-area; blank
descriptions default to the PLACEHOLDER stub and a "Needs prose (N)" list
tracks them. **Recoverability:** deletion gates on `RoomProfile.exported_at`
(stamped by `grid_export`; ADR-0220 — a fixture key alone no longer bricks a
room), `staff_remove_area` removes empty areas, area slugs stay re-sluggable
until a room fixture key bakes them in, and `staff_move_room` re-parents a
mis-dug room. **Navigation:** world canvas gets minZoom 0.05 + MiniMap +
refit-on-room-set-change; the phantom unplaced-room tray is replaced by a
side-panel list with click-to-place mode; a cross-area room search
(`room-search` endpoint + header box) answers "where did I put it". The
rename bug (db_key vs longname split-brain) is fixed in
`set_room_display_data`, `%r`/`%t` normalization now applies to web
description writes, occupant counts exclude exits in SQL, and the
`areas_areaclosure` refresh runs CONCURRENTLY so live readers never block
during bulk authoring. The builder shows an explicit actor banner instead of
silently no-oping when no character is played. Phases B (full room authoring:
stats/places/features/staffing/ambient/exits/travel/bindings) and C (area
metadata) remain — see #3269's spec.

## Built (2026-07-19, epic #2436 slice 4 / #2451 — discovery/portal authoring)

The last of the epic's authoring slices: staff can now place clues and portal
anchors from the world-builder canvas instead of Django admin. `RoomDetailPanel`
gains staff-only "Clues" and "Portal anchors" sections
(`PlaceClueDialog`/`PlacePortalAnchorDialog`); `WorldRoomNode` shows a combined
clue+trigger count badge; `WorldCanvas` renders paired same-kind `PortalAnchor`s as
dashed edges between rooms (`pairPortalAnchors` + `portalEdges` in
`map-canvas/edges.ts` — an unpaired anchor still shows, just with no edge). Six new
`world_builder`-category REGISTRY actions
(`staff_place_clue`/`staff_remove_clue`/`staff_place_clue_trigger`/
`staff_remove_clue_trigger`/`staff_place_portal_anchor`/`staff_remove_portal_anchor`,
`src/actions/definitions/world_builder.py`, `StaffOnlyPrerequisite`-gated, same as
slice 2's verbs) plus one new staff-authoring service,
`install_portal_anchor_as_staff` (`world.magic.services.portal_travel` — no
owner/tenant standing check, no `PORTAL_ANCHOR_INSTALL_COST` debit, still refuses a
duplicate active kind in the same room). `RoomClue`/`ClueTrigger`/`PortalAnchor` all
gain a nullable-unique `fixture_key` (same pattern as `RoomProfile.fixture_key`);
`Clue` gains a `NaturalKeyMixin` `slug` and joins `CONTENT_MODELS` — clues are now
lore-repo content, exported/imported by slug. The grid bundle format gains three
sidecar sections — `clues`/`clue_triggers`/`portal_anchors`, each keyed by
`fixture_key` — upserted by `grid_import.load_grid_bundles()`'s new 5th pass and
report-never-deleted (never hard-deletes a fixture-keyed row absent from a
reimported bundle). Ratified: reimporting an unchanged bundle always converges a
dissolved `PortalAnchor` back to active — see `docs/systems/magic.md`'s "Portal
travel" section for why this is intentional, not a bug. `WorldBuilderRoom`
(`world.areas.serializers`/`builder_views.py`) carries `clues`/`clue_triggers`/
`portal_anchors` arrays per room now, built via bulk queries. Epic #2436 is now
fully built except **#2452** (player building via projects, `needs-design`).

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
canvas), **#2452** (player room-building constraints — resolved: dig_room stays
instant, RoomEditAction widened to owner-or-tenant, player rooms confirmed never
touch the authored grid export).

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
(#2450, see "Built" below), clue/portal layers (#2451, since built — see "Built"
above).

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
model/service/action/API rundown. Clue/portal layers since built (#2451, see
"Built" above). Player room-building constraints resolved (#2452 — dig_room
stays instant; RoomEditAction opened to tenants).

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
  canvas (story areas + story rooms, #2450) now sits alongside it, see "Built" above;
  the staff canvas now also authors discovery/portal content (clue placements,
  clue triggers, portal anchors — #2451), see "Built" above
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
