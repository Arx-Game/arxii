# Review evidence

- Reviewed revision: `427d01473827239aebf6f86757a7e43f264e7d51`
- Reviewer: demo-fidelity-reviewer (Claude, vision-capable; viewed every cited screenshot and read the telnet captures, two passes: dda9110d6, then 427d01473 after the footnote fix)
- Reviewer verdict: PASS
- Application/build identity: branch feature-4374-favor-with-beings-slice-3-a-closed-pledg; production frontend build served by the branch's own Django server on http://localhost:4001 (rebuilt after 427d01473 for screenshots 07b, 12, 13, 14, 15, 16), telnet on :4000
- Environment: throwaway database rt_4374 (schema from the models, factory seed `seed.py.txt`), players on e2e_test_account, Brother Caddoc on onlooker_4374, staff_4374 for admin and the Deity Editor
- Viewports/themes: desktop 1280 (Playwright default) and one 390-wide capture (13); light theme
- Approved design: demo https://claude.ai/artifact/WnBj714NF8MQiPQVBb1ifG (revision 11), spec issue #4333 design 4 and 10, slice 3 of its "Proposed slice cut"; read in full from the saved HTML
- Visual review: completed for Player screen 4, Player screen 5 (close and vision lines), Onlooker screen 2, Admin 2 (Answer builder) and the Answer builder links on Admin 1 and Admin 6, against screenshots from the live server
- Visual verdict: PASS
- Screenshots: ![answer builder](docs/reviews/4374/12-answer-builder-success-cell.png) ![answer builder phone](docs/reviews/4374/13-answer-builder-phone.png) ![refused](docs/reviews/4374/03-answer-builder-refused.png) ![service builder](docs/reviews/4374/04-being-service-builder.png) ![object tools](docs/reviews/4374/05-being-change-object-tools.png) ![bram vision](docs/reviews/4374/15-bram-vision.png) ![ysmay vision](docs/reviews/4374/07b-ysmay-vision-after-footnote-fix.png) ![orla vision](docs/reviews/4374/08-orla-vision.png) ![play feed](docs/reviews/4374/16-dara-play-feed.png) ![onlooker feed](docs/reviews/4374/14-caddoc-play-feed.png) ![held](docs/reviews/4374/10-dashboard-held-while-short.png) ![counts](docs/reviews/4374/09-dashboard-counts-while-short.png) ![mira vision](docs/reviews/4374/11-mira-vision.png)
- Comparison notes: The Answer builder is a faithful build of Admin 2: coverage grid with the general row first, one answer's form with linked-row context under both clue fields and the cost pool, sacrifice lines with the rule, a Delete-left and Save-right submit row, and a rail with Preview, the being's worship, Checks and Credit; the page links forms.css and widgets.css itself. The vision card matches Player screen 4 (parts in order, one Silk line, other items named, footnotes "A clue came with it", "A mission came with it", "Condition"), in the sheet and in the play feed (16). The onlooker sees the rite line and then the staff onlooker line only, on telnet and in the web feed (14). Fixed during review: the follow-up footnote wording and the telnet footnotes (427d01473); follow-up labels and the submit order (d243278a2). Accepted differences, for the owner: on telnet the vision prints before the closing-award line, because it is a narrative message pushed while the close runs (the demo shows the closing line first); object-tool labels read "Open the being service builder / Open the Answer builder" (the longer wording the other admin object tools use); the clue and pool pickers are admin autocompletes without the demo's pencil and plus icons; the builder adds an "Answer 1 / + Add another answer" row the demo implies with "answer 1 of 2". Screenshots 01 and 02 predate d243278a2; 12 is current.
- Tested interactions: the Answer builder save (credited) and a refused fact on Partial Success; the Service builder's Answers row and the being change form's object tools; the pledge card's Close on the web (Ysmay, Bram); web dispatch closes for Orla (two, the first a retry) and Dara (play feed open); telnet pledge, pledge/close as Tobiah, Hobb, Mira, Nell and Ada with Brother Caddoc watching from a second account; the Deity Editor's counts card and held answers list; the held-answer and lapse ticks in a shell with the server stopped
- Fixture/live boundary: live server, real browser, real API, telnet and database; no routes mocked. Seeded by factories: being, resonances, facet, shrine, rite, pledge type, three answers, clues, cost pool, characters and items; the Success answer was written through the builder. Puppet locks, a second account for the onlooker and the short pool were set in a shell between sessions. Text slots are placeholders by design.
- Overall outcome: PASS

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
| --- | --- | --- | --- |
| P4-success-answer | PASS | 15, 11, telnet-session4.txt, telnet-session11.txt, db-state.txt (codex known, mission held, condition) | none |
| P4-below-success | PASS | 07b (Partial: no fact, follow-up kept), 08 and c-orla.json (Failure: delay, answer, cost; no clue) | none |
| P4-retry | PASS | b-close-toast.txt, c-orla.json | none |
| P4-held | PASS | 10-dashboard-held-while-short.png, e-held-while-short.json, ticks.txt, 11 | none |
| P4-play-feed | PASS | 16-dara-play-feed.png | none |
| P5-telnet | PASS | telnet-session11.txt: [VISION] with the three footnotes | line order kept: vision before the closing-award line, listed for the owner |
| O2-room-lines | PASS | 14, telnet-session4.txt, telnet-session11.txt, db-state.txt | none |
| A2-builder | PASS | 12, 03, 13 | pickers without icons and the answer tab row accepted |
| A1-answers-row | PASS | 04 | none |
| A6-object-tools | PASS | 05 | longer labels accepted |
| S4-S5-out | OUT_OF_SCOPE | n/a | Stewards and answering live are slices 4 and 5 of #4333 |

