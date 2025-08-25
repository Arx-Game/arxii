# Traits System - Character Statistics and Dice Resolution

Character stats and dice rolling mechanics based on Arx I's successful system. Uses point-to-rank conversion with configurable result charts.

## Key Files

### `models.py`
- **`Trait`**: Trait definitions (name, category, description) - uses SharedMemoryModel
- **`CharacterTraitValue`**: Character trait scores (1-100 internal, 1.0-10.0 display)
- **`PointConversionRange`**: Converts trait points to discrete ranks for dice rolling
- **`CheckRank`**: Dice pool configuration for different rank levels
- **`ResultChart`**: Success/failure tables for check resolution

### `handlers.py`
- **`TraitHandler`**: Character trait interface (get/set values, make checks)
- Accessed via `character.traits` on Character typeclass

### `resolvers.py`
- Links trait system to dice rolling mechanics
- Handles complex check types (opposed, extended, etc.)
- Integrates with flows system for automated checks

### `types.py`
- Type definitions for trait-related data structures

## Key Classes

- **`Trait`**: Case-insensitive trait lookups, SharedMemoryModel for performance
- **`CharacterTraitValue`**: Individual character trait scores with scale conversion
- **`PointConversionRange`**: Exponential difficulty curves, specialization rewards
- **`CheckRank`**: Dice count and modifiers for each rank level
- **`ResultChart`**: Configurable success/failure determination

## Check Resolution Process

1. Get character trait value (1-100 scale)
2. Convert points to rank via PointConversionRange
3. Determine dice pool from CheckRank
4. Execute dice roll with modifiers
5. Apply ResultChart to determine outcome

## Integration Points

- **Character Sheets**: Trait display and management
- **Flows System**: Automated trait checks during execution
- **Progression System**: Trait advancement through experience
