# ADR-4197: A drifted vocabulary is merged, never deleted, and its retired spellings route

**Status:** Accepted (2026-10-08, ApostateCD)
**Issue:** #4197
**Related:** ADR-0289 (the facet vocabulary is flat), ADR-0010 (FK direction)

## Context

`magic.Facet` is a flat vocabulary typed by many hands: staff on the deity page, players on
Motif and crafted items. It drifts the way every free-text catalog drifts: Scythe, Scythes,
Sickles, Scythe-like Weapons, Scything Tools, all meaning one thing and all believing they
are different. Eight relations bind to it (items, motif associations, thread anchors,
signature bonuses, vogue momentum, fashion styles, favored-by-beings, and now aliases), so a
duplicate is not one wrong row but a split in every mechanic that matches on the facet.
ApostateCD's reluctance on the issue was exactly this: "I don't know if there are any good
ways to avoid that, or if I could just have a convenient merge tool."

## Decision

Three guards share one spelling rule, `facet_key` (casefold, letters and spaces, one space
between words, the last word singular), and none of them is a tree:

1. **A picker shows the near-matches before it offers to create.** `GET /api/magic/facets/near/`
   answers what a typed spelling is near (same key, a shared stem, one edit apart), aliases
   included; the `FacetPicker` shows them as "Did you mean" and offers **Create** only to
   staff, only when nothing resolves.
2. **A spelling that already resolves is answered, not created.** `POST /api/magic/facets/`
   returns the existing facet with `matched: true` when the key matches a facet's name or an
   alias; a near-duplicate cannot be made through the API.
3. **Duplicates are merged, never deleted, and the retired names route.** `merge_facets`
   repoints every binding to the survivor in one transaction (an owner already on the survivor
   keeps one row), records each loser's name as a `FacetAlias`, and deletes the losers. The
   handler set is checked against `Facet._meta.related_objects` at run time, so a relation
   added later stops the merge instead of being stranded. The surface is a Django admin action
   with a confirmation page: sweeping a vocabulary is a staff task, not a game page.

An alias is content (`CONTENT_MODELS`, natural key `name`), never shown to a player; it only
routes a spelling to its facet.

## Alternatives rejected

- **Delete the duplicate and re-bind by hand.** Eight relations, some unique per owner; a
  human would miss one, and the thread anchored on the deleted facet would `PROTECT`-fail the
  delete anyway.
- **A facet tree, so "Scythes" sits under "Scythe".** Ruled out on 2026-09-11 (ADR-0289): depth
  makes a node's mechanical reach uneven.
- **Trigram similarity in the database.** The vocabulary is small and read whole by every
  picker; a Python normaliser over the list gives the same answer with no extension and no
  index.
- **Players create facets.** The vocabulary is authored content; players get the search and
  the near-matches, staff get the create.

## Consequences

Every binding site keeps using `Facet` exactly as before; nothing reads aliases but the
spelling rule. A merge changes the facet id some rows point at, so any cache keyed on the old
id refreshes on the next read (the identity map follows row saves; the merge saves row by
row for that reason rather than `QuerySet.update()`). The spelling rule is duplicated in
TypeScript (`frontend/src/magic/facetKey.ts`) so the picker can decide what to show while
typing; the server's answer is still the truth and the tests pin both to the same cases.
