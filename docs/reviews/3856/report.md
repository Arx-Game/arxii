# Review evidence: feed filter chips, editor, wake, minimise and dismiss (#3856, PR 2 of 3)

Refs #3856 (the issue stays open for PR 3, the Actions fold).

- Reviewed revision: 5938601f1ccf92fef1d19755c4deefca41297feb
- Reviewer: Claude Fable 5.1 (implementing session), vision review of the rendered application screenshots below, plus a separate demo-fidelity review pass (a general-purpose Sonnet 5 subagent following `tools/agents/demo-fidelity-reviewer.md`, since the named agent is not registered in this session) that read the approved demo's HTML and the same eight screenshots; its checklist and findings are folded into the tables below.
- Reviewer verdict: PASS
- Application/build identity: `pnpm build` of this branch at ff5396130, whose application code is identical to the reviewed revision 5938601f1 (that commit changes one assertion in the PR 1 journey and no application file) (Vite production bundle, output `src/web/static/dist`), served by `vite preview --port 4173` exactly as `playwright.config.ts` does.
- Environment: devcontainer (Ubuntu 24.04 x64), Chrome Headless Shell 145.0.7632.6 via Playwright 1.58.2 (chromium v1208), headless, `hasTouch: true` per `playwright.config.ts`.
- Viewports/themes: 1280x800, light theme (the system default; no `data-theme` stamp).
- Approved design: issue #3856's spec, treatment A "One feed, filter chips" (demo v5, https://claude.ai/code/artifact/d802b376-8d16-4d5a-9c49-5b3c3890b5f8, approved by Dan on 2026-09-14). PR 2's scope from the spec's PR plan: the chip strip (plain labels, `+`, All at the right end), the chip editor on right-click (name, kinds with "(in X)", wake, delete), custom chips capped at three, All as the master switch with the one-line empty state, show and wake separate per chip with the "new" pill, minimise and dismiss on any block, and per-account persistence. The Actions fold is PR 3 and is not reviewed here.
- Visual review: completed on the eight screenshots below, taken from the running application (not a mockup) by `frontend/e2e/feed-chips.spec.ts`, compared against the demo's `.strip`, `.chip`, `.pop`, `.ctl` and `.stub` rendering and its `shown`/`wakes` rules.
- Visual verdict: PASS
- Screenshots: ![Screen 1, the strip at rest above the column](https://raw.githubusercontent.com/Arx-Game/arxii/5938601f1ccf92fef1d19755c4deefca41297feb/docs/reviews/3856/chips-rest-1280.png) ![Screen 2, System pressed: the look, item and error notes fold out, poses and ambience stay](https://raw.githubusercontent.com/Arx-Game/arxii/5938601f1ccf92fef1d19755c4deefca41297feb/docs/reviews/3856/chips-system-off-1280.png) ![Screen 3, All pressed: every chip dark and the one-line message](https://raw.githubusercontent.com/Arx-Game/arxii/5938601f1ccf92fef1d19755c4deefca41297feb/docs/reviews/3856/chips-all-off-1280.png) ![Screen 3, Roleplay pressed from All off: only the poses come back](https://raw.githubusercontent.com/Arx-Game/arxii/5938601f1ccf92fef1d19755c4deefca41297feb/docs/reviews/3856/chips-roleplay-only-1280.png) ![Screen 4, right-click Roleplay: the editor](https://raw.githubusercontent.com/Arx-Game/arxii/5938601f1ccf92fef1d19755c4deefca41297feb/docs/reviews/3856/chips-editor-1280.png) ![Screen 5, three custom chips and no +](https://raw.githubusercontent.com/Arx-Game/arxii/5938601f1ccf92fef1d19755c4deefca41297feb/docs/reviews/3856/chips-three-custom-1280.png) ![Screen 6, ambience arrived silently, then a pose lit Roleplay](https://raw.githubusercontent.com/Arx-Game/arxii/5938601f1ccf92fef1d19755c4deefca41297feb/docs/reviews/3856/chips-new-pill-1280.png) ![Screen 7, a pose minimised to its stub](https://raw.githubusercontent.com/Arx-Game/arxii/5938601f1ccf92fef1d19755c4deefca41297feb/docs/reviews/3856/chips-minimised-1280.png)
- Comparison notes: In `chips-rest-1280.png` the strip above the column reads Roleplay, Whispers, Movement, Ambience, System, then `+`, then All at the far right, each a plain rounded label with no glyph, dot, hint or explainer, every chip pressed (filled) and the column below holding two poses, the ambience line, the look note, the item note and the error note; the demo's strip is the same order and shape (its optional dot swatch was ruled out as decoration). `chips-system-off-1280.png` shows System unfilled and the look, item and error notes gone while the poses and the ambience line stay. `chips-all-off-1280.png` shows All and every chip unfilled and the column replaced by the demo's exact line, "Everything is switched off. Press a chip to bring one kind back."; `chips-roleplay-only-1280.png` shows Roleplay pressed alone with only the poses back and the other chips dark, the demo's "press a chip while All is off" rule. `chips-editor-1280.png` shows the popover under Roleplay: the name in a plain underlined field, a checkbox per kind (Poses, Speech and GM emits ticked), "(in Whispers)", "(in Movement)", "(in Ambience)" and "(in System)" against the kinds those chips carry, "Wake me when this arrives" ticked and separated by a rule, "Delete chip" in the danger colour, the demo's `.pop` layout; the first capture of this screen caught the popover mid fade and was retaken after a settle. `chips-three-custom-1280.png` shows Talk, Second and Third after the five defaults and no `+`. `chips-new-pill-1280.png` shows the Ambience chip without a pill after the ambience line arrived and Roleplay with a small "new" pill after a pose arrived while the window was unfocused, the demo's show-and-wake separation. `chips-minimised-1280.png` shows the first pose folded to its stub, Nyx and the clock time, in dotted underline with a rule to a × at the right, the demo's `.stub`, and the rest of the column unchanged. Differences from the demo that are not defects: the demo's chips carry a small dot swatch, ruled out; the demo shows a "new" divider inside the column, which is not in this PR's scope; the app's pressed chip is a solid primary fill with primary-foreground text rather than the demo's soft accent tint: the demo-fidelity pass measured the first build's ten percent tint at a four percent luminance difference from an unpressed chip (this theme's primary is near-black), invisible as an on/off signal, and the fill was chosen so the state reads at a glance in the app's own token language; the screenshots above are from the build with that fix. The same pass noted the name field selected on a right-click open; the editor now takes over the popover's auto-focus so only a chip just added opens with its name selected.
- Tested interactions: reach "In world" with an active scene through the shared harness; receive two poses, a narrative line, and look, item and error frames; wait for the read dwell to clear the pill; read the strip's button order; press System twice; press All, read the message, press Roleplay; right-click Roleplay, read the editor, untick Speech and see the say line stay; press `+`, see the editor focused on the new name, type a name, tick Speech, press Escape, toggle the new chip to hide and show the say line; add two more chips by name and see `+` disappear; delete Talk from its editor and see the say line stay; reload the page and see the custom chips and `+` back; receive a pose, wait for the pill to clear, receive ambience with no pill, blur the window, receive a pose and see the pill; hover a pose, minimise, read the stub, reopen; hover the error note, dismiss, see it gone with the other three notes intact. Zero page errors in the first journey (asserted).
- Fixture/live boundary: REST and the game WebSocket are mocked through `frontend/e2e/support/gameHarness.ts` (the same fixture `narrative-play-delivery.spec.ts` uses); no Django or Evennia process and no database took part. The strip, the editor, both readers, the block frame, the preference store (real `localStorage`, per account) and the CSS are the real ones; only the backend is absent. The show, wake, ownership, cap, delete and persistence rules are pinned by the unit tests named in the ledger.
- Overall outcome: PASS

