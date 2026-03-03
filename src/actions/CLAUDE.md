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
- **`effect_configs.py`**: FK-backed config models (`ModifyKwargsConfig`, `AddModifierConfig`, `ConditionOnCheckConfig`)
- **`effects/`**: Effect handler package — dispatch registry and typed handlers
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
with a type discriminator) to a base action key, with a voluntary/involuntary flag.
The `apply()` method dispatches all attached effect configs to their handlers.

### Effect Config Models (effect_configs.py)
Each effect type is a concrete Django model inheriting from `BaseEffectConfig`.
No JSONField — all parameters are proper typed columns with FK integrity.

- **`ModifyKwargsConfig`**: Apply a named transform (uppercase/lowercase) to an action kwarg
- **`AddModifierConfig`**: Set a key-value modifier in `context.modifiers`
- **`ConditionOnCheckConfig`**: Apply a condition gated by a check roll (immunity → difficulty → roll → apply/immunity)

All configs share `enhancement` FK and `execution_order` from the abstract base.

### Effect Handlers (effects/)
- **`registry.py`**: `apply_effects()` queries all config tables, merges by `execution_order`, dispatches to handlers
- **`kwargs.py`**: `handle_modify_kwargs()` — applies named transforms to kwarg values
- **`modifiers.py`**: `handle_add_modifier()` — sets context.modifiers entries
- **`conditions.py`**: `handle_condition_on_check()` — orchestrates immunity/check/apply flow
- **`base.py`**: Shared steps (`check_immunity`, `resolve_target_difficulty`, `apply_immunity_on_fail`)

### Adding a New Effect Type

1. Create a new concrete model in `effect_configs.py` inheriting from `BaseEffectConfig`
2. Import it in `models.py` for Django model discovery
3. Create a handler function in `effects/<name>.py`
4. Register the handler in `effects/registry.py` `_HANDLER_REGISTRY`
5. Add the related name to `_CONFIG_RELATED_NAMES`
6. Write tests in `tests/test_effects.py`
7. Run `arx manage makemigrations actions`

### ActionContext
A mutable execution context built by `Action.run()` and passed to the action's `execute()`.
Contains:
- `action`, `actor`, `target`, `kwargs`, `scene_data` — read context
- `modifiers` — unstructured dict for enhancement-added modifiers
- `post_effects` — callables run after execution
- `result` — set after execution completes

### Source Contract
Source models implement one method:
- `should_apply_enhancement(actor, enhancement) -> bool` — involuntary filtering

Sources only answer "does this actor have me right now?" The *effect* of the enhancement
lives on the config model rows attached to the `ActionEnhancement`, not on the source.

### Enhancement Flow in `run()`
1. Build `ActionContext` with SceneDataManager
2. Apply voluntary enhancements via `enh.apply(context)` → dispatches to handlers
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
