# Review evidence

- Reviewed revision: `d77b08a651488b8ed4d1c1569b15588f1194e5ad`
- Reviewer: the implementing agent (Claude Code), with Playwright on the real `/characters/:entry` sheet from the production bundle, signed in as staff, every `/api/**` call answered by fixtures shaped like the serializers; screenshots read back by eye
- Reviewer verdict: PASS
- Application/build identity: `vite build` of the frontend at 744c1e44c, served by `vite preview --port 4187`; `git diff --stat 744c1e44c d77b08a651488b8ed4d1c1569b15588f1194e5ad -- frontend/src` is empty, so the bundle is the reviewed frontend (the later commit changed backend review fixes, docs and the harness only); harness `frontend/e2e/evidence/staff-estate-4226.spec.ts`, two readings, both passing (8.5 s)
- Environment: Linux devcontainer on WSL2, Playwright Chromium headless (build 1208)
- Viewports/themes: 1280x900 and 390x1100, the default light theme
- Approved design: no demo page; the approved spec is #3988's technical design, section "Kinship, estate and reputation (PR D)", approved by ApostateCD on #3988 and on #4226, and pieces A to C's established rows band (StaffRowsBand) as the surface these rows join
- Visual review: Completed
- Visual verdict: PASS
- Screenshots: ![A bare sheet in edit mode at 1280: the rows band ends with Family tree (an open-position picker with Claim position, and a family picker with Place in tree), Residence (a room search with Find, a room picker and Make residence), Property (the Beginnings grant default and Grant property), House claim, Vacancy and Reputation](docs/reviews/4226/01-bare-sheet-estate-editors-1280.png) ![The same sheet after three saves: Family tree reads "Second daughter (House Katta)" with the pickers gone, Residence lists "Katta Manor, East Wing", and Reputation lists The Lamplighters at 250 with its own Save](docs/reviews/4226/02-filled-estate-rows-1280.png) ![The bare sheet at 390 wide: every estate editor stacked in one column inside the band with no horizontal page overflow](docs/reviews/4226/03-estate-editors-390.png)
- Comparison notes: The spec asks for the kinship node, residence, property house, house claim and vacancy, and organization reputation to be editable in edit mode, each through a public writer CG's finalize also uses. All six appear as sections of the rows band, in the same section style, picker and button shapes as piece B's sections above them (Stats to Introductions), so staff meet one editing surface. The family tree section swaps its pickers for the held position once the sheet has one, since a sheet holds one position. Rooms are found by search and never listed, per the standing rule that rooms are searched; an empty search lists none. The Estate tab stays hidden: the spec allows opening it for these rows, and the rows band reaches them without exposing the rest of Estate, which stays with later piece 3. No copy explains the screen; labels are the field names.
- Tested interactions: open `/characters/1` as staff; turn on the header's Edit switch; in Family tree pick "Second daughter (House Katta)" and press Claim position; read the held position; in Residence type "east", press Find, pick "Katta Manor, East Wing", press Make residence; read the listed room; in Reputation pick The Lamplighters, type 250, press Set reputation; read the row's value. The harness asserts the three requests the page sent (path and body) and that no page error was raised. At 390 wide, turn on Edit and measure the page's horizontal overflow (none).
- Fixture/live boundary: the route, `ProtectedRoute`, the sheet page, its hooks, `StaffEditProvider`, the header toggle, `StaffRowsBand` and the bundle are real; every `/api/**` response is a fixture, and each staff write answers with a sheet payload whose `staff_edit.rows` carries the new kin node, residence or reputation. That the real endpoints write those rows and answer with them is proved over HTTP by `world.character_sheets.tests.test_staff_estate` (staff gating, room search, residence and reputation in the rows) and the writers by its service tests, on the Postgres parity tier; CG finalize through the delegated writers by `world.character_creation` (1215 tests with `world.character_sheets`, parity tier), `test_property_grant_hook`, `test_vacancy_finalize` and `world.societies.tests.test_house_creator`; the editors' requests by `StaffEdit.test.tsx` (11).
- Overall outcome: PASS

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Family tree section, bare sheet | open-position picker with Claim position; family picker with Place in tree | MATCH | docs/reviews/4226/01-bare-sheet-estate-editors-1280.png |
| Family tree section, placed | the held position by name, no pickers | MATCH | docs/reviews/4226/02-filled-estate-rows-1280.png |
| Residence section | room search with Find, a room picker, Make residence; held rooms listed | MATCH | docs/reviews/4226/02-filled-estate-rows-1280.png |
| Property, house claim and vacancy | a picker and one action each; property defaults to the Beginnings grant | MATCH | docs/reviews/4226/01-bare-sheet-estate-editors-1280.png |
| Reputation section | one row per organization with its value and Save; an add row with organization, value and Set reputation | MATCH | docs/reviews/4226/02-filled-estate-rows-1280.png |
| Same style as the rows band | section headings, pickers and buttons match pieces B and C | MATCH | docs/reviews/4226/01-bare-sheet-estate-editors-1280.png |
| Phone width | one column, no horizontal overflow | MATCH | docs/reviews/4226/03-estate-editors-390.png |

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| R01-kinship-node | PASS | captures 01 and 02; `EstateWriterTests` (self-serve once, claim, no second position, closed position refused) | #3988 spec, PR D table |
| R02-residence | PASS | capture 02; `test_residence_is_one_open_tenancy`, `test_a_guest_key_does_not_count_as_living_there`, the residence API test | #3988 spec, PR D table |
| R03-property-house | PASS | `test_property_is_granted_once_per_profile`, `test_a_property_without_a_profile_needs_one`, `test_property_grant_hook` | #3988 spec, PR D table |
| R04-house-claim-and-vacancy | PASS | `test_an_unapproved_house_claim_is_refused`, the vacancy tests (taken and counted down, refused membership keeps the count, kin opening refused to a placed sheet), `test_house_creator`, `test_vacancy_finalize` | #3988 spec, PR D table |
| R05-organization-reputation | PASS | capture 02; `test_reputation_is_set_to_the_value_not_bumped`, the reputation API test | #3988 spec, PR D table |
| R06-one-writer-shared-with-finalize | PASS | `world/character_creation/estate_writer.py`; finalize's residence, property, house-claim and vacancy helpers delegate; CG suite green on the parity tier | #3988 spec, backend |
| R07-staff-only | PASS | `test_the_player_cannot_use_the_estate_actions` | #3988 spec, `can_staff_edit_sheet` |
| R08-docs-in-tandem | PASS | `docs/systems/character_sheets.md`, `character_creation.md`, `INDEX.md` | CLAUDE.md, docs are directives |

## Unresolved findings

- None
