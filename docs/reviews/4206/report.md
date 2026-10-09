# Review evidence

- Reviewed revision: `d9ad3f5604595669685e83d5c9f79c92b09111f0`
- Reviewer: the implementing agent (Claude Code), with Playwright on the real character-creation Lineage page, the real staff Almanach house document and the real org page from the production bundle, every `/api/**` call answered by fixtures shaped like the serializers; no demo link on the issue (lightweight lane, the shape ruled in chat), so no demo-fidelity pass; the migration was reviewed against the reviewing-migrations checklist and the two models by the schema-shape reviewer (its one actionable finding, model-level calendar bounds, is folded into the reviewed revision)
- Reviewer verdict: PASS
- Application/build identity: `vite build` of the frontend at the reviewed revision, served by `vite preview --port 4193`; harness `frontend/e2e/evidence/house-observances-4206.spec.ts`, three readings, all passing
- Environment: Linux devcontainer on WSL2, Playwright Chromium headless (build 1208)
- Viewports/themes: 1280x900 and 390x1100, the default light theme
- Approved design: the issue's own shape (lightweight; ruled by ApostateCD in chat on 2026-10-09): a day of remembrance is a house styling with a date on it (an IC month and day, a name, the house's prose), never an aspect; the founder writes zero or more on the House chapter beside the words and sigil, the Almanach document edits them with the other stylings, staff author them in admin, and the org page and house document show each day with the game's one IC date spelling.
- Visual review: Completed
- Visual verdict: PASS
- Screenshots: ![The founder's House chapter at 1280: under "the house" prose, the "days of remembrance" block holds one row with name "Founding Night", month 10, day 18, and the story in "the day", with a remove control on the row and the "a day" add door below](docs/reviews/4206/01-founder-house-chapter-day-1280.png) ![The Almanach document's House chapter at 1280: the same block between "the house" and House Quiddity, holding "The Long Vigil" on 1/2 and "Founding Night" on 10/18 with their stories, each editable, the add door under them and the Save bar at the foot](docs/reviews/4206/02-document-house-chapter-days-1280.png) ![The org page at 1280: the House of Piropa card lists "Days of Remembrance" after the Quiddity chip, each day as its name, a dot, the spelled date "Dreaming 2 (1/2)" or "Masquing 18 (10/18)", then its prose on the next line](docs/reviews/4206/03-org-page-days-1280.png) ![The same org page at 390 wide: the days stack in one column with the prose wrapping under each name and date](docs/reviews/4206/04-org-page-days-390.png)
- Comparison notes: On the founder chapter the block sits exactly where the issue puts it, beside the other stylings and under the house prose, in the chapter's own grammar (the small-caps "days of remembrance" label, a row per day with "name", "month", "day" and "the day" controls, the row's remove at the right, the "⊕ a day" chip door). The document chapter renders the same block in the same place with the house's existing days filled in and their month and day as numbers, as the deity editor gives a feast day. The org page spells each day through the server's `when` and never computes a date itself; the prose sits under the name in the muted body face, and at phone width nothing overflows.
- Tested interactions: open `/characters/create` as a founder whose draft sits at Lineage with the Fervor claim open; click Claim Fervor; fill the name, words, colors, sigil and house prose; click "Add a day of remembrance"; type the name, month 10, day 18 and the story; read the month and day values back; click "Remove day of remembrance 1" and confirm the row's controls are gone and the add door remains. Open `/staff/almanach/houses/500` as staff; read the two days' names and the second day's month; click the add door; name a third day "The Ember Feast" on 6/21; click Save; read the dispatched `almanach_edit_house` body and confirm `observances` carries all three rows as `{ic_month, ic_day, name, lore}` with no spelled date. Open `/orgs/500` as a signed-in member; read the "Days of Remembrance" heading, both names, both spelled dates and the second day's prose; repeat at 390 wide. No page errors were raised on any reading.
- Fixture/live boundary: the pages, the Lineage stage and its founder Almanach, `FounderHouseChapter`, `HouseDocument`, `HouseChapter`, `ObservanceRows`, `OrgPage` and the bundle are real; every `/api/**` response is a fixture (the CG draft, claimable titles, ladder and charter from `e2e/evidence/fixtures/`, the house document with two `observances` carrying `when`, and an org payload whose house block carries the same two). That the real document and org payloads carry `observances` with that spelling is proved over HTTP by `test_document_carries_the_houses_days_of_remembrance` (`world.societies.tests.test_almanach_api`) and `test_house_payload_carries_the_days_of_remembrance` (`world.societies.tests.test_organization_api`); that the claim submit body accepts and echoes them by `test_post_observances_persist_and_get_echoes_them` (`world.character_creation.tests.test_house_claim_api`); that the gate, materialization and the edit action behave by `test_observance_gates`, `test_observance_model_refuses_off_calendar_dates`, `test_observances_materialize_onto_the_house` (`world.societies.tests.test_house_creator`) and `test_edit_house_replaces_observances_and_refuses_bad_rows` (`actions.tests.test_almanach_actions`); the two chapters' readings by `FounderHouseChapter.test.tsx`, `HouseDocument.test.tsx`, `founderDraft.test.ts` and `OrgPage.test.tsx`.
- Overall outcome: PASS

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Founder House chapter block | "days of remembrance" under the house prose, beside the other stylings | MATCH | docs/reviews/4206/01-founder-house-chapter-day-1280.png |
| A founder's row | name, month, day, the day's prose, a remove control, an add door below | MATCH | docs/reviews/4206/01-founder-house-chapter-day-1280.png |
| Document House chapter block | the house's days filled in, editable, between the house prose and the Quiddity | MATCH | docs/reviews/4206/02-document-house-chapter-days-1280.png |
| Org page house block | "Days of Remembrance" with name, spelled date, then prose per day | MATCH | docs/reviews/4206/03-org-page-days-1280.png |
| Phone width | one column, prose wrapping under each day, no overflow | MATCH | docs/reviews/4206/04-org-page-days-390.png |

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| R01-founder-writes-days-beside-stylings | PASS | the first capture; `FounderHouseChapter.test.tsx`; `founderDraft.test.ts` (payload carries `observances`); `test_post_observances_persist_and_get_echoes_them` | issue #4206, ruled by ApostateCD 2026-10-09 |
| R02-days-copy-onto-the-house | PASS | `test_observances_materialize_onto_the_house` | issue #4206 |
| R03-document-edits-days-with-the-stylings | PASS | the second capture; `HouseDocument.test.tsx`; `test_edit_house_replaces_observances_and_refuses_bad_rows` | issue #4206 |
| R04-staff-author-in-admin | PASS | `OrganizationObservanceAdmin` (`world/societies/admin.py`), `arx manage check` clean; `test_observance_model_refuses_off_calendar_dates` | issue #4206 |
| R05-shown-with-the-one-ic-date-spelling | PASS | the third and fourth captures; `test_document_carries_the_houses_days_of_remembrance`; `test_house_payload_carries_the_days_of_remembrance` | issue #4206 (`format_ic_month_day`) |
| R06-a-styling-not-an-aspect | PASS | no catalog, no typed target: `OrganizationObservance` carries only the date, a name and prose | ADR-0101 |
| R07-docs-in-tandem | PASS | `docs/systems/houses.md`, `docs/systems/INDEX.md`, `docs/systems/MODEL_MAP.md`, `docs/roadmap/societies.md`, `src/world/societies/AGENT_GLOSSARY.md` | CLAUDE.md, docs are directives |

## Unresolved findings

- None
