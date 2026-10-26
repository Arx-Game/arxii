# Review evidence: #4677 frontend CI speed and React warnings

- Reviewed revision: `6e3b5181dd20d3b263be39494b1c025fccb1d470`
- Reviewer: Claude Opus 5.5 (implementing session), with the test-layer-reviewer and mock-fidelity-reviewer agents over the same diff
- Reviewer verdict: PASS
- Application/build identity: `vite build` of this branch at the reviewed revision, served by `vite preview` on :4173 (`frontend/playwright.config.ts`); API answered by Playwright route mocks (`e2e/support/gameHarness.ts` mockRestRoutes plus a world-builder mock)
- Environment: devcontainer, Chromium (Playwright), one worker
- Viewports/themes: 1280x900 and 1280x800, default light theme
- Approved design: none; the issue is CI and test hygiene, and the two visible components were meant to look and behave exactly as before
- Visual review: completed for the two surfaces whose markup changed (the Atlas Lattice planned square, the account menu's character rows)
- Visual verdict: PASS
- Screenshots: ![Lattice, empty](.github/issue-evidence/4677/lattice-empty.png) ![Lattice, square 0,0 planned with its unplan control](.github/issue-evidence/4677/lattice-planned.png) ![Planned square opens its add dialog](.github/issue-evidence/4677/lattice-planned-add-dialog.png) ![Account menu open, character row reachable](.github/issue-evidence/4677/account-menu-character-focused.png)
- Comparison notes: the account-menu check was also run against a build with `main`'s CharacterLink.tsx (everything else this branch): it fails with `getByRole('menuitem', { name: 'Tehom' })` not found, because the old component dropped the role, ref and handlers Radix hands an `asChild` item. With the fix the row is a menuitem, ArrowDown focuses it, and its href is `/characters/1`. The Lattice square looks as before: "planned" in italics, the ✕ in its top-right corner.
- Tested interactions: Lattice: left click an empty square (plans it), check the ✕ is not inside the square's button and sits in its top-right quarter, click ✕ (unplans), plan again and left click the planned square (its add dialog opens). Account menu: click the "Test player" trigger, ArrowDown, read focus and href.
- Fixture/live boundary: the bundle is the real production build; every /api call is a Playwright route mock, so no server-side behavior is claimed here. The CI and warning changes are proven by the vitest runs below, not by this browser pass.
- Overall outcome: PASS

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| ci-shards | PASS | `.github/workflows/ci.yml` runs `pnpm test --shard=${{ matrix.shard }}/4` on 4 matrix jobs beside `frontend-typecheck` and `frontend-build`; the same command locally, shard 1/4: 165 of 658 files, 1514 tests, all passed in 61s | none needed |
| ci-required-check | PASS | the required `frontend` aggregator needs all three jobs, passes only on `success success success` or (no frontend change) `skipped skipped skipped`, and fails otherwise | none needed |
| no-react-warnings | PASS | full suite with `--reporter=default` at the reviewed code: 658 files, 5969 tests passed, 0 React/Radix/react-redux warnings (was ~2,500 per run, 1,846 from GamePage.test.tsx alone); log 2,399 lines, was ~52,000 | none needed |
| guard | PASS | `src/test/setup.ts` fails the test during which a listed warning is logged; with the guard on and fixes absent, 40 files and 144 tests failed, each naming the component | none needed |
| component-bugs | PASS | duplicate FolioCrumb keys, button in button (Lattice), div in p (DuranceCard), CharacterLink ref and props, three selectors returning a fresh object each call; each was a warning that is now gone, and the Lattice and account menu were exercised in the browser above | none needed |

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Lattice planned square | dashed border, "planned" in italics, same size as its neighbours | MATCH | lattice-planned.png, square at bottom left |
| Unplan control | ✕ in the square's top-right corner, outside the square's button | MATCH | lattice-planned.png; bounding boxes and DOM check in the spec |
| Planned square's own action | left click opens the add dialog | MATCH | lattice-planned-add-dialog.png |
| Account menu character row | listed under Characters, a menuitem, keyboard-focusable, links to the sheet | MATCH | account-menu-character-focused.png; fails on main's CharacterLink |

## Unresolved findings

None
