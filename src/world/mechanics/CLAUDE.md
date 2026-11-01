# Mechanics - Game Engine Mechanics

Core game engine for the modifier system, roll resolution, and mechanical calculations. This app provides the infrastructure for how modifiers from various sources are collected, stacked, and applied.

## Purpose

The mechanics app centralizes all game mechanical calculations:
- Modifier collection and stacking from multiple sources
- Roll resolution and check processing
- Mathematical operations for game mechanics

## Key Files

### `models.py`
- **`ModifierCategory`**: Categories for organizing modifier targets (stat, magic, affinity, resonance, goal, roll). Uses SharedMemoryModel for caching.
- **`ModifierTarget`**: Unified registry of all things that can be modified. Replaces separate Affinity, Resonance, and GoalDomain models. Uses SharedMemoryModel for caching. Has an optional `target_trait` FK for stat-category targets.
- **`ManeuverEffect`** (#4783): the fixed catalog of eight named maneuver numbers (`key` unique, `base_value`, staff `notes`). Staff edit a base value and cannot add or delete a row; code finds a row by `key`, never by name (`ensure_maneuver_effects`, `get_maneuver_effect` in `maneuver_effects.py`).
- **`CharacterModifier`**: Active modifiers on a character with source tracking and direct target FK. Uses regular Model (not SharedMemoryModel) since this is per-character data.

### `types.py`
Dataclasses for service layer results and intermediate calculations.

### `services.py`
Service functions for modifier operations:
- **`effect_value(sheet, key)` / `effect_modifier_total(sheet, key)`** (`effect_targets.py`, #4783): a character's number for a maneuver effect. `effect_modifier_total` is the unclamped sum of every modifier on a target in the "maneuver_effect" category scoped to that effect or its kind; `effect_value` adds the catalog base, floors at 0 and caps partial protection at 100.
- **Technique effect readers** (`effect_targets.py`, #4822): `technique_effect_context(sheet, technique, damage_type_id=None)` builds a frozen `TechniqueEffectContext` (`types.py`); `technique_effect_targets(kind)` loads the active kind targets that name no one maneuver effect; `technique_effect_total(sheet, context, targets)` sums those whose technique scopes all match; `TechniqueConditionBonus.for_cast(sheet, technique).for_target(target)` returns the `(severity, duration)` pair for a condition landing on one target. `effect_modifier_total(sheet, key, kind_wide=False)` drops kind-only targets (Charge damage uses it, since the technique's own damage term counts them). A maneuver reader never matches a technique-scoped or opponent-scoped target.
- **Opponent facts** (`effect_targets.py`, #4823): `opponent_facts(target)` returns the frozen `OpponentFacts` (`types.py`): the property ids a target has (stored `ObjectProperty`, a property an active condition's template or current stage grants, a PC's primary persona tag) and the template ids of its active unsuppressed conditions, in four bounded queries. `opponent_targets_exist(targets)` is the gate: facts are read only when an opponent-scoped target exists. Damage reads them once per opponent through `TechniqueDamageBonus.read_opponent` and caches the total per (damage type, opponent); conditions read them once per target through `TechniqueConditionBonus.for_target`.
- **Sized effect modifiers** (#4876): a target whose kind is damage, to-hit or partial protection has a `value_lane` (`EFFECT_KIND_LANE`); `_modifier_total` in `effect_targets.py` reads it through `modifier_target_contributions` and `condition_target_contributions` in that lane and tapers by its rows, so a sized distinction or technique buff counts the lane's value. Other kinds stay flat, and a size on them is refused.
- **`get_modifier_total(sheet, modifier_target)`**: Get total for a specific ModifierTarget.
- **`get_modifier_breakdown(sheet, modifier_target)`**: Get detailed breakdown with amplification/immunity.
- **`create_distinction_modifiers(char_distinction)`**: Create modifiers when distinction is granted.
- **`delete_distinction_modifiers(char_distinction)`**: Clean up when distinction is removed.
- **`update_distinction_rank(char_distinction)`**: Recalculate values when rank changes.
- **`ensure_aspect_target(aspect)`** (#4827): the aspect-category target (`target_aspect`) a card's `+N <aspect>` lands on, created if missing; `None` when another category owns the name. Called by `AspectAdmin.save_model` and the `ensure_aspect_targets` seed.
- **`ensure_skill_target(trait)`** (#4820): the stat-category target a skill's bonuses land on, created if missing; `None` when another category owns the name. Called by `SkillAdmin.save_model` and the Distinction Builder's paste.
- **`skill_modifiers_for_sheet(sheet, skills)`** (#4820): skill pk to the modifier a roll on it gets, for the character sheet; picks skills from card, condition and worn-equipment (crafted piece, equipment walk) sources, the last read from cached handlers.
- **`property_damage_bonus(target, damage_type)`**: Sum `PropertyDamageModifier` values for a target's active `Property` rows (see below).

## Models

### ModifierCategory
Categories for organizing modifier targets into logical groups.

| Field | Type | Description |
|-------|------|-------------|
| name | CharField(50) | Unique category name |
| description | TextField | Description of the category |
| display_order | PositiveIntegerField | Ordering for display |

### ModifierTarget
Slim pointer registry for things that can be modified. Resonance and Affinity domain data has been extracted into proper models in the magic app (`magic.Resonance`, `magic.Affinity`), each with an optional OneToOne FK back to ModifierTarget.

| Field | Type | Description |
|-------|------|-------------|
| name | CharField(100) | Target name (unique within category) |
| category | FK(ModifierCategory) | Parent category |
| description | TextField | Description of the target |
| display_order | PositiveIntegerField | Ordering within category |
| is_active | BooleanField | Whether currently active |
| target_trait | FK(Trait, null) | FK to the Trait this target modifies (stat-category targets) |
| target_capability | OneToOne(CapabilityType, null) | FK to the CapabilityType this target represents |
| target_check_type | OneToOne(CheckType, null) | FK to the CheckType this target represents |
| target_aspect | OneToOne(Aspect, null) | The Aspect this target represents (#4827); the check seam's ASPECT block reads it |
| target_damage_type | OneToOne(DamageType, null) | FK to the DamageType this target represents (resistance) |
| scope_maneuver_effect | FK(ManeuverEffect, null, CASCADE) | A "maneuver_effect" target scoped to one effect (#4783) |
| scope_effect_kind | CharField(blank) | A "maneuver_effect" target scoped to one `EffectKind` across every maneuver; exactly one of the two scope columns is set on such a target, and neither on any other category (`clean()`, and the `modifier_target_one_scope` constraint stops both). A target with neither matches nothing. A target with a technique scope sets the kind and no effect |
| scope_technique | FK(Technique, null, CASCADE) | Technique scope (#4822): this technique only |
| scope_gift | FK(Gift, null, CASCADE) | Technique scope: every technique of this gift or of its child gifts |
| scope_technique_function | CharField(blank, `TechniqueFunction`) | Technique scope: every technique carrying this function |
| scope_damage_type | FK(DamageType, null, CASCADE) | Technique scope: damage of this type (damage kind only; untyped damage is Physical) |
| scope_resonance | FK(Resonance, null, CASCADE) | Technique scope: techniques whose gift manifests as this resonance for the caster. Technique scopes combine, need a kind and no `scope_maneuver_effect` (`modifier_target_technique_scope_needs_kind`) |
| scope_opponent_property | FK(Property, null, CASCADE) | Opponent scope (#4823): only when the opponent has this property (stored, condition-granted or a PC's persona tag). Follows the technique scope rules; `has_opponent_scope` |
| scope_opponent_condition | FK(ConditionTemplate, null, CASCADE) | Opponent scope: only while the opponent has an active unsuppressed instance of this condition. Same rules |

### CharacterModifier
Per-character modifier values with source tracking. Sources are responsible for creating/deleting their modifier records.

| Field | Type | Description |
|-------|------|-------------|
| character | FK(CharacterSheet) | Character who has this modifier |
| value | IntegerField | Modifier value (can be negative) |
| source | FK(ModifierSource) | Source that grants this modifier |
| target | FK(ModifierTarget) | What this modifier affects (denormalized from source for direct queries) |
| expires_at | DateTimeField | When this modifier expires (null = permanent) |
| created_at | DateTimeField | When this modifier was created |

**target FK**: Stored directly on CharacterModifier for efficient queries (e.g., `CharacterModifier.objects.filter(target__name="strength")`). Set from `source.modifier_target` at creation time.
**Stacking**: All modifiers stack (sum values for a given target).
**Display**: Hide modifiers with value 0.

### PropertyDamageModifier (#1793)

Defines how a target's `Property` modifies damage of a given `DamageType` (or all
types when `damage_type` is null). Read via `property_damage_bonus(target, damage_type)`
in `services.py`, folded into combat technique damage in
`CombatTechniqueResolver._profile_damage` (`world/combat/services.py`). Mirrors
`ConditionResistanceModifier`'s shape but keyed on `Property` instead of `Condition`.

## Integration Points

This app integrates with multiple systems that provide modifiers:

- **Distinctions**: Talents and quirks that grant bonuses/penalties
- **Magic**: Spells and magical effects that modify checks
- **Equipment**: Weapons, armor, and items with mechanical effects
- **Conditions**: Status effects that alter capabilities and checks

## Design Principles

- **SharedMemoryModel** for lookup tables (ModifierCategory, ModifierTarget)
- **Regular Model** for per-character data (CharacterModifier)
- **No slug fields** - use name or pk for lookups
- **Absolute imports** throughout
- **Structured consequences only** — all mechanical outcomes must be structured effect primitives (ConsequenceEffect) that the system applies automatically. GMs select from pre-authored consequence templates; they never freehand mechanical effects. `mechanical_description` is display flavor, never parsed for game logic. This prevents killer GM / soft GM inconsistency and eliminates players gaming GM discretion.
- **Risk transparency** — players must always know the risk level before committing to an action. If character loss is possible in the consequence pool, the UI must communicate this before the player acts. THREAT-type challenges and high-severity situations are clearly flagged.

## Modifier Target Naming Conventions

When creating new ModifierTargets, follow these patterns:

| Category | Naming Pattern | Examples |
|----------|---------------|----------|
| `stat` | Lowercase stat name | `strength`, `dexterity`, `charm` |
| `action_points` | `ap_` prefix + descriptor | `ap_daily_regen`, `ap_weekly_regen`, `ap_maximum` |
| `development` | Category + `_skill_development_rate` | `physical_skill_development_rate`, `all_skill_development_rate` |
| `height_band` | Descriptive name | `max_height_band_bonus` |

**General rules:**
- Use lowercase with underscores (snake_case)
- Be descriptive - the name should explain what's being modified
- For percentages, include "rate" in the name
- For caps/limits, include "max" or "maximum" in the name