## Requirement ledger

| id | status | evidence | authorized decision |
| --- | --- | --- | --- |
| strip-plain-chips-plus-all | PASS | `FeedChipStrip.test.tsx` (button order, no explainer text); `chips-rest-1280.png` | n/a |
| chip-toggles-and-hides-its-kinds | PASS | `feedChips.test.ts` show rules; `GamePage.test.tsx` "pressing Roleplay hides the poses"; `chips-system-off-1280.png` | n/a |
| all-master-switch-and-empty-line | PASS | `feedChips.test.ts` All rules; `GamePage.test.tsx` All case; `chips-all-off-1280.png`, `chips-roleplay-only-1280.png` | n/a |
| unowned-kind-still-shows | PASS | `feedChips.test.ts` "unticking a kind leaves it unowned, and an unowned kind still shows"; journey 2 (Speech unticked, the say line stays) | spec Decision 3 |
| editor-name-kinds-wake-delete | PASS | `FeedChipStrip.test.tsx` editor cases; `chips-editor-1280.png` | n/a |
| custom-chips-cap-three | PASS | `feedChips.test.ts` cap; `FeedChipStrip.test.tsx` "+ hidden at three"; `chips-three-custom-1280.png` | spec Decision 5 |
| delete-keeps-kinds | PASS | `feedChips.test.ts` delete; journey 2 | spec Decision 5 |
| show-and-wake-separate | PASS | `attention.test.ts` wake filtering and `chipUnread`; `chips-new-pill-1280.png` (ambience silent, pose lights Roleplay) | spec Decision 4 |
| wake-reaches-badges | PASS | `GameTopBar.tsx` and `GameWindow.tsx` pass `AttentionOptions` from the chips; `attention.test.ts` | n/a |
| minimise-dismiss-any-block | PASS | `FeedBlockFrame.test.tsx`; `gameSlice.test.ts` minimise/dismiss; `GamePage.test.tsx` minimise case; `chips-minimised-1280.png`; journey 4 dismisses a note | spec Decision 6 |
| persistence-per-account | PASS | `playPreferences.test.ts` round-trip and repair; `GamePage.test.tsx` writes the account key; journey 2 reload | spec Decision 9 |
| reference-view-untouched | PASS | `GameWindow.tsx`: no strip, no filtering, null block controls when `reference` is set | n/a |
| docs-in-tandem | PASS | `frontend/src/game/CLAUDE.md`, `frontend/src/store/CLAUDE.md`, `docs/systems/scenes.md` | n/a |
| actions-fold | OUT_OF_SCOPE | PR 3 of the same issue | spec: "three PRs" |

