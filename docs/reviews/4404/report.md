# Review evidence

- Reviewed revision: `7591f1de25808f19476403bf0c842a1e76b01018`
- Reviewer: `real-testing pass by the implementing agent (Form B without a browser, plus one headless screenshot); the bypassed-writer-reviewer agent this PR adds is the reviewer for the defect's class; no demo-fidelity reviewer, since the issue carries no demo`
- Reviewer verdict: `PASS`
- Application/build identity: the branch's own Evennia server at 7591f1de25808f19476403bf0c842a1e76b01018 on :4001 against a throwaway Postgres database rt_4404 built with tools/build_schema.py from this worktree; no frontend bundle (the surfaces are the Django admin and finalize_character)
- Environment: Linux devcontainer (6 GB), Evennia/Django backend on Postgres; the admin driven with urllib as the staff account through the same headless login the web client uses; finalize_character run from a plain Django process against the same live database (no test runner, no rollback), the modifier read back from the rows; headless Chromium for the screenshot
- Viewports/themes: 1200x700 desktop, light theme (one admin screenshot); the rest is HTTP and SQL
- Approved design: none; #4404 is a lightweight defect fix with no demo. The expectations were written before the run (scratch file expected_4404.md)
- Visual review: Not applicable
- Visual verdict: NOT_APPLICABLE
- Screenshots: ![The Character modifiers changelist after the two finalizes](docs/reviews/4404/01-character-modifiers-admin.png)
- Comparison notes: not a visual change; the screenshot shows the stock admin changelist of CharacterModifier rows after the two finalizes (the plain-born character's residence-comfort rows, none for the Sheltered-born)
- Tested interactions: staff login; Admin > Modifier categories / Modifier targets / Distinctions > Add for the comfort category and target and a Sheltered distinction with a -1 comfort effect (302 each, on the changelists; the authoring script also authored the other #4394 rows, unused here). Then, against the live database: a starting area set to grant residence in a level-6 room (amenity 200); a draft with no picks finalized through finalize_character: home is that room, comfort level 6, daily regen modifier +1; a draft that picked Sheltered, same area: home is the room, level read as 5, no modifier. Before this fix the same plain-born finalize produced no modifier at all (seen live in #4394's round 3 on the queued tree, the issue comment on #4394)
- Fixture/live boundary: the staff account, the distinction category, the ward and room with its amenity row, and the creation prerequisites (realm, area, species, beginning, path, tradition, gift, technique) were seeded by a throwaway script; the lever rows and Sheltered were authored through the admin on the live server; the finalizes ran against the live database and were read back from its rows (three CharacterModifier rows in the database: the plain-born's residence-comfort rows on the AP-regen targets, and the Sheltered-born's comfort lever row). Unit coverage: ComfortAtCreationTests (parity tier) through finalize_character; world.character_creation 768 tests on the fast tier
- Overall outcome: PASS

## Requirement ledger

| ID | Status | Evidence |  Authorized decision |
|---|---|---|---|
| C-plain-born-has-modifier | PASS | finalize into the level-6 starting residence: home is the room, level 6, modifier +1; screenshot 01 | |
| C-sheltered-born-reads-lever | PASS | finalize with Sheltered picked: level 5, no modifier | |
| C-author-rows | PASS | admin adds -> 302, rows on the changelists | |
| C-reviewer-agent | PASS | tools/agents/bypassed-writer-reviewer.md and its README row, in this PR | |

## Unresolved findings

- None
