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
- **Login puppets the account's character; there is no OOC screen** (#3812,
  ADR-0293). `at_post_login` reproduces Evennia's three login side effects
  (protocol flags, the `logged_in` OOB, the connect-channel line) and then
  puppets `resolve_login_character()`'s pick: the durable selection, then
  Evennia's `_last_puppet`, then a sole character — several with nothing
  recorded gets a one-line list, never a silent first pick. It does NOT call
  `super().at_post_login`, which renders the stock OOC screen unconditionally
  on this path. `@ic` (`puppet_character_in_session`) stays for switching and is
  a no-op for the session's own puppet, which is what the web client sends on
  every socket open.
- **Sessions share a character** (`MULTISESSION_MODE = 3`). `can_puppet_character`
  never refuses "another of your sessions has it"; two windows are one
  `Character`. Any hook that means "came online"/"went offline" fires on the
  first/last session only — see `Character.at_post_puppet`/`at_post_unpuppet`
  and `tests/test_puppet_session_hooks.py`.
- **Puppeting records the selection** (`_record_selection` → `set_selected_entry`,
  ADR-0241 as amended). Selecting still never puppets.
- **A row that skipped first-save setup heals itself.** `at_pre_login` calls
  `evennia_extensions.account_setup.heal_account_setup`; the server-start sweep
  does the same for every row. Never repair such a row by writing
  `db_typeclass_path` — that leaves it with no cmdset (the #3812 production
  shape). Use `heal_account_setup`, which is `swap_typeclass(...,
  run_start_hooks="all")`.
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