## Visual checklist

| Element | Expected | Result | Evidence |
| --- | --- | --- | --- |
| Strip order | Roleplay, Whispers, Movement, Ambience, System, +, All | MATCH | `chips-rest-1280.png` |
| Chip look | Plain rounded label, filled when on, no glyph or hint | MATCH | `chips-rest-1280.png` |
| All chip | Bold, at the right end | MATCH | `chips-rest-1280.png` |
| System pressed | Look, item, error gone; poses and ambience stay | MATCH | `chips-system-off-1280.png` |
| All pressed | Every chip dark; one italic line, the demo's wording | MATCH | `chips-all-off-1280.png` |
| One chip back from All off | Only that chip on; only its kinds shown | MATCH | `chips-roleplay-only-1280.png` |
| Editor popover | Name field, kinds with checkboxes and "(in X)", wake line, Delete chip | MATCH | `chips-editor-1280.png` |
| Three custom chips | Named chips after the defaults; + absent | MATCH | `chips-three-custom-1280.png` |
| Ambience arrival | No pill on Ambience | MATCH | `chips-new-pill-1280.png` |
| Pose arrival while away | "new" pill on Roleplay | MATCH | `chips-new-pill-1280.png` |
| Minimised block | "Name · time" stub in dotted underline, rule, × | MATCH | `chips-minimised-1280.png` |
| Composer and Here panel intact | Toolbar and nine-tab grid unchanged | MATCH | all eight |

## Unresolved findings

None
