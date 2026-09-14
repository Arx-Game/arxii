# Review evidence: header chip reads live presence (#3859)

Closes #3859.

- Reviewed revision: ba0084907bd01aa60d6b8d4ec3a6bcad8d1c5e19
- Reviewer: Claude Fable 5.1 (implementing session), vision review of the rendered application screenshots below. The `demo-fidelity-reviewer` agent was not dispatched: the issue carries no demo page; its approved design is the written direction in the issue body and the ADR-0295 model it cites.
- Reviewer verdict: PASS
- Application/build identity: `pnpm build` of this branch at ba0084907 (Vite production bundle, output `src/web/static/dist`), served by `vite preview --port 4173` exactly as the Playwright config does.
- Environment: devcontainer (Ubuntu 24.04 x64), Chrome Headless Shell 145.0.7632.6 via Playwright 1.58.2 (chromium v1208), headless, `hasTouch: true` per `playwright.config.ts`.
- Viewports/themes: 1280x800, light theme (the system default; no `data-theme` stamp).
- Approved design: issue #3859, "Design direction": while the active character has a live session the chip reads as in the world and its button is a return, not an entry, with "Leave the world" reachable from outside `/game`; with no live session, the entry affordance with real presence wording instead of the placeholder; closing the tab already unpuppets and needs nothing; the chip follows the Folio design system.
- Visual review: completed on the three screenshots below, taken from the running application (not a mockup) by `frontend/e2e/selected-character-chip.spec.ts` along the journey Dan hit on production: enter the world on `/game`, open the Hall from the world menu.
- Visual verdict: PASS
- Screenshots: ![Hall opened from inside the world: the chip reads In the world, Quiet courtyard, with Return to the world and Leave the world; the characters card reads In the world](docs/reviews/3859/hall-live-1280.png) ![After pressing Leave the world: the chip reads Not in the world with Enter the world, the Leave button is gone, and the card reads Not in the world](docs/reviews/3859/hall-after-leave-1280.png) ![A cold Hall load with no session: Enter the world and Not in the world](docs/reviews/3859/hall-no-session-1280.png)
- Comparison notes: `hall-live-1280.png` is the state the old chip got wrong. The header chip now reads "as Tehom · In the world, Quiet courtyard", the primary Folio button is "Return to the world" and a secondary outlined "Leave the world" sits beside it; the Hall's "Your Characters" card, one screen below, reads "In the world" instead of "Playing: Currently Offscreen". `hall-after-leave-1280.png` shows the same page after one press of "Leave the world": the chip reads "Not in the world", the button is "Enter the world", the Leave button is gone, the card reads "Not in the world", and the character stays selected (name, portrait and switcher unchanged, "Clear Active Character" untouched). `hall-no-session-1280.png` is a cold load of `/hall` with no session and is pixel-identical to the after-leave state, which is the point: leaving returns the page to the no-session truth. Both chip layouts keep the squared, tracked-uppercase Folio button and the small-caps name; no realm-token colours changed.
- Tested interactions: open `/game` and reach "In world" (room_state and puppet_changed over the mocked socket); open the world menu and choose "Your characters", a client-side navigation that keeps the module-scope socket open (ADR-0295); read the chip and the card over the live session; press "Leave the world" and assert the page closed that character's socket (`WebSocketRoute.onClose`), that the chip and card flipped to the no-session state, and that the selection stayed; cold-load `/hall` with no session.
- Fixture/live boundary: REST (`/api/user/` with `selected_entry`, `/api/roster/entries/mine/`, `/api/interactions/`, `/api/magic/character-resonances/`; every other endpoint 404) and the game WebSocket are mocked with `page.route` and `page.routeWebSocket`, following `game-entry.spec.ts`. No Django or Evennia process and no database took part; the server-side unpuppet on socket close is Evennia's existing behaviour and is not exercised here. The rendered bundle, the header, the chip, the Hall and the store are the real ones.
- Overall outcome: PASS

## Requirement ledger

| id | status | evidence | authorized decision |
| --- | --- | --- | --- |
| live-reads-in-world | PASS | `selected-character-chip.spec.ts` journey 1: header text "In the world, Quiet courtyard"; `hall-live-1280.png` | n/a |
| live-button-is-return | PASS | journey 1: link "Return to the world" to `/game`, no "Enter the world" link; `hall-live-1280.png` | n/a |
| leave-reachable-outside-game | PASS | journey 1: "Leave the world" button in the header on `/hall`; pressing it closes the socket (`onClose` observed) | n/a |
| leave-keeps-selection | PASS | journey 1: after leaving, the chip still shows Tehom and the switcher; unit test "Leave the world closes that character's socket and nothing else" (`selectMutate` never called) | n/a |
| no-session-wording | PASS | journey 2 and post-leave: "Enter the world" and "Not in the world"; no "Currently Offscreen" anywhere; `hall-no-session-1280.png` | n/a |
| hall-card-agrees | PASS | journey 1: the characters card reads "In the world" then "Not in the world"; `CharactersBand.test.tsx` live-session case | n/a |
| degraded-states-kept | PASS | `SelectedCharacterChip.test.tsx` CAPTURED and DEAD cases; `CharactersBand.test.tsx` CAPTURED/DEAD/RETIRED/UNKNOWN cases | n/a |
| unit-tests | PASS | `vitest run` on `SelectedCharacterChip.test.tsx`, `Header.test.tsx`, `CharactersBand.test.tsx`: 31 passed | n/a |
| docs-in-tandem | PASS | `frontend/src/components/CLAUDE.md` gains the chip entry; the band's and the helper's doc comments describe the store-backed line | n/a |

## Visual checklist

| Element | Expected | Result | Evidence |
| --- | --- | --- | --- |
| Chip sub-line, live | "as Tehom · In the world, Quiet courtyard" | MATCH | `hall-live-1280.png`, header left |
| Chip primary button, live | Squared uppercase "Return to the world" with the door icon | MATCH | `hall-live-1280.png` |
| Chip secondary button, live | Outlined uppercase "Leave the world" beside the primary | MATCH | `hall-live-1280.png` |
| Characters card meta, live | "In the world" | MATCH | `hall-live-1280.png`, Your Characters plate |
| Chip after Leave | "Not in the world", "Enter the world", no Leave button, name and portrait unchanged | MATCH | `hall-after-leave-1280.png` |
| Characters card meta after Leave | "Not in the world" | MATCH | `hall-after-leave-1280.png` |
| Cold Hall, no session | Identical to the after-leave state | MATCH | `hall-no-session-1280.png` |
| Folio styling | Small-caps Cinzel name, squared tracked-uppercase button, token colours | MATCH | all three screenshots |

## Unresolved findings

None
