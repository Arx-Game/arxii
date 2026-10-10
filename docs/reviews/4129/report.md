# Review evidence

- Reviewed revision: `443e3373e407df64949e7f4869115e5ee519ca3f`
- Reviewer: the `demo-fidelity-reviewer` agent against the saved demo page (artifact UJtRxbmoLBGDcc9sc6f3Jj, the approved design), with the implementing agent (Claude Code) driving Playwright on the real `/game` from the production bundle, every `/api/**` call and the socket answered by the shared harness's fixtures. The reviewer's first pass returned FAIL on one rendered defect (a table-talk refusal banner on a page row, from `tagReachability` treating the page mode as a room-heard address) and one illegible capture (the row menu shot mid fade-in); both are fixed in the reviewed revision, with a unit test for the first and the empty-find quiet line captured too. The reviewer judged the five deliberate differences below acceptable.
- Reviewer verdict: PASS
- Application/build identity: `vite build` of the frontend at the reviewed revision, served by `vite preview --port 4129`; harness `frontend/e2e/evidence/conversation-rail-4129.spec.ts`, two readings, both passing, no page errors
- Environment: Linux devcontainer on WSL2, Playwright Chromium headless (build 1208)
- Viewports/themes: 1280x800 and 390x844, the default light theme
- Approved design: the demo on issue #4129 (https://claude.ai/artifact/UJtRxbmoLBGDcc9sc6f3Jj), seven rounds with ApostateCD; its six walkthrough screens and the folded strip are the checklist. Deliberate, reviewer-accepted differences: the room row is labelled with the room's name while the composer names the scene, as the demo does; All and the room row keep the pose/say/emit choice (every one of them is the room's audience) while whisper, tabletalk and page rows lock the composer; a page in the feed renders as the existing boxed System note rather than the demo's left-bordered page note; the find mark is the browser's default colour; the face's left-click persona menu is the existing #4030 `PersonaMenu` and was not captured (its API is not mocked), the row's right-click menu was.
- Visual review: Completed
- Visual verdict: PASS
- Screenshots: ![Screen 1 at 1280: the rail on the far left with All current, Here holding Quiet courtyard, Nyx (whisper) and The long table (tabletalk) with counts, OOC Pages holding Bram (page), the find box at the foot; the feed with the chips above it and no tab strip; the sidebar with Here and History only](docs/reviews/4129/rail-all-1280.png) ![Screen 2: Nyx picked, the feed holds the whisper alone, the row's count cleared, the composer locked to Whisper → Nyx](docs/reviews/4129/rail-picked-nyx-1280.png) ![A page row picked: the feed holds Bram's page alone, the composer locked to Page → Bram, no refusal banner](docs/reviews/4129/rail-picked-bram-1280.png) ![Screen 3: the Nyx row's right-click menu headed Nyx, with Minimize all from Nyx, Hide all from Nyx, Expand all, Unhide all](docs/reviews/4129/rail-person-menu-1280.png) ![Screen 4: find "gate" narrows All to the whisper with the match marked](docs/reviews/4129/rail-find-1280.png) ![Screen 4, no match: one quiet line, Nothing in this session says that.](docs/reviews/4129/rail-find-empty-1280.png) ![The folded strip: the rail at 44px with the expand control and one count](docs/reviews/4129/rail-collapsed-1280.png) ![Screen 6 at 390: the Rail pane with the pane toggle Rail / Story / Sidebar at the foot](docs/reviews/4129/rail-pane-390.png)
- Comparison notes: The rail sits where the demo draws it (first grid column, `--play-rail-width`, the `.play-rail-pane` and `.play-workspace` rules present in `frontend/src/index.css` and reaching the page, since the column is there at 1280 and fills the screen at 390) with the demo's parts in the demo's order: the uppercase Conversations head and «, All, the uppercase group labels, rows with face, name, kind word and dark count pill, the find box with the demo's placeholder. A picked row takes the accent fill and bold weight and shows its conversation alone; the composer's label follows the selection with the demo's wording. The person row's right-click menu carries exactly the demo's four items under the person's name. Find narrows within All and the chips and marks the match; no match is the one quiet line. The sidebar has Here and History and nothing above the feed but the chips. Below 960px the foot toggle reads Rail / Story / Sidebar. Beyond the deliberate differences above, the reviewer noted only existing chrome the demo does not draw (the reader's "N conversations / Mark conversation read / Accessible full text / Chronological" header and the Open Speaker Line bar) and that All shows a summed count while not current, which the demo leaves unspecified.
- Tested interactions: reach a ready session at 1280; push a room pose from Nyx, a tabletalk pose from Bram at The long table, a whisper from Nyx to the viewer, and a `text` frame typed `page` from Bram; read every row, count, the find box and the rail's resize handle (200 to 320); read the sidebar's modes and the absence of a tablist; pick Nyx and read the feed, the composer label and the cleared count; pick Bram and read the page alone, Page → Bram and the absence of a refusal banner; right-click the Nyx row and read the four menu items, Escape closes it; click the Nyx face's menu button exists; pick All, type "gate" and read the narrowed feed and the mark, type "zzzz" and read the quiet line, press Escape and read the restored feed and the emptied box; press « and read the strip's one count, press it and read the rail reopened on The long table with TT → The long table. At 390 after reaching the ready state wide: read the toggle's three buttons, open the Rail pane, pick Nyx, open Story and read Whisper → Nyx.
- Fixture/live boundary: the page, `GameLayout`, `ConversationRail`, `GameWindow`, the readers, the composer and the bundle are real; the account, roster, room state, scene, interactions and the page frame are fixtures (`e2e/support/gameHarness.ts` and the spec). That the real server types a page frame with its correspondent on both sides is proved by `commands.tests.test_cmd_page` (`test_page_routes_to_character`, the account-block tests); that a `page`-typed frame becomes a note with `from` and groups into a row by `railRows.test.ts` and `GamePage.test.tsx` ("lists a page correspondent under OOC Pages"); the rest of the rail's contract by `GamePage.test.tsx`'s "conversation rail (#4129)" block, `railRows.test.ts`, `feedFind.test.tsx`, `gameSlice.test.ts` ("the rail selection"), `PlaySidebar.test.tsx`, `GameLayout.test.tsx`, `playPreferences.test.ts` and `tagReachability.test.ts`.
- Overall outcome: PASS

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Rail column | far left, before the story pane, with the head Conversations and « | MATCH | docs/reviews/4129/rail-all-1280.png |
| All row | first, current by default, no count while current | MATCH | docs/reviews/4129/rail-all-1280.png |
| Here group | the room first, then Nyx (whisper) with a face and The long table (tabletalk), counts on the right | MATCH | docs/reviews/4129/rail-all-1280.png |
| OOC Pages group | Bram (page) with a face and a count; Channels not drawn | MATCH | docs/reviews/4129/rail-all-1280.png |
| Find box | at the rail's foot, placeholder Find in this session | MATCH | docs/reviews/4129/rail-all-1280.png |
| Picked row | accent fill, bold, count cleared, the feed holds that conversation alone, composer Whisper → Nyx | MATCH | docs/reviews/4129/rail-picked-nyx-1280.png |
| Page row | the page alone, composer Page → Bram, no refusal | MATCH | docs/reviews/4129/rail-picked-bram-1280.png |
| Row right-click menu | Nyx; Minimize all from Nyx, Hide all from Nyx; Expand all, Unhide all | MATCH | docs/reviews/4129/rail-person-menu-1280.png |
| Find | the feed narrowed to matching lines, the match marked | MATCH | docs/reviews/4129/rail-find-1280.png |
| Find, no match | one quiet line and nothing else | MATCH | docs/reviews/4129/rail-find-empty-1280.png |
| Sidebar | Here and History only; no tab strip above the feed | MATCH | docs/reviews/4129/rail-all-1280.png |
| Folded strip | 44px, the expand control, a count per row with unread | MATCH | docs/reviews/4129/rail-collapsed-1280.png |
| Narrow screens | the foot toggle Rail / Story / Sidebar; the Rail pane holds the whole rail | MATCH | docs/reviews/4129/rail-pane-390.png |

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| R01-rail-third-column-resizable-collapsible | PASS | first and seventh captures; `GameLayout.test.tsx`; `playPreferences.test.ts` (`railWidth` clamp, `railCollapsed`) | #4129 decision 1 |
| R02-all-then-here-then-ooc-pages-newest-first | PASS | first capture; `railRows.test.ts` | #4129 decision 2 |
| R03-one-selection-in-full-count-cleared-composer-locked | PASS | second and third captures; `GamePage.test.tsx` "picking a whisper row…", "a picked conversation shows a hidden line in full…"; `gameSlice.test.ts` "the rail selection" | #4129 decision 3 |
| R04-chips-inside-selection-tab-strip-and-conversations-mode-removed | PASS | first capture; `PlaySidebar.test.tsx`; the removed `ConversationTabStrip.tsx`, `ConversationSidebar.tsx`, `threadTabsStorage.ts` | #4129 decision 4, ADR-4129 |
| R05-person-row-two-clicks | PASS | fourth capture; `ConversationRail.tsx` (`PersonaMenu leftClick`, `RailPersonMenu`) | #4129 decision 5 |
| R06-session-lifetime-nothing-persisted | PASS | `gameSlice.ts` (no storage, `setSessionScene` reset, room row excepted); `gameSlice.test.ts` | #4129 decision 6 |
| R07-find-in-this-session | PASS | fifth and sixth captures; `feedFind.test.tsx`; `GamePage.test.tsx` "the find box narrows…" | #4129 decision 7 |
| R08-pages-typed-with-correspondent | PASS | third capture; `commands.tests.test_cmd_page`; `railRows.test.ts` pages | #4129 decision 8 |
| R09-channels-reserved-only | PASS | no Channels group drawn (first capture); nothing built | #4129 decision 9 |
| R10-docs-in-tandem | PASS | `frontend/src/game/CLAUDE.md`, `frontend/src/store/CLAUDE.md`, `docs/systems/scenes.md`, `docs/roadmap/rp-scenes.md`, ADR-4129 | CLAUDE.md, docs are directives |

## Unresolved findings

- None
