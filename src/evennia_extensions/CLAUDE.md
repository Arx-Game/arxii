# Evennia Extensions - Core System Extensions

Extends Evennia's functionality with additional models and data handlers while preserving Evennia's architecture.

## Key Files

### `models.py`
- **`PlayerData`**: Extends AccountDB with player preferences and session tracking
- **`Media`**: Media storage and gallery management
- **`PageBackground`**: Maps a named page slot (homepage/roster/CG stage/game client) to a Media row
- **`ObjectDisplayData`**: Custom display settings for objects
- **`PlayerAllowList`**: Social allow lists for player communication (contact allowlist; separate
  from `world.scenes.Block`/`Mute`, which are the OOC block/mute primitives — see
  `world/scenes/CLAUDE.md`. The old account-level `PlayerBlockList` was removed (#1278), superseded
  by `world.scenes.Block`.)

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

### `mfa_adapter.py`
- **`ArxMFAAdapter`**: `MFA_ADAPTER` (#3591, ADR-0265) - encrypts what allauth
  stores in `Authenticator.data` (TOTP secret, recovery-code seed) under
  `MFA_SECRETS_KEY` via `cryptography.fernet.MultiFernet`
- `fernet_from_setting`, `split_keys` - parse the comma-separated key list,
  first key current, shared with the system check and the `mfa-secrets-key`
  sentinel probe

### `checks.py`
- `check_mfa_secrets_key` (`evennia_extensions.E001`, #3591) - Django system
  check that every key in `MFA_SECRETS_KEY` is a valid Fernet key, run at
  `migrate`/`check` time so a bad key fails the converge, not a player's
  sign-in

### `typeclass_hook_guard.py`
- Guards Evennia's server reload/shutdown lifecycle hooks (`at_server_reload`,
  `at_server_shutdown`, `unpuppet_all`, `_pause_task`) against a cached `ObjectDB`,
  `AccountDB`, or `ScriptDB` instance that is running bare (not as its typeclass) —
  see issue #3195 and ADR-0217. `install_lifecycle_hook_guards()` runs once from
  `EvenniaExtensionsConfig.ready()` and adds a loudly-logging no-op only for a hook
  genuinely missing from the bare model class; a typeclass's own hook is never
  touched. Never edit `evennia/server/service.py` (site-packages) to "fix" this —
  the guard is the sanctioned fix location. Does not address how a bare instance
  enters the idmapper cache; that root cause is still open in #3195.

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
