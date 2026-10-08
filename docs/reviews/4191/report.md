# Review evidence

- Reviewed revision: `f3fb31bce51e35bb439baa1aa8dbb68d85ae5d39`
- Reviewer: the implementing agent (Claude Code), with the Playwright harness on the real page; no demo link on the issue, so no demo-fidelity pass
- Reviewer verdict: PASS
- Application/build identity: production bundle from `vite build` at the reviewed revision, served by `vite preview` on port 4184
- Environment: Linux devcontainer, Playwright 1.58.2 Chromium headless; every `/api/**` response is a fixture (no Django behind the preview build)
- Viewports/themes: 1280x900 and 390x1100, the default light theme (the wash leans on `--primary`, so it is grey here and amber on the parchment and realm themes)
- Approved design: the rulings on issue #4191 (ApostateCD, 2026-10-08, in chat): the staff banner goes; every non-public entry takes a light, subtle shade with nothing written; the per-character badges only on multi-character accounts. Every entry name and line in the fixtures is placeholder copy, so wording is never a finding.
- Visual review: Completed
- Visual verdict: PASS
- Screenshots: ![Staff at a subject: no banner, the two restricted cards washed, no badges](docs/reviews/4191/01-staff-subject-1280.png) ![A one-character player: the same wash, Researching on the uncovered entry, no badge bearing their own name, no scope dropdown](docs/reviews/4191/02-player-subject-1280.png) ![A two-character player: the scope dropdown and a badge per character on each held entry](docs/reviews/4191/03-two-characters-subject-1280.png) ![A restricted entry read in full on a washed plate, no Known by line](docs/reviews/4191/04-entry-detail-1280.png) ![Search results: the restricted result washed, the public one plain](docs/reviews/4191/05-search-1280.png) ![Phone width](docs/reviews/4191/06-player-subject-390.png)
- Comparison notes: The page opens on the subject with no line above the sidebar or the content for staff or players. The two public cards sit on the plain card ground; the two restricted cards carry a wash and a shifted border, and nothing on them says restricted, private or secret. For staff the restricted cards carry no badge (staff have no characters). For a one-character player the same two cards are washed, the uncovered one keeps its Researching badge, and the player's own name appears nowhere; the character-scope dropdown is absent. For a two-character player the dropdown is present and each held card lists both characters. The entry detail of a restricted entry is a washed plate with the breadcrumb, the name and the lore; no "Known by" line for one character. In the sidebar search the restricted result is washed and the public one plain. At phone width the cards stack and nothing overflows. The first evidence run found the class on the card and no wash on the page (Tailwind's `bg-card` won the background-color); the wash moved to a background-image and the run was repeated at this revision.
- Tested interactions: open `/codex?subject=3` as staff, as a one-character player and as a two-character player; read the computed `background-image` of a restricted card (a gradient) and of a public card (none); open `/codex?subject=3&entry=3` and read the plate's computed background-image; type "sh" in the search box and read the two results' classes; the subject at 390px. No page errors were raised.
- Fixture/live boundary: the page, router, sidebar, tree, search, entry grid, entry detail and bundle are real. Every `/api/**` response is a fixture: one category and one leaf subject, four entries (two public, one restricted and known, one restricted and uncovered) filtered to what the viewer may see the way `_visible_entry_ids` filters them, `known_by` per viewer, the account (`is_staff` for staff) and the viewer's roster entries (none, one, two). The server side (`is_public` on both serializers, the visibility gate) is unchanged by this PR and proved by `world.codex.tests`.
- Overall outcome: PASS

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| No "Staff view" line for staff | absent | MATCH | docs/reviews/4191/01-staff-subject-1280.png |
| Restricted card: a light wash and a shifted border, nothing written | as ruled | MATCH | docs/reviews/4191/01-staff-subject-1280.png |
| Public card: the plain card ground | plain | MATCH | docs/reviews/4191/01-staff-subject-1280.png |
| The wash reaches the page (computed background-image, not the class) | gradient on restricted, none on public | MATCH | the spec's assertions at this revision |
| One-character player: no badge with their own name, no scope dropdown | absent | MATCH | docs/reviews/4191/02-player-subject-1280.png |
| Uncovered entry keeps its Researching badge | present | MATCH | docs/reviews/4191/02-player-subject-1280.png |
| Two-character player: scope dropdown and a badge per character | present | MATCH | docs/reviews/4191/03-two-characters-subject-1280.png |
| Entry detail of a restricted entry: washed plate, no "Known by" for one character | as ruled | MATCH | docs/reviews/4191/04-entry-detail-1280.png |
| Search results: restricted washed, public plain | as ruled | MATCH | docs/reviews/4191/05-search-1280.png |
| Phone width | cards stack, nothing overflows | MATCH | docs/reviews/4191/06-player-subject-390.png |

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| R01-banner-out | PASS | `CodexPage.restricted.test.tsx` "tells staff nothing about their view"; the staff capture | issue #4191, ruling 1 |
| R02-non-public-entries-washed | PASS | `EntryGrid.test.tsx`, `EntryDetail.test.tsx`, `CodexPage.restricted.test.tsx` (class); the spec's computed-style assertions (the rule reaches the page) | issue #4191, ruling 2 |
| R03-nothing-written | PASS | `EntryGrid.test.tsx` "writes nothing"; the captures | the no-unnecessary-labeling rule |
| R04-badges-only-multi-character | PASS | `EntryGrid.test.tsx` and `EntryDetail.test.tsx` "only on a multi-character account"; the player and two-character captures | issue #4191, ruling 3 |
| R05-same-word-as-the-sheet | PASS | `codex.css` header; a tone shift and nothing else, as the sheet's private region (#4124) | #4124 ruling, 2026-10-03 |
| R06-sharing-an-entry | OUT_OF_SCOPE | no Codex API or UI for `CodexTeachingOffer`; stated on the issue | issue #4191, out of scope |

## Unresolved findings

- None
