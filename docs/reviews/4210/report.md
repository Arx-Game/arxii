# Review evidence

- Reviewed revision: `12655097340c2a88170c14fa3e5385bcc5b10058`
- Reviewer: the implementing agent (Claude Code), with Playwright on the real `/characters/:entry` sheet page from the production bundle, every `/api/**` call answered by fixtures shaped like the serializers; no demo link on the issue (lightweight lane), so no demo-fidelity pass; no migration
- Reviewer verdict: PASS
- Application/build identity: `vite build` of the frontend at the reviewed revision, served by `vite preview --port 4213`; harness `frontend/e2e/evidence/family-kin-4210.spec.ts`, four readings, all passing
- Environment: Linux devcontainer on WSL2, Playwright Chromium headless (build 1208)
- Viewports/themes: 1280x900 and 390x1100, the default light theme
- Approved design: the issue's own change (lightweight; ruled by ApostateCD in chat on 2026-10-09): the sheet's House row is plain text, since a Family pk is not an Organization pk and the org page is member-only; the Kin block reads "House X" only for a house-styled kind, draws `Family.description` under the family line, and links a selected sheeted kinsperson to their sheet by roster entry id (a third id space beside the Kinsperson pk and the sheet pk); an unplayed NPC links nowhere.
- Visual review: Completed
- Visual verdict: PASS
- Screenshots: ![The sheet front at 1280: the At a glance block with the House row reading "Katta" as plain text, the same weight as the rows around it, with no link styling](docs/reviews/4210/01-sheet-front-house-row-1280.png) ![The Ties tab at 1280: the Kin block headed by the ledger line "House Katta", the family's description as a prose paragraph under it, and the four-node tree below](docs/reviews/4210/02-kin-block-house-description-1280.png) ![The sister's node selected: the detail entry's name "Maren mar Katta" styled as a link, "pc" beside it, her description, and "Related as sibling."](docs/reviews/4210/03-kin-selected-sister-link-1280.png) ![The late father's node selected: the detail entry's name "Aldous mar Katta" as plain text, "described" beside it, his description, and the line that nobody on the roster answers to this person](docs/reviews/4210/04-kin-selected-npc-no-link-1280.png) ![The same Kin block for a commoner-kind family: the ledger line reads the bare "Katta" with the description under it](docs/reviews/4210/05-kin-block-commoner-1280.png) ![The Ties tab at 390 wide with the sister selected: the family line, description, tree and the linked detail entry stacked in one column](docs/reviews/4210/06-kin-block-390.png)
- Comparison notes: On the front, the House row's value is set in the same face and colour as Age, Kind and Beginning beside it, with none of the underline-and-rule treatment the page gives its links (the Journal button in the plate is the reference), and the DOM carries no anchor whose href starts with `/orgs/`. On Ties, the Kin block opens with the ledger line, then the description as a `.refsheet-prose` paragraph in the sheet's body face, then the tree plateau, in that order. Selecting Maren renders the entry name as a link in the sheet's link treatment with href `/characters/2` (her roster entry, not her sheet id 21 and not her node id 102); selecting Aldous renders the name plain. The commoner variant differs from the house variant in exactly the ledger line. At 390 the Ties section stacks and nothing overflows the viewport.
- Tested interactions: open `/characters/1` as a signed-in non-owner; read the At a glance block; count `/orgs/` anchors (zero). Click Ties in the section navigation; read the Kin ledger line and the description; click the node with `data-node-id` 102 and read the detail entry's link and relatedness line; click node 103 and read the plain name and the no-roster line. Repeat on a commoner-kind payload and read the bare family name. Repeat at 390 wide. No page errors were raised on any reading.
- Fixture/live boundary: the page, its hooks, `SheetPanel`, `TiesPanel`, `KinshipPanel`, `KinTreeGraph` and the bundle are real; every `/api/**` response is a fixture (the account, the roster entry, the sheet payload with `family {id 7, name Katta}`, the kin tree with a family carrying `kind.styles_as_house` and `description` and four nodes carrying `sheet_id` and `roster_entry_id`, and `{label: "sibling"}` for the relationship query). That the real kin tree payload (`GET /api/roster/kin/tree/{character_id}/`) carries `roster_entry_id` with those semantics is proved over HTTP by `test_nodes_name_the_roster_entry_of_a_sheeted_kinsperson` (`world.roster.tests.test_kin_api`, 21 tests), not by these captures; the two components' readings are also proved by `KinshipPanel.test.tsx` (10) and `SheetPanel.test.tsx` (2).
- Overall outcome: PASS

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| House row on the sheet front | "Katta" as plain text, no link | MATCH | docs/reviews/4210/01-sheet-front-house-row-1280.png |
| Kin ledger line for a house-styled kind | House Katta | MATCH | docs/reviews/4210/02-kin-block-house-description-1280.png |
| Family description under the ledger line | the family's description paragraph, in the sheet's prose face | MATCH | docs/reviews/4210/02-kin-block-house-description-1280.png |
| Selected sheeted kinsperson's name | a link to /characters/2 (her roster entry), with "Related as sibling." | MATCH | docs/reviews/4210/03-kin-selected-sister-link-1280.png |
| Selected unplayed NPC's name | plain text, with the no-roster line | MATCH | docs/reviews/4210/04-kin-selected-npc-no-link-1280.png |
| Kin ledger line for a commoner kind | Katta, no "House" | MATCH | docs/reviews/4210/05-kin-block-commoner-1280.png |
| Phone width | one column, the linked entry readable, no overflow | MATCH | docs/reviews/4210/06-kin-block-390.png |

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| R01-house-row-is-plain-text | PASS | the first capture; `SheetPanel.test.tsx` (name present, no link named Katta) | issue #4210, lightweight |
| R02-kin-block-reads-family-description | PASS | the second and fifth captures; `KinshipPanel.test.tsx` (description read; none drawn when empty) | issue #4210, ruled by ApostateCD 2026-10-09 |
| R03-sheeted-kin-link-by-roster-entry | PASS | the third and fourth captures; `KinshipPanel.test.tsx` (href /characters/503 from roster_entry_id 503, sheet_id 903; no link when null); `test_kin_api` (payload carries `roster_entry_id`, null for an unsheeted node) | issue #4210 |
| R04-house-prefix-only-for-house-styled-kinds | PASS | the fifth capture; `KinshipPanel.test.tsx` (bare name for `styles_as_house` false) | issue #4210 |
| R05-docs-in-tandem | PASS | `docs/systems/kinship.md`, `docs/systems/INDEX.md`, `docs/roadmap/character-creation.md`; `OrgPage.tsx` header corrected | CLAUDE.md, docs are directives |

## Unresolved findings

- None
