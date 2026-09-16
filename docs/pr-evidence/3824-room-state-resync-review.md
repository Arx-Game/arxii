# #3824 same-connection room-state resync review

**Reviewed revision:** approved issue specification posted 2026-09-16, plus implementation branch `feature/3824-room-state-resync` (implementation commit recorded below).
**Review mode:** local fixture and automated tests. No reload or reconnect is used by the recovery path.

## Scenario-to-criterion matrix

| Scenario | Acceptance criterion | Evidence |
| --- | --- | --- |
| Refresh from open socket | Exact `request_room_state` tuple; same connection | `frontend/src/hooks/useGameSocket.ts`; focused Vitest socket seam |
| Snapshot and ACK | Viewer-scoped full state, revision metadata, requester-only ACK | `src/server/conf/inputfuncs.py`, `src/typeclasses/characters.py`, inputfunc test |
| Stale callback | Lower/equal revisions and old generations are ignored | `frontend/src/store/gameSlice.ts`, socket generation guards |
| Draft/feed/focus preservation | Recovery only replaces room/scene slices | `handleRoomStatePayload.ts` and Redux slice |
| Place repair | `/game` PlaceBar is controlled by `viewer_place_id` | `frontend/src/scenes/components/PlaceBar.tsx`, GamePage wiring |
| Exact invalidation | Scene and Place keys include room/scene and character | ACK handler and `useSceneInteractions` keys |
| Timeout/partial/failure | Six-second timeout and close-before/after-snapshot statuses | socket pending lifecycle and RoomHeader status |
| Accessible UI | Refresh control and live status strings | `RoomHeader.tsx`; fixture below |
| Visual walkthrough | Room view, refresh, and reconciled status | `3824-room-state-resync-fixture.html` and `3824-room-state-resync.png` (host-visible local fixture and screenshot) |

## Commands

- `just test-fast web` — 736 tests, OK.
- `cd frontend && pnpm typecheck` — OK.
- Focused Vitest: `handleRoomStatePayload`, `useGameSocket`, `gameSlice` — 150 tests, OK.
- `uv run ruff check` on changed Python files — OK.

## Fixture

Open `docs/pr-evidence/3824-room-state-resync-fixture.html` from the repository
or serve the repository root with a local static server. It is deliberately
labeled as a local review fixture and does not represent production data.
