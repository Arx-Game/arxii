# Review evidence

- Reviewed revision: `5a476b108bc1f09662ac811df3bd4284dc5bf4ce`
- Reviewer: `implementer self-review against the issue's Expected section; no demo exists for this issue (a Perform control on an existing card), so demo-fidelity-reviewer does not apply`
- Reviewer verdict: `PASS`
- Application/build identity: production frontend bundle built with pnpm from this branch (code revision above, the docs commit on top of the code commits ab993a297 and 6e3c20841), served by the branch's own Evennia server on :4001 and :4000 against a throwaway Postgres database rt_4451
- Environment: Linux devcontainer, Chromium (Playwright, 1 worker), database built with tools/build_schema.py and Evennia's own initial setup, then one throwaway seed script (the test account, a character Ysmay with a magical profile and 2 of 10 anima, her personal anima ritual, check outcomes and awards of 0, 2, 4 and 8, a Soulfray condition at severity 2 with 1 budget per point)
- Viewports/themes: 1280x720 desktop, light theme
- Approved design: none (no demo on #4451; the expected behavior is the issue's Expected section and the maintainer's ratified direction recorded in its discovery assessment)
- Visual review: Completed
- Visual verdict: PASS
- Screenshots: ![1](docs/reviews/4451/1-before.png) ![2](docs/reviews/4451/2-performed.png) ![3](docs/reviews/4451/3-refused.png)
- Comparison notes: In scope: the Perform control on the personal anima ritual's card and the line it shows. Observed while operating it: the Rituals page only offers the card while the character is puppeted in a connected game session (its active character comes from the account's puppeted flag), so the check used a second browser tab while the first sat in the world; a client-side move from the game page to /rituals in the same tab kept showing "You need an active character", and a full reload of /rituals in the same tab dropped the puppet. Both are how the page already worked before this change and are reported, not changed. Out of scope: any navigation link to the Rituals page (the header has none), the outcome tuning, and the scene-action-request resolver.
- Tested interactions: signed in through the real login form, entered the world as Ysmay on /game, opened /rituals in a second tab, clicked Perform with no scene running (refused: "You cannot perform a ritual right now."), clicked Start Scene on the game page, clicked Perform (the card showed the outcome line), clicked Perform again (refused). Then, in a new scene started the same way, typed `ritual anima` into a real telnet connection on :4000 twice. Read back from the database after the web perform: the performance row, the anima pool and the Soulfray condition
- Fixture/live boundary: everything reached the live backend; the scripted parts were the seed and the account's puppet lock on the character. The roll itself was not forced: the web run came up Success and the telnet run came up Failure on the real chart
- Overall outcome: PASS

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Perform and Manage on the anima ritual's card | Both buttons on the card, Perform first | MATCH | ![1](docs/reviews/4451/1-before.png) shot 1: Perform (filled) and Manage (outline) at the card's right |
| Outcome line after Perform | One line under the card names the ritual and the tier, then what it did | MATCH | ![2](docs/reviews/4451/2-performed.png) shot 2 reads "You perform Ysmay's Anima Ritual: Success. Your Soulfray eases by 2. The Soulfray is gone. You recover 2 anima." |
| Refusal line | A second try in the same scene shows the refusal in the destructive style | MATCH | ![3](docs/reviews/4451/3-refused.png) shot 3 reads "You've already performed your ritual in this scene." in red |

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| R-web-perform | PASS | shot 2; after the click the database held one performance row (ritual 1, successful, anima_recovered 2, severity_reduced 2), anima 4 of 10 (was 2) and the Soulfray condition resolved at severity 0 | |
| R-order | PASS | Success budget was 4 and the cost 1 per point, so Soulfray took 2 and the other 2 went to anima: the pool went from 2 to 4, matching the contract (Soulfray first, then anima) | |
| R-once-per-scene | PASS | shot 3 and the telnet run: the second try in the same scene was refused with the same message both ways | |
| R-needs-scene | PASS | with no scene running the card showed "You cannot perform a ritual right now."; the seeded scene had already ended when the check began (its row carried a finish time), so this was found rather than staged | |
| R-telnet | PASS | typed `ritual anima` on telnet: "You perform Ysmay's Anima Ritual: Failure." then, a second time, "You've already performed your ritual in this scene." | |
| R-own-ritual-only | PASS | not repeated on the live server; the journey test, which runs the real REST route and the real command handler, posts another player's ritual id as Ysmay and gets 400 with no performance row; telnet by another player's ritual name finds nothing (test_performing_the_anima_ritual_journeys) | |

## Unresolved findings

- None
