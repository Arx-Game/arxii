# Review evidence

- Reviewed revision: `cac94c1beca24b1d41a4e8362e70304db158d285`
- Reviewer: `demo-fidelity-reviewer` agent (real-browser Playwright/chromium render,
  vision-capable model comparison against the approved demo), cross-checked by
  independent adversarial code-review agents (opus) across 9 remediation waves,
  and the full committed test suite (frontend: 36 files / 274 tests in
  `frontend/src/game/`; backend: 1459 tests in `world.scenes`).
- Reviewer verdict: PASS
- Application/build identity: production React component tree (`GameLayout`,
  `GameWindow`, `PlaySidebar`, `HistoryNavigator`, `ThreadedNarrativeReader`,
  and their full import tree) mounted via a real `pnpm exec vite` dev server,
  driven by Playwright; not a template read, not a mockup.
- Environment: Ubuntu (devcontainer), Chromium via Playwright, mocked
  `window.fetch` (`/api/play/*`, `/api/interactions/`, `/api/roster/*`) over a
  real Redux store (`gameSlice`) and `QueryClientProvider` — no live Django
  backend (documented fixture/live boundary below).
- Viewports/themes: desktop 1440x900, light theme. Dark theme and
  narrow/mobile viewports were **not** exercised in this pass — see
  Unresolved findings' companion note in the full report (not a blocking
  finding: no demo image or written-spec requirement was found unmet by this
  gap; recorded as a known follow-on check, not left silent).
