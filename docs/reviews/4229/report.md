# Review evidence

- Reviewed revision: `2f03b2d2d42f06af435c6514b81fb6042dbe4c68`
- Reviewer: the implementing agent (Claude Code), with Playwright on the real `/characters/:entry` sheet from the production bundle, signed in as staff, every `/api/**` call answered by fixtures shaped like the serializers; screenshots read back by eye
- Reviewer verdict: PASS
- Application/build identity: `vite build` of the frontend at 787b9bc0a, served by `vite preview --port 4187`; `git diff --stat 787b9bc0a 2f03b2d2d42f06af435c6514b81fb6042dbe4c68 -- frontend/src` is empty, so the bundle is the reviewed frontend (the later commits changed backend review fixes, docs and the harness only); harness `frontend/e2e/evidence/staff-group-fit-4229.spec.ts`, two tests, both passing (6.3 s)
- Environment: Linux devcontainer on WSL2, Playwright Chromium headless (build 1208)
- Viewports/themes: 1280x900 and 390x1100, the default light theme
- Approved design: no demo page; the approved spec is #3988's technical design, section "Group fit (PR E)", approved by ApostateCD on #3988 and on #4229, and pieces B to D's rows band (StaffRowsBand) as the surface these rows join
- Visual review: Completed
- Visual verdict: PASS
- Screenshots: ![A bare sheet in edit mode at 1280: after Reputation the rows band adds Identities (a name field and Add identity), Titles (face, title reward and deed pickers with Grant title; a noble title picker with Seat on title), Ties (a character search with Find, then character, side, relationship and awareness pickers with Declare), Covenants (covenant, role and rank pickers with Swear in) and Mentor bonds (a character search, covenant, character and role pickers with Bond)](docs/reviews/4229/01-bare-sheet-group-editors-1280.png) ![The same sheet after four saves: Identities lists The Grey Lady (established); Ties shows Ser Aldric Venn with a Rival label marked "binds at pickup", its awareness picker, End, a tier picker and summary; Covenants lists The Lantern Oath with its role, rank, Engage and End; Mentor bonds reads "Sidekick of Ser Aldric Venn, in The Lantern Oath" with the band warning beside it](docs/reviews/4229/02-filled-group-rows-1280.png) ![The bare sheet at 390 wide: every group-fit editor stacked in one column inside the band with no horizontal page overflow](docs/reviews/4229/03-group-editors-390.png)
- Comparison notes: The spec asks for personas, titles, relationships (both sides, with a picker for the other character), covenants and mentors to be editable in edit mode. All five appear as sections of the rows band, in the section, picker and button style of pieces B to D above them, so staff meet one editing surface. Looks are not a new section: #4151's gallery already lets staff add character art to the entry, tag moods, crop and wear a look as the profile picture, which is the spec's looks row. Other characters are found by search and never listed. A staff label on a character nobody plays is marked "binds at pickup", the one fact a staff member cannot otherwise see; a bond outside the level band carries its warning on its row rather than refusing. No copy explains the screen; labels are field names.
- Tested interactions: open `/characters/1` as staff; turn on the header's Edit switch; in Identities type "The Grey Lady" and press Add identity; read it listed; in Ties type "aldric", press Find, pick Ser Aldric Venn, Rival and Clandestine, press Declare; read the label with its waiting mark; in Covenants pick The Lantern Oath and Vanguard and press Swear in; read the membership with Engage; in Mentor bonds pick The Lantern Oath, Ser Aldric Venn and "The sidekick", press Bond; read the bond and its warning. The harness asserts the four requests the page sent (path and body) and that no page error was raised. At 390 wide, turn on Edit and measure the page's horizontal overflow (none).
- Fixture/live boundary: the route, `ProtectedRoute`, the sheet page, its hooks, `StaffEditProvider`, the header toggle, `StaffRowsBand`, `StaffGroupFitEditors` and the bundle are real; every `/api/**` response is a fixture, and each staff write answers with a sheet payload whose `staff_edit.rows` carries the new identity, tie, membership or bond. That the real endpoints write those rows and answer with them is proved over HTTP by `world.character_sheets.tests.test_staff_group_fit` (staff gating on all fourteen actions, another character's face refused, a face and a tie in the rows, a bond's warning in the rows, characters searched) and the writers by its service tests, on the Postgres parity tier; the staff label binding at pickup and counting as mutual by `test_an_unpicked_character_s_label_is_inert_until_pickup_then_mutual`; a complete sheet from a bare minted one through the staff endpoints by `test_staff_completeness`; the changed shared services by the covenants, relationships, roster and scenes suites (398 tests, parity tier); the editors' requests by `StaffEdit.test.tsx` (13).
- Overall outcome: PASS

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Identities section | each face expandable for rename, cover bio and remove; a name field with Add identity | MATCH | docs/reviews/4229/02-filled-group-rows-1280.png |
| Titles section | face, title reward and deed pickers with Grant title; noble title picker with Seat on title | MATCH | docs/reviews/4229/01-bare-sheet-group-editors-1280.png |
| Ties section | each tie with both sides, labels with awareness and End, tier and summary; a character search and a declare row | MATCH | docs/reviews/4229/02-filled-group-rows-1280.png |
| Waiting label | a staff label on an unplayed character marked "binds at pickup" | MATCH | docs/reviews/4229/02-filled-group-rows-1280.png |
| Covenants section | each membership with role, rank, Engage or Disengage, End; a swear-in row | MATCH | docs/reviews/4229/02-filled-group-rows-1280.png |
| Mentor bonds section | each bond with its party and covenant, any band warning, End; a bond row | MATCH | docs/reviews/4229/02-filled-group-rows-1280.png |
| Same style as the rows band | section headings, pickers and buttons match pieces B to D | MATCH | docs/reviews/4229/01-bare-sheet-group-editors-1280.png |
| Phone width | one column, no horizontal overflow | MATCH | docs/reviews/4229/03-group-editors-390.png |

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| R01-personas | PASS | captures 01 and 02; `PersonaWriterTests` (past the cap, own face refused, versioned guise with no empty version, worn face reset on removal, a face with history stays) | #3988 spec, PR E table |
| R02-looks | PASS | already built by #4151: staff upload character art to the entry, tag moods, crop and wear a look (`world.roster.services.gallery`) | #3988 spec, PR E table |
| R03-titles | PASS | `TitleWriterTests` (reward once, non-title refused, deed only on its own face, noble title needs a place in the tree) | #3988 spec, PR E table |
| R04-relationships-both-sides | PASS | capture 02; `TieWriterTests` (inert until pickup then mutual, a played side counts at once, a shift keeps it waiting, tier without XP or capstone) | #3988 spec, PR E table; ADR-4229 |
| R05-covenants | PASS | capture 02; `test_staff_assignment_skips_the_band_gate_and_the_sworn_act`, `test_a_membership_takes_one_change_at_a_time` | #3988 spec, PR E table |
| R06-mentors | PASS | capture 02; `test_a_band_violation_warns_staff_and_the_cap_still_holds`, `test_a_bond_rolls_back_when_its_health_recompute_fails` | #3988 spec, PR E table |
| R07-no-notifications | PASS | `StaffWritesSendNothingTests` | #3988 spec, group fit preamble |
| R08-completeness | PASS | `test_a_bare_staff_character_gets_every_family_cg_writes` | #3988 spec, Tests |
| R09-staff-only | PASS | `test_the_player_cannot_use_the_group_actions` | #3988 spec, `can_staff_edit_sheet` |
| R10-docs-in-tandem | PASS | `character_sheets.md`, `INDEX.md`, `covenants.md`, `roster.md`, relationships and scenes app guides, ADR-4229, glossary, MODEL_MAP | CLAUDE.md, docs are directives |

## Unresolved findings

- None
