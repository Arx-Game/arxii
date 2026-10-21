# Review evidence

- Reviewed revision: `97ae9254a9e77caa58e8bb2c9401f95eeffe9053`
- Reviewer: `demo-fidelity-reviewer agent (local); first pass FAIL on three small defects (the builder's Delete? column cut off, the template select without its value, the keepsake rail without its arithmetic), all fixed; second pass PASS`
- Reviewer verdict: `PASS`
- Application/build identity: this branch's code; Django dev server on :4811 (`arx manage runserver`, never `arx start`) with the Vite dev server on :4810 proxying to it, against the worktree's own scratch Postgres database arxiidev_4530 (a copy of the development database, migrated to this branch's 0270)
- Environment: Linux devcontainer, Chromium (Playwright), Postgres. Own database and ports; no other session's server or database was touched by the real-test run. The world rows (the character at a shrine, a being, a pledge, items, a deed) and the mission graph were made by throwaway scripts run in `arx shell`; the web client, the admin pages and the actions were operated for real.
- Viewports/themes: 1300 to 1400 px wide desktop, light and dark
- Approved design: local copy of the demo for spec #4462 (demo.html: "Keep as a keepsake (6b)", "Pledge card, afterwards", "Examining the coat", "Room view of a sacrifice (6b)", the Being Service builder, the Keepsake and Relic forms, the Devotion config fieldsets)
- Visual review: Completed
- Visual verdict: PASS
- Screenshots: ![keepsake form](docs/reviews/4530/2-keepsake-form-light.png) ![trophy](docs/reviews/4530/4-trophy-light.png) ![pledge card](docs/reviews/4530/12b-pledge-card-light.png) ![builder](docs/reviews/4530/5b-builder-requests-light.png) ![keepsake admin](docs/reviews/4530/6-keepsake-admin-light.png)
- Comparison notes: In scope: the keepsake form and kept state on the item panel, the trophy line and chip, the pledge card's requested items, the sacrifice dialog's own-line field, the builder's requested-items table and rail, the Keepsake, Relic and Devotion config admin forms. Accepted divergences: the Relic form keeps its existing Lore field; the builder's For column lists "Pledge: <name>" and "Rite: <name>" where the demo draws "this pledge"; the pledge card captions the table "<being> asks for" where the demo uses its section label; the hint input is narrow (the text is all there). The Call on favor picker rows for keepsakes and the Relic are checked by a component test and by the live invocation-options response below, not in a browser (that picker lives inside mission and scene checks).
- Tested interactions: in the web client as the character: opened the item panel, kept a rope as a keepsake of her deed with her own words and "show on examine", saw the kept state and released it, kept it again in dark mode; opened the trophy lantern; took the Highwind's pledge, read the pledge card's requested items, gave the requested pin up in the sacrifice dialog with a line of her own, read the credit and the "1 of 1 given" count; gave up a keepsake of the being after its wait. In the admin as staff: authored the request on the Being Service builder and saved it, opened the Keepsake, Relic and Devotion config pages. Through the mission engine: ran a real mission whose Success route grants an item and a renown deed.
- Fixture/live boundary: the scene was seeded by scripts; every step shown was a real page, action or service call. The sacrifice rolls were real and random (no forced outcome); the mission's check was forced to Success in the script process (the test seam), then the real resolution and reward router ran.
- Overall outcome: PASS

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Keepsake form | item name, "carried N months" chip, "It stands for" radios (tie, deed, being, organization, person, place), "In your words", Show on examine, treasured, slots line, Save keepsake | MATCH | ![](docs/reviews/4530/2-keepsake-form-light.png) ![](docs/reviews/4530/2-keepsake-form-dark.png) |
| Trophy line and chip | "Trophy of <deed>" on examine and in the panel | MATCH | ![](docs/reviews/4530/4-trophy-light.png) |
| Pledge card requests | Asked for, Hint, Given, Points each, the rule paragraph, the credit with the request's points | MATCH | ![](docs/reviews/4530/12b-pledge-card-light.png) ![](docs/reviews/4530/12b-pledge-card-dark.png) |
| Builder requests table | For, Item template (with value), or Facet, Quantity, Points, Hint, Delete?, rules paragraph, add button, rail "Where the requested items come from" | MATCH | ![](docs/reviews/4530/5b-builder-requests-light.png) ![](docs/reviews/4530/5b-builder-requests-dark.png) |
| Keepsake admin | item, sheet, words (never scored), shown on examine, six subject fields, computed rail with the arithmetic and the counts-from date | MATCH | ![](docs/reviews/4530/6-keepsake-admin-light.png) ![](docs/reviews/4530/6-keepsake-admin-dark.png) |
| Relic admin | being, item, invocation points with help | MATCH | ![](docs/reviews/4530/7-relic-admin-light.png) |
| Devotion config | Keepsakes and trophies, Rites and requests, invocation ease per keepsake point | MATCH | ![](docs/reviews/4530/8-devotion-config-light.png) |
| Sacrifice dialog | own-line field with the room-hears-it note | MATCH | ![](docs/reviews/4530/13-sacrifice-dialog-light.png) |

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| keepsake-declare | PASS | live: kept the rope for the deed "Cliff rescue" in the web form; saved; the panel shows "Kept as a keepsake of the deed Cliff rescue. It starts to count on 11/4/2026." and her words; the examine line shows her words only because she ticked Show on examine | |
| keepsake-wait-and-words | PASS | live: a keepsake of the being backdated 15 days eased the call; the live invocation-options response lists the rope as 3 points x 3 = eased 9 (1 subject + 2 match, computed by hand from the rules) and the Relic as 2 points x 3 = eased 6, total 15 under the cap of 40; her words appear nowhere in any signal | |
| keepsake-give-up | PASS | live: giving the rope up in the dialog read "carried 1, keepsake 1 (stands for The Highwind), keepsake match 2 = 4 points, eased 40", a real roll (Failure) | |
| trophy | PASS | live: a real mission (Success route with an item reward and a renown deed, level-3 character, tier 4) resolved through the engine; the reward router granted the lantern; it is linked to "Mission deed: The cliff ascent", is a physical item in her inventory, and examine reads "Trophy of Mission deed: The cliff ascent." A first run with a tier too low to pay Legend minted no deed and linked nothing, as intended | |
| requested-item | PASS | live: staff authored the request on the builder and saved it; the player took the pledge; the pledge card listed "weathervane pin, 0 of 1, 3 points"; giving the pin up read "requested 3 (asked for: weathervane pin) = 3 points, eased 30. Partial Success: 2 base, +2 favor"; the card then read "1 of 1" and the credit line; a Critical Failure landing as Failure is covered by test_a_roll_a_request_eased_cannot_botch, which fails when the lift is removed (checked) | |
| relic-ease | PASS | live: invocation-options response above | |
| relic-not-a-sacrifice-signal | PASS | live: giving the Relic lamp up read "No meaning points: given up, no roll, no favor", as designed (a Relic eases invocations only) | |
| own-line | PASS | live: the sacrifice dialog accepted a line; the room hears the system line then the line verbatim (journey test with the Interaction rows) | |
| found-defect | PASS | live: the Keepsake admin page raised a FieldError (a field I had listed that is not editable); fixed, covered by test_the_rail_computes_the_subjects_points_and_the_page_carries_its_rules | |
| migration | PASS | just prod-migration-check over the newest production dump (arxii-20261021T033021Z): forward 0267 to 0270, back to 0269, forward again, no pending migrations, RESULT: PASS; migration-reviewer: no findings (twice) | |

## Unresolved findings

- None
