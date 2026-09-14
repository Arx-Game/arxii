# Review evidence: feed word-wrap (#3862)

Closes #3862.

- Reviewed revision: 2163fa019e44d15c241bba3c5959297e6248091f
- Reviewer: Claude Fable 5.1 (implementing session), vision review of the rendered application screenshots below. The `demo-fidelity-reviewer` agent was not dispatched: the issue carries no demo page, and its approved design is the written rule in the issue body (a bug fix, not a designed surface).
- Reviewer verdict: PASS
- Application/build identity: `pnpm build` of this branch at 2163fa019 (Vite production bundle, 4029 modules, output `src/web/static/dist`), served by `vite preview --port 4173` exactly as the Playwright config does.
- Environment: devcontainer (Ubuntu 24.04 x64), Chrome Headless Shell 145.0.7632.6 via Playwright 1.58.2 (chromium v1208), headless, `hasTouch: true` per `playwright.config.ts`.
- Viewports/themes: 1280x800 and 1040x720, light theme (the system default; no `data-theme` stamp).
- Approved design: issue #3862, "Design direction": every message body in the feed wraps at the boundary where it would meet the side panel; no horizontal scroll in the feed, ever; the rule lives once on the shared body wrapper; the composer textarea wraps the same input.
- Visual review: completed on the four screenshots below, taken from the running application (not a mockup) by `frontend/e2e/feed-wrap.spec.ts`.
- Visual verdict: PASS
- Screenshots: ![After, 1280 wide: the 500-character pose wraps inside its card](docs/reviews/3862/after-1280.png) ![After, 1280 wide: the same run typed into the composer wraps in the textarea](docs/reviews/3862/after-1280-composer.png) ![Before, 1280 wide: the rule removed by an injected style, the pose runs under the side panel](docs/reviews/3862/before-1280.png) ![After, 1040 wide: an unbroken run mixed with ordinary words wraps at the narrower column](docs/reviews/3862/after-1040.png)
- Comparison notes: In `after-1280.png` the pose body breaks into seven lines inside the pose card, the card stays inside the story pane, and the Here panel on the right is untouched; the pane shows no horizontal scrollbar. In `before-1280.png`, produced by injecting `overflow-wrap: normal !important` on the wrapper (the only rule this change adds), the identical pose is one line that runs past the pane's right edge and under the Here panel: the production failure shape. `after-1040.png` shows the mixed body (run, ordinary words, run) wrapping at the narrower column with the ordinary words breaking at spaces as before. `after-1280-composer.png` shows the same run typed into the composer wrapping within the textarea.
- Tested interactions: open `/game` and reach the "In world" state (room_state and puppet_changed over the mocked socket); receive a pose of 500 unbroken characters from another character over the socket; measure the pose text's rightmost client rect against the story pane's right edge (0 px or less of overflow); measure the document's and the pane's horizontal scroll range (0); type the same run into the composer and measure its scroll range (0); inject a style removing the wrap rule and measure again (overflow of more than 50 px, proving the assertions measure this rule); repeat the pose at 1040x720.
- Fixture/live boundary: REST (`/api/user/`, `/api/roster/entries/mine/`, `/api/interactions/`, `/api/magic/character-resonances/`) and the game WebSocket are mocked with `page.route` and `page.routeWebSocket`, following `game-entry.spec.ts` and `narrative-play-delivery.spec.ts`. No Django or Evennia process and no database took part. The rendered bundle, the reader components, and the CSS are the real ones; only the backend is absent.
- Overall outcome: PASS

## Requirement ledger

| id | status | evidence | authorized decision |
| --- | --- | --- | --- |
| wrap-unbroken-run | PASS | `feed-wrap.spec.ts` test 1: pose overflow measured at 0 px or less; `after-1280.png` | n/a |
| no-horizontal-scroll | PASS | `feed-wrap.spec.ts` test 1: document and story-pane scroll range 0; `after-1280.png` | n/a |
| rule-lives-once | PASS | `FormattedContent.tsx` carries `[overflow-wrap:anywhere]`; `EvenniaMessage.tsx` carries the same class for the frames it renders without the wrapper; `FormattedContent.test.tsx` and `EvenniaMessage.test.tsx` pin both | n/a |
| composer-wraps | PASS | `feed-wrap.spec.ts` test 1: textarea scroll range 0 after filling the run; `after-1280-composer.png` | n/a |
| sensitivity | PASS | `feed-wrap.spec.ts` test 1: with the rule removed the overflow exceeds 50 px; `before-1280.png` | n/a |
| narrow-viewport | PASS | `feed-wrap.spec.ts` test 2 at 1040x720; `after-1040.png` | n/a |
| unit-mechanism | PASS | `vitest run` on `FormattedContent.test.tsx` and `EvenniaMessage.test.tsx`: 13 passed; `PoseUnit.test.tsx` and `ExplorationReader.test.tsx`: 35 passed | n/a |
| docs-in-tandem | PASS | `frontend/src/components/CLAUDE.md` gains the FormattedContent entry naming the rule's home; `frontend/src/game/CLAUDE.md` updates the EvenniaMessage entry | n/a |

## Visual checklist

| Element | Expected | Result | Evidence |
| --- | --- | --- | --- |
| Pose body at 1280 | Breaks into several lines inside the pose card, never past the card | MATCH | `after-1280.png`: seven wrapped lines of x inside the grey card |
| Pose card at 1280 | Sits inside the story pane, clear of the Here panel | MATCH | `after-1280.png`: card right edge well left of the sidebar |
| Story pane at 1280 | No horizontal scrollbar | MATCH | `after-1280.png`: none rendered; measured scroll range 0 |
| Here panel at 1280 | Untouched by the pose | MATCH | `after-1280.png`: tabs, room, characters, exits all in place |
| Composer textarea | The typed run wraps inside the textarea | MATCH | `after-1280-composer.png`: run wraps within the editor |
| Before state | With the rule removed, the pose runs under the side panel | MATCH | `before-1280.png`: one line of x crossing into the Here panel |
| Pose body at 1040 | Mixed body wraps at the narrower column, words break at spaces | MATCH | `after-1040.png`: five lines, "then ordinary words" on its own break |

## Unresolved findings

None
