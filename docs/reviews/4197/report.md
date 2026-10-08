# Review evidence

- Reviewed revision: `db8c2f555cb265b374ed716d387e65f7225d3348`
- Reviewer: the implementing agent (Claude Code), with the Playwright harness on the real deity edit page; the migration-reviewer agent on 0209 (PASS); no demo link on the issue, so no demo-fidelity pass
- Reviewer verdict: PASS
- Application/build identity: production bundle from `vite build` at the reviewed revision, served by `vite preview` on port 4187
- Environment: Linux devcontainer, Playwright 1.58.2 Chromium headless; every `/api/**` response is a fixture (no Django behind the preview build)
- Viewports/themes: 1280x900, the default light theme
- Approved design: the spec on issue #4197 (spec:approved by ApostateCD, 2026-10-08): search in the picker, near-matches before create, staff-only create, the merge as an admin action, aliases on merge. The names in the fixture are placeholder vocabulary (Scythe, Silk, Wolf; "Sickles" typed), never content rows.
- Visual review: Completed
- Visual verdict: PASS
- Screenshots: ![The picker open on the Fleshreaper's Favored facets with "Sickles" typed: the typed spelling first, Did you mean with Scythe, and the Create item](docs/reviews/4197/01-near-and-create-1280.png) ![After Create: the Sickles chip beside Wolf and the picker closed](docs/reviews/4197/02-created-chip-1280.png) ![The picker with "scythes" typed: Scythe listed, no Create item](docs/reviews/4197/03-resolves-no-create-1280.png)
- Comparison notes: The Favored facets row holds the Wolf chip and the "+ Add facet" button, as the editor had it. Opening the picker shows a search box; typing "Sickles" lists nothing from the loaded vocabulary, then "Did you mean" with Scythe (the near endpoint's answer) and "Create “Sickles”" with a plus. Choosing Create POSTs the spelling and the chip appears beside Wolf with its own remove control; the options refetch includes the new row so the chip is named. Typing "scythes" lists Scythe (its key equals the typed one) and offers no Create. The staff account is the fixture's `is_staff: true`; the player case (no Create) and the aliases are proved by the unit tests below.
- Tested interactions: open `/staff/pantheon/7/edit` as staff; open the picker; type "Sickles" and read the near list and the Create item; click Create and read the chip; reopen, type "scythes" and read that Create is absent. No page errors were raised.
- Fixture/live boundary: the page, the editor's sections, the picker, the popover and the bundle are real. Every `/api/**` response is a fixture: the staff account, the being's page and the editor options (three facets), `GET /api/magic/facets/near/` answering Scythe for a spelling starting "sick", `POST /api/magic/facets/` answering a new row, bare lists for everything else the chrome asks for. The server side (the spelling rule, find and near, the staff-only create answering an existing facet with `matched: true`, the merge across all eight relations, the admin action's confirmation page) is proved by `world.magic.tests.test_facets` (16), not by this harness.
- Overall outcome: PASS

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Favored facets row: existing chip and the "+ Add facet" button | as the editor had it | MATCH | docs/reviews/4197/01-near-and-create-1280.png |
| Picker open with a search box | present | MATCH | docs/reviews/4197/01-near-and-create-1280.png |
| A new spelling: "Did you mean" with the near answer | Scythe | MATCH | docs/reviews/4197/01-near-and-create-1280.png |
| A new spelling, staff: the Create item | Create “Sickles” | MATCH | docs/reviews/4197/01-near-and-create-1280.png |
| After Create: the chip beside the existing one, picker closed | Sickles | MATCH | docs/reviews/4197/02-created-chip-1280.png |
| A spelling that resolves: the facet listed, no Create | Scythe, no Create | MATCH | docs/reviews/4197/03-resolves-no-create-1280.png |

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| R01-create-from-the-picker-staff-only | PASS | the first two captures; `FacetPicker.test.tsx` "never offers a player the create item"; `test_facets.py` `FacetApiTests` (a player's POST is 403, staff 201) | spec section 1, decision 2 |
| R02-near-matches-before-create | PASS | the first capture; `test_facets.py` `FindAndNearTests` (equal key, contained, one edit, aliases); `FacetPicker.test.tsx` | spec section 2 |
| R03-a-spelling-that-resolves-is-answered-not-created | PASS | the third capture; `FacetApiTests.test_a_spelling_that_resolves_answers_the_existing_facet` (`matched: true`, one row) | spec section 1 |
| R04-merge-repoints-every-relation | PASS | `MergeFacetsTests` (all eight relations, the collision rule, the winner among the losers); `test_every_live_relation_has_a_handler`; `test_a_relation_without_a_handler_stops_the_merge` | spec section 3 |
| R05-merge-is-an-admin-action-with-a-confirmation | PASS | `MergeAdminTests` (the confirmation page lists the survivors' bindings; apply merges; one selection refused) | spec section 3, decision 3 |
| R06-aliases-on-merge | PASS | `MergeFacetsTests.test_bindings_follow_the_winner_and_the_losers_become_aliases` (retired names become aliases of the winner, existing aliases follow) | spec section 4, decision 1 |
| R07-migration | PASS | `0209_facet_alias`, schema-only CreateModel on main's leaf, migration-reviewer PASS | CLAUDE.md, migrations |
| R08-docs-in-tandem | PASS | `docs/systems/magic.md`, `worship.md`, `INDEX.md`, `MODEL_MAP.md`, `AGENT_GLOSSARY.md`, ADR-4197, the two frontend `CLAUDE.md` files | CLAUDE.md, docs are directives |

## Unresolved findings

- None
