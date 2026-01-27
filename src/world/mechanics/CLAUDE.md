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

### `services.py` (planned)
Service functions for:
- Collecting modifiers from all sources for a character
- Stacking rules and modifier resolution
- Roll calculations with modifier application

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
| character | FK(Character) | Character who has this modifier |
| modifier_type | FK(ModifierType) | What type of modifier this is |
| value | IntegerField | Modifier value (can be negative) |
| source_distinction | FK(CharacterDistinction) | Distinction that grants this modifier (nullable) |
| source_condition | FK(ConditionInstance) | Condition that grants this modifier (nullable) |
| expires_at | DateTimeField | When this modifier expires (null = permanent) |
| created_at | DateTimeField | When this modifier was created |

**Stacking**: All modifiers stack (sum values for a given modifier_type).
**Display**: Hide modifiers with value 0.
**Source tracking**: Exactly one source FK should be set.

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
