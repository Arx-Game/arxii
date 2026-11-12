# Review evidence: #3299 player channels (rework after owner review)

- Reviewed revision: `efe51c72812faa618af42b0f8133d1745b882244`
- Reviewer: coordinator agent for #3299 (Claude Opus 5.5, read every screenshot below with vision); owner review by ApostateCD on PR #5095 is the design input
- Reviewer verdict: PASS
- Application/build identity: production bundle built with `pnpm --dir frontend build` at efe51c72812faa618af42b0f8133d1745b882244, served by Evennia on :4001 from the feature-3299 worktree
- Environment: shared devcontainer, throwaway Postgres database rt_3299b (tools/build_schema.py, seed_test_account for e2e_test_account and e2e_channels_reader, integration_tests.live_seeds.seed_channels_spec for e2e_channels_reader), Chromium 1208 headless via Playwright 1.65; database dropped afterwards
- Viewports/themes: 1280x720 and 1280x800 desktop, 390x844 phone; light theme
- Approved design: the #3299 spec plus ApostateCD's review on PR #5095 (2026-11-12): channel lines in the main window, filtered by the feed chips at the top, defaulting to OOC; a side lane only as an option, never the default
- Visual review: completed against the owner's review and the spec's identity and block rules
- Visual verdict: PASS
- Screenshots: ![Main column, OOC chip on](docs/reviews/issue-3299/channels-main-ooc-on.png) ![Main column, OOC chip off](docs/reviews/issue-3299/channels-main-ooc-off.png) ![Sidebar opt-in](docs/reviews/issue-3299/channels-sidebar-optin.png) ![Live line in the main column, desktop](docs/reviews/issue-3299/channels-live-main-desktop.png) ![Live line in the main column, phone](docs/reviews/issue-3299/channels-live-main-phone.png) ![/channels controls](docs/reviews/issue-3299/channels-page-controls.png) ![Org channel joined](docs/reviews/issue-3299/channels-06-org-joined.png)
- Comparison notes: channel lines now sit in the main column interleaved with room notes, each led by the channel name, then the chosen speaker and the text, styled like an OOC note; turning the OOC chip off hides them; the rail has a Channels group (one row per joined channel) for posting; the side lane appears only when "Channels in sidebar" is ticked, and then the main column and rail drop the lines. Speakers are character names only; the blocked player's line is a "1 hidden" rule.
- Tested interactions: log in as e2e_channels_reader; /channels: join Public, pick Speak as, post, Mute and Collapse persisting across reloads, join The Lantern Guild; /game: see channel lines in the main column under All with the OOC chip on, toggle the OOC chip off and on, post from the rail's Public row, tick "Channels in sidebar" and see the lines move to the sidebar's Channels mode, untick to restore; a second session of the account posts over telnet while /game is open and the line appears in the main column without reload at 1280x800 and 390x844
- Fixture/live boundary: live server and real Postgres for every request and websocket frame; rows from test factories in a throwaway database; the browser drove the real UI; telnet over the real :4000 socket
- Overall outcome: PASS

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| main-column-default | PASS | channels-main-ooc-on: lines in the main column, no Channels sidebar mode | ApostateCD review on PR #5095 |
| ooc-chip-filter | PASS | channels-main-ooc-off: OOC chip off hides every channel line | ApostateCD review on PR #5095 |
| sidebar-opt-in | PASS | channels-sidebar-optin: checkbox ticked, lines in the sidebar mode, none in the main column | ApostateCD review on PR #5095 |
| live-push-main | PASS | channels-live-main-desktop and channels-live-main-phone: telnet post appears without reload | spec decision 7 |
| identity-not-account | PASS | every screenshot: speakers are character names; the spec asserts other accounts' names appear nowhere | spec decision 2 |
| blocked-divider | PASS | channels-main-ooc-on: "1 hidden" rule where the blocked line is | spec decision 5 |
| controls-on-channels-page | PASS | channels-page-controls: Speak as, Mute, Collapse, Notifications, Move, Leave | coordinator instruction 2026-11-12 |

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Channel line | Channel name, speaker, text, OOC-note styling, in time order with room notes | MATCH | channels-main-ooc-on, channels-live-main-phone |
| OOC chip | Greyed when off and the lines gone | MATCH | channels-main-ooc-off |
| Rail Channels group | Heading and one row per joined channel | MATCH | channels-main-ooc-on |
| Display setting | "Channels in sidebar" checkbox, off by default | MATCH | channels-main-ooc-on, channels-sidebar-optin |
| Sidebar mode when opted in | Channels button beside Here and History, lanes below | MATCH | channels-sidebar-optin |
| Phone width | Lines wrap in the main column with no horizontal scroll | MATCH | channels-live-main-phone |

## Unresolved findings

None
