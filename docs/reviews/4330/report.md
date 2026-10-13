# Review evidence: feed notes take the Display settings and fill the column (#4330)

- Reviewed revision: `d8ac121024f330ce637cfbb3742c1853a2d4ae75`
- Reviewer: the implementing agent (Claude Opus 5.5), operating the built page through Playwright with a vision read of every screenshot
- Reviewer verdict: PASS
- Application/build identity: `pnpm exec vite build` of the reviewed revision's frontend, served by `vite preview --port 4183 --strictPort`; the before shots and red run use `origin/main` (5c122aae6) unpacked with `git archive`, built with `vite build --outDir dist-base` and served on 4184
- Environment: devcontainer on the solo laptop (6 GB), Chromium 1208 headless through Playwright, a scratch config that is the real `playwright.config.ts` minus its webServer with baseURL on the private port
- Viewports/themes: 1280x900, light theme; notes use the reader's existing tokens only, so dark follows by construction and was not separately shot
- Approved design: the reporter's stated expectation on #4330 (ApostateCD, 2026-10-13): these lines "use the display settings format" and expand "like poses are"; recorded in the issue's discovery assessment. #3856's approved demo is superseded for note sizes and widths only (it drew notes at 12px sans in a 64ch box when the whole column was capped at 90ch); its glyphs, frames, italics and colours are kept.
- Visual review: completed on the built page for both readers, before (main) and after (this revision), with each screenshot read
- Visual verdict: PASS
- Screenshots: ![Quiet room on main, reader set to 19px serif: the look, item, system and error notes are small boxes ending two thirds across the column; the italic lines are a different size from the room description](docs/reviews/4330/main-quiet-19px-serif-1280.png) ![Quiet room on this revision, same settings: every note is in the 19px serif of the room description and spans the column; glyphs, boxes, the red error, italics and the ambience hairline still tell the kinds apart](docs/reviews/4330/quiet-room-19px-serif-1280.png) ![Scene on main: a 19px serif pose above 12px boxed notes in a narrow strip](docs/reviews/4330/main-scene-19px-serif-1280.png) ![Scene on this revision: the notes match the pose's size and face and span the column](docs/reviews/4330/scene-19px-serif-1280.png)
- Comparison notes: computed styles with the reader at 19px serif, full line length (column content width 697px quiet, 713px scene). Main: look, item, system and error text 12px (sans except look), box width 489px; arrive and move 14px in the quiet room; ambience 534px wide. This revision: every kind 19px ui-serif, every note as wide as the column (697 / 713), and in the scene each equals the pose's computed size and face. Kinds remain distinct by glyph (◎, ✦, !), box, destructive tokens, italics and the ambience hairline.
- Tested interactions: open /game with REST and socket fixtures; reach In world in a quiet room and, separately, in a scene with one pose; receive one of each note kind (look, item, system, error, arrive, move, narrative-as-ambience) as typed text frames; open Display settings in the sidebar and set Text size 19, Font Serif, Line length Full width through the controls; read computed styles and widths; then set Text size 13 and Font Sans and read them again (notes follow both ways). `e2e/feed-notes-display-settings.spec.ts` encodes this: 2 passed on this revision, 2 failed on main (`look note text` expected 19px serif, received 12px).
- Fixture/live boundary: REST and the game WebSocket are fixtures (`page.route`, `page.routeWebSocket`), the same technique as `e2e/feed-notes.spec.ts`; the server's typing of these frames is pinned by the Python tests named in #3856 and is unchanged here. The page, its hooks, the readers, `FeedNoteBlock` and `DisplaySettings` are the real built bundle. Not operated: a live game server, which this change does not touch.
- Overall outcome: PASS

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Look note text, quiet room | the reader's size and face (19px serif) | MATCH | docs/reviews/4330/quiet-room-19px-serif-1280.png; computed 19px ui-serif |
| Look note width | spans the column | MATCH | quiet 697 of 697px, scene 713 of 713px; both after screenshots |
| Item, system and error lines | the reader's size and face, full width, glyph and box kept | MATCH | docs/reviews/4330/quiet-room-19px-serif-1280.png; computed 19px ui-serif, 697px |
| Arrive, move and ambience lines | the reader's size and face, italic, ambience hairline kept | MATCH | docs/reviews/4330/quiet-room-19px-serif-1280.png; computed 19px ui-serif |
| Notes beside a pose in a scene | the same computed size and face as the pose | MATCH | docs/reviews/4330/scene-19px-serif-1280.png; pose and notes 19px ui-serif |
| Changing the settings again | notes follow to 13px sans | MATCH | spec step after the screenshot, both readers |

## Requirement ledger

| id | status | evidence | authorized decision |
|---|---|---|---|
| notes-follow-text-size | PASS | spec: every kind equals the reader's computed size at 19px and at 13px, both readers | expected behavior stated by ApostateCD on #4330 |
| notes-follow-font | PASS | spec: every kind equals the reader's computed face at serif and at sans, both readers | expected behavior stated by ApostateCD on #4330 |
| notes-fill-the-column | PASS | spec: look note width equals the column's content width at Full width, both readers | expected behavior stated by ApostateCD on #4330 |
| scene-notes-match-poses | PASS | spec: look and system text equal the pose's computed style | expected behavior stated by ApostateCD on #4330 |
| kinds-stay-distinct | PASS | after screenshots: glyphs, boxes, red error, italics, hairline | #3856 demo kept for everything but size and width |
| red-on-main | PASS | spec against main's build: 2 failed, look note 12px under a 19px reader | regression evidence for the kept spec |

## Unresolved findings

None
