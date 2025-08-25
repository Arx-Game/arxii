# Character Sheets - Character Demographics and Identity

Character identity, appearance, and biographical data using Django models. Replaces Evennia attributes with structured data storage and integrates with item_data system.

## Key Files

### `models.py`
- **`CharacterSheet`**: Primary character data (age, gender, concept, description, background)
- **`Race`**: Character race definitions with bonuses - uses SharedMemoryModel
- **`Subrace`**: Race variants within broader categories
- **`Characteristic`**: Physical traits (height, build, hair_color, etc.)
- **`CharacteristicValue`**: Character-specific characteristic data
- **`Guise`**: Disguise system for alternate appearances

### `types.py`
- Type definitions for character sheet data structures
- Enum definitions for gender, characteristics, etc.

## Key Classes

- **`CharacterSheet`**: OneToOne with ObjectDB, automatic creation via item_data
- **`Race`**: Extensible race system with characteristic restrictions
- **`Characteristic`**: Flexible trait system with category organization
- **`Guise`**: Multiple disguises per character with temporary/permanent support

## Item Data Integration

Character data accessed through unified item_data system:

```python
character.item_data.age        # Routes to CharacterSheet
character.item_data.race       # Routes to Race model  
character.item_data.sheet      # Direct CharacterSheet access
```

Data routing:
- `age`, `gender`, `race` → character_sheets models
- `traits.*` → traits system
- `classes.*` → classes system

## Key Features

- **Race-Based Validation**: Characteristic restrictions by race
- **Guise System**: Multiple identities for disguised participation
- **Item Data Handler**: Unified data access across systems
- **Automatic Creation**: CharacterSheet created on first access

## Integration Points

- **Evennia Extensions**: item_data system for unified access
- **Roster System**: Character applications and race selection
- **Scenes System**: Guise integration for disguised participation
- **Traits System**: Race bonuses and characteristic restrictions
