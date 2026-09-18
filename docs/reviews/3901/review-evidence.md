# Review evidence — issue #3901, Holdings becomes Estate

- Reviewed revision: `87ef465752b42401659cd2f48439b36cd11ea803`
- Reviewer: demo-fidelity-reviewer, run twice — a first pass that returned FAIL with two defects, and a second on this revision after both were fixed
- Reviewer verdict: PASS
- Application/build identity: the shipped `CharacterSheetPage` mounted at a real route with its real hooks, the shipped `frontend/src/character_sheets/sheet.css` and the application's real `frontend/src/index.css` token cascade. Nothing is stubbed above the network: every fixture is served as an HTTP response to the query the page actually makes, and the section is opened by clicking the page's own section-row button
- Environment: Chromium driven by Playwright against a Vite 6.4.3 server on localhost:4175, in the project devcontainer on Linux. The preview entry and its HTML page were throwaway and were deleted before commit; they are not part of the branch
- Viewports/themes: 1440x1000 desktop and 400x1000 phone, deviceScaleFactor 1, light theme with the root carrying `data-realm="arx"`
- Approved design: this issue has no demo of its own. Its design source is Apostate's ruling in conversation, recorded verbatim in the issue body, over the section the #3898 demo already drew (https://claude.ai/artifact/KaVL8KAS5B23bhThLtV6v7). Where the built section and that demo disagree, the disagreements are the two the ruling asked for and are listed below
- Visual review: completed. Three captures of the rendered application were compared against the #3898 demo's Holdings screen and against the ruling this issue carries
- Visual verdict: PASS
- Screenshots: ![Estate, owner](docs/reviews/3901/owner-estate.png) ![Physical, owner](docs/reviews/3901/owner-physical.png) ![Estate at 400px](docs/reviews/3901/owner-estate-phone.png)
- Comparison notes: the section reads Estate in the row and as the open section; the Property column now carries a second block naming the land the character's organizations hold; Physical's owner-only door still reaches the section under its new name. The dead "Domains your organizations hold will appear here" line is gone, replaced by the real read rather than deleted outright. That line was never in the demo — the demo's Holdings screen has no domains block at all; the placeholder came from #1887 and predates the demo entirely
- Tested interactions: clicking Estate in the section row opens the panel and moves the `aria-current` marker; the owner-only "Change outfit" door on Physical switches the page to Estate. Unit tests cover the block appearing with a domain and vanishing without one, and the backend tests cover the membership gate
- Fixture/live boundary: the page, every component it composes, the stylesheet and the token cascade are the real shipped code, and so is every hook between them. Fixture is the HTTP layer alone: the sheet payload (including `domains`), the roster entry, vitals, languages, inventory, outfits and the composed panels' own endpoints are hand-written responses matching the serializer TypedDicts in `src/world/character_sheets/types.py`. Not mounted: authentication and `Layout`; the signed-in account and this tab's browsing identity are seeded into the real store
- Overall outcome: PASS

## Requirement ledger

| id | status | evidence | authorized decision |
| --- | --- | --- | --- |
| real-surface | PASS | The shipped page was mounted and rendered, not a mockup. Build identity above. | |
| rename-complete | PASS | `owner-estate.png` shows Estate in the section row and as the open section. No `Holdings` string remains in the sheet components, the page, its tests, or the docs. | |
| domains-read | PASS | `owner-estate.png` shows "Their houses hold" with Thornmere, The Lantern Ward, tagged House du Verane. Backend `TestDomainsSection` covers the gate. | |
| render-or-vanish | PASS | `EstateDomains.test.tsx` asserts the block is absent with no domains, and that no "no domains" line replaces it. This is the common case: most organizations hold no land. | |
| membership-gate | PASS | `_build_domains` reads memberships where `left_at` and `exiled_at` are both null. Backend tests cover leaving, a house held by others, and a landless house. | |
| styling-reaches-page | PASS | The new block uses the sheet's existing `Heading`, `Ledger`, `Entries`, `Entry` and `Tag` primitives, every one of which already has a rule in `sheet.css`. No new class was introduced. | |
| responsive | PASS | `owner-estate-phone.png` at 400px: single column, no horizontal page scroll. | |
| no-errors | PASS | No page errors and no console errors on any of the three captures. | |
| fixture-boundary | PASS | Stated in full above. | |
| divergences-enumerated | PASS | Two, both below, both the ruling this issue carries. | |
| query-cost | PASS | The domains read is ONE joined query off the already-prefetched personas, and the bounded-count fixture now seeds a house that holds land so the query is actually measured rather than skipped. | |
| live-database | OUT_OF_SCOPE | The dev database refuses `migrate` because generation 1 is partially recorded, and a fresh database cannot be migrated from zero because the app has two leaf nodes. | Both blockers pre-date this branch and are the generation split ADR-0276 describes. Repairing the migration graph is not in this branch's scope. |

