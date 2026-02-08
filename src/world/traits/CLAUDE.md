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

### `types.py`
- **`StatDisplayInfo`**: Display-formatted stat information for API/UI responses

## Key Classes

- **`Trait`**: Case-insensitive trait lookups, SharedMemoryModel for performance
- **`CharacterTraitValue`**: Individual character trait scores with scale conversion
- **`PointConversionRange`**: Exponential difficulty curves, specialization rewards
- **`CheckRank`**: Dice count and modifiers for each rank level
- **`ResultChart`**: Configurable success/failure determination

## Check Resolution

Check resolution has moved to `world/checks/`. This app provides the lookup tables (PointConversionRange, CheckRank, ResultChart, CheckOutcome) used by the checks app's `perform_check()` service.

## Integration Points

- **Checks app**: Uses PointConversionRange, CheckRank, ResultChart for check resolution
- **Character Sheets**: Trait display and management
- **Progression System**: Trait advancement through experience
