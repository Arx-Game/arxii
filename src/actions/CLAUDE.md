# Actions — Self-Contained Game Actions

The action layer is the core unit of game behavior. Each action owns its full
lifecycle: prerequisites, execution, and events. Both telnet commands and the
web dispatcher call `action.run()` — the action handles everything.

## Architecture

```
Web:    frontend → websocket → action dispatcher → action.run()
Telnet: text → command.parse() → command.func() → action.run()
```

Actions call service functions directly (from `flows/service_functions/`).
They do not use the command system, dispatchers, or handlers.

## Key Files

- **`base.py`**: `Action` dataclass — base class with `run()`, `execute()`, `check_availability()`
- **`types.py`**: `ActionResult`, `ActionAvailability`, `ActionContext`, `TargetType`, `ActionInterrupted`
- **`models.py`**: `ActionEnhancement` — explicit FK model linking sources to base actions
- **`effects.py`**: Standard effect vocabulary (`modify_kwargs`, `add_modifiers`, `post_effect`)
- **`enhancements.py`**: `get_involuntary_enhancements()` — query function for auto-applied enhancements
- **`prerequisites.py`**: `Prerequisite` base class — `is_met(actor, target, context)`
- **`registry.py`**: Action lookup by key (`get_action`) and by target type (`get_actions_for_target_type`)
- **`definitions/`**: Concrete action implementations grouped by category

## Adding a New Action

1. Create a new class in the appropriate `definitions/` file (or create a new file)
2. Subclass `Action`, set `key`, `name`, `icon`, `category`, `target_type`
3. Override `execute(actor, context, **kwargs)` with the action's logic
4. Override `get_prerequisites()` if the action has prerequisites
5. Add the action instance to `_ALL_ACTIONS` in `registry.py`
6. Write tests in `tests/`
7. (Optional) Create a telnet command in `commands/` that delegates to the action

## Enhancement System

### ActionEnhancement Model
Database entities (techniques, distinctions, conditions) modify base actions via
`ActionEnhancement` records. Each record links a source model (via explicit nullable FKs
with a type discriminator) to a base action key, with effect parameters and a
voluntary/involuntary flag. The `apply()` method delegates to `effects.apply_standard_effects()`.

### Standard Effect Vocabulary (effects.py)
Effect behavior is data-driven via `effect_parameters` JSON:
- `modify_kwargs`: dict mapping kwarg names to transforms (e.g. `{"text": "uppercase"}`)
- `add_modifiers`: dict merged into `context.modifiers` (e.g. `{"check_bonus": 5}`)
- `post_effect`: str naming a post-effect type, with remaining keys as parameters

### ActionContext
A mutable execution context built by `Action.run()` and passed to the action's `execute()`.
Contains:
- `action`, `actor`, `target`, `kwargs`, `scene_data` — read context
- `modifiers` — unstructured dict for enhancement-added modifiers
- `post_effects` — callables run after execution
- `result` — set after execution completes

### Source Contract
Source models inherit from `EnhancementSource` (in `types.py`) and implement one method:
- `should_apply_enhancement(actor, enhancement) -> bool` — involuntary filtering

Sources only answer "does this actor have me right now?" The *effect* of the enhancement
lives on the `ActionEnhancement` record's `effect_parameters`, not on the source.

### Enhancement Flow in `run()`
1. Build `ActionContext` with SceneDataManager
2. Apply voluntary enhancements via `enh.apply(context)`
3. Query and apply involuntary enhancements via `enh.apply(context)`
4. Call `execute()` with context and kwargs
5. Run post-effects

## What's Not Built Yet

### SyntheticAction Model
Wholly new actions granted by database entities. Uses parameterized templates
or flow definitions for execution. Same source contract as enhancements.

### Event Emission
`Action.run()` has TODOs for emitting intent/result events. When implemented,
the action will emit events that triggers can respond to.

### CharacterCapabilities Facade
Unified query interface for checking character capabilities. Used by
prerequisites to evaluate "can this character do X right now?"

### On-Demand Action Availability
WebSocket endpoint for the frontend to request available actions for a
specific actor/target pair. Evaluates prerequisites on demand rather than
pre-computing for every entity.
