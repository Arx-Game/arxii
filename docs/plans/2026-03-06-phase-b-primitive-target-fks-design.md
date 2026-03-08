# Phase B: Primitive Target FKs — Design

## Problem

After Phase A extracted Resonance/Affinity into proper domain models with ModifierTarget
pointing to them (`target_resonance`, `target_affinity`), several other primitive types
still lack this pattern:

- **CapabilityType** (conditions app) — no ModifierTarget link
- **CheckType** (checks app) — no ModifierTarget link; also duplicated as a simpler
  `conditions.CheckType` model
- **DamageType** (conditions app) — no ModifierTarget link for resistance primitives;
  also has a stale `resonance` FK pointing to `mechanics.ModifierTarget` instead of
  `magic.Resonance`

## Solution

Follow the Phase A pattern: domain models stay where they are, ModifierTarget gets
OneToOneField FKs pointing to them.

### 1. New FKs on ModifierTarget

```python
# mechanics/models.py — ModifierTarget gains:
target_capability = models.OneToOneField(
    "conditions.CapabilityType", on_delete=models.SET_NULL,
    null=True, blank=True, related_name="modifier_target",
)
target_check_type = models.OneToOneField(
    "checks.CheckType", on_delete=models.SET_NULL,
    null=True, blank=True, related_name="modifier_target",
)
target_damage_type = models.OneToOneField(
    "conditions.DamageType", on_delete=models.SET_NULL,
    null=True, blank=True, related_name="modifier_target",
)
```

New ModifierCategory rows: `"capability"`, `"check"`, `"resistance"`.

### 2. Merge `conditions.CheckType` into `checks.CheckType`

`conditions.CheckType` is a simple name/description lookup. `checks.CheckType` has those
fields plus category, trait weights, aspect weights, etc. They represent the same domain
concept — conditions built a simpler version before the checks app existed.

FKs that re-point from `conditions.CheckType` to `checks.CheckType`:
- `ConditionCheckModifier.check_type`
- `ConditionTemplate.cure_check_type`
- `ConditionStage.resist_check_type`

`conditions.CheckType` and its factory are deleted. Tests/services/serializers that
import it switch to `checks.CheckType` / `checks.factories.CheckTypeFactory`.

### 3. Fix `DamageType.resonance` FK

Currently `DamageType.resonance` is a OneToOneField to `mechanics.ModifierTarget`.
After Phase A, resonances are proper `magic.Resonance` models. Re-point this FK:

```python
# Before:
resonance = models.OneToOneField("mechanics.ModifierTarget", ...)

# After:
resonance = models.OneToOneField("magic.Resonance", ...)
```

This is a domain relationship ("fire damage is associated with the Fire resonance"),
not a modifier-system relationship.

### 4. What does NOT change

- `ConditionCapabilityEffect`, `ConditionCheckModifier`, `ConditionResistanceModifier`,
  `ConditionDamageOverTime` — stay as-is. Effect unification is Phase C/D.
- `DistinctionEffect` — stays, still points at ModifierTarget.
- `ModifierSource` / `CharacterModifier` — unchanged.
- Conditions services (`get_capability_status`, `get_check_modifier`,
  `get_resistance_modifier`) — same logic, just `CheckType` import changes.
- `CapabilityType` stays in conditions app.

## Files Changed

### mechanics app
- `models.py` — Add `target_capability`, `target_check_type`, `target_damage_type` to ModifierTarget
- `CLAUDE.md` — Update ModifierTarget field table
- `TECH_DEBT.md` — Mark capability/check/resistance rows as done

### conditions app
- `models.py` — Delete `CheckType` model; re-point `DamageType.resonance` to `magic.Resonance`;
  re-point `ConditionCheckModifier.check_type`, `ConditionTemplate.cure_check_type`,
  `ConditionStage.resist_check_type` to `checks.CheckType`
- `factories.py` — Delete `CheckTypeFactory`; update `ConditionCheckModifierFactory` to use
  `checks.factories.CheckTypeFactory`
- `services.py` — Change `CheckType` import from conditions to checks
- `serializers.py` — Update imports
- `admin.py` — Update imports/registrations
- `views.py` — Update imports
- `tests/test_services.py` — Update imports and factories

### mechanics tests
- `test_resonance_integration.py` — May need updates if ModifierTarget factory changes

### Migration regeneration
- All affected apps get fresh migrations (no production data)

## Implementation Order

1. Add three target FKs to ModifierTarget
2. Merge conditions.CheckType → checks.CheckType (re-point all FKs, delete model)
3. Fix DamageType.resonance FK to point to magic.Resonance
4. Update CLAUDE.md and TECH_DEBT.md docs
5. Regenerate migrations, reset DB, full test run
