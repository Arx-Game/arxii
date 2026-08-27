# Test Utilities

This directory provides helpers for writing frontend tests.

- `renderWithProviders.tsx` wraps components with the Redux store, React Query client, and React Router for rendering.
- `playerActionFixtures.ts` — `makeGMPlaceAction(positionId)` builds a `gm_place_in_position` `PlayerAction` (#3385), shared by `CombatTacticalMap.test.tsx` and `SceneTacticalMap.test.tsx`. Most `PlayerAction` fixtures stay local to their own test file (the established per-file convention here); this one moved here because it was duplicated byte-for-byte across two files exercising the same feature.

Add additional utilities here as needed and update this document when they are introduced or modified.