## Visual checklist

| Element | Expected | Result | Evidence |
| --- | --- | --- | --- |
| Admin 2 breadcrumb | Home > Worshipped beings > Ombrin > Answers > Pledge type > Success | MATCH | 12 |
| Admin 2 page title | "Answer builder: Ombrin" | MATCH | 12 |
| Header pills | Service builder, Deity Editor | MATCH | 12 |
| Coverage grid | Pledge type rows by five tiers, "No pledge type (live answers)" row first, counts, "select a cell to edit it" | MATCH | 12 |
| Coverage cell state | selected cell outlined; empty cells in a warning tint | MATCH | 12 |
| Answer header bar | "Pledge type · Success · answer 1 of N" with "weight · used N times" chip | MATCH | 12; build adds an "Answer 1 / + Add another answer at Success" tab row, additive |
| Delay text and help | "Opens the vision and states that the character's effort was acknowledged." | MATCH | 12 |
| Answer text and help | "The main body. Sacrifice lines are added after it." | MATCH | 12; build says "(below)" dropped |
| Fact text and help | "States one fact." plus tier rule | MATCH | 12 |
| Fact clue with linked-row context | picker, then "Clue name · Codex · Automatic" and what it grants | MATCH | 12 |
| Clue and pool pickers | a picker per linked row (the demo draws magnifier, pencil and plus icons; accepted difference: admin autocomplete with a clear mark) | MATCH | 12: autocomplete selects styled by widgets.css, linked-row context under each |
| Tier rule line | "fact text and fact clue are allowed on Success and Critical Success only" | MATCH | 12 |
| Cost text, cost pool with summary | pool named with consequence count and summary | MATCH | 12; build adds "At this tier: Marked (Success)" |
| Follow-up text and clue with context | "Assigns a mission template with N nodes" | MATCH | 12 |
| Follow-up labels | "Follow-up text", "Follow-up clue" | MATCH | 12 vs 01; in 12; 01 and 02 still show "Follow up" (fixed by the follow-up commit |
| Onlooker line and help | "Sent to the room as a public line. Others in the room see this line and nothing else from the answer." | MATCH | 12 |
| Options row | Weight, Conceal Ombrin as the source, Active | MATCH | 12 |
| Sacrifice lines panel | header chip "one line per facet; Ombrin favors Silk", Facet / Text / Delete? columns | MATCH | 12 |
| Add another sacrifice line and rule | button plus the one-line-per-facet rule text | MATCH | 12 |
| Submit row | Delete left; Save and edit Critical, Save and continue, Save right | MATCH | 12 (02 shows the old order) |
| Rail Preview | vision card with delay, answer, sacrifice line, fact, cost, follow-up, clue footnote; "Preview shows the saved text, with one Silk sacrifice." | MATCH | 12 |
| Rail Ombrin's worship | resonances, favored facets, rites, worship pool, (build adds answers held) | MATCH | 12 |
| Rail Checks | OK/Warn lines, including "No Critical answer. Critical uses Success." | MATCH | 12 |
| Rail Credit | Written by, Reviewed by, Mark reviewed | MATCH | 12 |
| Admin 1 Answers row | "N of 5 outcome tiers written. Open in Answer builder" inside the pledge type | MATCH | 04 |
| Admin 1 Answer builder pill | pill before Change being and Deity Editor | MATCH | 04 |
| Admin 1 Checks | demo warns when a pledge type has no answers | MATCH | 04; build's OK line "A close of every pledge type can draw an answer" |
| Admin 6 object tools | Service builder and Answer builder links beside History (accepted: the longer labels the other admin object tools use) | MATCH | 05: "Open the Being Service builder", "Open the Answer builder", History |
| Player 4 vision card | "VISION from Ombrin", just-now stamp, delay then answer then sacrifice line then fact then cost then follow-up, no field labels | MATCH | 11, 07 |
| Player 4 one Silk line plus "Also sacrificed:" list | one line per facet, extra items named | MATCH | 07 (silk ribbon, brass bell listed); 11 |
| Player 4 footnotes | "A clue came with it: [codex clue]. A mission came with it: [mission clue]. Condition: [..]" | MATCH | 15 and 07b read "A clue came with it: Ombrin codex clue. A mission came with it: Ombrin mission clue. Condition: Marked by Ombrin." (fixed in 427d01473; 11 predates the fix) |
| Player 4 closing line | "Success. Closing award for Success: 5 base, at 200% = +10" | MATCH | `g-close-toast.txt`, 07 sheet row "Closing award for Success" |
| Player 4 vision card, web close | vision card with all three footnotes after a web close | MATCH | 15, `i-bram-visions.json` (`follow_up_footnote` field) |
| Player 4 vision in the play feed | card arrives in the feed after the closing line | MATCH | 16-dara-play-feed.png: the emerald vision card in the play feed, then the rite line and the onlooker line |
| Player 5 telnet closing | `> pledge/close`, `[VISION]` text, clue line | MATCH | telnet-session11: `[VISION]` ends with "A clue came with it: Ombrin codex clue. A mission came with it: Ombrin mission clue. Condition: Marked by Ombrin." |
| Player 5 telnet line order | the close's lines and the vision (the demo prints the closing line first; accepted difference pending owner ruling: the vision is pushed while the close runs, so it prints first) | MATCH | telnet-session11: [VISION] with footnotes, rite line, onlooker line, then the closing-award line |
| Onlooker 2 rite line | "X performs Ombrin's rite." | MATCH | telnet-session4, 5 |
| Onlooker 2 authored line | staff onlooker line follows | MATCH | telnet-session4, 5, 11 |
| Onlooker 2 web play feed | rite line then the staff onlooker line, nothing else | MATCH | 14 (rows "Bram Okes performs Ombrin's rite." then "[staff-authored onlooker line: success]") |
| Onlooker 2 hides the roll, vision, clue and mission | nothing else shown | MATCH | session4, 5 onlooker blocks |
| Deity Editor counts (added, not in demo's slice 3 screens) | counts of pledge types, answers, held | MATCH | 09; in scope per Admin 4 note "Deity Editor shows their counts" |

## Unresolved findings

None
