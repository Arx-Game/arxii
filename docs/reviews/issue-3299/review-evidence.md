# Review evidence: #3299 player channels

- Reviewed revision: `f20635cc04ac7e178fc408044b3c587e434089b0`
- Reviewer: coordinator agent for #3299 (Claude Opus 5.5, read every screenshot below with vision; no demo exists for this issue, so there is no demo-fidelity comparison)
- Reviewer verdict: PASS
- Application/build identity: production bundle built with `pnpm --dir frontend build` at f20635cc04ac7e178fc408044b3c587e434089b0, served by Evennia on :4001 from the feature-3299 worktree
- Environment: shared devcontainer, throwaway Postgres database rt_3299 (tools/build_schema.py + seed_test_account + integration_tests.live_seeds.seed_channels_spec), Chromium 1208 headless via Playwright 1.65; database dropped afterwards
- Viewports/themes: 1280x720 and 1280x800 desktop, 390x844 phone; light theme
- Approved design: spec in the #3299 issue body (decision 7: Channels lane in the right-hand play surface plus a standalone page) and the coordinator-approved placement as a right-hand PlaySidebar "Channels" mode; no demo page
- Visual review: completed against the spec's lane, controls, divider and identity rules
- Visual verdict: PASS
- Screenshots: ![Public joined](docs/reviews/issue-3299/channels-02-public-joined.png) ![Posted](docs/reviews/issue-3299/channels-03-public-posted.png) ![Muted after reload](docs/reviews/issue-3299/channels-04-public-muted-after-reload.png) ![Collapsed](docs/reviews/issue-3299/channels-05-public-collapsed.png) ![Org joined](docs/reviews/issue-3299/channels-06-org-joined.png) ![Play sidebar](docs/reviews/issue-3299/channels-07-play-sidebar-channels.png) ![Live push in play sidebar](docs/reviews/issue-3299/channels-08-live-push-play-sidebar.png) ![Live on /channels, phone](docs/reviews/issue-3299/channels-09-live-push-channels-page-phone.png)
- Comparison notes: no demo; compared against the spec text. Speakers render as character names only (Linnea Channelwright, Odo Brightwater); the blocked player's line renders as a "1 hidden" divider with no name or text; channel lines never appear in the center IC feed or the left conversation rail, only in the sidebar's Channels mode and on /channels.
- Tested interactions: log in; join Public from "Join a channel"; pick "Speak as"; post; reload and read back; Mute on, reload, still on; Collapse, reload, still collapsed; join The Lantern Guild; open /game and switch the sidebar to Channels; a second session of the account posts over telnet (`channel public=...`) while the page is open and the line appears without reload in the /game sidebar and on /channels at phone width; telnet `channel`, `channel as public`, `pub hello` (stale Evennia alias, answers "not available") and `@channel public=...` (reaches the new command)
- Fixture/live boundary: live server and real Postgres for every request and websocket frame; rows come from test factories in a throwaway database; the browser drove the real UI; telnet over the real :4000 socket
- Overall outcome: PASS

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| lane-out-of-ic | PASS | channels-07 and channels-08: lanes only in the right sidebar's Channels mode; the center feed shows only room text | coordinator approval 2026-11-12 (PlaySidebar mode) |
| identity-not-account | PASS | channels-03, channels-08: speakers are character names; spec asserts the other accounts' names appear nowhere | spec decision 2 |
| blocked-divider | PASS | channels-02, channels-03: "1 hidden" divider where the blocked player's line is | spec decision 5 |
| controls-persist | PASS | channels-04 (Mute on after reload), channels-05 (collapsed after reload) | spec story 3 |
| org-channel | PASS | channels-06: The Lantern Guild lane after join, identity limited to the member character | spec decisions 2-3 |
| live-push | PASS | channels-08 (/game sidebar) and channels-09 (/channels, phone, polling without a socket): the telnet post appears without reload | spec decision 7 |
| telnet | PASS | session transcript in the PR Verification section | spec design (telnet command) |

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Channels sidebar mode | Third mode button "Channels" beside Here and History; lanes stacked | MATCH | channels-07, channels-08 |
| Lane header | Channel name, collapse chevron, settings button | MATCH | channels-03, channels-06 |
| Hidden divider | Centered "1 hidden" rule, no author or text | MATCH | channels-02, channels-03 |
| Settings popover | Speak as, Mute, Collapse, Notifications, Move up/down, Leave; no captions | MATCH | channels-04 |
| Newest message in view | Lane scrolled to the newest line after a live arrival | MATCH | channels-08, channels-09 |
| Phone width | Lane and composer fit 390px with no horizontal scroll | MATCH | channels-09 |

## Unresolved findings

None
