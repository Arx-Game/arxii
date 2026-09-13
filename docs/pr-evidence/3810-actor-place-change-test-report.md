# #3810 test-coverage gap: actor's-own-place-change trigger

## What was added

A demo-fidelity review found that `tagReachability.ts`'s `tt`-mode check
(`character.place_id !== venue.currentPlaceId`) was only exercised by tests
where the TARGET's `place_id` changes across a rerender, never by the
symmetric case where the ACTOR's own `currentPlaceId` changes instead.

Added one new test to the existing `describe('tag reachability (#3810)', ...)`
block in `frontend/src/game/components/CommandInput.test.tsx`:

> `recomputes live when the actor moves to a different place, with the target
> and composerMode unchanged`

It mounts `CommandInput` in `tt` mode with Vayne at place 5 and the actor also
at place 5 (no banner, Send enabled), then rerenders with only `currentPlaceId`
changed to 9 (Vayne's own `place_id` and `composerMode` untouched) and asserts
the `tag-refusal` banner now appears and Send disables. This mirrors the
pre-existing "fresh room_state push moves an already-tagged target to a
different place" test but inverts which side of the equality check moves,
proving both sides of `character.place_id !== venue.currentPlaceId` recompute
live identically.

No other test in the file was touched.

## Test command and output

```
pnpm exec vitest run src/game/components/CommandInput.test.tsx
```

```
Test Files  1 passed (1)
     Tests  84 passed (84)
```

(84 = 83 pre-existing + 1 new; all passed, including the 5 pre-existing tests
in the `tag reachability (#3810)` describe block.)

Also ran:

- `pnpm typecheck` (`tsc -b --noEmit`) — clean, no errors.
- `pnpm exec eslint src/game/components/CommandInput.test.tsx` — clean, no
  warnings or errors.

## Files changed

- `frontend/src/game/components/CommandInput.test.tsx` (+24 lines, one new
  test only)

## Commit

`7e3d3adf7` "Test the symmetric actor-place-change trigger for tag
reachability (#3810)"

## Note

`docs/pr-evidence/3810-demo-fidelity-report.md` shows as modified in the
working tree but was not touched by this task; it appears to be in-flight
work from a separate concurrent session in the shared worktree and was
deliberately left out of this commit.
