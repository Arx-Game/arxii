# ADR-0097: Generalized crossing-option catalog

Date: 2026-07-09

## Status

Accepted

## Context

Thread crossings (at PathStage thresholds 3, 6, 11, 16, 21) produce
player-chosen personalization. The TRAIT crossing (#1989) established an
authored-options + player-choice pattern, but its models were TRAIT-specific
(`TraitCrossingOption` with inline `effect_kind`/payload columns).

Two problems with this approach:

1. **Type coupling.** The option model was specific to one thread kind. Each
   new kind (FACET, MANTLE, etc.) would need its own parallel option/choice/offer
   model trio — a proliferation of near-identical tables.

2. **Payload coupling.** The effect payload (flat_bonus_amount,
   vital_bonus_amount, etc.) was inline on the option, tightly coupling the
   buff definition to the acquisition path. But "a buff is a buff — it
   shouldn't care how you got it." The condition system already has a
   generic buff model (`ConditionTemplate` with `ConditionModifierEffect`).

## Decision

Generalize the crossing-option catalog into a single `CrossingOption` model
keyed on `(target_kind, resonance, crossing_level)` that references an
acquisition-agnostic `ConditionTemplate` FK. The option model carries no
inline effect payload — the buff's effects live entirely on the condition.

Crossing buffs carry `ConditionModifierEffect` rows only (stat/check axis via
`ModifierTarget`). Capabilities and survivability bonuses remain on
`ThreadPullEffect` / survivability-baseline axes — they are separate
mechanical systems with their own read paths.

Each `TargetKind` defines its own handler and read-path gating:
- TRAIT = always-on (the buff is always active once chosen)
- FACET = wear-gated (active only while wearing an item with the anchor facet)

But the option catalog, choice receipt, and pending-offer models are shared.

## Consequences

- One catalog table for all thread kinds — no per-kind model proliferation.
- Buffs are defined once on `ConditionTemplate` and can be referenced by any
  acquisition path.
- The TRAIT crossing's inline-payload read paths are rewritten to traverse
  `condition_template`'s `ConditionModifierEffect` rows.
- `VITAL_BONUS` and `CAPABILITY_GRANT` crossing choices are removed — they
  don't map cleanly to `ConditionModifierEffect` (different axes).
- Each kind's handler inherits from a shared `_CrossingChoiceHandler` base,
  differing only in `target_kind`.
