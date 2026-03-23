# Character Sheets - Character Demographics and Identity

Character identity, appearance, and biographical data using Django models. Replaces Evennia attributes with structured data storage and integrates with item_data system.

## Key Files

### `models.py`
- **`CharacterSheet`**: Primary character data (age, gender, concept, description, background)
- **`Race`**: Character race definitions with bonuses - uses SharedMemoryModel
- **`Subrace`**: Race variants within broader categories
- **`Characteristic`**: Physical traits (height, build, hair_color, etc.)
- **`CharacteristicValue`**: Character-specific characteristic data
- **`CharacterIdentity`**: OneToOne link between a character and their active Persona (lives in this app)

### `types.py`
- Type definitions for character sheet data structures
- Enum definitions for gender, characteristics, etc.

## Key Classes

- **`CharacterSheet`**: OneToOne with ObjectDB, automatic creation via item_data
- **`Race`**: Extensible race system with characteristic restrictions
- **`Characteristic`**: Flexible trait system with category organization
- **`CharacterIdentity`**: Links a character to the Persona system (Persona model lives in `scenes` app)

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
- **Persona System**: Multiple identities via CharacterIdentity + Persona (PersonaType: PRIMARY/ESTABLISHED/TEMPORARY)
- **Item Data Handler**: Unified data access across systems
- **Automatic Creation**: CharacterSheet created on first access

## Integration Points

- **Evennia Extensions**: item_data system for unified access
- **Roster System**: Character applications and race selection
- **Scenes System**: Persona model (in `scenes` app) for identity in scenes; CharacterIdentity bridges character_sheets to scenes
- **Traits System**: Race bonuses and characteristic restrictions
