# ModifierType → ModifierTarget Rename & FK Integrity

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rename `ModifierType` to `ModifierTarget`, add a `target_trait` FK to `Trait` for stat-category entries, and eliminate string-based modifier lookups — fixing Phase 1 of the tech debt in `src/world/mechanics/TECH_DEBT.md`.

**Architecture:** Direct FK linkage replaces string-name conventions. Only `target_trait` is added now (YAGNI); other target FKs are added when their systems are built. String-based `get_modifier_for_character()` is removed entirely. Consumers without a target system yet are explicitly stubbed.

**Tech Stack:** Django models, SharedMemoryModel, fixtures with natural keys, existing modifier/distinction infrastructure.

---

## Context

### The Problem

`ModifierType` is a registry of "things that can be modified" but has no FK to the actual model it represents. The link is purely a string-name convention: `ModifierType(name="strength", category="stat")` corresponds to `Trait(name="strength")` only because consumer code passes matching strings. A typo in either side silently breaks the link.

### The Fix

- Rename `ModifierType` → `ModifierTarget` (resolves naming confusion with `ModifierCategory`)
- Add `target_trait` FK to `Trait` for stat-category entries
- Replace string-based lookups with FK-based lookups
- Stub consumers whose target systems don't exist yet
- Track remaining work in TECH_DEBT.md and roadmap

### What Stays the Same

- `ModifierCategory` — name is fine alongside `ModifierTarget`
- `ModifierSource` — untouched beyond import/FK reference updates (Phase 2 scope)
- `DistinctionEffect` — FK updated to `ModifierTarget`, otherwise unchanged (Phase 2 scope)
- `CharacterModifier` — FK reference updates only

---

## Model Changes

### ModifierTarget (renamed from ModifierType)

```python
class ModifierTarget(NaturalKeyMixin, SharedMemoryModel):
    name = CharField(max_length=100)
    category = FK(ModifierCategory, related_name="targets")
    description = TextField(blank=True)
    display_order = PositiveIntegerField(default=0)
    is_active = BooleanField(default=True)

    # FK to what this target actually modifies (Phase 1: traits only)
    target_trait = FK("traits.Trait", null=True, blank=True, on_delete=SET_NULL)
    # Future FKs — added as systems are built:
    # target_capability = FK("conditions.CapabilityType") — when capability modifier system exists
    # target_check_type = FK("conditions.CheckType") — when roll modifier system exists
    # See TECH_DEBT.md and docs/roadmap/ for tracking

    # Resonance-specific fields (unchanged)
    affiliated_affinity = FK("self", null=True, blank=True)
    opposite = OneToOneField("self", null=True, blank=True)
    resonance_affinity = CharField(max_length=20, choices=ResonanceAffinity)
```

Only `stat` category entries have `target_trait` populated. All other categories leave it null — they don't have target models yet.

### Other Model Updates (reference-only)

- `ModifierCategory.types` related_name → `targets`
- `ModifierSource.modifier_type` property → `modifier_target` (returns `ModifierTarget`)
- `CharacterModifier.modifier_type` property → `modifier_target`
- `DistinctionEffect.target` FK → points at `ModifierTarget` (field name unchanged)
- `DamageType.resonance` OneToOneField → points at `ModifierTarget`
- All magic models referencing `ModifierType` → `ModifierTarget`

---

## Service Layer Changes

### Remove String-Based Lookup

**Delete** `get_modifier_for_character(character, category_str, name_str)` entirely.

**Keep** `get_modifier_total(sheet, modifier_target)` which takes a `ModifierTarget` instance — this is the correct pattern.

### Stat Consumer (traits/handlers.py)

Update `TraitHandler._get_stat_modifier()` to look up `ModifierTarget` via `target_trait` FK:

```python
# Before: string-based
modifier_target = get_modifier_for_character(character, "stat", trait.name)

# After: FK-based
modifier_target = ModifierTarget.objects.get(target_trait=trait)
total = get_modifier_total(sheet, modifier_target)
```

### Unfinished Consumers

These currently call `get_modifier_for_character()` with strings for systems that don't have target models yet. Each is stubbed with a clear TODO:

- **action_points/models.py** — `_get_ap_modifier()`: stub, TODO comment explaining AP regen system needed
- **progression/services/awards.py** — development rate lookups: stub, TODO comment explaining progression system needed
- **goals/services.py** — goal modifier lookups: stub, TODO comment explaining goal modifier system needed
- **character_creation/models.py** — `attribute_free_points` / `bonus_gift_slots`: stub, TODO comment

