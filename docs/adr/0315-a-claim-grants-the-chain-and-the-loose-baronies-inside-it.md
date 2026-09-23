# ADR-0315: A claim grants its own seat chain plus the loose baronies inside it, never a vassal's own held seat

**Status:** Accepted (2026-09-23, #3983 Plan B).

`claim_grants(title)` (`world.societies.houses.almanach`) is what a founder's claim on a title
actually seats the house on: the title's own seat chain top-first (`_require_chain_top`, sorted by
`TITLE_TIER_RANK` rather than the chain's alphabetical-by-tier-name DB order), plus every houseless
BARONY lying directly inside one of the chain's own Areas that isn't itself a member of another
chain — a county's own seat barony always stays with its county, never double-listed. A duchy claim
therefore grants duchy, county, barony, then any loose baronies the chain swallows, and
`materialize_house_claim` seats the whole list in one pass (`assign_holder` on the chain top, then
again per loose-barony extra) rather than the founder claiming each rung separately. Two narrower
and one broader alternative were weighed and rejected. **Chain only** (grant just
`_require_chain_top`'s own family, nothing extra) was rejected because `batch_unclaimed` can plant
loose baronies alongside a county's own seat (`baronies_per_county`) specifically so a duchy's
domain has spare land beyond its formal chain — stranding those as separately-claimable-only titles
would mean a founder claiming the whole duchy still can't describe or hold land the duchy plainly
contains, forcing every duchy-tier founder into a second, unexplained claim just to complete their
own demesne. **Everything beneath the chain** (grant every Title anywhere in the chain's Area
subtree, including a vassal's own already-held seat) was rejected because it would let a duchy claim
silently swallow a county a DIFFERENT house already holds — `claim_grants` only ever looks at
houseless (`house__isnull=True`) baronies, so a held seat, at any depth, is never a candidate; a
duchy's vassals stay vassals (by fealty, `assign_holder`/`rehome_vassals`), never subsumed rows on
the new claim.
