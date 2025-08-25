# Commands - User Interface Layer

Extremely thin command layer that parses syntax and delegates to flows. Commands contain no business logic - all game logic lives in the flows system.

## Architecture

```
User Input → Command → Dispatcher → Handler → Flow → Service Function
```

## Key Components

- **Commands**: Parse input, match dispatchers, handle errors
- **Dispatchers**: Map regex patterns to object resolution  
- **Handlers**: Orchestrate flow execution with prerequisite events
- **Flows**: Actual game logic execution (in `flows/` system)

## Subdirectories

- **`account/`** - Account management commands (@ic, sheet, etc.)
- **`evennia_overrides/`** - Evennia command overrides for Arx II
- **`handlers/`** - Flow orchestration handlers

See `CLAUDE.md` for detailed component information.
