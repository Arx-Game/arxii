# Review evidence: presence is a server fact (#4321)

- Reviewed revision: `23be0ad88ffbdf78fa3ddb28d8db8bcbe705b955`
- Reviewer: the implementing agent (Claude Fable 5.1), operating the built page through Playwright with a vision read of every screenshot
- Reviewer verdict: PASS
- Application/build identity: `pnpm --prefix frontend exec vite build` of the reviewed revision, served by `vite preview --port 4183 --strictPort`; backend `arx test --sqlite world.roster.tests.test_mine_presence` plus its neighbours on the same revision (the disconnect test autospecs the handler and hands back sessions with a sessid, per the mock-fidelity review)
- Environment: devcontainer on the solo laptop (6 GB), Chromium 1208 headless through Playwright 1.x, `frontend/playwright.scratch-4321.config.ts` (the real config minus its webServer, baseURL on 4183)
- Viewports/themes: 1280x800, light theme (the viewer's default); the chip and the Hall card use realm tokens only, so dark follows by construction and was not separately shot
- Approved design: the rulings recorded on issue #4321 (ApostateCD, 2026-10-12 and 2026-10-13): presence from the server; Return to the world joins the same character; Disconnect Character with This connection / Every connection only when there is a second session; Log Out Account and Disconnect Character as the words; the account menu from your own name in the Who tab; the form switcher hidden with nothing to switch to. No demo page: the owner waived one for copy and bug work on existing surfaces.
- Visual review: completed against the rulings on the issue, on the built page, with each screenshot read
- Visual verdict: PASS
- Screenshots: ![A fresh tab with no socket: the chip says In the world, Quiet courtyard, with Return to the world and Disconnect Character; the Hall card says In the world](docs/reviews/4321/fresh-tab-in-the-world-1280.png) ![After Disconnect Character from that tab: the request went to the disconnect endpoint, the roster list refetched, and the chip and the card say Not in the world with Enter the world](docs/reviews/4321/fresh-tab-after-disconnect-1280.png) ![With a local socket and a second session reported by the server, Disconnect Character opens the two-item choice: This connection, Every connection](docs/reviews/4321/hall-disconnect-choice-1280.png)
- Comparison notes: the chip's words, buttons and sub-line match ruling 7 (In the world plus the room, the same as for a local socket) and ruling 4 (Disconnect Character); the two-item menu matches ruling 3 and only appears in the journey whose fixture reports two sessions; the fresh-tab journey shows no menu item on the press, per ruling 3's refinement and the pending working assumption 9 (no This connection without a socket). No visual regression on the Hall's other plates.
- Tested interactions: cold load of /hall in a tab with no socket while the fixture reports one session elsewhere; Return to the world link target; Disconnect Character press from a tab without a socket (one request to POST /api/roster/entries/1/disconnect/, no menu, chip and card flip to Not in the world after the refetch); enter the world through the fixture socket, open the Hall from the world menu, press Disconnect Character with the fixture reporting two sessions, read the choice, pick Every connection (one request to the endpoint, the local socket untouched by the fixture); the pre-existing journeys (enter, Hall, Disconnect closes the socket; a fresh Hall with no session says Not in the world) still pass with the renamed control. Backend: the mine payload reports session_count 0 and room_name null out of the world, a location without a session is not presence, two faked sessions report 2 and the room; the endpoint closes every session with reason quit, reports what it closed, treats nothing-to-close as success, and refuses a stranger's character without touching the session handler.
- Fixture/live boundary: REST and the game WebSocket are fixtures (`page.route`, `page.routeWebSocket`), the same technique as the file's #3859 journeys: the fixture's mine payload plays the server's presence, and after a disconnect it reports the sessions gone the way the server would. The server side of that is proven by the backend tests on the real serializer, view and session handler (`src/world/roster/tests/test_mine_presence.py`, 7 tests, OK), not by the journeys. Not operated live: two real browser contexts against a running game server on this laptop (BLOCKED: resources; the dev stack and a Chromium pair do not fit beside the build in 6 GB), so the end-to-end proof that one tab's disconnect closes the other tab's socket rests on the backend test of the quit reason plus the client's existing, pinned handling of that reason (`src/web/tests/test_quit_close_reason_parity.py`). The Who tab's account menu and the hidden form switcher are proven by component tests on the real components (`PresencePanel.test.tsx`, `FormSwitcher.test.tsx`), not shot here.
- Overall outcome: PASS

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Header chip sub-line, fresh tab | In the world, Quiet courtyard, from the server's room_name | MATCH | docs/reviews/4321/fresh-tab-in-the-world-1280.png, chip at top left |
| Header chip buttons, fresh tab | Return to the world and Disconnect Character, no Enter the world | MATCH | docs/reviews/4321/fresh-tab-in-the-world-1280.png |
| Hall docked card meta line, fresh tab | In the world | MATCH | docs/reviews/4321/fresh-tab-in-the-world-1280.png, Your Characters band |
| Chip and card after Disconnect Character from the fresh tab | Not in the world, Enter the world, no Disconnect button | MATCH | docs/reviews/4321/fresh-tab-after-disconnect-1280.png |
| Disconnect Character with a local socket and a second session | A two-item menu, This connection then Every connection | MATCH | docs/reviews/4321/hall-disconnect-choice-1280.png |
| Disconnect Character from a tab without a socket | A plain press, no menu | MATCH | the fresh-tab journey asserts zero menu items on the press; docs/reviews/4321/fresh-tab-after-disconnect-1280.png shows the result |

## Requirement ledger

| id | status | evidence | authorized decision |
|---|---|---|---|
| presence-from-server | PASS | fresh-tab journey and `test_in_the_world_from_two_tabs` (session_count 2, room_name) | ruling 1 and 7 on #4321 |
| return-joins-same-character | PASS | Return to the world links to /game; GamePage's mount connect opens a socket on the selected character (MULTISESSION_MODE 3 joins, unchanged) | ruling 2 on #4321 |
| disconnect-choice-only-with-two | PASS | two-session journey shows the menu; one-session journey and the chip's component tests show the plain press | ruling 3 on #4321 |
| disconnect-everywhere-endpoint | PASS | `DisconnectEverywhereTests` (4 tests): every session closed with reason quit, count reported, stranger refused | technical design on #4321 |
| copy-log-out-account-disconnect-character | PASS | GameTopBar.menu, ProfileDropdown and chip component tests assert the new names and the absence of the old | ruling 4 and 6 on #4321 |
| who-tab-account-menu | PASS | `PresencePanel.test.tsx`: own row opens the account menu with Profile, Create Character, Log Out Account; another row keeps the persona menu | ruling 8 on #4321 |
| form-switcher-hidden | PASS | `FormSwitcher.test.tsx`: empty with no alternate self, drawn with one | ruling 5 on #4321 |
| front-door-redirect-unchanged | PASS | GatefoldPage untouched; the fresh-tab journey loads /hall directly and is not redirected | working assumption 10 on #4321 |
| live-two-browser-proof | OUT_OF_SCOPE | not operable on this laptop beside the build; covered by the backend quit-reason test and the client's pinned handling of that reason | BLOCKED: resources, stated in the PR verification for the maintainer's call |

## Unresolved findings

None
