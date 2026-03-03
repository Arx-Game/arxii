# Commands — Telnet Compatibility Layer

Thin command layer that parses telnet text input and delegates to Actions.
Commands contain no business logic — all game behavior lives in actions
and service functions.

## Architecture

Commands exist for telnet compatibility only. The web frontend bypasses
commands entirely and calls `action.run()` directly.

```
Telnet: text → command.parse() → command.func() → action.run()
Web:    frontend → websocket → action dispatcher → action.run()
```

## Key Files

### `command.py`
- **`ArxCommand`**: Base command class
  - `action`: The Action instance this command delegates to
  - `resolve_action_args()`: Override to parse telnet text into action kwargs
  - `func()`: Calls `resolve_action_args()` → `action.run()` → sends result to caller

### Command Files
- **`evennia_overrides/perception.py`**: `CmdLook`, `CmdInventory`
- **`evennia_overrides/communication.py`**: `CmdSay`, `CmdWhisper`, `CmdPose`, `CmdPage`
- **`evennia_overrides/movement.py`**: `CmdGet`, `CmdDrop`, `CmdGive`, `CmdHome`
- **`evennia_overrides/exit_command.py`**: `CmdExit` (dynamic exit traversal)
- **`door.py`**: `CmdLock`, `CmdUnlock` (stubs pending LockAction/UnlockAction)
- **`evennia_overrides/builder.py`**: `CmdDig`, `CmdOpen`, `CmdLink`, `CmdUnlink` (Evennia overrides)

### Account Commands (`account/`)
- **`account_info.py`**: `CmdAccount` — account information display
- **`character_switching.py`**: `CmdIC`, `CmdCharacters` — character switching
- **`sheet.py`**: `CmdSheet` — character sheet display

### Frontend Integration
- **`frontend.py`**: `FrontendMetadataMixin` — for non-action commands (builder, page)
- **`utils.py`**: `serialize_cmdset()` — serializes cmdset for frontend
- **`serializers.py`**: `CommandSerializer` — DRF serializer for command payloads

### Other
- **`default_cmdsets.py`**: Command set registration
- **`exceptions.py`**: `CommandError` — raised for invalid input
- **`payloads.py`**: Look/examine payload builders
- **`descriptors.py`**: Serializable command/dispatcher descriptors

## Adding a New Command

1. Create the Action first (see `src/actions/CLAUDE.md`)
2. Create a command class inheriting from `ArxCommand`
3. Set `key`, `aliases`, `locks`, and `action`
4. Override `resolve_action_args()` to parse telnet text into action kwargs
5. Add to the appropriate cmdset in `default_cmdsets.py`
