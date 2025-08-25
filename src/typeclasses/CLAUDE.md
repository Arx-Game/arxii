# Typeclasses - Evennia Object Definitions

Core game objects (characters, rooms, exits, etc.) with Arx II customizations extending Evennia's default typeclasses.

## Key Files

### `characters.py`
- **`Character`**: Extends `DefaultCharacter`
- Traits handler, item_data interface, roster integration, scene state management

### `rooms.py`
- **`Room`**: Extends `DefaultRoom`
- Scene data management, trigger registry, active scene tracking, state broadcasting

### `exits.py`
- **`Exit`**: Extends `DefaultExit`
- Flow-based traversal, lock system integration

### `objects.py`
- **`Object`**: Extends `DefaultObject`
- Basic game object with Arx II extensions

### `accounts.py`
- **`Account`**: Extends `DefaultAccount`
- Integration with roster system and character management

### `channels.py`
- **`Channel`**: Extends `DefaultChannel`
- Custom channel functionality

### `scripts.py`
- **`Script`**: Extends `DefaultScript`
- Custom script functionality

### `mixins.py`
- Shared functionality across multiple typeclass types
- Common patterns for DRY implementation

## Key Classes

- **`Character`**: Primary player interface with traits, item_data, roster integration
- **`Room`**: Location management with scene tracking and trigger registry
- **`Exit`**: Movement interface with flow-based traversal
- **Account**: Player account with character management integration

## Integration Points

- **Item Data**: Unified character data access via evennia_extensions
- **Flows System**: All actions delegate to flow execution
- **Roster System**: Character lifecycle and player management
- **Scenes System**: Real-time scene state tracking
