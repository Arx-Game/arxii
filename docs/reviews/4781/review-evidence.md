# Review evidence — Issue #4781

- Reviewed revision: `a675e7da8a0040e958e1b7dc1cf0373c00925057`
- Reviewer: `review-4781-mobile-header` (independent reviewer)
- Reviewer verdict: PASS
- Application/build identity: Vite production build via `pnpm build`; production preview at `http://localhost:4173`; test `frontend/e2e/header-overflow-4781.spec.ts`
- Environment: Linux devcontainer, Chromium via Playwright; Django REST calls mocked in Playwright route fixtures; no live backend
- Viewports/themes: 400 × 850 CSS px, default light theme
- Approved design: Not applicable; bug report #4781 specifies eliminating 10px horizontal overflow on a 400px screen, not a separate visual design
- Visual review: Completed by independent reviewer against current source and captures; reviewer PASS
- Visual verdict: PASS
- Screenshots: ![400px header with selected long-name character](docs/reviews/4781/header-400-selected.png) ![400px header with no selected character](docs/reviews/4781/header-400-no-selection.png)
- Comparison notes: At 400px, title and menu remain on the first header row; the selected-character chip occupies a second row. Long character/persona text truncates and the Enter the World control remains visible. With no character selected, only title/menu remain. The document scroll width is asserted to equal 400 in both states. Captures are 400px wide. Selected PNG SHA-256: `7bd9757efe9b089188aa594754c5ab7f0d8e1d03b2abc9d0161f0048465c4578`; no-selection PNG SHA-256: `ec9b5d99af637d78556849cc9fdbdf3e852da120d8175b552216545cf5e5edcd`.
- Tested interactions: At 400px, open mobile menu, verify the Play link is visible, close with Escape. Verify selected character name appears in selected state and is absent in no-selection state; assert document scrollWidth is 400 for both.
- Fixture/live boundary: Production frontend build and real app shell/layout are used. Auth, account, roster, persona, mail, narrative, and ritual API responses are Playwright mocks. No request reached a live backend; this is not live-backend fidelity evidence. Build/test execution was performed on the working tree based on `a675e7da8a0040e958e1b7dc1cf0373c00925057`; source snapshot SHA-256 was `c007074110f7c8815f533a35e48e0f96202d4a3a5809712c57808e2677ad80bb`. The capture is not tied to a committed source SHA. The exact command/output provenance is the agent run: `pnpm build` passed; `pnpm exec playwright test e2e/header-overflow-4781.spec.ts --project=chromium` passed (1 test). `pnpm typecheck` passed. `pnpm exec vitest run src/components/__tests__/Header.test.tsx` passed (16 tests); full Vitest suite passed before final fixture-only adjustment (666 files, 6108 tests). This report discloses that the screenshots are not build-artifact/commit-bound.
- Overall outcome: PASS

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Title and mobile menu | Both controls fit on the first row at 400px without horizontal page overflow | MATCH | ![Selected state](docs/reviews/4781/header-400-selected.png) |
| Selected character chip | Long name/persona truncate; Enter the World remains visible | MATCH | ![Selected state](docs/reviews/4781/header-400-selected.png) |
| No-selection header | Title/menu remain visible and no chip is rendered | MATCH | ![No-selection state](docs/reviews/4781/header-400-no-selection.png) |

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| A01 | PASS | `pnpm build`; `pnpm typecheck`; focused Header tests 16/16; Playwright 1/1 at 400px, selected and no-selection states with `scrollWidth === 400` | |

## Unresolved findings
