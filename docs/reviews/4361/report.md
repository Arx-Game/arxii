# Review evidence

- Reviewed revision: `7a07273146073bf3f43883bde8307bc4b2e1400b`
- Reviewer: `demo-fidelity-reviewer agent (local), two passes; report docs/reviews/4361/demo-fidelity.md`
- Reviewer verdict: `PASS`
- Application/build identity: production frontend bundle built with pnpm build from this branch, served by the branch's own Evennia server on :4001 against a throwaway Postgres database rt_4361
- Environment: Linux devcontainer, Chromium (Playwright, 1 worker), Evennia/Django backend on Postgres, database built with tools/build_schema.py and seeded by a throwaway script
- Viewports/themes: 1500x1100 desktop, light theme
- Approved design: https://claude.ai/artifact/1926LF7noogf1hKijgL3v8 (spec on #4121, slice 2)
- Visual review: Completed
- Visual verdict: PASS
- Screenshots: ![faction rules page](docs/reviews/4361/01-faction-rules-page.png) ![test a character](docs/reviews/4361/02-faction-rules-test-character.png) ![placement before](docs/reviews/4361/03-placement-before.png) ![placement after save](docs/reviews/4361/04-placement-after-save.png) ![beat dialog](docs/reviews/4361/05-gm-beat-dialog-placement.png) ![beat dialog panel](docs/reviews/4361/05b-gm-beat-dialog-placement-panel.png) ![gm panel](docs/reviews/4361/06-gm-panel-edits-and-sources.png) ![player angle](docs/reviews/4361/07-player-angle-from-organization-rule.png) ![gm panel after template edit](docs/reviews/4361/08-gm-panel-after-template-edit.png) ![profile builder](docs/reviews/4361/09-profile-builder-affiliation-and-inherited.png)
- Comparison notes: The screenshots come from a run of 7a0727314's tree less its last one-line change (the Standoff Profile Builder's placement list now names a beat by its description instead of its default label); the admin page tests pass on 7a0727314. Screen 1 (beat dialog panel, GM panel marks and From column), Admin A's affiliation row and inherited rail, Admin B (Faction Rules) and Admin C (Placement) were compared with the demo. The first pass found five cosmetic gaps and three missing shots; the widget's add buttons beside a single test, the template affiliation placeholder and the missing shots were fixed. Stated divergences: drive and drive shift stay as two standard admin form rows; the character test is a plain name field (no admin autocomplete source for character sheets); the beat dialog keeps a search box under the affiliation select because organizations are searched server-side. The "set on this line" mark for an overridden affiliation is not in a screenshot; GMStandoffPanel.test.tsx and test_placement.py cover it. Named NPC groups, language, cause_effect and the approach, terms and config previews belong to later slices.
- Tested interactions: signed in through the real login form as staff, the GM and a player; Organization change page to its Faction Rules page; test a character by name (a former member, honored by another organization) with the reasons shown; Beat change page "Edit placement" link; Placement page drive edit, removal and rule switch-off, Save and continue, marks read back; story author beat dialog placement panel read the saved edits, switched off a second rule, Save Beat; scene GM tab after the beat ran; player card angles; Standoff Profile Builder cause change after the spawn and the GM panel reloaded
- Fixture/live boundary: everything reached the live backend; the scripted steps were the seed (accounts, characters, organizations, memberships, reputation, template, rules, story, beat and line) and running the beat's encounter through RunBeatAction's own _run_encounter_beat in a shell between the two browser phases
- Overall outcome: PASS

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Faction Rules page | Rules this organization holds as stacked rule blocks, predicate widget, Delete, add row, Save row; rail with Inherits from above, precedence note, Reaches, Test a character | MATCH | ![faction rules](docs/reviews/4361/01-faction-rules-page.png) |
| Test a character | Each rule with matches or no match and the staff-only reason (association, reputation tier) | MATCH | ![test](docs/reviews/4361/02-faction-rules-test-character.png) |
| Placement page | This placement fields beside template values, Drives here table with Template, Here and Effect, Inherited faction rules with From and a switch-off box, rail What spawns, The beat, The GM's own path | MATCH | ![placement](docs/reviews/4361/04-placement-after-save.png) |
| Beat dialog placement panel | Standoff for this line, opens as a standoff, cause and affiliation with template values, drives table, add a drive, inherited rules with From and Off here, spawn summary | MATCH | ![panel](docs/reviews/4361/05b-gm-beat-dialog-placement-panel.png) |
| GM standoff panel | Drives edited-here mark, Affiliation row, faction rule table with a From column | MATCH | ![gm](docs/reviews/4361/06-gm-panel-edits-and-sources.png) |
| Player angle | Angle from an organization's rule shown privately with Share | MATCH | ![player](docs/reviews/4361/07-player-angle-from-organization-rule.png) |
| Standoff Profile Builder | Affiliation row, Also applies (inherited) rail with sources, predicate widget on each rule | MATCH | ![builder](docs/reviews/4361/09-profile-builder-affiliation-and-inherited.png) |

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| S2-placement-edits | PASS | 04 and 05b screenshots; world/standoffs/tests/test_placement.py SavePlacementTests; test_placement_api.py beat dialog saves every placement field | |
| S2-spawn-snapshot | PASS | 06 and 08 screenshots (template cause changed after the spawn, panel unchanged); test_placement.py SpawnSnapshotTests | |
| S2-org-society-rules | PASS | 01 and 07 screenshots; test_placement.py InheritanceTests | |
| S2-suppression | PASS | 04, 05b and 06 screenshots (switched-off rules absent from the spawned group) | |
| S2-precedence | PASS | test_placement.py PrecedenceTests | |
| S2-reputation-leaves | PASS | 02 screenshot; world/predicates/tests/test_faction_leaves.py MaxReputationTests | |
| S2-association-leaves | PASS | 02 and 07 screenshots; test_faction_leaves.py AssociationTests | |
| S2-admin-pages | PASS | 01 to 04 and 09 screenshots; web/admin/tests/test_faction_rules_page.py | |
| S2-predicate-widget | PASS | 01 and 09 screenshots | |
| S2-beat-dialog | PASS | 05 and 05b screenshots; frontend PlacementPanel.test.tsx | |
| S2-mission-studio | PASS | OptionPage uses the same OpponentLinesEditor panel; test_placement_api.py and test_placement.py mission option line | |
| S2-migrations | PASS | newest production dump restored to a scratch database, migrated forward, back to 0229 and forward again; old-shape rows carried across (PR Verification) | |

## Unresolved findings

- None
