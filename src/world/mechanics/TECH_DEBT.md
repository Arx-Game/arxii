# Mechanics App — Tech Debt

This document tracks known architectural issues in the modifier/effect system.
These are intentionally deferred to avoid breaking the junior developer's workflow.
Fix these before building more modifier sources.

## 1. ModifierType Has No FK to What It Modifies

**Severity:** High — silent data corruption risk

`ModifierType` is a registry of "things that can be modified" (strength, flight, ap_daily_regen)
but has no foreign key to the actual model it represents. The link is purely a string-name
convention.

Example: `ModifierType(name="strength", category="stat")` corresponds to `Trait(name="strength")`
only because `TraitHandler` calls `get_modifier_for_character(char, "stat", "strength")`.

**Consumers using hardcoded strings:**
- `TraitHandler._get_stat_modifier()` → `"stat"`, stat name
- `ActionPointPool._get_ap_modifier()` → `"action_points"`, modifier name
- `progression/services/awards.py` → `"development"`, modifier name

**Risk:** A typo in either the ModifierType name or the consumer string silently breaks the link.
A distinction that grants "+10 to stength" creates a CharacterModifier targeting a ModifierType
that no code ever reads.

**Fix:** Add a discriminator FK pattern to `ModifierType`:
```python
class ModifierType(SharedMemoryModel):
    name = CharField(100)
    category = FK(ModifierCategory)
    target_type = CharField(choices=["trait", "capability", "system_param"])
    target_trait = FK("traits.Trait", null=True)
    target_capability = FK("conditions.CapabilityType", null=True)
    # Add more target FKs as needed
```

With a CheckConstraint ensuring exactly one target FK is populated per `target_type`.

## 2. ModifierCategory vs ModifierType Naming Confusion

**Severity:** Low — readability issue

`ModifierCategory` groups `ModifierType` records into logical buckets (stat, magic, capability,
action_points, development, etc.). `ModifierType` is the specific thing being modified (strength,
flight, ap_daily_regen).

The naming is backwards from intuition — "type" sounds like it should be the category, and
"category" sounds like it should be the specific type.

**Fix:** Consider renaming `ModifierType` → `ModifierTarget` or `Modifiable` to make the
relationship clearer: "A ModifierTarget belongs to a ModifierCategory."

## 3. Three Parallel Systems for Persistent Effects

**Severity:** High — blocks feature development

Three different patterns exist for "source X grants ongoing effects to character":

| Pattern | Scope | Bundle? | Source-specific? |
|---------|-------|---------|-----------------|
| `DistinctionEffect` → `ModifierType` | Stat/modifier bonuses | No (flat) | Distinction only |
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

`DistinctionEffect` is one row = one modifier on one `ModifierType`. A distinction can only grant
stat/modifier bonuses. It cannot:
- Grant capabilities
- Apply conditions
- Modify action execution (that's `ActionEnhancement`, separate and correct)

This means a distinction like "Giant's Blood" that should grant +10 strength AND climbing
capability AND an "Imposing Presence" condition requires three different systems with three
different source-tracking patterns.

**Fix:** Replace with the EffectBundle pattern (see #3).

## Priority

Fix #1 first (FK integrity), then #3/#4 together (EffectBundle unification). #2 is cosmetic
and can be done alongside either.
