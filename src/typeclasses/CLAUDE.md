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
- **An override must accept everything the base method accepts.** Read the
  parent's docstring for the argument contract before narrowing it.
  `unpuppet_object` takes `Session OR a list of sessions` and fans out with
  `make_iter`; an override that assumed a single session raised AttributeError
  under `unpuppet_all` — which the Server calls on every cached account during
  reload and shutdown — killing the shutdown Deferred and hanging
  `evennia reload` until systemd timed it out (#3195). The same trap applies to
  every hook the reload path touches.
- **Do not use `MagicMock` for a session in tests.** It auto-creates `__iter__`,
  so `make_iter` treats it as an empty sequence and the base call silently does
  nothing. Use a plain `Mock` (see `_session_mock` in
  `tests/test_account_puppet_broadcast.py`), which behaves like a real,
  non-iterable session.

### `channels.py`
- **`Channel`**: Extends `DefaultChannel`
- Custom channel functionality

### `scripts.py`
- **`Script`**: Extends `DefaultScript`
- Custom script functionality

### `mixins.py`
- Shared functionality across multiple typeclass types
- Common patterns for DRY implementation
- **Not here:** examine-time display extras (reactive scars, ranking displays,
  captivity status, board postings, catering history, crafted provenance, room
  functionaries/notice-board hint/heat) live at the `LookAction` action-layer
  seam (`actions.definitions.examine_extras.gather_examine_extras`), not on a
  typeclass hook — see ADR-0213. `ObjectParent` carries no `at_examined`/
  `return_appearance` override.

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
