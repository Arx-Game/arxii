# Review evidence

- Reviewed revision: `b6e31d0fc4362f5d9e81b1745dd5ac4eff07c09f`
- Reviewer: `demo-fidelity-reviewer`
- Reviewer verdict: `PASS`
- Application/build identity: production bundle built from revision b6e31d0fc4362f5d9e81b1745dd5ac4eff07c09f with `vite build` (the review's first pass ran on 046bb5406; b6e31d0fc adds only the rule above the Staff section and the settled-dropdown screenshot timing, and the eight screens were retaken on it), served by `vite preview` at http://localhost:4183
- Environment: Linux devcontainer (WSL2), Chromium 1208 headless via Playwright, no backend, every `/api/**` request answered by fixtures shaped like the serializers; spec file `frontend/e2e/evidence/gming-nav-4188.spec.ts`, all eight tests passed with no page errors
- Viewports/themes: 1280x720 light (header screens), 1280 wide full-page light (dashboard screens), 390x844 light (phone sheet)
- Approved design: https://claude.ai/artifact/Vdu27N2C5296w367Z6H5xn (Style B screens B1, B2, B3, C1, C2 and the right-hand phone sheet of Screen D; Style A is the rejected alternative), read in full from its saved file, with the spec's Decisions 1 to 10 in the issue body ruling where the two disagree
- Visual review: `Completed`
- Visual verdict: `PASS`
- Screenshots: ![C1 signed out](docs/reviews/4188/01-c1-signed-out-world-1280.png), ![C2 player](docs/reviews/4188/02-c2-player-1280.png), ![B1 GM menu](docs/reviews/4188/03-b1-gm-menu-1280.png), ![B2 staff GM menu](docs/reviews/4188/04-b2-staff-gm-menu-1280.png), ![Decision 8 staff-only menu](docs/reviews/4188/05-staff-only-menu-1280.png), ![B3 dashboard strip](docs/reviews/4188/06-b3-dashboard-strip-1280.png), ![Decision 10 quiet dashboard](docs/reviews/4188/07-quiet-dashboard-1280.png), ![D phone sheet](docs/reviews/4188/08-d-phone-sheet-390.png)
- Comparison notes: Every screenshot was opened and compared with the drawing at the same theme (light). The header order is Play, Characters, Story, GMing, World, Inbox, Staff and each group's rows match B1, B2, C1, C2 and D. Deliberate departures from the drawing, all spec-ruled and not defects: (1) Decision 1 puts Lead GM Queue among the GM rows (the drawing's B2 puts it under Staff); the build shows it as the fourth GM row in B1, B2 and the phone sheet. (2) Decision 7 adds a "My claims" strip row the drawing lacks; the build shows it fifth, muted at zero. (3) Decision 3 labels the invites row "Crossover invites" (plural; the drawing says "Crossover invite"). Known non-defects: the drawing's B3 door text reads "Offers", "Crossover Invites", "Update Requests", "Lead GM Queue" and the build names the invites door "Crossover Inbox" (the page's own name) and keeps the arrow; the drawing's B3 draws only the Episodes-ready and Waiting-for-GM tiles while the build keeps the Pending applications and Open invites tiles that #3268 added before this issue, which the spec says stay; the build's strip row label "Assistant GM claims to approve" is the plural of the drawing's "Assistant GM claim to approve"; the site name reads "Arx" in the app where the drawing says "Arx II", unchanged by this PR. Two gaps from the first pass were fixed in b6e31d0fc and re-compared on the retaken screens: (a) the drawing's B2 hairline between the GM rows and the Staff section is now drawn (a border above the section, in the dropdown and the sheet; screenshots 04 and 08). (b) The dropdown screens (01, 03, 04, 05) are now taken after the fade-in settles, so the rows are opaque. Scope notes, not defects: (c) The drawing's B3 puts the stat tiles directly under the strip; the build keeps the page's existing Your GM Profile, GM settings, My Tables and My NPCs sections between the strip and the tiles. The strip is still the first thing under the title, which is the drawing's point; the drawing is abbreviated and the spec says nothing else on the page moves. (d) Screenshot 04 shows the Staff top-bar link without the badge the drawing draws as 4; the fixture supplied no open-submission count, and the Staff badge is untouched by this PR. The tile "Stories waiting on you" and the tile the drawing calls "Waiting for GM" are the same pre-existing tile.
- Tested interactions: opening the World dropdown signed out (01); loading the header as a signed-in player (02); opening the GMing dropdown as a GM with a count of 7 (03), as staff who is also a GM (04) and as staff with no GMProfile (05); loading the Dashboard with things waiting (06) and with nothing waiting (07); clicking the Story offers strip row and landing on `/stories/my-offers` (spec file, B3 test); opening the phone sheet from the menu button at 390 wide (08). The unit tests in `Header.test.tsx` and `GMDashboardPage.test.tsx` cover the My claims link target and the zero-row behavior. No failure or reconnect path exists in this change beyond the 403 for a non-GM, which `test_attention.py` covers.
- Fixture/live boundary: fixture at the network for every `/api/**` call (account, GM attention counts, GM dashboard, roster, codex); no live backend was reached and no database was read. The header and Dashboard components are the real ones from the production bundle.
- Overall outcome: `PASS`

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Header group order, signed out (C1) | Play, Characters, Story, World; no GMing, no Inbox, no Staff | MATCH | [01](docs/reviews/4188/01-c1-signed-out-world-1280.png) |
| World dropdown open, signed out (C1) | Codex, Tidings, Journals, Realms, four rows | MATCH | [01](docs/reviews/4188/01-c1-signed-out-world-1280.png) |
| Crossover absent from World (C1) | no Crossover row anywhere in the menu | MATCH | [01](docs/reviews/4188/01-c1-signed-out-world-1280.png) |
| Signed-out right side (C1) | theme toggle; build adds Register and Log in, the app's existing auth links | MATCH | [01](docs/reviews/4188/01-c1-signed-out-world-1280.png) |
| Header group order, signed-in non-GM (C2) | Play, Characters, Story, World, Inbox; no GMing | MATCH | [02](docs/reviews/4188/02-c2-player-1280.png) |
| Signed-in right side (C2) | theme toggle and avatar with account name | MATCH | [02](docs/reviews/4188/02-c2-player-1280.png) |
| Header group order, GM (B1) | Play, Characters, Story, GMing, World, Inbox | MATCH | [03](docs/reviews/4188/03-b1-gm-menu-1280.png) |
| GMing trigger badge (B1) | one red round count, 7, beside the label | MATCH | [03](docs/reviews/4188/03-b1-gm-menu-1280.png) |
| GMing dropdown rows (B1) | Dashboard, Story Builder, Tables, plus Lead GM Queue as the fourth GM row | MATCH | [03](docs/reviews/4188/03-b1-gm-menu-1280.png); per Decision 1 |
| No per-row counts in the menu (B1) | rows carry no counts, only the trigger does | MATCH | [03](docs/reviews/4188/03-b1-gm-menu-1280.png) |
| Dropdown opacity (B1) | rows fully opaque | MATCH | [03](docs/reviews/4188/03-b1-gm-menu-1280.png); retaken after the fade on b6e31d0fc |
| Header group order, staff GM (B2) | Play, Characters, Story, GMing 7, World, Inbox, Staff | MATCH | [04](docs/reviews/4188/04-b2-staff-gm-menu-1280.png) |
| Staff GM menu GM rows (B2) | Dashboard, Story Builder, Tables | MATCH | [04](docs/reviews/4188/04-b2-staff-gm-menu-1280.png) |
| Lead GM Queue placement (B2) | drawing: under the Staff label | MATCH | [04](docs/reviews/4188/04-b2-staff-gm-menu-1280.png); per Decision 1: among the GM rows, above the Staff label |
| Staff section label (B2) | small muted "Staff" label | MATCH | [04](docs/reviews/4188/04-b2-staff-gm-menu-1280.png) |
| Staff section row (B2) | Story Workload under the label | MATCH | [04](docs/reviews/4188/04-b2-staff-gm-menu-1280.png) |
| Staff section separator (B2) | hairline rule above the Staff label | MATCH | [04](docs/reviews/4188/04-b2-staff-gm-menu-1280.png); added in b6e31d0fc |
| Loose Story Workload top-bar link (B2) | gone from the top bar | MATCH | [04](docs/reviews/4188/04-b2-staff-gm-menu-1280.png) |
| Staff top-bar link badge (B2) | Staff with a red 4 | MATCH | [04](docs/reviews/4188/04-b2-staff-gm-menu-1280.png); link present; the drawing's 4 is illustrative, the fixture gave no open-submission count, and the Staff badge is outside this change |
| Staff-only GMing menu (Decision 8) | GMing trigger without badge, menu holds only the Staff label and Story Workload, no Dashboard | MATCH | [05](docs/reviews/4188/05-staff-only-menu-1280.png); per Decision 8 |
| Dashboard title (B3) | "GM Dashboard" heading | MATCH | [06](docs/reviews/4188/06-b3-dashboard-strip-1280.png) |
| Waiting on you heading (B3) | "Waiting on you" subheading above a bordered strip, first under the title | MATCH | [06](docs/reviews/4188/06-b3-dashboard-strip-1280.png) |
| Strip row: story offers (B3) | bold 2, "Story offers", door at right | MATCH | [06](docs/reviews/4188/06-b3-dashboard-strip-1280.png); door reads "Offers →" |
| Strip row: crossover invites (B3) | bold 1, label, door at right | MATCH | [06](docs/reviews/4188/06-b3-dashboard-strip-1280.png); per Decision 3: "Crossover invites"; door "Crossover Inbox →" is the page's own name |
| Strip row: sheet update requests (B3) | bold 3, label, "Update Requests →" | MATCH | [06](docs/reviews/4188/06-b3-dashboard-strip-1280.png) |
| Strip row: claims to approve (B3) | bold 1, "Assistant GM claims to approve", "Lead GM Queue →" | MATCH | [06](docs/reviews/4188/06-b3-dashboard-strip-1280.png) |
| Strip row: my claims | not drawn; spec adds it, muted zero row, no door | MATCH | [06](docs/reviews/4188/06-b3-dashboard-strip-1280.png); per Decision 7 |
| Strip row: session requests, zero (B3) | muted 0, label, no door text, unlinked | MATCH | [06](docs/reviews/4188/06-b3-dashboard-strip-1280.png) |
| Remaining tiles (B3) | Episodes ready to run 1, Waiting for GM 2 | MATCH | [06](docs/reviews/4188/06-b3-dashboard-strip-1280.png); tile labelled "Stories waiting on you", the page's existing name |
| Extra tiles (B3) | drawing shows two tiles; spec keeps Pending applications and Open invites from #3268 | MATCH | [06](docs/reviews/4188/06-b3-dashboard-strip-1280.png); spec keeps them |
| Pending Story Offers section and AGM-claims and session tiles folded away (B3) | not on the page any more | MATCH | [06](docs/reviews/4188/06-b3-dashboard-strip-1280.png) |
| My Tables and Open Group Requests (B3) | My Tables (1) with the Lantern Table; Open Group Requests (0) with "No covenants are recruiting right now." | MATCH | [06](docs/reviews/4188/06-b3-dashboard-strip-1280.png) |
| Tile position (B3) | tiles directly under the strip | MATCH | [06](docs/reviews/4188/06-b3-dashboard-strip-1280.png); the strip is first under the title; the drawing abbreviates the page and the spec says nothing else on it moves, so the existing Profile, settings, Tables and NPCs sections stay between |
| Quiet header (Decision 10) | GMing trigger with no badge at zero | MATCH | [07](docs/reviews/4188/07-quiet-dashboard-1280.png); per Decision 10 |
| Quiet strip (Decision 10) | six rows each muted 0, no door text, no links | MATCH | [07](docs/reviews/4188/07-quiet-dashboard-1280.png); per Decision 10 |
| Phone sheet Play and Characters group (D right) | Play link; Characters label with Roster, Progression, Threads | MATCH | [08](docs/reviews/4188/08-d-phone-sheet-390.png) |
| Phone sheet Story group (D right) | Story label with Scenes, Events, My Stories, Books | MATCH | [08](docs/reviews/4188/08-d-phone-sheet-390.png) |
| Phone sheet GMing label (D right) | "GMing (7)" | MATCH | [08](docs/reviews/4188/08-d-phone-sheet-390.png) |
| Phone sheet GMing rows (D right) | Dashboard, Story Builder, Tables, plus Lead GM Queue | MATCH | [08](docs/reviews/4188/08-d-phone-sheet-390.png); per Decision 1 |
| Phone sheet Staff section | not drawn (drawing's viewer is a GM); build shows a rule, a small "Staff" label and Story Workload under GMing | MATCH | [08](docs/reviews/4188/08-d-phone-sheet-390.png); per Decision 6, staff who is also a GM |
| Phone sheet World group (D right) | World label with Codex, Tidings, Journals, Realms; no Crossover | MATCH | [08](docs/reviews/4188/08-d-phone-sheet-390.png) |
| Phone sheet Inbox (D right) | Inbox link last | MATCH | [08](docs/reviews/4188/08-d-phone-sheet-390.png) |

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| S01 | PASS | GMing group reaches Dashboard, Story Builder, Tables, Lead GM Queue: [03](docs/reviews/4188/03-b1-gm-menu-1280.png); B1 test asserts the Dashboard href and the other three rows | Decision 1 |
| S02 | PASS | one count on the GMing trigger: [03](docs/reviews/4188/03-b1-gm-menu-1280.png) shows 7; `gm-attention-badge` asserted in the B1 test | Decision 6 |
| S03 | PASS | Dashboard opens on what is waiting, each row a link: [06](docs/reviews/4188/06-b3-dashboard-strip-1280.png); B3 test asserts each non-zero row's href and that the strip sits above the tiles |  |
| S04 | PASS | assistant GM reaches claims from the strip: [06](docs/reviews/4188/06-b3-dashboard-strip-1280.png) shows the My claims row; its `/stories/my-claims` link when non-zero is asserted in `GMDashboardPage.test.tsx` | Decision 7 |
| S05 | PASS | staff who is not a GM gets Story Workload under GMing: [05](docs/reviews/4188/05-staff-only-menu-1280.png); the loose top-bar link is gone | Decisions 5 and 8 |
| S06 | PASS | staff who is also a GM gets one menu with both: [04](docs/reviews/4188/04-b2-staff-gm-menu-1280.png) | Decision 2 |
| S07 | PASS | World holds only lore for a signed-out visitor: [01](docs/reviews/4188/01-c1-signed-out-world-1280.png) | Decisions 3 and 4 |
| S08 | PASS | no GMing group for a signed-in non-GM: [02](docs/reviews/4188/02-c2-player-1280.png) | Decision 2 |
| S09 | PASS | phone sheet mirrors the group and count: [08](docs/reviews/4188/08-d-phone-sheet-390.png) shows "GMing (7)" and the same rows |  |
| S10 | PASS | nothing waiting means no badge and a strip of zeros: [07](docs/reviews/4188/07-quiet-dashboard-1280.png) | Decision 10 |

## Unresolved findings

- None
