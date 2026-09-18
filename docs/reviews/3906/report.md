# Review evidence — issue #3906, Ties visibility

- Reviewed revision: `1db0d5d4d855e4533c8b7bc5f62d1efe0fd502b6`
- Reviewer: demo-fidelity-reviewer, one pass against this revision
- Reviewer verdict: PASS
- Application/build identity: the shipped `CharacterSheetPage` mounted at a real route with its real hooks, composing the shipped `TiesPanel` (`frontend/src/character_sheets/components/sheet/panels.tsx`) and `ReputationTab` (`frontend/src/reputation/components/ReputationTab.tsx`), with the shipped `frontend/src/character_sheets/sheet.css` and the application's real `frontend/src/index.css` token cascade
- Environment: Chromium driven by Playwright against a Vite 6.4.3 dev server on localhost:4174, in the project devcontainer on Linux. The preview entry (`frontend/src/refsheet-preview.tsx`) and its HTML page were throwaway and are not part of the branch
- Viewports/themes: 1440x1400 desktop and 400x1400 phone, deviceScaleFactor 1, light theme with the root carrying `data-realm="arx"`
- Approved design: the Reference Sheet demo at https://claude.ai/artifact/KaVL8KAS5B23bhThLtV6v7, linked from the parent issue #3898. #3906 draws no new surface — it changes who may see two blocks the demo already draws — so the demo's Ties rail, plus the Reference Sheet vocabulary recorded in `docs/systems/character_sheets.md` and `frontend/src/character_sheets/components/sheet/primitives.tsx`, is the design of record
- Visual review: completed. Four captures of the rendered application at three distinct viewer tiers were inspected by a vision-capable reviewer against the Reference Sheet vocabulary and against the ruling's own requirements
- Visual verdict: PASS
- Screenshots: ![Ties, the character's own player](docs/reviews/3906/owner-ties.png) ![Ties, a viewer resolved to FRIENDS](docs/reviews/3906/friend-ties.png) ![Ties, a viewer below the tier](docs/reviews/3906/stranger-ties.png) ![Ties at 400px, friend](docs/reviews/3906/friend-ties-phone.png)
- Comparison notes: the reviewer could not reach the demo URL from this environment and said so. In its place it used the Reference Sheet vocabulary recorded in `docs/systems/character_sheets.md` and `frontend/src/character_sheets/components/sheet/primitives.tsx`, plus the approved spec in #3906's issue body. Its finding: the two-column `refsheet-columns-2` layout is intact at all three tiers, the right rail always runs Standing then Titles then Covenant, and Belongs to / Thought of as appear or vanish inside Standing without disturbing what sits below them. Belongs to and Thought of as render as `Subheading` over hairline `Entries`/`Entry` rows with the rank as the row's aside and the tier as its `Tag`, the same shape as Titles and Mentors beside them. No divergence from the Reference Sheet vocabulary was found. One informational note, not a defect: the phone capture shows a broken-image glyph over the portrait, which is the throwaway harness's empty fixture URL and is untouched by this branch
- Tested interactions: the section row was clicked through to Ties on each capture rather than deep-linked, so the rail is what the page's own navigation produces. The three viewer tiers are driven by the payload the server would send, not by a client flag: owner receives populated `standing` and `covenants`, friend receives the same `standing` with every SELF-gated section emptied, stranger receives `standing: {memberships: [], reputations: []}` and the same public `covenants`. Organization and covenant names render as links into `/orgs/:id` and `/covenants/:id`
- Fixture/live boundary: the page, its components, the stylesheet and the token cascade are the real shipped code. The sheet payload is a hand-written fixture matching the serializer TypedDicts in `src/world/character_sheets/types.py`. Every other API call the page makes was intercepted and answered — and three of them were answered DELIBERATELY EMPTY: `/api/societies/memberships/`, `/api/societies/reputations/` and `/api/covenants/`, the three endpoints these blocks used to call. Starving them is the test: anything still drawn on the rail can only have come from the sheet payload. The application shell (authentication, Layout, providers beyond a Redux store and a query client) was not mounted, and the server-side visibility resolution is covered by unit tests rather than by these captures
- Overall outcome: PASS

## Requirement ledger

| id | status | evidence | authorized decision |
| --- | --- | --- | --- |
| real-surface | PASS | The shipped `CharacterSheetPage` and `sheet.css` were mounted and rendered at a real route, not a mockup. Build identity above. | |
| covenant-public | PASS | `stranger-ties.png` draws the Covenant block with Lampwright / Second / ENGAGED, the same rows the owner sees in `owner-ties.png`. | |
| standing-friends | PASS | `friend-ties.png` draws Belongs to and Thought of as in full; `stranger-ties.png` draws neither. The friend is not the owner — no Mentors block, the renown CARD rather than the panel. | |
| payload-not-endpoints | PASS | The three account endpoints were served empty, and the rail still draws. Nothing on it can have come from a query. | |
| no-false-empty-state | PASS | `stranger-ties.png` contains no sentence about belonging to nobody. Withheld and genuinely empty both vanish, so neither states a falsehood and neither is distinguishable from the other. | |
| named-tier-only | PASS | HONORED / LIKED / DISFAVORED render as tags; no raw reputation value appears anywhere in the captures. | |
| kin-unnested | PASS | `owner-ties.png` shows Mentors AND Kin; `friend-ties.png` and `stranger-ties.png` have no Mentors block and still show Kin. #3901 had nested Kin inside `mentors.length > 0`, so every character without a Mentor's Vow lost their family from the page. | |
| page-keeps-shape | PASS | All three tiers keep Relationships, Kin, Standing, Titles in the same places; only the blocks the ruling governs change. | |
| responsive | PASS | `friend-ties-phone.png` at 400px: single column, rows wrap, no horizontal page scroll, nothing clipped. | |
| no-errors | PASS | No page errors and no console errors on any of the four captures. | |
| fixture-boundary | PASS | Stated in full above, naming what is real, what is fixture, and which three endpoints were deliberately starved. | |
| server-side-gate | PASS | Not visible in a capture, because the captures feed the page the payload the server would send. Proven instead by `TestStandingAndCovenantSections` in `src/world/character_sheets/tests/test_viewset.py`: seven tests over the three access levels, plus the query-count guard at 52. `just test-fast world.character_sheets` ran 370 tests, OK. | |

## Visual checklist

| Element | Expected | Result | Evidence |
| --- | --- | --- | --- |
| Covenant for a stranger | Public per the ruling, the same rows the owner sees | MATCH | Covenant / Lampwright / Second / ENGAGED appears identically in owner-ties.png, friend-ties.png and stranger-ties.png |
| Standing for a friend | Belongs to and Thought of as populated | MATCH | friend-ties.png: House du Verane / Voice, The Pawnbrokers of the Ward / Sister, and Honored / Liked / Disfavored, identical to the owner's rows |
| Standing for a stranger | Absent entirely | MATCH | stranger-ties.png: Standing carries Renown alone, then straight to Titles. Neither subheading is present |
| No false empty state | Withheld and empty indistinguishable, neither stating a falsehood | MATCH | stranger-ties.png draws no line about belonging to nobody; the block returns null |
| Reputation tier | The named tier, never a raw value | MATCH | owner-ties.png and friend-ties.png: HONORED, LIKED, DISFAVORED as tags |
| Kin without a Mentor's Vow | Kin present whether or not mentors are | MATCH | owner-ties.png shows Mentors and Kin both; friend-ties.png and stranger-ties.png show Kin with no Mentors block |
| Shape across tiers | No collapsed or orphaned rail | MATCH | The two-column layout holds in all three captures; the rail runs Standing, Titles, Covenant throughout |
| Phone at 400px | One column, no horizontal scroll, nothing clipped | MATCH | friend-ties-phone.png is exactly 400px wide and stacks plate, nav, Relationships, Kin, Standing, Titles, Covenant |
| Reference Sheet vocabulary | Subheadings over hairline entries, the rank or tier as the row's tag, render-or-vanish | MATCH | owner-ties.png, friend-ties.png, stranger-ties.png; the touched components import only `Entries`, `Entry`, `Stack`, `Subheading`, `Tag` from `primitives.tsx` |

## Divergences

None. The reviewer found no divergence from the Reference Sheet vocabulary.

One boundary is drawn deliberately rather than left silent. The plate's glance line names `House du Verane` for every viewer, including the stranger whose Standing rail is withheld. That is the character's LINEAGE (`identity.family`, a `Profile` field) rather than an organization membership: it is a different model, it was public before this branch, and #3906 rules on standing only. Narrowing it would be a separate ruling on a separate surface.

## Unresolved findings

None
