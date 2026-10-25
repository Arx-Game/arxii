# Review evidence: #4641 battle map in the sidebar

- Reviewed revision: 7295120d49f523c66b8d17f1fbddd04b451cfac1
- Reviewer: Claude Opus 5.5 (implementing agent; vision read of each screenshot)
- Reviewer verdict: PASS
- Application/build identity: `pnpm build` production bundle of the reviewed revision, served by `vite preview` on port 4173
- Environment: devcontainer, Playwright Chromium headless with touch emulation (`hasTouch: true`, so `pointer: coarse` matches)
- Viewports/themes: 1280x720 for the four spec tests; 1280x1200 for the screenshots; light theme
- Approved design: none; the issue carries no demo. The expected behaviour is the issue's own Expected section
- Visual review: completed against the issue's Expected section, before and after builds side by side
- Visual verdict: PASS
- Screenshots: ![before, sidebar map](.github/issue-evidence/4641/before-sidebar-map-closeup.png) ![after, sidebar map](.github/issue-evidence/4641/after-sidebar-map-closeup.png) ![before, full page](.github/issue-evidence/4641/before-sidebar-map.png) ![after, full page](.github/issue-evidence/4641/after-sidebar-map.png)
- Comparison notes: before, the map opens at scale 0.5 and Ditch and Orchard are cut off at the sidebar's left and right edges; after, all ten positions sit inside the map at about 0.37 scale. Position labels are small at that scale; the zoom-in button, now clickable, enlarges them
- Tested interactions: open the Combat sidebar mode and its Map tab; plain mouse click on zoom in and on fit view; mouse drag on the sidebar's resize edge; read the touch grip's computed size and position
- Fixture/live boundary: REST and WebSocket are mocked (`frontend/e2e/support/gameHarness.ts` plus an encounter with ten positions in two rings); the React app, React Flow and the CSS are the real production bundle
- Overall outcome: PASS

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| controls-clickable | PASS | `frontend/e2e/battle-map-sidebar.spec.ts` "the zoom and fit buttons take a real mouse click" passes on the fix; on the old build it times out with "the button with data-testid sidebar-resize intercepts pointer events" (the live run's error). At the zoom button's centre `elementFromPoint` returns `react-flow__controls-zoomin` after, `play-sidebar-resize ... w-11` before | n/a |
| map-fits-on-open | PASS | "the map opens with the whole room inside the visible sidebar" passes on the fix; on the old build a position's right edge is at x=1328, past the sidebar's right edge at 1280. Viewport transform before: `scale(0.5)` (React Flow's default minZoom) | n/a |
| sidebar-still-resizes | PASS | "the sidebar still resizes from its edge" passes on both builds: a 60px mouse drag on the 12px handle widens the pane by more than 40px | n/a |
| touch-target-kept | PASS | "a touch screen gets a 44px grip at the middle of the edge only" passes on the fix: the grip's `::before` is 44x44 at `left: 0`, and the map's controls start more than 22px below its centre | n/a |
| unit-and-static | PASS | `vitest run` GameLayout, CombatTacticalMap and `src/areas`: 37 passed; `pnpm typecheck` and eslint clean; pre-commit hooks passed on the commit | n/a |

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Map on open | every position of the room inside the sidebar | MATCH | after-sidebar-map-closeup.png shows all ten; before shows eight |
| Zoom and fit buttons | not covered by the resize handle | MATCH | elementFromPoint result above; spec test passes |
| Resize handle | still present on the pane's edge, thin strip | MATCH | `w-3` class in the built bundle; drag test passes |

## Unresolved findings

None
