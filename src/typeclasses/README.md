# Typeclasses - Evennia Object Definitions

Core game objects extending Evennia's default typeclasses with Arx II customizations.

## Key Files

- **`characters.py`** - Player characters with traits, item_data, roster integration
- **`rooms.py`** - Game locations with scene tracking and trigger registry
- **`exits.py`** - Movement interface with flow-based traversal
- **`objects.py`** - Basic game objects with Arx II extensions
- **`accounts.py`** - Player accounts with character management
- **`mixins.py`** - Shared functionality across typeclass types

## Integration Points

- **Item Data**: Unified character data access via evennia_extensions
- **Flows System**: All actions delegate to flow execution  
- **Roster System**: Character lifecycle and player management
- **Scenes System**: Real-time scene state tracking

See `CLAUDE.md` for detailed information.