Each stub should make it obvious to a future developer that the modifier integration is unfinished and what needs to happen.

---

## Fixture and Data Changes

### Renamed Fixtures

- `initial_modifier_types.json` → `initial_modifier_targets.json`
- `new_modifier_types.json` → `new_modifier_targets.json`
- All entries: `"model": "mechanics.modifiertype"` → `"model": "mechanics.modifiertarget"`

### Stat Entries Gain target_trait FK

The 9 stat-category entries get `target_trait` populated using Trait natural keys:

```json
{
  "model": "mechanics.modifiertarget",
  "fields": {
    "name": "strength",
    "category": ["stat"],
    "target_trait": ["strength"],
    ...
  }
}
```

### Load Order Dependency

`initial_primary_stats` (traits) must load before `initial_modifier_targets` (mechanics).

### Other Fixture Updates

All fixtures referencing `mechanics.modifiertype` natural keys update to `mechanics.modifiertarget`:
- Distinction effect fixtures
- Magic/resonance fixtures
- Any cross-app fixture references

### Migration Strategy

Dev environment, no production data. Squash all mechanics migrations into fresh `0001_initial.py`. Wipe DB and reload from fixtures.

---

## Rename Blast Radius

### Models (FK/import references)
- `mechanics/models.py` — the model itself, ModifierSource property, CharacterModifier property
- `distinctions/models.py` — DistinctionEffect.target FK
- `magic/models.py` — resonance references (CharacterResonance, etc.)
- `conditions/models.py` — DamageType.resonance OneToOneField

### Services
- `mechanics/services.py` — all lookup functions, remove get_modifier_for_character
- `traits/handlers.py` — stat modifier lookup
- `action_points/models.py` — stub AP modifier call
- `progression/services/awards.py` — stub development modifier call
- `goals/services.py` — stub goal modifier call
- `character_creation/models.py` — stub attribute_free_points / bonus_gift_slots

### Serializers, Admin, Factories, Tests
Across mechanics, distinctions, magic, traits, action_points, progression, goals, character_creation.

### Fixtures
All files referencing `mechanics.modifiertype` or using ModifierType natural keys.

### Documentation
- CLAUDE.md files for mechanics, magic, distinctions
- TECH_DEBT.md (update Phase 1 as done, add future FK tracking)
- Roadmap
- Systems index

---

## Testing

### Mechanics Tests
- ModifierTarget model: FK to Trait works, null target_trait is valid, natural key serialization
- `get_modifier_total` works with ModifierTarget instance (not strings)
- Stat modifier lookup via `target_trait` FK returns correct totals

### Distinction Tests
- DistinctionEffect creates CharacterModifiers correctly via renamed model
- Existing distinction service tests updated to use ModifierTarget references

### Stub Consumer Tests
- Action points: modifier integration is stubbed (no string lookup, clear TODO)
- Progression: development rate modifiers are stubbed
- Goals: goal modifier lookups are stubbed
- Each stub test documents what needs to happen when the system is built

### Fixture Integrity Tests
- Load order: traits before modifier_targets
- All stat ModifierTargets have non-null `target_trait`
- All non-stat ModifierTargets have null `target_trait` (expected for now)

### Not Tested
- No frontend tests (ModifierTarget is not exposed to the frontend API)

---

## Tracking Remaining Work

After this PR, TECH_DEBT.md is updated:
- Phase 1 (FK integrity + rename): **Done**
- Phase 2 (EffectBundle unification): Still pending
- New section: "Future target FKs" listing each category and what system/FK it needs

Categories needing future target FKs:

| Category | Future FK | Blocked On |
|----------|----------|------------|
| action_points | target system TBD | AP regen/cron system |
| development | target system TBD | Progression system |
| height_band | target system TBD | Height band system |
| goal_percent | target_goal_domain? | Goal modifier system |
| goal_points | target system TBD | Goal modifier system |
| condition_control_percent | target_condition? | Condition modifier system |
| condition_intensity_percent | target_condition? | Condition modifier system |
| condition_penalty_percent | target_condition? | Condition modifier system |
| roll_modifier | target_check_type? | Roll modifier system |
| resonance | (self-referential, may not need FK) | Magic system review |