## Visual checklist

| Element | Expected | Result | Evidence |
| --- | --- | --- | --- |
| Section name in the row | Reads Estate, not Holdings | MATCH | owner-estate.png |
| Open section marker | Estate underlined in the rubric accent | MATCH | owner-estate.png |
| Purse block | Coin on hand with its note | MATCH | owner-estate.png |
| Carried block | Count with a wardrobe link, notable pieces, outfits row | MATCH | owner-estate.png |
| The law block | Present in the upper row | MATCH | owner-estate.png |
| Property block | Dwellings, tenanted rooms and ships | MATCH | owner-estate.png |
| Domains block | Names the land, whose it is, and where | MATCH | owner-estate.png |
| Domains block wording | Says the land is the organization's, not the character's | MATCH | owner-estate.png |
| Agreements block | The will, beside Property | MATCH | owner-estate.png |
| Change outfit door | Owner-only on Physical, reaching the renamed section | MATCH | owner-physical.png |
| Phone layout | Single column, no horizontal scroll | MATCH | owner-estate-phone.png |

## Divergences from the #3898 demo, and why

Both are the ruling this issue exists to carry.

1. **The section is called Estate, not Holdings.** "Holdings" reads as fiefs in this genre and the section is one person's money, things, roof and record. Estate is also the word the Agreements block inside it already uses.
2. **The dead domains line is a real read rather than a deleted line.** The instinct was to delete it, because a domain is org-owned and a building is individual-owned, so org land on a personal page muddies the section. Apostate ruled the other way on discovery grounds: a player coming onto a roster character may not know their house holds a keep and has nowhere else to learn it.

## What the first pass found, and what was done

| Finding | Severity | Resolution |
| --- | --- | --- |
| The domains read used two top-level `personas__...` prefetches, which cannot reuse the `cached_personas` Prefetch, so Django re-fetched every persona to redescend | BLOCKER | Fixed. Nesting it would have needed a `to_attr` on an idmapper parent, which ADR-0278 forbids and the ratchet caught, so it is one joined query now: cheaper than either prefetch shape and needing no suppression. |
| The bounded query count was not measuring the new read at all — the fixture seeded no memberships, so the join returned nothing and the bound of 50 was a coincidence | BLOCKER | Fixed. The fixture seeds a house that holds land, and the real cost is 49. |
| The ships queryset's docstring was rewritten to claim it mirrored the membership fix while its query underneath still had no lifecycle filter | MAJOR | Fixed. It calls the helper rather than repeating the query, so the two cannot drift, and a departed or exiled covenant member stops listing ships they no longer have standing in. |
| The `INDEX.md` payload list never gained `worn` or `mentors` and would not have gained `domains` | MINOR | Folded in. |
| The second pass found this report misattributing the dead placeholder to the demo, and the commit message overstating the vacancy filter as a live defect | MINOR | Both corrected. The placeholder came from #1887 and predates the demo; the vacancy filter is defence in depth, since the one production writer of `exiled_at` always sets `left_at` in the same save. |

## Folded in

`_persona_organization_ids` asserted in its own docstring that `OrganizationMembership`
had no lifecycle fields and that departures were deletes. That stopped being true when
`left_at` and `exiled_at` landed, so every departed and exiled member still inherited
their old organization's location tenancies and its vault access — an exile kept the key
to the keep they were thrown out of. Found because the domains read sits on the same
membership semantics. Two regression tests, and the stale claim removed from the ships
queryset that had copied it.

Eight pre-existing failures in `world.locations.tests.test_permissions` are unrelated and
not introduced here: they resolve through `AreaClosure`, a Postgres materialized view the
SQLite tier cannot build. CI's Postgres shard is their gate. The two tests added here pass
locally.

## Unresolved findings

None
