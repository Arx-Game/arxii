# Review evidence

- Reviewed revision: `f14267f04231e8fb0a6654cdc8df761edb93838c`
- Reviewer: `real-testing pass by the implementing agent, two rounds (Form B without a browser, plus one headless screenshot per round); schema-shape-reviewer and migration-reviewer agents on the diff; no demo-fidelity reviewer, since the issue's artifact link is the creation study, not a demo of this surface`
- Reviewer verdict: `PASS`
- Application/build identity: the branch's own Evennia server at f14267f04231e8fb0a6654cdc8df761edb93838c on :4001 (round 1 ran the server at 6c2293dd9 against rt_4398; round 2 at 569659a5b against rt_4398b); no frontend bundle (the surfaces are the Django admin and the REST API)
- Environment: Linux devcontainer (6 GB), Evennia/Django backend on Postgres, HTTP driven with urllib as the staff account through the same headless login the web client uses; finalize_character run in a plain Django process against the same live database (no test runner, no rollback); headless Chromium for the screenshots
- Viewports/themes: 1200x700 desktop, light theme (two admin screenshots); the rest is HTTP and SQL
- Approved design: none; #4398 is a lightweight backend issue with no demo. The study it cites (https://claude.ai/artifact/QRMFjYc5mfBx77S2iRVzt7) is the source of the requirement, not a design to match
- Visual review: Not applicable
- Visual verdict: NOT_APPLICABLE
- Screenshots: ![Distinction Item Grants changelist with the keepsake row](docs/reviews/4398/01-distinction-item-grants-admin.png) ![Item Templates changelist after staff retired the pendant](docs/reviews/4398/02-item-template-retired.png)
- Comparison notes: not a visual change; the screenshots show the plain admin changelists (the keepsake row in round 1; the pendant template with Is active off in round 2)
- Tested interactions: round 1 (rt_4398, server at 6c2293dd9): staff login; Admin > Distinction Item Grants > Add rendered with both raw-id fields; saving distinction 1 + template 1 redirected to the changelist, which showed the row; the same pair again was refused on the page (200, the admin's own uniqueness line) with no second row; GET /api/distinctions/distinctions/ listed "Comes with A Chimera Pendant" on the keepsake distinction and nothing on the plain one; deleting the grant through the admin made the list drop the line at once, and adding it back made it return at once, in the same server process; the database read back one row. Round 2 (rt_4398b, built as production is: main's 0234 schema, then the branch's real migrate applied 0235 from the final migration file, "Applying arxii.0235_distinctionitemgrant... OK", showmigrations [X] 0235, table columns id, distinction_id, item_template_id): finalize_character on the live database for a draft that picked the keepsake, twice before the fix (characters 3 and 4: one pendant row each, but GET /api/items/inventory/?character=N returned an empty list, because the row had no game object and the inventory lists objects located on the character); after the fix (569659a5b) twice more (characters 5 and 7: one pendant row each, game object located on the character, and the inventory API lists exactly one "A Chimera Pendant" for each); staff retired the pendant template through Admin > Item Templates (is_active off, 302), after which the distinction list showed no "Comes with" line, and a third finalize (character 9) minted nothing: inventory API empty, zero item rows for that sheet in the database
- Fixture/live boundary: the staff account, two player accounts, the pendant template, the two distinctions, the grant and the creation prerequisites (realm, area, species, beginning, path, tradition, gift, technique) were seeded by a throwaway script; everything after that went through the live server or finalize_character against the live database. Round 1's first server run was built with an earlier column the diff later dropped and returned four 500s on save; the column was dropped from that throwaway schema and every round-1 result is from after that. Round 2's database was built fresh. The two fixes this pass found are commits 6c2293dd9 (cache clearing) and 569659a5b (materialize the keepsake so the inventory sees it)
- Overall outcome: PASS

## Requirement ledger

| ID | Status | Evidence |  Authorized decision |
|---|---|---|---|
| K-admin-add | PASS | round 1: staff add -> 302, changelist shows the row; screenshot 01; the database read-back | |
| K-unique-pair | PASS | round 1: the same pair again -> 200 refused, one row in the database | |
| K-list-advertises | PASS | round 1: GET /api/distinctions/distinctions/ "Comes with A Chimera Pendant" on the keepsake, nothing on the plain distinction | |
| K-cache-clears-live | PASS | round 1: admin delete -> list drops the line; admin add -> list shows it; same process | |
| K-finalize-once | PASS | round 2: finalize_character on the live database, characters 5 and 7: one pendant row each, one row on GET /api/items/inventory/?character=5 and =7 | |
| K-inventory-sees-it | PASS | round 2: before 569659a5b the inventory API returned [] for characters 3 and 4; after it, one pendant each; world/items/tests/test_distinction_item_grant.py reads the inventory API as the playing account | |
| K-retired-template | PASS | round 2: staff retire through the admin -> 302; list API shows no "Comes with"; finalize of character 9 mints nothing (API [], zero rows); screenshot 02 | |
| K-migration | PASS | round 2: the branch's migrate applied 0235 from the final file onto main's 0234 schema; migration-reviewer agent, twice (before and after dropping quantity) | |

## Unresolved findings

- None
