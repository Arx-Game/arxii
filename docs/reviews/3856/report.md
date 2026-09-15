# Review evidence: the Actions fold in the Here panel (#3856, PR 3 of 3)

Closes #3856.

- Reviewed revision: c94c5119ba818dc9f287b4f3ddd18dd63cb0ebe0
- Reviewer: Claude Fable 5.1 (implementing session), vision review of the rendered application screenshots below, plus a separate demo-fidelity review pass (a general-purpose Sonnet 5 subagent following `tools/agents/demo-fidelity-reviewer.md`, since the named agent is not registered in this session) that read the approved demo's HTML and the same three screenshots; its checklist and findings are folded into the tables below.
- Reviewer verdict: PASS
- Application/build identity: `pnpm build` of this branch at the reviewed revision (Vite production bundle, output `src/web/static/dist`), served by `vite preview --port 4173` exactly as `playwright.config.ts` does.
- Environment: devcontainer (Ubuntu 24.04 x64), Chrome Headless Shell 145.0.7632.6 via Playwright 1.58.2 (chromium v1208), headless, `hasTouch: true` per `playwright.config.ts`.
- Viewports/themes: 1280x800, light theme (the system default; no `data-theme` stamp).
- Approved design: issue #3856's spec, treatment A "One feed, filter chips" (demo v5, https://claude.ai/code/artifact/d802b376-8d16-4d5a-9c49-5b3c3890b5f8, approved by Dan on 2026-09-14), screen 8 and Decision 7: the Here panel keeps every control it has; the nine reference tabs become a grid under an "Actions" arrow, open by default, directly under the room sections; pressing one swaps the panel to that section with a way back to the room. PR 1 (#3871) and PR 2 (#3873) covered the notes, the "you" row and the chips and are not reviewed here.
- Visual review: completed on the three screenshots below, taken from the running application (not a mockup) by `frontend/e2e/feed-actions-fold.spec.ts`, compared against the demo's `.ref` fold, its `.rows` grid and its `.refpage` back control.
- Visual verdict: PASS
- Screenshots: ![The Here panel: the room sections, then the Actions fold open with the eight sections in a three-column grid](https://raw.githubusercontent.com/Arx-Game/arxii/c94c5119ba818dc9f287b4f3ddd18dd63cb0ebe0/docs/reviews/3856/actions-fold-1280.png) ![Journal open after Status: the section in place of the room, the way back naming the room, the fold still below with Journal marked](https://raw.githubusercontent.com/Arx-Game/arxii/c94c5119ba818dc9f287b4f3ddd18dd63cb0ebe0/docs/reviews/3856/actions-section-1280.png) ![The fold closed on its arrow](https://raw.githubusercontent.com/Arx-Game/arxii/c94c5119ba818dc9f287b4f3ddd18dd63cb0ebe0/docs/reviews/3856/actions-fold-closed-1280.png)
- Comparison notes: In `actions-fold-1280.png` the Here panel keeps the Display settings disclosure, the room name and scene line, Description, Characters with "Tehom YOU" first and Nyx second, the occupant hint, and Exits, and ends in the ACTIONS eyebrow with a down-pointing chevron and a three-column grid of Who, Stories, Events, Codex, Status, Items, Journal and Travel, each with its small icon, on a faintly tinted ground with a rule above: the demo's `.ref` fold and `.rows` grid, in its order, under the room sections, open by default. No tab row sits above the room any more. `actions-section-1280.png` shows the panel after Status was pressed and then Journal from the fold: the room sections are gone, the panel starts with "← Quiet courtyard" in muted text, the demo's `.refpage` back control, then the Journal section's own content (its Write an entry button, its empty line and its Full journal link), and the Actions fold stays below it with Journal marked, the demo's grid rendered after the room and after a section alike. The demo-fidelity pass found the first build rendering the fold under the room only, which cost a trip back through the room for every switch between sections; that was fixed at the reviewed revision and the screenshot retaken. A section whose content is REST-backed (Status, Who, Events) renders its body empty under the fixture, which is an artefact of the fixture and not of this PR; those panels are unchanged. `actions-fold-closed-1280.png` shows the fold closed on its summary with the chevron pointing right and the grid hidden, the room sections untouched above it. Differences from the demo that are not defects: the demo's grid uses text glyphs for icons and the app uses its icon set; the demo's fold ground is its note tint and the app's is its muted token; the demo drew Room among the nine and the app's back control is the way back to the room, so the grid holds the eight sections.
- Tested interactions: reach "In world" with an active scene through the shared harness; read the room sections (name, Characters with the "you" row, Exits); read the fold's `open` attribute and its eight buttons in order; assert no element with the tab role remains; press Status and read the way back naming the room, with the room sections gone; read Status marked in the fold below; press Journal in that fold and see Journal marked with the way back still there; press the way back and see the room sections and the fold return; press the fold's summary and see it close with its buttons hidden; press it again and see them back. Zero page errors (asserted).
- Fixture/live boundary: REST and the game WebSocket are mocked through `frontend/e2e/support/gameHarness.ts` (the same fixture `narrative-play-delivery.spec.ts` uses); no Django or Evennia process and no database took part. The sidebar, the fold, the grid, the back control and the CSS are the real ones; the section panels' own content (Status, Who, Events and the rest) is REST-backed and absent under the fixture, and those panels are untouched by this PR.
- Overall outcome: PASS

## Requirement ledger

| id | status | evidence | authorized decision |
| --- | --- | --- | --- |
| fold-under-room-sections-open-by-default | PASS | `SidebarTabPanel.test.tsx` "shows the room with the Actions fold open below it"; `actions-fold-1280.png` | spec Decision 7 |
| grid-of-eight-sections | PASS | `SidebarTabPanel.test.tsx` button order; `actions-fold-1280.png` | n/a |
| section-in-place-with-way-back | PASS | `SidebarTabPanel.test.tsx` "a section opens in place of the room with a way back that names the room"; `actions-section-1280.png` | spec, Here panel paragraph |
| fold-stays-under-a-section | PASS | `SidebarTabPanel.test.tsx` (Events to Who through the fold, the open one marked); journey (Status to Journal); `actions-section-1280.png` | demo `renderSide`: the grid follows the room and a section alike |
| way-back-names-focused-subject | PASS | `SidebarTabPanel.test.tsx` label override case (title carries the full name, visual truncation) | n/a |
| fold-closes-and-opens | PASS | `SidebarTabPanel.test.tsx` fold case; `actions-fold-closed-1280.png` | n/a |
| controlled-by-page-and-lazy-mount | PASS | `SidebarTabPanel.test.tsx` "calls onTabChange instead of managing activeTab internally", "renders the section passed via activeTab", lazy events mount; `GamePage.test.tsx` and `PlaySidebar.test.tsx` green | n/a |
| nothing-dropped | PASS | every section panel prop and fallback line kept in `SidebarTabPanel.tsx`'s `sectionContent`; the room sections untouched (`RoomPanel.tsx`, `FocusPanel.tsx` not in this diff); Display settings kept | spec Decision 7 |
| docs-in-tandem | PASS | `frontend/src/game/CLAUDE.md` gains the `SidebarTabPanel.tsx` entry; the scenes-doc sentence rides PR 2's paragraph (both touch one paragraph; not duplicated here) | n/a |

## Visual checklist

| Element | Expected | Result | Evidence |
| --- | --- | --- | --- |
| Room sections above the fold | Name, scene line, Description, Characters with the "you" row, Exits, in place | MATCH | `actions-fold-1280.png` |
| Actions summary | Uppercase eyebrow "Actions" with an arrow at the right | MATCH | `actions-fold-1280.png` |
| Fold open by default | The grid visible on entry | MATCH | `actions-fold-1280.png` |
| Grid | Three columns, eight sections in the demo's order, each with an icon | MATCH | `actions-fold-1280.png` |
| No tab row above the room | Nothing with the tab role | MATCH | `actions-fold-1280.png`, asserted in the journey |
| Section view | The section in place of the room, "← Quiet courtyard" at the top | MATCH | `actions-section-1280.png` |
| Fold under a section | The grid still below, the open section marked | MATCH | `actions-section-1280.png` |
| Fold closed | Arrow turned, grid hidden, room sections untouched | MATCH | `actions-fold-closed-1280.png` |
| Composer and feed | Unchanged | MATCH | all three |

## Unresolved findings

None
