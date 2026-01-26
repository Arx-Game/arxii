# Mechanics - Game Engine Mechanics

Core game engine for the modifier system, roll resolution, and mechanical calculations. This app provides the infrastructure for how modifiers from various sources are collected, stacked, and applied.

## Purpose

The mechanics app centralizes all game mechanical calculations:
- Modifier collection and stacking from multiple sources
- Roll resolution and check processing
- Mathematical operations for game mechanics

## Key Files

### `models.py`
Models to be added:
- **`ModifierCategory`**: Groupings for modifier types (passive, active, situational)
- **`ModifierType`**: Specific modifier definitions (bonus, penalty, advantage, disadvantage)
- **`CharacterModifier`**: Active modifiers on a character with source tracking

### `types.py`
Dataclasses for service layer results and intermediate calculations.

### `services.py` (planned)
Service functions for:
- Collecting modifiers from all sources for a character
- Stacking rules and modifier resolution
- Roll calculations with modifier application

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