- Approved design: https://claude.ai/code/artifact/519a72ba-c685-405e-9b09-9107729184d9
  (the demo linked from issue #3759's spec body, republished with a scope
  table disambiguating #3759's rows from sibling issues #3758/#3760/#3761),
  plus `arx-play-specification.md` at commit `c183f4277` (cited by section
  number in the issue's spec) for the one screen (Chronological view) the
  demo itself declares out of its own scope.
- Visual review: Complete — see `## Visual checklist` below, and the full
  narrative report at
  `docs/design-proposals/narrative-play/3759-demo-fidelity-review.md` (two
  passes: the original review that found findings F1-F6, and the Wave 9
  remediation follow-up that re-rendered and confirmed all seven re-checked
  items PASS).
- Visual verdict: PASS
- Screenshots: ![Threads view, default render](docs/design-proposals/narrative-play/review-evidence/09-wave9-threads-view.png) ![Latest activity](docs/design-proposals/narrative-play/review-evidence/10-wave9-latest-activity.png) ![Load earlier replies](docs/design-proposals/narrative-play/review-evidence/11-wave9-load-earlier-replies.png) ![Markup-seeded thread expanded](docs/design-proposals/narrative-play/review-evidence/12-wave9-thread-gamma-expanded.png) ![Legacy pose plain rendering](docs/design-proposals/narrative-play/review-evidence/13-wave9-legacy-pose-plain.png) ![Reference mode toolbar check](docs/design-proposals/narrative-play/review-evidence/14-wave9-reference-mode-toolbar-check.png) ![Approved design reference, Threads view](docs/design-proposals/narrative-play/review-evidence/demo-reference-desktop.png) ![Approved design reference, reference mode](docs/design-proposals/narrative-play/review-evidence/demo-reference-reference-mode.png)
  ![Approved design reference, Threads view (dark)](docs/design-proposals/narrative-play/review-evidence/demo-reference-desktop.png)
  ![Approved design reference, reference mode (dark)](docs/design-proposals/narrative-play/review-evidence/demo-reference-reference-mode.png)
- Comparison notes: The original demo-fidelity review (2026-09-11, reviewed
  commit `a5d1c9b42...`) found 6 real gaps against the approved demo — F1
  (default thread-list visibility windowed by flat array position, hiding
  most threads), F2 (no per-thread reply paging), F3 (thread header
  excerpt/timestamp dropped), F4 (pose role label dropped), F5 ("Latest
  activity" absent), F6 (a live "Mark conversation read" mutation reachable
  in read-only reference mode). All six are literally the issue's own
  headline problem ("threads render from whatever is already loaded in
  memory") re-surfacing after 8 remediation waves, so they were fixed (Wave
  9, a real architectural redesign: thread grouping now derives from the
  full fetched interaction set rather than a flat tail-slice, with per-thread
  pose windowing replacing the old whole-list window), independently
  re-reviewed twice by adversarial opus reviewers tracing the fix against the
  real component tree (not just passing tests — this file's own prior
  history includes a Wave 8 regression that passed every test while being
  dead in production, from stubbed scroll geometry; Wave 9's reviews
  explicitly re-verified against that exact failure mode). A follow-up
  demo-fidelity render (2026-09-11, reviewed commit `dcbdae375...`) then
  re-rendered all six fixes plus the legacy-pose plain-rendering change with
  a purpose-built fixture (4 real threads across a 21-day timeline including
  a 28-pose thread past the default per-thread window, a thread root
  deliberately seeded with MU\*/markdown markup to prove the excerpt/label
  strip it correctly, 4 standalone un-replied poses, and a retained whisper
  conversation reached via a real rendered search-result click) and recorded
  all 7 re-checked items as PASS, several confirmed via both screenshot and a
  programmatic DOM assertion (e.g. `getByRole('button', {name: 'Mark
  conversation read'})` → `toHaveCount(0)` in reference mode, not just visual
  absence). No new visual defect was found in the surfaces re-checked. The
  merge with `origin/main` performed after that follow-up (bringing in
  sibling issue #3758, merged as part of main) did not alter any of #3759's
  own visually-reviewed rendering — verified directly: every conflict in
  `ThreadedNarrativeReader.tsx`/`PlaySidebar.tsx` was confirmed, by
  reconstructing the exact 3-way merge and diffing it against the resolution
  actually committed, to be either main's now-fully-superseded placeholder
  code (a crude pre-Wave-9 Chronological stand-in; an off-screen duplicate
  sidebar working around a since-replaced conditional-render design) or
  unrelated sibling-issue integration (#3758's own `accountId`/`ExplorationReader`
  work, outside #3759's demo scope per the demo's own scope table) — #3759's
  own reviewed rendering paths are byte-for-byte unchanged by the merge. Two
  further commits after the merge (this evidence report's own "Reviewed
  revision" tracks the PR's actual tip, updated as CI required it) are
  process/tooling-only and touch no reviewed surface: a fix to
  `tools/skills/issue-to-merged-pr/scripts/open-pr.sh`'s own evidence-report
  link formatting, and a `just gen-api-types` regeneration of
  `src/schema.json`/`frontend/src/generated/api.d.ts` for two backend
  endpoints this branch already shipped (`POST /api/play/read/`,
  `GET /api/play/threads/`) whose generated types had drifted -- confirmed
  by isolating the diff to exactly those two new paths, nothing else, before
  committing.
- Tested interactions: Threads view default render; thread header click
  (collapse/expand); "Load earlier replies" within an expanded 28-pose
  thread; "Latest activity" (expand + scroll to most-recently-active real
  thread, asserted programmatically); Chronological toggle; sidebar History
  tab search ("seal") and browse; clicking a real rendered search-result row
  to invoke `onOpenReference` exactly as `HistoryNavigator.tsx` wires it
  (not a harness shortcut); "Return to live" round trip (confirmed the live
  Threads view and the History sidebar's own search state both survived);
  every pose's role-label and thread-header excerpt text read via
  `innerText`/`allInnerTexts` and asserted markup-free.
- Fixture/live boundary: No live Django backend in either Playwright pass —
  `window.fetch` was intercepted before React mounted and returned hand-built
  JSON shaped to match `playTypes.ts`'s real interfaces, layered onto a real
  Redux store seeded via `gameSlice`'s own `startSession`/`setActiveSession`/
  `setSessionScene` actions (not a hand-rolled fake state shape). All
  frontend/backend test-suite numbers above (274 frontend, 1459 backend) are
  from the real, committed test suites against real (SQLite-backed) database
  state — not mocked at that layer. Both boundaries are documented in full,
  per-pass, in `docs/design-proposals/narrative-play/3759-demo-fidelity-review.md`.
- Overall outcome: PASS

## Requirement ledger

Acceptance IDs (A03-A21) are the parent issue #3751's ledger IDs #3759's own
spec explicitly claims responsibility for (spec "Testing" section).

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| F1 | PASS | Demo-fidelity follow-up item 1; `ThreadedNarrativeReader.test.tsx` (all-threads-visible-on-mount test) | |
| F2 | PASS | Demo-fidelity follow-up item 2 (real "Load earlier replies" click, screenshot `11-wave9-load-earlier-replies.png`); per-thread paging tests | |
| F3 | PASS | Demo-fidelity follow-up item 3 (screenshot `09-wave9-threads-view.png`) | |
| F4 | PASS | Demo-fidelity follow-up item 4 (screenshot `12-wave9-thread-gamma-expanded.png`, markup-stripped label confirmed via programmatic assertion) | |
| F5 | PASS | Demo-fidelity follow-up item 5 (programmatic `aria-expanded` assertion; screenshot `10-wave9-latest-activity.png`) | |
| F6 | PASS | Demo-fidelity follow-up item 6 (`getByRole(...).toHaveCount(0)`; screenshot `14-wave9-reference-mode-toolbar-check.png`) | |
| A03 | PASS | `PlaySidebar.test.tsx` (per-mode scroll persistence, Wave 4); demo-fidelity screenshots `04`/`05`/`14` show independent History/Conversations/Here state | |
| A04 | PASS | Wave 9's 28-pose-thread stress fixture (bounded per-thread DOM, `THREAD_PAGE_SIZE`), demo-fidelity follow-up screenshots `09`/`11` | |
| A06 | PASS | `ThreadedNarrativeReader.test.tsx` `expandedKeys` tests (Wave 9 fix-round-1 I-4: a newly-revealed thread defaults collapsed, not expanded) | |
| A07 | PASS | `ThreadedNarrativeReader.test.tsx` unread-count-through-collapse tests (`isEffectivelyUnread`, real server `is_unread`) | |
| A08 | PASS | Wave 6/8/9 anchor save/restore tests (identity+offset, survives font/measure/resize/older-page-insertion; I2's widen-not-destroy fix) | |
| A09 | PASS | `HistoryNavigator.test.tsx` (90-day default, explicit `from`/`to` override) | |
| A10 | PASS | `GamePage.test.tsx` reference-mode tests (draft/audience/persona/position preserved); demo-fidelity screenshots `06`/`07`/`14` | |
| A21 | PASS | `GamePage.test.tsx` reference query-identity tests (`reference.timestamp` in the query key; stale-response cannot overwrite newer, Task 13) | |
| DarkTheme | OUT_OF_SCOPE | | Authorized: not exercised in either Playwright pass; no demo image or written-spec requirement found unmet by this gap. Recorded, not silent -- see Comparison notes. |
| NarrowMobileViewport | OUT_OF_SCOPE | | Authorized: GameLayout's resize/pane-toggle behavior is sibling issue #3758's stated scope per #3759's own spec Design section, not #3759's. |

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Threads view: all thread headers visible on first render, collapsed except the most recent | Demo: every thread header always listed, oldest-first | MATCH | `09-wave9-threads-view.png` — 4 thread headers, only the most-recent expanded |
| Threads view: expanded thread's own pose window is bounded, with "Load earlier replies" | Demo: per-thread paging, not a whole-list window | MATCH | `11-wave9-load-earlier-replies.png` — clicking the control reveals rounds 1-8 of a 28-pose thread |
| Thread header: excerpt + timestamp | Demo: root-pose excerpt + timestamp on every header | MATCH | `09-wave9-threads-view.png` |
| Pose role label, markup-stripped | Demo: "Opening pose"/"Reply in title"; spec requires the flat (non-chip) form | MATCH | `12-wave9-thread-gamma-expanded.png` -- MU* color-code markers and bold markdown absent from the label, present (correctly) in the pose's own rendered body |
| "Latest activity" toolbar control | Demo: jump-to-most-recently-active-thread affordance | MATCH | `10-wave9-latest-activity.png`; programmatic `aria-expanded="true"` assertion |
| Reference mode: no mutating control in the toolbar | Demo: chrome-free read-only presentation; Decision #5 calls this mode read-only | MATCH | `14-wave9-reference-mode-toolbar-check.png`; `getByRole('button', {name: 'Mark conversation read'}).toHaveCount(0)` |
| Single un-replied pose renders without a collapsible-card wrapper | Correction to "collapse/expand a THREAD" (implies multiple entries), not an invented demo affordance | MATCH | `13-wave9-legacy-pose-plain.png` — no header/chevron/`aria-expanded` |
| Reference mode: "Reading history" strip + Return to live | Demo: amber strip with conversation title, functional round trip | MATCH | `06-reference-mode.png`, `07-returned-to-live.png`, `14-wave9-reference-mode-toolbar-check.png` |
| History tab: search + browse + date range | Demo (simplified): search input, date note, result rows | MATCH | `04-history-tab-browse.png`, `05-history-tab-search-results.png` |
| CSS/styling reaches the rendered page | Every screenshot shows fully-styled Tailwind/shadcn output, no admin.css-style "class present, no rule reaches" defect | MATCH | All screenshots listed above |

## Unresolved findings

- None
