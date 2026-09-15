# Review evidence: the composer poses by default, a slash escapes to a command, and staff get a Commands mode with a console (#3857)

Closes #3857.

- Reviewed revision: 945d36d5aa3253f7499b55aa5ef12714ddab85bf
- Reviewer: Claude Fable 5.1 (implementing session), vision review of the rendered application screenshots below, plus a demo-fidelity review pass (a general-purpose Sonnet 5 subagent following `tools/agents/demo-fidelity-reviewer.md`, since the named agent is not registered in this session) that read the approved demo's HTML, the same screenshots and the code; its first pass returned FAIL with three findings, all folded in at commit 49f709c8e (see the comparison notes), and the screenshots below were retaken after that fold-in.
- Reviewer verdict: PASS
- Application/build identity: `pnpm build` of this branch at the reviewed revision (Vite production bundle, output `src/web/static/dist`), served by `vite preview --port 4173` exactly as `playwright.config.ts` does.
- Environment: devcontainer (Ubuntu 24.04 x64), Chrome Headless Shell 145.0.7632.6 via Playwright 1.58.2 (chromium v1208), headless, `hasTouch: true` per `playwright.config.ts`.
- Viewports/themes: 1280x800, light theme (the system default; no `data-theme` stamp).
- Approved design: issue #3857's spec (demo v1, https://claude.ai/code/artifact/08ec05c7-e750-4819-80b7-47b7b0a99d06, built from Dan's design direction, which carries `spec:approved`; approved 2026-09-14). Five screens: a plain line poses; `/look` is a command; staff see Commands after a rule and a Console control; Commands mode sends as typed and the answer opens the console; a mistyped command answers in the console, never the column.
- Visual review: completed on the three screenshots below, taken from the running application (not a mockup) by `frontend/e2e/composer-commands.spec.ts`, compared against the demo's composer, its selector menu, its `.sheet` console with the `.in` echo line and its header controls.
- Visual verdict: PASS
- Screenshots: ![A player's composer in a scene: the selector reads Pose, the formatting controls present, "/look" typed and the look note already in the column](https://raw.githubusercontent.com/Arx-Game/arxii/945d36d5aa3253f7499b55aa5ef12714ddab85bf/docs/reviews/3857/composer-slash-1280.png) ![A staff composer with the selector open: Pose, Say, Emit, Whisper, a rule, Commands; a Console control in the toolbar](https://raw.githubusercontent.com/Arx-Game/arxii/945d36d5aa3253f7499b55aa5ef12714ddab85bf/docs/reviews/3857/composer-staff-menu-1280.png) ![Commands mode with the console open beside the play surface: the @dig line echoed after a chevron, the server's two lines under it in monospace, Clear and Close in the header, the composer in the monospace face with no formatting controls](https://raw.githubusercontent.com/Arx-Game/arxii/945d36d5aa3253f7499b55aa5ef12714ddab85bf/docs/reviews/3857/composer-console-1280.png)
- Comparison notes: In `composer-slash-1280.png` the selector reads "Pose" on a fresh connection with nothing chosen, the formatting controls and the entrance star are present, the box holds "/look", and the look note "Quiet courtyard / Rain rests on the stones." sits in the column from the earlier `/look`: the demo's screens 1 and 2. No Commands entry and no Console control for a player. `composer-staff-menu-1280.png` shows the staff selector open with Pose, Say, Emit, Whisper, a hairline rule, then Commands, and the Console control between the formatting controls and the companion selector: screen 3. `composer-console-1280.png` shows Commands mode: the selector reads Commands, the formatting controls and the scene controls are gone, the box carries the placeholder "A staff command, sent as typed" in the monospace face, and the console sheet stands at the right with the play surface undimmed and unblurred beside it, its serif title, the subtitle, Clear and Close as text controls, the sent `@dig` line muted after a chevron and the server's two answers under it in monospace: screens 4 and 5's surface. The demo-fidelity pass found the first build rendering the sheet modal with a dimming overlay over the whole page, no echo of the sent line, and an icon-only Close; all three were changed at 49f709c8e and the screenshot retaken. Differences from the demo that are not defects: the demo colours a successful answer green and the app does not, since the server does not mark success; the subtitle ends in a full stop.
- Tested interactions: as a player, reach "In world" with an active scene through the shared harness; read "Pose" on the selector; type a plain line and see it reach the pose endpoint as prose, never the socket; open the selector and see no Commands; type `/look` and see `look` on the socket, then the look note in the column; type `//shrugs` and see `/shrugs` posed. As staff (the harness's `staff` option): open the selector and see Commands after a rule; pick it and see the formatting controls gone and the Console control present; type an `@dig` line and see it on the socket as typed with `console: true`; receive two tagged frames and see the sheet open with the echo and both lines while no feed note appears; press Close and see it gone; type a mistyped line, receive a tagged error frame and see the sheet reopen with it while no error note appears in the column; press Clear and read the empty line. Zero page errors (asserted in both journeys).
- Fixture/live boundary: REST and the game WebSocket are mocked through `frontend/e2e/support/gameHarness.ts` (the same fixture `narrative-play-delivery.spec.ts` uses), with the pose endpoint answered by the journey itself; no Django or Evennia process and no database took part, so the server-side tagging is covered by `web/tests/test_console_capture.py` (7 tests, SQLite tier) rather than the journey. The composer, the selector, the sheet, the readers, the store and the CSS are the real ones.
- Overall outcome: PASS

## Requirement ledger

| id | status | evidence | authorized decision |
| --- | --- | --- | --- |
| pose-by-default-on-fresh-connection | PASS | `GamePage.test.tsx` "a fresh connection poses what is typed instead of sending it verbatim"; `CommandInput.test.tsx` "picking a mode works before any mode was set"; `composer-slash-1280.png`; journey screen 1 | spec Decision 1 |
| slash-escapes-to-a-command | PASS | `CommandInput.test.tsx` "/ is sent as the command after the slash", "/ in say mode is still a command", "/ line in a scene goes over the socket, never to the pose endpoint"; journey screen 2 | spec Decision 2 |
| double-slash-poses-a-literal-slash | PASS | `CommandInput.test.tsx` "// poses a literal slash", "// in a scene poses a literal slash through the pose endpoint"; journey screen 2 | spec Decision 2 |
| known-verbs-still-pass-through | PASS | `CommandInput.test.tsx` in-scene case (`page Nyx=...` verbatim) | spec Decision 2 |
| commands-mode-staff-only-after-a-rule | PASS | `ModeSelector.test.tsx`; `CommandInput.test.tsx` "offers Commands in the selector for staff only"; `composer-staff-menu-1280.png` | spec Decision 3 |
| commands-mode-sends-as-typed | PASS | `CommandInput.test.tsx` "in Commands mode every line goes through sendConsole as typed, with the formatting hidden"; `useGameSocket.test.ts` "sendConsole flags the text frame"; journey screen 4 | spec Decision 3 |
| server-tags-console-output | PASS | `web/tests/test_console_capture.py` (inputfunc flag set and cleared, `data_out` tagging of string and tuple frames, `type` kept, untagged outside the window) | spec, console tagging paragraph |
| console-lines-never-in-the-column | PASS | `useGameSocket.test.ts` "a text frame tagged console becomes a console line, never a note"; `gameSlice.test.ts` (bounded at 500, never unread); journey screens 4 and 5 (`feed-note` count 0) | spec Decision 4 |
| console-is-the-apps-own-sheet-beside-the-play-surface | PASS | `StaffConsole.test.tsx` "sits beside the play surface: no dimming overlay, and the page stays reachable"; `composer-console-1280.png` | spec Decision 4; demo ruling "Not a terminal bolted on" |
| console-echoes-the-sent-line | PASS | `StaffConsole.test.tsx` "echoes the sent line above its answers, muted, and never counts it as new"; `useGameSocket.test.ts` echo dispatch; `composer-console-1280.png` | demo screen 4 |
| console-opens-itself-and-can-close | PASS | `StaffConsole.test.tsx` "opens itself when a line arrives while Commands mode is active", "stays closed once closed, until the next line arrives"; journey screen 5 | spec screen 5 |
| console-control-counts-unseen-answers-and-clear-empties | PASS | `StaffConsole.test.tsx` count and Clear cases; journey screen 5 | spec screen 5 |
| players-composer-not-busier | PASS | `composer-slash-1280.png` (no Commands, no Console control for a player) | spec Decision 5 |
| docs-in-tandem | PASS | `frontend/src/game/CLAUDE.md`, `hooks/CLAUDE.md`, `store/CLAUDE.md`, `docs/systems/scenes.md`, `src/server/CLAUDE.md` in this branch | n/a |
| where-a-players-command-output-renders | OUT_OF_SCOPE | #3856 owns the typed notes in the column; this branch only relies on them | spec Decision 6 |

## Visual checklist

| Element | Expected | Result | Evidence |
| --- | --- | --- | --- |
| Selector on a fresh connection | Reads Pose | MATCH | `composer-slash-1280.png` |
| Player's composer | Formatting controls, entrance star, no Commands, no Console | MATCH | `composer-slash-1280.png` |
| Look note from `/look` | In the column as a boxed look note | MATCH | `composer-slash-1280.png` |
| Staff selector menu | Pose, Say, Emit, Whisper, a rule, Commands | MATCH | `composer-staff-menu-1280.png` |
| Console control | In the toolbar for staff | MATCH | `composer-staff-menu-1280.png` |
| Commands mode composer | Formatting and scene controls gone, monospace box, "sent as typed" placeholder | MATCH | `composer-console-1280.png` |
| Console sheet | At the right, play surface undimmed beside it | MATCH | `composer-console-1280.png` |
| Console header | Serif title, subtitle, Clear and Close text controls | MATCH | `composer-console-1280.png` |
| Console lines | Sent line muted after a chevron, answers under it in monospace | MATCH | `composer-console-1280.png` |

## Unresolved findings

None
