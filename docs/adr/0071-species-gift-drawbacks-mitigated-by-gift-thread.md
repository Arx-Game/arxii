# Species-gift drawbacks are conditions the gift's own thread mitigates

A species gift's downside is a real `ConditionTemplate` applied at character-creation
finalization by `provision_species_gifts` (`world/species/services.py`); the gift's own GIFT
thread carries a tier-0 `ThreadPullEffect` with `effect_kind=RESISTANCE` (`resistance_amount`,
optional `resistance_damage_type` FK to `conditions.DamageType`; null = all types), whose
passive value offsets the drawback's negative `ConditionResistanceModifier` (a vulnerability)
at the one seam where combat damage reads resistance — `apply_damage_to_participant`. Paid
pull tiers scale via `CombatPullResolvedEffect.level_multiplier`. This minimum vulnerability
substrate lives in #1580; the broad immunity/vulnerability framework and environmental triggers
(sunlight as a world-driven damage event) are deferred to #1588. We rejected a bespoke
per-species ability/vulnerability subsystem: routing through gifts, conditions, and the
existing thread-pull machinery reuses proven infrastructure (ADR-0050 — species abilities
are Minor Gifts — and ADR-0016 — no parallel implementations of the same concept).

> Status: accepted · Source: issue #1580 · Confidence: built (E2E `test_species_gift_e2e.py`)
