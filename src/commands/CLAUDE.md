# Commands - User Interface Layer

Extremely thin command layer that parses syntax and delegates to flows. Commands contain no business logic.

## Key Files

### `command.py`
- **`ArxCommand`**: Base command class with minimal functionality
- Parses input, matches dispatchers, handles errors, generates help

### `dispatchers.py`  
- **`BaseDispatcher`**: Base dispatcher for pattern matching
- **`TargetDispatcher`**: Object resolution dispatcher
- **`LocationDispatcher`**: Location-based command dispatch
- **`TextDispatcher`**: Text-based command dispatch

### `handlers/`
- **`base.py`**: `BaseHandler` - orchestrates flow execution
- Connects command layer to flow system via handlers

### Core Command Files
- **`default_cmdsets.py`**: Default command set configuration
- **`descriptors.py`**: Command descriptor utilities
- **`door.py`**: Door-related command implementations  
- **`frontend.py`**: Frontend command integration
- **`payloads.py`**: Command payload management
- **`serializers.py`**: Command serialization for API
- **`utils.py`**: Command utilities and helpers

### Account Commands (`account/`)
- **`account_info.py`**: Account information commands
- **`character_switching.py`**: Character switching (@ic command)
- **`sheet.py`**: Character sheet commands

### Evennia Overrides (`evennia_overrides/`)
- **`builder.py`**: Building command overrides
- **`cmdset_handler.py`**: Command set handling modifications
- **`communication.py`**: Communication command overrides
- **`exit_command.py`**: Exit traversal command modifications
- **`movement.py`**: Movement command overrides
- **`perception.py`**: Perception command overrides

## Key Classes

- **`ArxCommand`**: Minimal command base with dispatcher integration
- **`BaseHandler`**: Runs prerequisite events then main flows
- **`BaseDispatcher`**: Maps regex patterns to object resolution
- Dispatcher types handle different syntax patterns (target, location, text)

## Architecture Pattern

```
User Input → Command → Dispatcher → Handler → Flow → Service Function
```

Commands are pure UI layer - all game logic lives in flows system.
