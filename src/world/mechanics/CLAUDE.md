# Mechanics - Game Engine Mechanics

Core game engine for the modifier system, roll resolution, and mechanical calculations. This app provides the infrastructure for how modifiers from various sources are collected, stacked, and applied.

## Purpose

The mechanics app centralizes all game mechanical calculations:
- Modifier collection and stacking from multiple sources
- Roll resolution and check processing
- Mathematical operations for game mechanics

## Key Files

### `models.py`
- **`ModifierCategory`**: Categories for organizing modifier types (stat, magic, affinity, resonance, goal, roll). Uses SharedMemoryModel for caching.
- **`ModifierType`**: Unified registry of all things that can be modified. Replaces separate Affinity, Resonance, and GoalDomain models. Uses SharedMemoryModel for caching.
- **`CharacterModifier`**: Active modifiers on a character with source tracking. Uses regular Model (not SharedMemoryModel) since this is per-character data.

### `types.py`
Dataclasses for service layer results and intermediate calculations.

### `services.py`
Service functions for modifier operations:
- **`get_modifier_for_character(character, category, type_name)`**: Main helper for looking up modifiers. Use this when you have a character ObjectDB.
- **`get_modifier_total(sheet, modifier_type)`**: Get total for a specific ModifierType.
- **`get_modifier_breakdown(sheet, modifier_type)`**: Get detailed breakdown with amplification/immunity.
- **`create_distinction_modifiers(char_distinction)`**: Create modifiers when distinction is granted.
- **`delete_distinction_modifiers(char_distinction)`**: Clean up when distinction is removed.
- **`update_distinction_rank(char_distinction)`**: Recalculate values when rank changes.

## Models

### ModifierCategory
Categories for organizing modifier types into logical groups.

| Field | Type | Description |
|-------|------|-------------|
| name | CharField(50) | Unique category name |
| description | TextField | Description of the category |
| display_order | PositiveIntegerField | Ordering for display |

### ModifierType
Unified registry replacing separate Affinity, Resonance, GoalDomain models.

| Field | Type | Description |
|-------|------|-------------|
| name | CharField(100) | Type name (unique within category) |
| category | FK(ModifierCategory) | Parent category |
| description | TextField | Description of the type |
| display_order | PositiveIntegerField | Ordering within category |
| is_active | BooleanField | Whether currently active |

### CharacterModifier
Per-character modifier values with source tracking. Sources are responsible for creating/deleting their modifier records.

| Field | Type | Description |
|-------|------|-------------|
| character | FK(CharacterSheet) | Character who has this modifier |
| value | IntegerField | Modifier value (can be negative) |
| source | FK(ModifierSource) | Source that grants this modifier (also defines modifier_type) |
| expires_at | DateTimeField | When this modifier expires (null = permanent) |
| created_at | DateTimeField | When this modifier was created |

**modifier_type**: Derived from `source.modifier_type` (property, not stored directly).
**Stacking**: All modifiers stack (sum values for a given modifier_type).
**Display**: Hide modifiers with value 0.

## Integration Points

This app integrates with multiple systems that provide modifiers:

- **Distinctions**: Talents and quirks that grant bonuses/penalties
- **Magic**: Spells and magical effects that modify checks
- **Equipment**: Weapons, armor, and items with mechanical effects
- **Conditions**: Status effects that alter capabilities and checks

## Design Principles

- **SharedMemoryModel** for lookup tables (ModifierCategory, ModifierType)
- **Regular Model** for per-character data (CharacterModifier)
- **No slug fields** - use name or pk for lookups
- **Absolute imports** throughout

## Modifier Type Naming Conventions

When creating new ModifierTypes, follow these patterns:

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
