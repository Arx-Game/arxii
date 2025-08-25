# Evennia Extensions - Core System Extensions

Extends Evennia's functionality with additional models and data handlers while preserving Evennia's architecture.

## Key Files

### `models.py`
- **`PlayerData`**: Extends AccountDB with player preferences and session tracking
- **`PlayerMedia`**: Media storage and gallery management
- **`ObjectDisplayData`**: Custom display settings for objects
- **`PlayerAllowList`**: Social allow lists for player communication
- **`PlayerBlockList`**: Social block lists for player communication

### `data_handlers/`
- **`base_data.py`**: `BaseItemDataHandler` - unified data access foundation
- **`character_data.py`**: `CharacterItemDataHandler` - character data routing
- **`object_data.py`**: `ObjectItemDataHandler` - object data management
- **`room_data.py`**: `RoomItemDataHandler` - room data access
- **`exit_data.py`**: `ExitItemDataHandler` - exit data handling

### `mixins.py`
- Shared functionality for extending Evennia objects
- Common patterns for data handler integration

### `adapters.py`
- Adaptation layer between Evennia and Arx II systems
- Integration utilities for data conversion

## Key Classes

- **`PlayerData`**: Account extensions without replacing core Evennia models
- **`BaseItemDataHandler`**: Unified data access pattern across object types
- **`CharacterItemDataHandler`**: Routes character data to appropriate systems
- Handler classes provide `character.item_data.field` access patterns

## Data Routing Pattern

```python
character.item_data.age        # → character_sheets.CharacterSheet
character.item_data.traits     # → traits.TraitHandler  
character.item_data.classes    # → classes system
```

Handlers route data access to appropriate world/ apps while maintaining unified interface.
