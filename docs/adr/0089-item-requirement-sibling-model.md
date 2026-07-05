# ADR-0089: ItemRequirement as a new sibling model, not a RitualComponentRequirement extension

## Status

Accepted

## Context

#1859 needs a way to gate a specific `ClassLevelUnlock` (Ritual of the Durance,
per-level advancement) on the character possessing a physical touchstone/trophy
item. #707 already built the exact match-mode vocabulary needed — `item_template`
XOR `min_touchstone_tier` — on `RitualComponentRequirement` (ADR-0087
(`docs/adr/0087-touchstone-dynamic-resonance-match.md`)), which is scoped to
`Ritual` rows.

Two designs were considered:

1. **Extend `RitualComponentRequirement`** with a `class_level_unlock` FK
   alongside its existing `ritual` FK, reusing the one model across both domains.
2. **A new sibling model, `ItemRequirement`**, in `world/progression`'s existing
   one-model-per-requirement-type system (`TraitRequirement`, `AchievementRequirement`,
   `TierRequirement`, etc.), reusing the *shape* (dual match-mode) but not the model.

## Decision

New sibling model (`ItemRequirement`, `world/progression/models/unlocks.py`),
subclassing `AbstractClassLevelRequirement` like every other requirement type in
that system. `check_requirements_for_unlock()`'s hardcoded `requirement_types`
list is the established extension point for new requirement types in this
domain — adding one more entry there is idiomatic; adding a `class_level_unlock`
FK to `RitualComponentRequirement` (a `Ritual`-scoped model) would blur two
domains that dispatch through entirely different pipelines (`PerformRitualAction`
vs. `check_requirements_for_unlock`/`RitualSession`).

`ItemRequirement` is possession-only (never consumes the item) — a real
behavioral difference from `RitualComponentRequirement`, which is always
consumed on ritual performance. This reinforces that the two are siblings by
vocabulary, not by mechanism.

## Consequences

- Every existing `RitualComponentRequirement` row and caller is unaffected —
  no schema or behavior change to that model.
- A future requirement type needing item possession-checking in a *third*
  domain would add its own sibling model too, following this same precedent,
  rather than growing `RitualComponentRequirement` into a general-purpose
  polymorphic item-matching model spanning unrelated domains.
