# Review evidence

- Reviewed revision: ec750658fedbec67e17256b0b66a9f383e70b9f2
- Reviewer: demo-fidelity-reviewer
- Reviewer verdict: PASS
- Application/build identity: `pnpm preview` production build of the `frontend/` Vite app at the reviewed revision, served on :4173 (the config Chromium/Playwright loaded for `frontend/e2e/history-threads.spec.ts`)
- Environment: Chromium (Playwright) in the devcontainer; the WebSocket session, roster and all four play endpoints (`/api/play/conversations/`, `/api/play/threads/`, `/api/play/search/`, `/api/play/context/`) are fixture-routed via `mockRestRoutes`/`page.route()`, not a live backend
- Viewports/themes: 1280x1600 Chromium viewport (`page.setViewportSize` in the spec, so the sidebar's internal scroll container does not crop rows out of an element screenshot); default/light application theme (no dark-mode toggle exercised)
- Approved design: https://claude.ai/code/artifact/ebc215a7-bceb-48ff-b94e-9d490575c19d
- Visual review: completed
- Visual verdict: PASS
- Screenshots: ![Screen 1](docs/reviews/3772-screen1-collapsed.png) ![Screen 2](docs/reviews/3772-screen2-expanded.png) ![Screen 3](docs/reviews/3772-screen3-reader.png) ![Screen 4](docs/reviews/3772-screen4-states.png)
- Comparison notes: The one remaining blocking finding from round 2 is fixed and confirmed distinct from a look-alike. `docs/reviews/3772-screen1-collapsed.png` now shows a "Next page" button below the "Scene 398" row, full width, outside every conversation row's own box - the demo's Screen 1 top-level cursor pager. This is not a per-conversation thread pager wearing the same label: `history-threads.spec.ts:259` scopes the assertion to `historyNav.locator('.border-t.pt-3')` (the "Recent conversations" section container, `HistoryNavigator.tsx:179`) at a point in the test (line 267) before any conversation's Threads disclosure has been opened, so the only "Next page" button that can exist in the DOM at that assertion is the top-level one; `CONVERSATIONS.after` is now `'cursor-conversations-2'` rather than `null` (spec line 69). `docs/reviews/3772-screen2-expanded.png` independently confirms the two pagers are visually distinct once both exist on screen at once: one "Next page" sits indented inside Scene 412's expanded thread list (bordered, per-conversation, asserted separately at spec line 287 scoped to `scene412Row`), and a second, full-width "Next page" sits below the collapsed "Scene 398" row, outside any row's box - matching the demo's separate placements for the per-conversation thread pager (documented in the "month-long scene" card) and the Screen 1 conversation-list pager. `docs/reviews/3772-screen4-states.png` shows the same top-level pager still present alongside the newly-exercised "No reply threads" empty state, confirming the fixture change did not perturb that screen. `docs/reviews/3772-screen3-reader.png` is pixel-identical in content to the prior round (the reader is unaffected by a conversations-list fixture change), so the anchor-navigation and collapsed-neighbour-thread mechanism already confirmed in round 2 stand unchanged. All prior-round-2 confirmations (date order "14 Jun", "Opening pose" role label, the collapsed neighbour thread card with its second pose absent from the DOM, the whisper's "No reply threads" state, the temporary "Scene 398" row, the third un-pilled thread row, the per-conversation pager) remain visually confirmed in this round's re-captured screenshots. A final commit (`f57b7d989`) gated the already-mounted `ConversationThreadList` panel on `isExpanded && conversation.canRead`, matching the collapse control's own gate, so a background refetch revoking `canRead` for an open row cannot strand the panel mounted with no way to close it; every fixture row in `history-threads.spec.ts` sets `canRead: true`, so this gate is a no-op for all four rendered screens, confirmed by re-reading all four images: three are byte-identical to the prior revision and the fourth (`3772-screen4-states.png`) differs by 2 bytes on disk with no visible content change on inspection (matching the implementer's own reported 6-pixel/1-of-255 delta).
- Tested interactions: opening the sidebar's History mode; pressing each conversation's "Threads" disclosure to expand/collapse its thread list (Scene 412, the whisper, and Scene 398 in turn); paging the top-level conversation list via its own "Next page" control; pressing a thread row to open reference mode anchored at that thread's first pose; observing the reader's already-collapsed neighbour thread card (all driven through real clicks and DOM assertions in `frontend/e2e/history-threads.spec.ts`, not simulated state)
- Fixture/live boundary: Live: `HistoryNavigator`, `ConversationThreadList` (including the corrected `shortDate()`), and the reader's reference-mode rendering (`GameWindow`/`ThreadedNarrativeReader`) exactly as built, their CSS, and every click/disclosure/navigation/pagination the spec drives, including the real `referenceKind`/`referenceKey`/`referencePose` URL wiring and the reader's own anchor-seek/highlight/collapse logic. Fixture: the entire session (account, roster, WebSocket frames) and the four play-endpoint JSON payloads (`CONVERSATIONS` with three rows and a non-null `after` cursor, `THREADS` with three threads and an `after` cursor, `EMPTY_THREADS`, `CONTEXT` with a real second thread `a9`) hard-coded in the spec file; no interaction/thread/pose row exists in any database for this journey. The backend contract itself (pagination, unread counts, thread grouping) is covered by `src/world/scenes/tests/test_play_views.py`, not by this visual review.
- Overall outcome: PASS

## Requirement ledger

| id | status | evidence | authorized decision |
| --- | --- | --- | --- |
| screen1-conv-row-preserved | PASS | docs/reviews/3772-screen1-collapsed.png shows "Scene 412" / "3 new · Retained" unchanged from today's row | |
| screen1-threads-disclosure-collapsed | PASS | docs/reviews/3772-screen1-collapsed.png shows a separate "Threads ▸" control on all three rows, no count | |
| screen1-whisper-row | PASS | docs/reviews/3772-screen1-collapsed.png shows "Whisper with two others" / "Retained" / "Threads ▸" | |
| screen1-temporary-row | PASS | docs/reviews/3772-screen1-collapsed.png shows "Scene 398" / "Temporary · not saved" / "Threads ▸" | |
| screen1-search-date-type-fields | PASS | docs/reviews/3772-screen1-collapsed.png shows "Search history" + search button, From/To date inputs, and "All accessible" | |
| screen1-heading | PASS | docs/reviews/3772-screen1-collapsed.png shows "RECENT CONVERSATIONS" | |
| screen1-cursor-pager | PASS | docs/reviews/3772-screen1-collapsed.png shows a full-width "Next page" button below the "Scene 398" row, outside every row's own box; `history-threads.spec.ts:69` sets `CONVERSATIONS.after: 'cursor-conversations-2'` and line 267 asserts it inside `historyNav.locator('.border-t.pt-3')` before any row is expanded, so no per-conversation pager can be what satisfied that assertion; docs/reviews/3772-screen2-expanded.png shows both pagers on screen simultaneously and visually distinct (one indented inside Scene 412's thread list, one full-width below Scene 398) | |
| screen2-disclosure-expanded | PASS | docs/reviews/3772-screen2-expanded.png shows "3 threads ▾" | |
| screen2-thread-row-1 | PASS | docs/reviews/3772-screen2-expanded.png: "You came anyway. I did wonder." / "4 poses · 14 Jun" / pill "2" | |
| screen2-thread-row-2 | PASS | docs/reviews/3772-screen2-expanded.png: "Keep your voice down. The steward is still at the door." / "6 poses · 14 Jun" / pill "1" | |
| screen2-thread-row-3-no-pill | PASS | docs/reviews/3772-screen2-expanded.png: "Then we are agreed, and neither of us will say so twice." / "2 poses · 14 Jun" / no pill | |
| screen2-date-order | PASS | docs/reviews/3772-screen2-expanded.png reads "14 Jun" at every occurrence; `ConversationThreadList.tsx:28` (`Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short' })`) and `ConversationThreadList.test.tsx:51` (asserts literal `'4 poses · 14 Jun'`) pin it | |
| screen2-indented-left-border | PASS | docs/reviews/3772-screen2-expanded.png shows the thread rows indented behind a left rule; `ConversationThreadList.tsx:71` (`border-l-2 pl-2`) | |
| screen2-per-conversation-pager | PASS | docs/reviews/3772-screen2-expanded.png shows a "Next page" button indented inside the expanded thread list, distinct from the full-width top-level pager below it | |
| screen3-anchor-navigation | PASS | docs/reviews/3772-screen3-reader.png plus the spec's `toHaveURL(/referencePose=11/)` assertion confirm pressing a thread opens reference mode anchored at the thread's first visible pose | |
| screen3-anchored-role-labels | PASS | docs/reviews/3772-screen3-reader.png shows "Opening pose" on pose 11 (verbatim demo match) and a distinct reply label on pose 12; `CONTEXT` fixture poses carry `thread_id: 'a1'` | |
| screen3-collapsed-neighbor-mechanism | PASS | docs/reviews/3772-screen3-reader.png shows a genuinely collapsed thread card ("Nyx" / "2 poses" / "Someone has moved the chairs again.", chevron right); the spec asserts its second pose has `toHaveCount(0)` in the DOM, proving the collapse is real, not merely visual | |
| screen3-pose-role-wording | OUT_OF_SCOPE | `ThreadedNarrativeReader.tsx` (owns `poseRoleLabel`, `` `Reply in ${excerptOf(rootPose.content, 60)}` ``) is absent from `git diff origin/main...HEAD --stat`; docs/reviews/3772-screen3-reader.png reads "Reply in You came anyway. I did wonder." where the demo reads plain "Reply" | controller ruling: pre-existing #3759 behaviour of `ThreadedNarrativeReader`, absent from this branch's diff, confirmed by the controller alongside the reader-bar and summary-line rulings |
| screen3-anchor-highlight-transience | OUT_OF_SCOPE | Same file, same diff-absence; the highlight applied to the anchored pose (`ring-2 ring-primary`, `data-highlighted="true"`) is a 2-second transient rather than the demo's persistent left border, mechanically confirmed by the spec's `[data-pose-id="11"][data-highlighted="true"]` assertion rather than by a visible border in the still screenshot | controller ruling: pre-existing #3759 behaviour of `ThreadedNarrativeReader`, absent from this branch's diff, confirmed by the controller alongside the reader-bar and summary-line rulings |
| screen3-reader-bar-copy | OUT_OF_SCOPE | docs/reviews/3772-screen3-reader.png reads "Reading history · scene:412 · read-only" where the demo reads "Scene 412 · reference"; `GameWindow.tsx` is not in this PR's diff | controller ruling: pre-existing UI owned by `GameWindow`, untouched by this branch, introduced in #3785 |
| screen3-collapsed-note-wording | OUT_OF_SCOPE | docs/reviews/3772-screen3-reader.png has no literal "N earlier poses in this scene" / "N other threads in this scene, collapsed" text; the mechanism (collapsed neighbour thread card, verified above) is genuinely present | controller ruling: the demo's illustrative summary-line wording is out of scope; the reader was built in #3759, not here; the mechanism must be (and is) present |
| screen3-return-to-live | PASS | docs/reviews/3772-screen3-reader.png shows a "Return to live" button matching the demo's wording exactly | |
| screen4-whisper-empty-state | PASS | docs/reviews/3772-screen4-states.png shows "No reply threads ▾" and the verbatim line "Every pose here stands on its own. Open the conversation to read it." | |
| screen4-temporary-row-alongside | PASS | docs/reviews/3772-screen4-states.png shows "Scene 398" / "Temporary · not saved" / collapsed "Threads ▸" visible in the same frame | |
| screen4-cursor-pager-unperturbed | PASS | docs/reviews/3772-screen4-states.png shows the same full-width "Next page" control below "Scene 398", confirming the fixture change for the pager did not disturb this screen's state | |

