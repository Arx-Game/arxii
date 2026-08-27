# ADR-0234: Material economy renames stocks over duplicating them, keeps per-category stock, drives crafting via allowance, and sells only at collection time

**Status:** accepted (2026-08-26, #2540 slice 2)

Four related decisions from the slice-2 material economy build, which generalizes Build 0b's
gem-only stock machinery so any bulk material (not just gems) can share it:

**1. Rename-and-widen the gem stocks, don't duplicate them.** `CommonGemBucket`/
`StreamCommonGemPool`/`OrgGemStock` became `MaterialBucket`/`StreamMaterialPool`/
`OrgMaterialStock` in place (migration 0174, `Rename*` ops preserving history), each model's
`tier` FK retargeted to `material_category`. **Rejected:** a parallel `Material*` model family
living beside the untouched gem models — doubles every call site (production, collection,
spend) and leaves two stock tables to keep synchronized for what is definitionally one
aggregate-value concept. Genuinely gem-specific machinery (`GemGrade`, `GemDetails`,
`PendingRareFind`, rare-find rolling) stays gem-named in `gems.models` — only the
category-keyed value surface renamed.

**2. Stock stays per-category, not per-material.** `MaterialBucket`/`StreamMaterialPool`/
`OrgMaterialStock` remain one row per `(holder, MaterialCategory)`, uniqueness enforced
production-side (`get_or_create` + a `UniqueConstraint`), never one row per concrete material
type. **Rejected:** per-material stock rows — multiplies row count by the material catalog's
cardinality for no gameplay payoff this slice (nothing here distinguishes two materials sharing
a category), and every consumer (bulk crafting requirements, the allowance leg, auto-sell)
would have to fan out across materials within a category instead of reading one row.

**3. The crafting draw is an individual allowance, not a coffer to dip into.**
`distribute_material_allowance` ("the crafting draw") splits a PLACEHOLDER share of what a
collection lands, per category, into each active piloted member's own `MaterialBucket` — the
materials analogue of the coin `distribute_allowance`, riding the same non-discretionary rail
and the same active-piloted population scan (`_active_allowance_sheets`, shared by both legs).
**Rejected:** direct member spend straight off `OrgMaterialStock` (Apostate: reads as a coffer
members drain, the same social friction a shared treasury already causes, and needs a bespoke
per-member limit to stop one crafter emptying the house's stock in a sitting) and **rejected:**
steward manual transfers as the only path (adds a permission-gated bottleneck to a draw the
coin allowance already automates on the same cadence — a crafter would wait on a steward's
login just to craft).

**4. Selling is player-frictionless; org-side selling only rides a collection.**
`sell_materials` (personal `MaterialBucket` → coppers, `SellMaterialsAction`) needs no stall, no
NPC, no location gate — Apostate's ruling: bulk material is abstract bucket value, not a
physical good to haggle over in person, unlike the fence's item-instance sales (#2862).
`auto_sell_excess_materials` liquidates any `OrgMaterialStock` row over threshold, but only as
the last leg of `collect_and_distribute` — it rides an active, piloted collection dispatch,
never the weekly cron directly. **Rejected:** cron-driven auto-sell independent of collection —
would sell org material on a schedule with nobody piloting anything, which is exactly the
"automatic gain" ADR-0081 forbids.

**Nuance carried forward from ADR-0081 (adjudicated in slice 1's final review, reaffirmed
here):** the "automatic loss is fine, automatic gain is not" asymmetry rule is not violated by
the route-graded mission landing (`tasking._land_route_collection`) also driving
`collect_and_distribute` — and therefore the materials allowance and auto-sell — without a live
steward summon at the moment of landing. Task **assignment** is the piloted act; deadline
resolution merely completes a dispatch a player already piloted into motion, so materials or
coin landing on that deadline is the delayed payout of a real decision, not unpiloted automatic
gain. No code change follows from this; the ruling is recorded here so the next reader of
`_land_route_collection` doesn't re-litigate it.

**Observation, not a decision of this ADR:** a rolled-back `@transaction.atomic` mutation on a
`SharedMemoryModel` instance can still read its pre-rollback in-Python value back until
`flush_instance_cache()` runs — the identity map (ADR-0008) is process-wide and does not listen
for a DB rollback. This surfaced while fixing `sell_materials`'/`sell_to_fence`'s atomicity: a
test read a stale in-memory bucket value even though the underlying row had genuinely rolled
back; the fix was an explicit `flush_instance_cache()` before the post-rollback read, now the
test convention for this shape. It is a systemic ADR-0008 trade-off, not a defect introduced by
this slice — a repo-wide mitigation is deliberately deferred, not designed here.

**Rejected globally:** leaving the gem-only naming in place — every doc, glossary entry, and
future non-gem material feature would keep tripping over "gem" vocabulary for a concept that
stopped being gem-specific the moment a farm or quarry needed the same shape.
