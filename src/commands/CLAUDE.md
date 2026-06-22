# Commands — Telnet Compatibility Layer

Thin command layer that parses telnet text input and delegates to Actions.
Commands contain no business logic — all game behavior lives in actions
and service functions.

## Architecture

Commands exist for telnet compatibility only. The web frontend bypasses
commands entirely and calls `dispatch_player_action()`.

```
Telnet (ArxCommand):      text → command.parse() → command.func() → action.run()
Telnet (DispatchCommand): text → command.parse() → command.func() → dispatch_player_action()
Web:                      frontend → websocket → action dispatcher → dispatch_player_action()
```

`dispatch_player_action()` routes by backend: REGISTRY → `action.run()`,
CHALLENGE → `resolve_challenge()`, COMBAT → `declare_action()`/`resolve_round()`.
Use `DispatchCommand` whenever the command must reach a CHALLENGE or COMBAT backend.

## Key Files

### `command.py`
- **`ArxCommand`**: Base command class for REGISTRY actions
  - `action`: The Action instance this command delegates to
  - `resolve_action_args()`: Override to parse telnet text into action kwargs
  - `func()`: Calls `resolve_action_args()` → `action.run()` → sends result to caller
- **`DispatchCommand(ArxCommand)`**: Base class for commands that ride the player-action dispatcher
  - `resolve_action_ref()`: Override to return an `ActionRef` (backend + params)
  - `resolve_action_args()`: Override to return extra kwargs passed alongside the ref
  - `func()`: Calls `dispatch_player_action(caller, ref, kwargs)` — the same seam the web uses
  - `_report_dispatch_result()`: Sends the caller a deferred-round confirmation or inline result

### When to subclass `DispatchCommand` vs `ArxCommand`

| Use | Base class |
|---|---|
| REGISTRY action (most look/say/move/item commands) | `ArxCommand` |
| CHALLENGE backend (magic attempt, non-combat skill check) | `DispatchCommand` |
| COMBAT backend (technique declaration into the current round) | `DispatchCommand` |

Both bases stay thin: no business logic in commands — all behavior lives in
actions, backends, and service functions.

### Command Files
- **`evennia_overrides/perception.py`**: `CmdLook`, `CmdInventory`
- **`evennia_overrides/communication.py`**: `CmdSay`, `CmdWhisper`, `CmdPose`, `CmdPage`
- **`evennia_overrides/movement.py`**: `CmdGet`, `CmdDrop`, `CmdGive`, `CmdHome`
- **`evennia_overrides/exit_command.py`**: `CmdExit` (dynamic exit traversal)
- **`door.py`**: `CmdLock`, `CmdUnlock` (stubs pending LockAction/UnlockAction)
- **`ritual.py`**: `CmdRitual` (alias `perform`) — telnet face of
  `PerformRitualAction`; parses `ritual <name> [key=value ...]` for SERVICE rituals
- **`weave.py`**: `CmdWeaveThread` (`weave`) — telnet face of `WeaveThreadAction`;
  parses `weave resonance=<name> trait=<id> [name=<...>]` (TRAIT anchor only — the
  reference grammar; other anchor kinds are extended by the thread-weaving journey
  issue). Proves the direct-viewset→Action telnet pattern (#1337)
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