## Visual checklist

| element | expected | result | evidence |
| --- | --- | --- | --- |
| Screen1: sidebar nav tabs | Here / Conversations / History(active) | MATCH | docs/reviews/3772-screen1-collapsed.png |
| Screen1: History heading + subtitle | "History" with icon; "Find authorized scenes, whispers, and communications." | MATCH | docs/reviews/3772-screen1-collapsed.png |
| Screen1: search field + button | "Search history" input + search icon button | MATCH | docs/reviews/3772-screen1-collapsed.png |
| Screen1: From/To date fields | two labeled date inputs | MATCH | docs/reviews/3772-screen1-collapsed.png |
| Screen1: Type selector | "All accessible" | MATCH | docs/reviews/3772-screen1-collapsed.png |
| Screen1: Recent conversations heading | uppercase "Recent conversations" label | MATCH | docs/reviews/3772-screen1-collapsed.png |
| Screen1: conversation row title+meta | "Scene 412" / "3 new · Retained" | MATCH | docs/reviews/3772-screen1-collapsed.png |
| Screen1: Threads disclosure (collapsed) | "Threads" label, no count, right-pointing caret | MATCH | docs/reviews/3772-screen1-collapsed.png |
| Screen1: whisper conversation row | "Whisper with two others" / "Retained" / "Threads" | MATCH | docs/reviews/3772-screen1-collapsed.png |
| Screen1: temporary conversation row | "Scene 398" / "Temporary · not saved" / "Threads" | MATCH | docs/reviews/3772-screen1-collapsed.png |
| Screen1: cursor pager | full-width "Next page" control below the conversation list | MATCH | docs/reviews/3772-screen1-collapsed.png |
| Screen2: Threads disclosure (expanded) | "N threads" label, down-pointing caret | MATCH | docs/reviews/3772-screen2-expanded.png |
| Screen2: thread row 1 excerpt | italic "You came anyway. I did wonder." | MATCH | docs/reviews/3772-screen2-expanded.png |
| Screen2: thread row 1 sub-line | "4 poses · 14 Jun" | MATCH | docs/reviews/3772-screen2-expanded.png |
| Screen2: thread row 1 pill | "2" | MATCH | docs/reviews/3772-screen2-expanded.png |
| Screen2: thread row 2 excerpt | italic "Keep your voice down. The steward is still at the door." | MATCH | docs/reviews/3772-screen2-expanded.png |
| Screen2: thread row 2 sub-line | "6 poses · 14 Jun" | MATCH | docs/reviews/3772-screen2-expanded.png |
| Screen2: thread row 2 pill | "1" | MATCH | docs/reviews/3772-screen2-expanded.png |
| Screen2: thread row 3 (no pill) | "Then we are agreed, and neither of us will say so twice." / "2 poses · 14 Jun" / no pill | MATCH | docs/reviews/3772-screen2-expanded.png |
| Screen2: indented threadlist with left border | thread rows sit indented under the conversation row behind a left rule | MATCH | docs/reviews/3772-screen2-expanded.png |
| Screen2: "No reply threads" disclosure state | second conversation's control reads "No reply threads" | MATCH | docs/reviews/3772-screen4-states.png |
| Screen2: empty-thread-list line | "Every pose here stands on its own. Open the conversation to read it." | MATCH | docs/reviews/3772-screen4-states.png |
| Screen2: per-conversation pager | "Next page" inside the expanded block, distinct from the conversation-list pager | MATCH | docs/reviews/3772-screen2-expanded.png |
| Screen3: Return to live button | "Return to live" | MATCH | docs/reviews/3772-screen3-reader.png |
| Screen3: anchored pose role label | "Opening pose" | MATCH | docs/reviews/3772-screen3-reader.png |
| Screen3: collapsed neighbour thread | a second real thread renders collapsed, one press away | MATCH | docs/reviews/3772-screen3-reader.png |
| Screen4: whisper row with no reply threads | "No reply threads" + empty line, alongside the temporary row | MATCH | docs/reviews/3772-screen4-states.png |

## Unresolved findings

None
