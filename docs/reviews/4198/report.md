# Review evidence

- Reviewed revision: `69cdc13797247d2501702049463cb5c48ff35b79`
- Reviewer: the implementing agent (Claude Code), with the Playwright harness on the real Codex entry page; the migration-reviewer agent on 0210 (PASS); the demo-fidelity-reviewer agent against demo version 3 (PASS with three fixes, all folded in: the section label takes the Lore's amber, one feast day reads singular, the fixture's tree count is the viewer's)
- Reviewer verdict: PASS
- Application/build identity: production bundle from `vite build` at the reviewed revision, served by `vite preview` on port 4198
- Environment: Linux devcontainer, Playwright 1.58.2 Chromium headless; every `/api/**` response is a fixture (no Django behind the preview build)
- Viewports/themes: 1280x1000 and 390x1100, the default light theme
- Approved design: demo version 3 linked from issue #4198 (direction B, the rail beside the Lore and the stories under it) and the spec on the issue (spec:approved by ApostateCD, 2026-10-08). The two gods are the demo's own rows (ApostateCD's text for the Fleshreaper and Calyx); the Fleshreaper's side of the feud is the demo's placeholder line.
- Visual review: Completed
- Visual verdict: PASS
- Screenshots: ![The Fleshreaper read by staff: the rail beside the Lore with Domains, Also called, Feast day, Cards (The Tower reversed), Favored, Associated and the Feud link to Calyx; under the Lore the feast day's section with its date and the feud's section](docs/reviews/4198/01-fleshreaper-staff-1280.png) ![Calyx read by staff: the long quote atop, her rail, and her own side of the feud under the Lore](docs/reviews/4198/02-calyx-staff-1280.png) ![Calyx read by a stranger who cannot see the Fleshreaper: no Feud line in the rail and no Feud section](docs/reviews/4198/03-calyx-stranger-1280.png) ![The Fleshreaper at phone width: the tree above the content, the rail folded under the Lore with a top rule, the sections below](docs/reviews/4198/04-fleshreaper-390.png)
- Comparison notes: The entry card keeps its breadcrumb, title and (for Calyx) the italic quote atop; the Lore box and the rail sit in a two-column grid, the rail with a left rule and small uppercase muted labels in the demo's order. The feast-day line reads "The Reaping Festival · Masquing 18 (10/18)" and is a link down to its section; the cards read "Death, The Tower reversed"; the Feud line is a link that opens Calyx. Under the Lore, each section is headed by an amber uppercase label, the bold name and the muted date, then the story. Calyx's page shows her own side of the feud. A stranger's reading of Calyx draws no Feud line and no Feud section. At 390px the tree stacks above the content (the Codex page's own sidebar did not fold before this branch; fixed here) and the rail folds under the prose with a top rule. Two deliberate differences from the demo: the feast-day rail line is one link over the name and the date where the demo linked the name alone; the rail is 14rem wide where the demo drew 230px.
- Tested interactions: open `/codex?subject=3&entry=1` as staff and read the rail and the sections; click the feast-day line and read that its section scrolls into view; click the Feud line and read that Calyx opens with her quote and her own feud section; open Calyx as a stranger and read that no feud is drawn; open the Fleshreaper at 390px and read the one-column fold with the rail below the Lore. No page errors were raised.
- Fixture/live boundary: the page, the tree, the entry card, the rail, the sections, the links and the bundle are real. Every `/api/**` response is a fixture: the account (staff or a stranger), the tree and subject, the two entries with their `companion` as the provider shapes it (the stranger's Calyx without the feud, as the server would answer). The server side (the provider's groups and order, the "reversed" suffix, the date spelling, the visibility gate on relationships, the research gate on the companion, the registry asked on retrieve only, the editor's reversed pick and per-side story, the migration) is proved by `world.worship.tests.test_companion` (5), `world.codex.tests.test_companions` (4), `world.worship.tests.test_editor` and `test_models`, `world.game_clock.tests.test_services`, not by this harness.
- Overall outcome: PASS

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| The rail beside the Lore box, two columns, left rule | present at 1280 | MATCH | docs/reviews/4198/01-fleshreaper-staff-1280.png |
| Rail groups in the demo's order with uppercase muted labels | Domains, Also called, Feast day, Cards, Favored, Associated, Feud | MATCH | docs/reviews/4198/01-fleshreaper-staff-1280.png |
| The feast-day line with its date | The Reaping Festival · Masquing 18 (10/18) | MATCH | docs/reviews/4198/01-fleshreaper-staff-1280.png |
| A reversed card | Death, The Tower reversed | MATCH | docs/reviews/4198/01-fleshreaper-staff-1280.png |
| The feast-day section under the Lore: label, name, date, story | Feast day / The Reaping Festival / Masquing 18 (10/18) | MATCH | docs/reviews/4198/01-fleshreaper-staff-1280.png |
| The feud section: label, the other god as a link, this god's side | Feud / Calyx | MATCH | docs/reviews/4198/01-fleshreaper-staff-1280.png |
| Calyx: the quote atop, her own side of the feud | present | MATCH | docs/reviews/4198/02-calyx-staff-1280.png |
| A stranger's Calyx: no Feud line, no Feud section | absent | MATCH | docs/reviews/4198/03-calyx-stranger-1280.png |
| Phone width: one column, the rail under the Lore with a top rule | folded | MATCH | docs/reviews/4198/04-fleshreaper-390.png |

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| R01-companion-on-the-entry-registry | PASS | `test_companions.py` (a provider is asked on retrieve, not on list; no provider gives null; the reader carries the visible set); the first capture | spec section 1 |
| R02-the-deitys-provider-every-group-in-order | PASS | `test_companion.py` `test_every_group_in_order_and_nothing_the_reader_may_not_see` (calendar order, "The Tower reversed", empty groups omitted, the feast-day anchor); the first capture | spec section 2 |
| R03-a-relationship-rides-the-other-entrys-visibility | PASS | `test_companion.py` (staff read the feud, never a god without a page; a player reads it once a character knows Calyx); the third capture | spec section 2, the ruling on the demo |
| R04-the-companion-rides-the-research-gate | PASS | `test_companions.py` `test_an_entry_still_being_researched_carries_no_companion` | spec section 2 (gate) |
| R05-a-card-link-with-an-orientation | PASS | `test_models.py` (one row per card, reversal a flag, `.add()` still upright); `test_editor.py` (a reversed pick persists and reads back); `PantheonPages.test.tsx` (each card offered both ways, a picked card neither) | spec section 3, decision 3 |
| R06-a-story-per-side | PASS | `test_models.py` (stories swap with their sides); `test_editor.py` (saving one side leaves the other untouched); the second capture | spec section 4 |
| R07-every-ic-date-carries-its-number | PASS | `game_clock/tests/test_services.py` ("Dreaming 14 (1/14/1012)"); events, relationships and tidings tests; the CG ReviewStage; the first capture | spec section 5, decision 2 |
| R08-the-page-and-the-modal | PASS | the four captures; `EntryDetail.test.tsx` (rail and sections from a fixture, nothing when null, a line opens the other entry); the modal untouched | spec section 6, decision 1 |
| R09-migration | PASS | `0210_being_tarot_orientation_and_relationship_sides`, schema-only, the auto M2M table adopted in state, migration-reviewer PASS | CLAUDE.md, migrations |
| R10-docs-in-tandem | PASS | `docs/systems/codex.md`, `worship.md`, `INDEX.md`, `MODEL_MAP.md`, both `AGENT_GLOSSARY.md`, ADR-4198, `docs/roadmap/worship.md`, `game_clock/CLAUDE.md`, `pantheon/CLAUDE.md` | CLAUDE.md, docs are directives |

## Unresolved findings

- None
