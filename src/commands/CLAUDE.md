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
| CHALLENGE backend (dungeon puzzle challenges — requires `challenge_instance_id`) | `DispatchCommand` |
| Non-combat magic cast (`attempt`) — calls `request_technique_cast` directly | `ArxCommand` |
| COMBAT backend (technique declaration into the current round) | `DispatchCommand` |

Both bases stay thin: no business logic in commands — all behavior lives in
actions, backends, and service functions.

### Command Files
- **`evennia_overrides/perception.py`**: `CmdLook`, `CmdInventory`
- **`evennia_overrides/communication.py`**: `CmdSay`, `CmdWhisper`, `CmdPose`, `CmdPage`
- **`evennia_overrides/movement.py`**: `CmdGet`, `CmdDrop`, `CmdGive`, `CmdHome`
- **`evennia_overrides/exit_command.py`**: `CmdExit` (dynamic exit traversal)
- **`door.py`**: `CmdLock`, `CmdUnlock` (stubs pending LockAction/UnlockAction)
- **`offer_registry.py`**: `OfferHandler` protocol, `_REGISTRY`, `register_offer_handler`,
  `get_all_pending`, `find_handler` — pure-Python in-process registry; no DB model.
- **`offer_response.py`**: `CmdDecline` (`decline`) — registry-offer decline; see also
  extended `CmdAccept` in `consent.py`.
- **`consent.py`**: `ConsentRequestCommand` (base), `CmdIntimidate`, `CmdPersuade`, `CmdDeceive`, `CmdFlirt`, `CmdPerform`, `CmdEntrance`, `CmdRestoreSense` — telnet shells for social consent-flow actions (#1337/#1338); `CmdAccept` (extended to check offer registry first; consent
  fall-through unchanged), `CmdDeny` — target responses. All call `create_action_request` / `respond_to_action_request` — the same service the web viewset calls.
- **`ritual.py`**: `CmdRitual` (alias `perform`) — telnet face of
  `PerformRitualAction` and multi-participant session lifecycle; parses `ritual <name> [key=value ...]` for SERVICE and
  CEREMONY rituals, **and** `ritual sessions/draft/join/decline/fire` for session management.
  Single-actor rituals: SERVICE rituals execute immediately; CEREMONY rituals create a
  `PendingRitualEffect` that the matching finisher command (`weave`, `imbue`) consumes.
  Session subcommands call `draft_session` / `accept_session` / `decline_session` / `fire_session` directly.
- **`weave.py`**: `CmdWeaveThread` (`weave`) — telnet face of `WeaveThreadAction`;
  parses `weave resonance=<name> trait=<name or id> [name=<...>]` (TRAIT anchor only — the
  reference grammar; other anchor kinds are extended by the thread-weaving journey
  issue). Proves the direct-viewset→Action telnet pattern (#1337)
- **`imbue.py`**: `CmdImbue` (`imbue`) — finisher for the Rite of Imbuing CEREMONY;
  parses `imbue thread=<name|id> amount=<n>`. Requires an active `PendingRitualEffect`
  for Rite of Imbuing; calls `spend_resonance_for_imbuing` to advance thread level.
- **`magic.py`**: `CmdAttempt` (`attempt`) — non-combat technique cast shell (#1332); thin
  `ArxCommand` that parses `attempt <technique> [at <target>]`, resolves the persona via
  `persona_for_character`, and calls `request_technique_cast` (the same service the web
  viewset calls). No business logic; does NOT use CHALLENGE backend.
- **`pull.py`**: `CmdPull` (`pull`) — resonance pull command with optional `preview`
  mode; parses `pull [preview] resonance=<name> tier=<1-3> thread=<name|id>[,...]
  [trait=<name>] [technique=<name>]`. Preview mode returns cost estimate without
  debiting; live mode calls `spend_resonance_for_pull`.
- **`endorse.py`**: `CmdPoses` (`poses`) and `CmdEndorse` (`endorse`) — telnet faces of
  `PoseEndorseAction`, `SceneEntryEndorseAction`, `StylePresentationEndorseAction`.
  `poses <char>` lists endorseable poses in the current scene.
  `endorse pose/entry/style <char> resonance=<name> [confirm]` dispatches to the
  appropriate action. Both derive the active scene from the caller's room via
  `_get_active_scene` (#1340).
- **`fashion.py`**: `CmdJudgePresentation` (`judge`) — telnet face of
  `JudgePresentationAction`; parses `judge <presentation_id>` (#1340).
- **`evennia_overrides/builder.py`**: `CmdDig`, `CmdOpen`, `CmdLink`, `CmdUnlink` (Evennia overrides)

### Account Commands (`account/`)
- **`account_info.py`**: `CmdAccount` — account information display
- **`character_switching.py`**: `CmdIC`, `CmdCharacters` — character switching
- **`sheet.py`**: `CmdSheet` — character sheet display

### Social Commands (`social/`)
- **`blocking.py`**: `CmdBlock`/`CmdUnblock`/`CmdShareBlock`/`CmdMute`/`CmdUnmute`/`CmdBlockList`
  (#1278) — telnet face of the persona block/mute menu; thin over `world.scenes.block_services`.
- **`secrets.py`**: `CmdSecrets` (`+secrets`, #1334) — telnet face of the secret tab; thin over
  `world.secrets.services` (`secrets_owned_by` / `known_secrets_for`). Caller is the active
  character, so IC scoping is automatic; locked layers render "Unknown".

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
