# Review evidence: #3758 Narrative play shell

- Reviewed revision: `506cef41f10aa7da2d224066e07ec6ceda3066ab`
- Reviewer: `narrative-play-shell-reviewer` (independent implementation and visual review agent)
- Reviewer verdict: PASS
- Application/build identity: Arx II frontend `/game`, Vite production build from the reviewed revision
- Environment: Playwright Chromium 145, local Vite preview on Linux container; fixture API and WebSocket routes are limited to the existing `frontend/e2e/game-entry.spec.ts` journey
- Viewports/themes: desktop 1280x720 light and dark themes; 960x800 breakpoint; mobile 320x800 light theme with touch Sidebar pane; 200% document zoom at 320px; DPR 1
- Approved design: Approved #3758 structured narrative play shell specification and narrative-play design study; the shell uses Here-first exploration, room-confirmed entry, typed ambient notices, and a persistent composer
- Visual review: The live `/game` journey entered the quiet courtyard, preserved the draft, rendered the room description and Here sidebar, kept the composer visible, and showed the mobile pane switch and 200% layout without horizontal clipping.
- Visual verdict: PASS
- Screenshots: ![Desktop quiet room](docs/reviews/assets/3758/desktop.png) ![Desktop dark theme](docs/reviews/assets/3758/dark-desktop.png) ![960 breakpoint](docs/reviews/assets/3758/960.png) ![Mobile Sidebar touch](docs/reviews/assets/3758/mobile-sidebar.png) ![Dark breakpoint](docs/reviews/assets/3758/dark.png) ![200 percent zoom](docs/reviews/assets/3758/zoom-200.png) ![Scene aftermath](docs/reviews/assets/3758/aftermath.png)
- Comparison notes: The desktop frame shows the wide reading measure, quiet-room prose, Here-first sidebar, structured room facts, and composer. The mobile frame shows a 320px Sidebar pane. The zoom frame shows the reader and composer remain usable at 200%. The report covers both themes, the 960px breakpoint, touch and keyboard pane switching, 200% zoom, and the scene aftermath transition.
- Tested interactions: Entered `/game`; typed and preserved a draft; verified Send is disabled before `room_state`; sent `@ic` with keyboard Control+Enter; delivered a `room_state`; verified In world, room heading, enabled Send, no raw `puppet_changed`; switched to Sidebar and Story panes using keyboard Enter and touchscreen taps at 320px; asserted visible tab controls have 44px targets and accessible names; captured 960px, dark, 200% zoom, and aftermath states.
- Fixture/live boundary: These screenshots are from the actual `/game` production bundle with fixture API/WebSocket responses. No demo screenshots are included. The local HTML fallback is separately labeled and is not used as acceptance evidence.
- Overall outcome: PASS

|id|status|evidence|authorizeddecision|
|---|---|---|---|
|quiet-room|PASS|`docs/reviews/assets/3758/desktop.png` shows confirmed room prose and quiet exploration|Approved #3758 specification|
|here-first|PASS|`docs/reviews/assets/3758/desktop.png` shows Here selected and room facts beside the reader|Approved #3758 specification|
|mobile-pane|PASS|`docs/reviews/assets/3758/mobile-sidebar.png` captured at 320x800 with Sidebar pane|Approved #3758 specification|
|zoom|PASS|`docs/reviews/assets/3758/zoom-200.png` captured after 200% document zoom|Approved #3758 specification|
|draft-entry|PASS|`frontend/e2e/game-entry.spec.ts` verifies draft preservation before and after room confirmation|Approved #3758 specification|
|dark-theme|PASS|`docs/reviews/assets/3758/dark-desktop.png` captures the dark shell with readable Start Scene and Send controls|Approved #3758 specification|
|breakpoint-960|PASS|`docs/reviews/assets/3758/960.png` captures the 960px desktop breakpoint|Approved #3758 specification|
|aftermath|PASS|`docs/reviews/assets/3758/aftermath.png` shows the scene-ended status while Here remains available|Approved #3758 specification|
|touch-keyboard-a11y|PASS|`frontend/e2e/game-entry.spec.ts` exercises touchscreen taps, keyboard Enter, accessible names, and 44px tabs|Approved #3758 specification|

## Visual checklist

|element|expected|result|evidence|
|---|---|---|---|
|quiet-reader|Room name and description occupy a calm wide reading column|MATCH|`docs/reviews/assets/3758/desktop.png`|
|here-sidebar|Here is the primary contextual sidebar with room facts|MATCH|`docs/reviews/assets/3758/desktop.png`|
|mobile-navigation|Story and Sidebar panes remain reachable at 320px|MATCH|`docs/reviews/assets/3758/mobile-sidebar.png`|
|large-text|Reader and composer remain usable at 200%|MATCH|`docs/reviews/assets/3758/zoom-200.png`|
|dark-theme|Dark shell controls remain readable|MATCH|`docs/reviews/assets/3758/dark-desktop.png`|
|breakpoint|The 960px shell uses the desktop composition|MATCH|`docs/reviews/assets/3758/960.png`|
|aftermath|Ended scenes retain room context and next-choice affordances|MATCH|`docs/reviews/assets/3758/aftermath.png`|
|accessibility|Touch and keyboard pane controls are reachable and named|MATCH|`frontend/e2e/game-entry.spec.ts`|

## unresolved findings

- None
