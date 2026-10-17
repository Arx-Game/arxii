# Review evidence

- Reviewed revision: `6c2293dd932e9ad0b039f36196d7bc55d01395d2`
- Reviewer: `real-testing pass by the implementing agent (Form B without a browser, plus one headless screenshot); schema-shape-reviewer and migration-reviewer agents on the diff; no demo-fidelity reviewer, since the issue's artifact link is the creation study, not a demo of this surface`
- Reviewer verdict: `PASS`
- Application/build identity: the branch's own Evennia server at 6c2293dd932e9ad0b039f36196d7bc55d01395d2 on :4001 against a throwaway Postgres database rt_4398 built with tools/build_schema.py; no frontend bundle (the surfaces are the Django admin and the distinctions REST list)
- Environment: Linux devcontainer (6 GB), Evennia/Django backend on Postgres, HTTP driven with urllib as the staff account through the same headless login the web client uses; one headless Chromium screenshot
- Viewports/themes: 1200x700 desktop, light theme (one admin screenshot); the rest is HTTP
- Approved design: none; #4398 is a lightweight backend issue with no demo. The study it cites (https://claude.ai/artifact/QRMFjYc5mfBx77S2iRVzt7) is the source of the requirement, not a design to match
- Visual review: Not applicable
- Visual verdict: NOT_APPLICABLE
- Screenshots: ![Distinction Item Grants changelist with the keepsake row](docs/reviews/4398/01-distinction-item-grants-admin.png)
- Comparison notes: not a visual change; the screenshot shows the plain admin changelist with the one row staff added (A Mother's Keepsake grants A Chimera Pendant), the same shape as the Distinction Starting Grants admin it mirrors
- Tested interactions: staff login through /api/auth/browser/v1/auth/login; Admin > Distinction Item Grants > Add rendered with both raw-id fields; saving distinction 1 + template 1 redirected to the changelist, which showed the row; saving the same pair again was refused on the page (200, the admin's own uniqueness line) with no second row; GET /api/distinctions/distinctions/ listed "Comes with A Chimera Pendant" on the keepsake distinction and no such line on the plain one; deleting the grant through the admin's delete page made the list drop the line at once, and adding it back made the line return at once, in the same server process; the database read back one row, A Mother's Keepsake to A Chimera Pendant. Finalize was exercised through the test client (Form A): finalize_character with the distinction picked leaves exactly one pendant in the inventory (test_finalize_mints_the_keepsake_once), and a retired template is neither minted nor advertised
- Fixture/live boundary: the staff account, the pendant template and the two distinctions were seeded by a throwaway script; everything after that went through the live server. The first server run was built with an earlier column the diff later dropped and returned four 500s on save (NotNullViolation on the stale column); the column was dropped from the throwaway schema and every result above is from after that. The cache fix (commit 6c2293dd9) was found by this pass: before it, the list kept advertising an empty keepsake list after an admin add in the same process
- Overall outcome: PASS

## Requirement ledger

| ID | Status | Evidence |  Authorized decision |
|---|---|---|---|
| K-admin-add | PASS | staff add -> 302, changelist shows the row; screenshot 01; the database read-back | |
| K-unique-pair | PASS | the same pair again -> 200 refused, one row in the database | |
| K-list-advertises | PASS | GET /api/distinctions/distinctions/ "Comes with A Chimera Pendant" on the keepsake, nothing on the plain distinction | |
| K-cache-clears-live | PASS | admin delete -> list drops the line; admin add -> list shows it; same process; world/items/tests/test_distinction_item_grant.py ItemGrantCacheTests | |
| K-finalize-once | PASS | world/items/tests/test_distinction_item_grant.py ItemGrantFinalizeTests (Form A through finalize_character; one pendant in the inventory) | |
| K-retired-template | PASS | world/items/tests/test_distinction_item_grant.py test_a_retired_template_is_not_minted and test_a_retired_template_is_not_advertised | |
| K-migration | PASS | migration-reviewer agent, twice (before and after dropping quantity): schema only, on the 0234 tip | |

## Unresolved findings

- None
