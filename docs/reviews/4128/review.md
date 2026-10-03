# Review evidence

- Reviewed revision: `a3a9e814f43bf393340e7f40e4f975db5ed22c19`
- Revision note: `a3a9e814f` is `2126423f3` rebased onto main (four commits, #4106/#4126/#4123/#4117); the rebase was clean, and of the branch's files only `communication.py`, `interaction_serializers.py` and `interaction_services.py` were also touched by main (#4126), so `world.scenes.tests.test_line_rendering` (23), `test_language_interactions`, `test_interaction_serializers` and `test_interaction_services` (119 together) were re-run green on the rebased tree; no frontend file overlapped, so the screenshots stand. They were taken at the pre-rebase build (`vite build` after the review fix pass, `2126423f3`); the `demo-fidelity-reviewer` pass ran at `920282b2c` and its three findings (the avatar taller than one line, the play menu captured mid-load, "minimised" in the game guide) were fixed in `4ca071e8f` and re-shot, and the whole-branch code review's findings were fixed in `2126423f3`, after which the browser spec and the screenshots were re-run on the final bundle.
- Reviewer: `demo-fidelity-reviewer` (local agent pass, dispatched before PR open on #4128) plus a whole-branch code review (general-purpose agent, Opus) and the controller's own screenshot read
- Reviewer verdict: PASS
- Application/build identity: the real production bundle (`pnpm exec vite build` at this revision, served by `vite preview --port 4185`), the real `/game` page and component tree, rendered by real Chromium (Playwright); only the network is a fixture (`frontend/e2e/support/gameHarness.ts`: mocked `/api/**` REST and a mocked game WebSocket, plus the persona-menu endpoint)
- Environment: devcontainer, headless Chromium (`@playwright/test` 1.58), `frontend/e2e/pose-lines.spec.ts` (committed) run with a scratch config pointing at port 4185 (not committed)
- Viewports/themes: 1600x900, default light theme (`data-theme` unset; the app's own tokens); no dark-theme pass (see Unresolved findings for why that is not a finding)
- Approved design: https://claude.ai/artifact/UJtRxbmoLBGDcc9sc6f3Jj (v13, the conversation-rail demo whose feed this issue builds; the rail itself is #4129). The agent reviewer cannot open claude.ai, so it compared against the spec's own description of the demo's pose rendering (issue #4128, Decisions 1-8), which the controller, who built the demo in this session, confirmed against the artifact.
- Visual review: completed. Four real renders of the built page were read element by element against the demo's pose rendering: a three-paragraph pose at rest and under hover (`images/paragraphs-1600.png`), a folded line (`images/folded-1600.png`), the sorting menu from a held right-click (`images/menu-1600.png`), and the play menu from a left-click on the avatar with the persona items resolved (`images/play-menu-1600.png`). The layout assertions (first line starts beside the avatar, second line and last line wrap flush left, time at opacity 0 at rest and 1 on hover) are measured by the committed browser spec, not eyeballed.
- Visual verdict: PASS
- Screenshots: ![Three paragraphs, hovered](docs/reviews/4128/images/paragraphs-1600.png) ![A folded line](docs/reviews/4128/images/folded-1600.png) ![The sorting menu](docs/reviews/4128/images/menu-1600.png) ![The play menu](docs/reviews/4128/images/play-menu-1600.png)
- Comparison notes: see the screen-by-screen section below
- Tested interactions: in the browser (`pose-lines.spec.ts`, 4/4): a foreign pose delivered over the mocked WebSocket; hover over the line; quick right-click on the text (fold) and on the stub (unfold); a 500 ms held right-click on the text (menu) and Hide from it; the Show hidden button; right-click on the avatar (sorting menu), Escape, left-click on the avatar (play menu with Reply, Kudos, Look, View sheet, Mute, Block…). In jsdom: fold/unfold, per-character fold, the menu items by button and by owner, keyboard-opened menu, portaled-child events ignored, touch press, a note's Minimize all, the avatar indent markup, reference mode (no menus), American labels (199 tests across the seven touched files). On the server: `world.scenes.tests.test_line_rendering` (23, green) covering the five lead-in forms, the already-named case under a place lead-in, the colon-stripping of a whisper emote, and telnet/web parity for every form.
- Fixture/live boundary: every screenshot's pose text, persona and menu payload is a hand-built fixture fed over the mocked REST routes and WebSocket; the real reader components (`ThreadedNarrativeReader`, `PoseUnit`, `ActorLine`, `FeedBlockFrame`, `LineMenu`, `PersonaMenu`) render it. The browser proves the layout and the pointer timing jsdom cannot; it does not run a live Django backend, so the server's lead-in grammar is proven by its unit tests and the parity test, not by a screenshot of a real whisper. The telnet line is not screenshotted; the parity test is the evidence that it is the web line with `{caller}` where the name goes.
- Overall outcome: PASS

## Approved-design reference

Demo URL (issue-cited): `https://claude.ai/artifact/UJtRxbmoLBGDcc9sc6f3Jj`. The spec's Walkthrough section cites it ("the rail demo; this issue is its feed") and Decisions 1-8 record what the demo shows for a pose: one prose line, the avatar an indent with later lines wrapping back under it, the time on hover, lead-ins for the whisper emote and tabletalk, the play menu on left click and the sorting menu on right click with its exact seven items.

## Environment / render method

- Frontend build: `pnpm exec vite build` at `2126423f3`, served by `vite preview --port 4185` (a private port; another session owns 4173).
- The page: `frontend/e2e/pose-lines.spec.ts` (committed with the branch) reaches "In world" through the shared harness (`reachReadySession`), pushes `interaction` frames over the mocked WebSocket, and drives the real page with Playwright's mouse. The persona menu's server half (`/api/actions/characters/*/personas/*/menu/`) is fixtured in the spec so the play menu renders its social items.
- Screenshots were copied from `frontend/test-results/pose-lines/` into `docs/reviews/4128/images/`.

## Screen 1 · a three-paragraph pose

Demo shows: the avatar at the start of the first line, the text beside it, the second and later lines wrapping back under it, paragraph breaks kept, no header row, no bubble, a hover tint on the line, the time at the top right only on hover.

Branch renders (`images/paragraphs-1600.png`, hovered): exactly that. The spec measures it: the first text rect starts right of the avatar's box, the second rect of the first text node and the last line start left of `avatar.x + 2`; `line.locator('header')` has count 0; `pose-time` has `opacity: 0` at rest and `1` on hover. The first fidelity finding (the avatar was 24px in a 21px line, and its inline trigger sat on the baseline, so line 2 was indented too) is fixed: `PersonaAvatar` gained an `xs` size (20px) and the float span is a block flex (`PoseUnit.tsx`, `ExplorationReader.tsx`); the second-line assertion went red at 44px and green at 16px.

## Screen 2 · a folded line

Demo shows: a quick right-click folds the line to "Name · time" on a dotted underline with a hairline, with a Hide control.

Branch renders (`images/folded-1600.png`): "Nyx · 7:52 AM" dotted-underlined with the hairline and the × (aria-label Hide) at the right; the text is gone from the page (`toHaveCount(0)`), and a right-click on the stub brings it back.

## Screen 3 · the sorting menu

Demo shows: a held right-click (or a right-click on the avatar, or a long-press) opens, under a "Name · time" head, Minimize or Expand, Hide; Minimize all from Name, Hide all from Name; Minimize all, Expand all, Unhide all. No hide-everything. American "Minimize".

Branch renders (`images/menu-1600.png`): the seven items in that order, asserted by `toHaveText([...])`; Hide takes the line out and Show hidden (top right of the feed) brings it back. A right-click on the avatar opens the same menu (first item Minimize). The document-level `contextmenu` swallow covers the held press and, since the fix pass, every right press that starts on a line.

## Screen 4 · the play menu

Demo shows: a left-click on the avatar opens Reply, Kudos, then the persona menu as today (#4030), Mute and Block included.

Branch renders (`images/play-menu-1600.png`): Nyx header, Reply, Kudos, separator, Look, View sheet, separator, Mute, Block…. The second fidelity finding (the capture showed "Loading…" because the harness did not fixture the menu endpoint) is fixed by fixturing it in the spec; Mute and Block are asserted.

## Lead-ins (not screenshotted)

The spec's lead-ins are the server's: `Quietly, Nyx leans in…` for a whisper opening with `:`, `At the long table, Bram deals…` for anything posed or said at a place. `test_line_rendering` covers each form, the already-named case under a place lead-in, and parity between the telnet form (`{caller}` with `actor_name`) and the web form. The code review found the telnet path could never match an already-named pose (it passed the placeholder as the name), which is why `actor_name` exists; the parity test is the one the spec's Test seams asked for.

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Pose line | One prose line, no header row, no bubble, no role label | MATCH | `paragraphs-1600.png`; `line.locator('header')` count 0 |
| Avatar | Floated indent at the start of the first line; line 2 and later wrap flush left | MATCH | `paragraphs-1600.png`; spec `firstLineLeft > avatar right`, `secondLineLeft < avatar.x + 2`, `lastLineLeft < avatar.x + 2` |
| Paragraphs | Paragraph breaks kept | MATCH | `paragraphs-1600.png` shows three paragraphs |
| Time | Hidden at rest, top right on hover | MATCH | spec `toHaveCSS('opacity', '0')` then `'1'` after hover; "7:52 AM" in `paragraphs-1600.png` |
| Hover tint | The line under the pointer is tinted | MATCH | `paragraphs-1600.png` (hovered) shows the tint |
| Folded stub | "Name · time", dotted underline, hairline, Hide control | MATCH | `folded-1600.png` |
| Sorting menu | Minimize, Hide, Minimize all from Nyx, Hide all from Nyx, Minimize all, Expand all, Unhide all; no hide-everything | MATCH | `menu-1600.png`; spec `toHaveText([...])` |
| Show hidden | Top right of the feed while anything is hidden; restores | MATCH | spec clicks it after Hide and the text returns |
| Play menu | Reply, Kudos, then Look, View sheet, Mute, Block… | MATCH | `play-menu-1600.png`; spec asserts each |
| Spelling | Minimize, not Minimise | MATCH | `menu-1600.png`; grep of `frontend/src` finds no "Minimis" |

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| US1 | PASS | A pose reads as its sentence or paragraphs with nothing around it: `paragraphs-1600.png`; `poseRoleLabel`, the header row and the bubble are gone from `PoseUnit` | |
| US2 | PASS | Avatar at the start of the line, time on hover: spec assertions on `pose-avatar` position and `pose-time` opacity | |
| US3 | PASS | `whisper Nyx=:leans in` reads `Quietly, Nyx leans in`: `test_a_whisper_emote_reads_quietly`, `test_a_whisper_emote_glues_a_semipose` | |
| US4 | PASS | Tabletalk reads `At the long table, …`: `test_a_pose_at_a_place_opens_with_the_place`, `test_a_say_at_a_place_opens_with_the_place`, `test_a_tabletalk_payload_renders_at_its_place` | |
| US5 | PASS | Telnet and web agree for every form, including a pose that names its actor: `test_telnet_and_web_agree_on_every_form`, `test_the_telnet_placeholder_leaves_an_already_named_pose_alone` | |
| US6 | PASS | Quick right-click folds, another on the stub unfolds: spec test 2; `useLineGestures.test.tsx` | |
| US7 | PASS | Minimize all from Nyx / Hide all from Nyx act on `keysOf(persona)` over every loaded line: `FeedBlockFrame.test.tsx` "each menu item acts on the right keys"; the reader's `sorting` memo | |
| US8 | PASS | Expand all, Unhide all, Show hidden: spec test 3; `FeedBlockFrame.test.tsx`; a note's Minimize all acts on every line (`FeedNoteBlock.test.tsx`) | |
| US9 | PASS | Reply, Kudos and the persona actions one left-click away on the avatar: `play-menu-1600.png`; `PoseUnit.test.tsx`; `GamePage.test.tsx` avatar left-click reaches View sheet | |
| US10 | PASS | Long-press is the touch equivalent: `useLineGestures.test.tsx` touch tests (jsdom, with the pointer polyfill carrying `pointerType`); selection and the iOS callout are held off for the press | |
| D7 | PASS | American spelling in every label and in the guides: grep finds no "Minimis" in `frontend/src`; `game/CLAUDE.md` and `scenes.md` corrected | |
| D8 | PASS | Browser context menu suppressed at document level while ours is open and for every right press on a line: `LineMenu.tsx` swallow; `useLineGestures` one-shot swallow; test "swallowed wherever it lands" | |
| REF | PASS | A reference view gets no menus and no fold gesture: `GamePage.test.tsx` reference-mode test; `FeedBlockFrame` outside a provider renders the block as it is | |

## Notes that are not findings

No dark-theme screenshot was taken; every colour on the line is a token the app already uses (`bg-muted/40`, `text-muted-foreground`), none introduced here. The telnet line is proven by the parity test rather than a telnet capture, and the lead-ins by unit tests rather than a screenshot of a live whisper, as the Fixture/live boundary field states.

## Unresolved findings

None
