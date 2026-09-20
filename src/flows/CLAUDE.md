# Flows System - Game Logic Engine

Database-driven workflow engine that replaces hardcoded command logic. All game state changes flow through this system.

## Key Files

### `models/`
- **`flows.py`**: `FlowDefinition`, `FlowStepDefinition`, `FlowStack` - database-defined workflows
- **`triggers.py`**: `TriggerDefinition` (with `event_name: EventName` choice), `Trigger` - event handlers that modify flows
- **`constants.py`**: `EventName(TextChoices)` - canonical event-name choices for the reactive
  layer, including the generic `ACTION_INTENT`/`ACTION_RESULT` pair every `Action.run()` emits
  (#3418, ADR-0243) - authored triggers discriminate the verb via a `payload.action_key` filter
  clause, not a per-action event name

### Authoring API (#3417)
- **`catalog.py`**: `StepActionSpec`/`ParamSpec` dataclasses, `STEP_ACTION_SPECS` - hand-declared
  per-action parameter schemas (the runtime has no way to introspect them from handler bodies);
  also `event_catalog()`, `service_function_catalog()`, `FILTER_OPS`. Single source of truth shared
  by server-side validation and the frontend palette.
- **`step_validation.py`**: `validate_step_tree()` - catalog-driven validation of an authored
  (unsaved) step tree; no DRF import.
- **`serializers.py`** / **`views.py`** / **`urls.py`**: DRF CRUD for `FlowDefinition` (full-tree
  step replace), `TriggerDefinition`, `Trigger`, plus the read-only `DslCatalogViewSet`. Mounted at
  `api/flows/`. See `docs/systems/flows.md#authoring-api-3417`.

### `object_states/`
- **`base_state.py`**: `BaseState` - mutable wrapper for Evennia objects during flows
- **`character_state.py`**: `CharacterState` - character permissions and state (`can_move`, `can_see`)
- **`room_state.py`**: `RoomState` - room scene and trigger management
- **`exit_state.py`**: `ExitState` - exit lock/unlock mechanics

### `service_functions/`
- **`communication.py`**: message sending, pose formatting, channels.
  **`send_message` and `message_location` take `echo_of: InteractionMode | None`**
  (#3933, ADR-0306). Set it when the same submission is also recorded and pushed
  as a structured Interaction: the line then goes out as Evennia's `(text,
{options})` form carrying `{"type": <mode>, "interaction_echo": True}`, so
  telnet prints the text while the web client drops the note (the Interaction is
  its render). Leave it `None` for everything else, which keeps the ordinary feed
  note. Say, pose, emit, pemit, whisper, mutter and companion poses pass it.
  **The place-scoped exception:** a pose or emit with a Place set passes `None`.
  `record_interaction` fills a place-scoped row's receivers from `PlacePresence`,
  so the Interaction reaches only personas at that Place, while the room line
  reaches the whole room; tagging it would leave a room occupant outside the
  Place with no render at all. Personas at the Place see both, which is a
  mitigation, not the fix. The real fix is place-aware room delivery.
- **`movement.py`**: room traversal, following, arrival/departure messages
- **`perception.py`**: looking, searching, inventory, object examination
- **`perception_registry.py`** (#2997): broadcast-exclusion registry —
  `register_broadcast_exclusion`/`resolve_broadcast_exclusions`, the Axis-1 seam
  `communication.py`'s `message_location` calls instead of importing one
  mechanism (e.g. dreamside) by name. See `docs/systems/scenes.md`'s "Perception
  & altered reality" section.
- **`packages.py`**: package imports and behavior attachment

### `service_functions/serializers/`
- **`commands.py`**: command metadata for frontend
- **`communication.py`**: message formatting and character data
- **`room_state.py`**: room state for web client. Exit visibility mirrors `ExitState.can_traverse`'s
  refusals (not just unenterable, invisible): an exit to an unpublished room is omitted for anyone
  but a story-runner (#3477), and an instance entrance is omitted for any looker the
  `instance_entrance` package would refuse, story-runner or not (#696 gap 7).

### Core Engine
- **`flow_execution.py`**: `FlowExecution` - orchestrates flow step execution
- **`scene_data_manager.py`**: `SceneDataManager` - manages temporary scene state
- **`flow_stack.py`**: manages nested flow execution with cleanup

### Helpers (`helpers/`)
- **`hooks.py`**: Evennia integration points
- **`logic.py`**: flow logic utilities and condition evaluation
- **`parsing.py`**: text parsing and command arguments
- **`payloads.py`**: data structure management for flow variables

## Key Classes

- **`FlowExecution`**: Executes flow steps (conditionals, service calls, events)
- **`SceneDataManager`**: Creates and manages object states during execution
- **`BaseState`**: Temporary object wrapper with dynamic permissions
- **`FlowDefinition`**: Database model defining workflow steps
