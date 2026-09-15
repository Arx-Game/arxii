# #3810 tag-reachability: live-rerender test coverage addition

## Why

The demo-fidelity review that gated this branch's PR found that all three existing
tests in `describe('tag reachability (#3810)', ...)` (in
`frontend/src/game/components/CommandInput.test.tsx`) mounted `CommandInput` already
in the refused or reachable state via props. None of them proved the feature's
actual headline claim: that `tagRefusal`'s `useMemo` recomputes LIVE when its
dependencies change after mount, without an unmount/remount cycle.

## What was added

Two new tests in the same `describe('tag reachability (#3810)', ...)` block in
`frontend/src/game/components/CommandInput.test.tsx`, both using this file's
existing harness (`rtlRender`'s `rerender`, and the module-level mutable
`mockRoomCharacters` array that the mocked `@/store/hooks` `useAppSelector`
reads fresh on every render):

1. **`recomputes live on a mode switch that carries a stale target across, without
   unmounting`** -- mounts with `composerMode = { command: 'whisper', targets:
   ['Vayne'] }` (Vayne in the room but at a different place: `place_id: null` vs.
   `currentPlaceId={5}`), asserts no `tag-refusal` banner and Send enabled, then
   calls `rerender()` with `composerMode` switched to `{ command: 'tt', targets:
   ['Vayne'] }` (same targets, same place mismatch, same `isAtPlace`/
   `currentPlaceId` props) and asserts the banner now appears and Send is
   disabled -- all on the same component instance.

2. **`recomputes live when a fresh room_state push moves an already-tagged target
   to a different place, with composerMode unchanged`** -- mounts already in `tt`
   mode with Vayne's `place_id` matching `currentPlaceId` (no banner, Send
   enabled), then reassigns `mockRoomCharacters` to move Vayne to a different
   place (simulating a fresh `room_state` WebSocket push) and calls `rerender()`
   with the exact same props (no `composerMode` change) to force React to
   re-invoke the component and re-read the mocked selector, then asserts the
   banner now appears and Send is disabled.

Both tests mutate `mockRoomCharacters`/`composerMode` after the initial render and
rely on RTL's `rerender()` (not a fresh `render()`/unmount) to prove the recompute
fires live, per the existing harness convention already used elsewhere in this file
(e.g. the `#3760 Task 12` reconnect-mid-send tests use the same `rerender()`
pattern for a live prop-driven state transition).

## Commands run

```
pnpm exec vitest run src/game/components/CommandInput.test.tsx
```
Result: 83 passed (81 pre-existing + 2 new), 0 failed.

```
pnpm typecheck
```
Result: clean (`tsc -b --noEmit`, no output).

```
pnpm exec eslint src/game/components/CommandInput.test.tsx
```
Result: clean, no output.

## Files changed

- `frontend/src/game/components/CommandInput.test.tsx` -- two new tests added to
  `describe('tag reachability (#3810)', ...)`. No other files touched.
