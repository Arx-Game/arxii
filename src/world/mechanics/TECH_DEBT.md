# Mechanics App — Tech Debt

This document tracks known architectural issues in the modifier/effect system.
These are intentionally deferred to avoid breaking the junior developer's workflow.
Fix these before building more modifier sources.

## 1. ModifierTarget Has No FK to What It Modifies — DONE

**Status:** Resolved (Phase 1)

Added `target_trait` FK to `ModifierTarget` for stat-category targets. The `TraitHandler`
now uses FK-based lookup instead of string matching. Action points and progression systems
still use string-based lookup (stubbed with TODO comments) pending their respective system
builds.

See "Future Target FKs" below for remaining categories.

## 2. ModifierCategory vs ModifierTarget Naming Confusion — DONE

**Status:** Resolved

Renamed `ModifierType` → `ModifierTarget` across the entire codebase. The relationship is
now clear: "A ModifierTarget belongs to a ModifierCategory."

## 3. Three Parallel Systems for Persistent Effects

**Severity:** High — blocks feature development

Three different patterns exist for "source X grants ongoing effects to character":

| Pattern | Scope | Bundle? | Source-specific? |
|---------|-------|---------|-----------------|
| `DistinctionEffect` → `ModifierTarget` | Stat/modifier bonuses | No (flat) | Distinction only |
| `ConditionTemplate` → effect subtypes | Capabilities, checks, damage, resistance | Yes | Condition only |
| `ModifierSource` → `CharacterModifier` | Tracks modifier provenance | N/A | Multi-source via discriminator |

Each system can only grant its own kind of effect. A distinction cannot grant a capability. A
condition cannot directly grant a stat modifier (it has `ConditionCheckModifier` which is
different from `CharacterModifier`).

**Fix:** Unify into an EffectBundle pattern:
```
Source (distinction/technique/equipment/species)
  └── EffectBundle (named package, unit of apply/remove)
        ├── EffectModifier: +10 strength
        ├── EffectCapability: +5 climbing
        ├── EffectCondition: apply "Imposing Presence"
        └── EffectActionEnhancement: (reference to ActionEnhancement)
```

Any source can grant any combination of effects. Bundle lifecycle is driven by source lifecycle.

**Note:** `ActionEnhancement` (actions app) handles a separate concern — modifying action
*execution* at runtime. It's clean, correctly scoped, and should NOT be folded into this pattern.

## 4. DistinctionEffect Is Flat and Distinction-Specific

**Severity:** Medium — limits distinction design

`DistinctionEffect` is one row = one modifier on one `ModifierTarget`. A distinction can only grant
stat/modifier bonuses. It cannot:
- Grant capabilities
- Apply conditions
- Modify action execution (that's `ActionEnhancement`, separate and correct)

This means a distinction like "Giant's Blood" that should grant +10 strength AND climbing
capability AND an "Imposing Presence" condition requires three different systems with three
different source-tracking patterns.

**Fix:** Replace with the EffectBundle pattern (see #3).

## Priority

#1 and #2 are resolved. Fix #3/#4 together (EffectBundle unification) as Phase 2.

## Future Target FKs

Target FKs to be added when their systems are built:

| Category | Future FK | Status |
|----------|----------|--------|
| resonance | target_resonance | **DONE** (Phase A) |
| capability | target_capability | **DONE** (Phase B) |
| roll_modifier | target_check_type | **DONE** (Phase B) |
| resistance | target_damage_type | **DONE** (Phase B) |
| action_points | target system TBD | Blocked on AP regen/cron system |
| development | target system TBD | Blocked on Progression system |
| height_band | target system TBD | Blocked on Height band system |
| goal_percent | target_goal_domain? | Blocked on Goal modifier system |
| goal_points | target system TBD | Blocked on Goal modifier system |
| condition_control_percent | target_condition? | Blocked on Condition modifier system |
| condition_intensity_percent | target_condition? | Blocked on Condition modifier system |
| condition_penalty_percent | target_condition? | Blocked on Condition modifier system |
