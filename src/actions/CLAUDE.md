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
- **`models/action_templates.py`**: `ActionTemplate` — includes `consent_category` (nullable FK →
  `SocialConsentCategory`). Social templates are tagged by staff (or the seed loader); uncategorized
  templates are gated only by the master `allow_social_actions` switch. See `docs/systems/consent.md`.
- **`effect_configs.py`**: FK-backed config models (`ModifyKwargsConfig`, `AddModifierConfig`, `ConditionOnCheckConfig`)
- **`effects/`**: Effect handler package — dispatch registry and typed handlers
- **`enhancements.py`**: `get_involuntary_enhancements()` — query function for auto-applied enhancements
- **`prerequisites.py`**: `Prerequisite` base class — `is_met(actor, target, context)`
- **`registry.py`**: Action lookup by key (`get_action`) and by target type (`get_actions_for_target_type`)
- **`definitions/`**: Concrete action implementations grouped by category
  (e.g. `alterations.py` — `ResolveAlterationAction`, key `"resolve_alteration"`,
  REGISTRY backend, `target_type=SELF`; resolves pending Mage Scars via library
  template or scratch authoring. Shared by telnet `CmdMageScar` and the web
  `PendingAlterationViewSet.resolve`, #1490;
  `ritual.py` — `PerformRitualAction`, key `"perform_ritual"`, the
  action.run() seam for SERVICE/FLOW ritual performance shared by telnet
  `CmdRitual` and the web `RitualPerformView`, #1331;
  `cast.py` — `CastTechniqueAction`, key `"cast_technique"`, the SCENE_ADAPTIVE
  seam for standalone technique casts — see "SCENE_ADAPTIVE Backend" below;
  `combat_maneuvers.py` (#1453/#1452) — the non-cast/non-clash combat verbs as REGISTRY
  actions: `FleeAction`/`CoverAction`/`InterposeAction`/`ReadyAction`/`UpgradeComboAction`/
  `RevertComboAction`/`JoinEncounterAction`/`LeaveEncounterAction` (keys prefixed `combat_`).
  Each `execute()` resolves the actor's active `CombatParticipant`/encounter and calls the
  existing combat service; shared by telnet `CmdCombat` (`combat <subverb>`) and the web
  `CombatEncounterViewSet`. `yield` is not here — `YieldAction` (`duels.py`) is reused. The one
  new service is `toggle_action_ready`, extracted from the inline web `ready` toggle;
  `locations.py` — `RoomEditAction`, key `"edit_room"` (#1470), owner-gated
  (`IsRoomOwnerPrerequisite`) edit of the current room's name/description/public-listing via
  `world.locations.services.set_room_display_data`; shared by telnet `CmdManageRoom` + web dispatch;
  `personas.py` — `SetActivePersonaAction`, key `"set_active_persona"` (#1347), REGISTRY backend,
  `target_type=SELF`, kwarg `persona_id`; the single action.run() path for set-active shared by
  telnet `CmdPersona` and the web `PersonaViewSet.set_active`. Validates the persona belongs to
  the actor's own sheet; wraps `world.scenes.services.set_active_persona` (the sole mutator).
  Pose/sdesc reflection of the active persona is #1109's scope, not this action.)

## SCENE_ADAPTIVE Backend (#1351)

`ActionBackend.SCENE_ADAPTIVE` is a fourth dispatch backend (alongside CHALLENGE, COMBAT, REGISTRY)
for actions that work in **and** out of a combat round — such as technique casts. The canonical
implementation is `CastTechniqueAction` (`actions/definitions/cast.py`, key `"cast_technique"`).

### Dispatch flow (`_dispatch_scene_adaptive` in `player_interface.py`)

1. **Anti-spam check** — `commands.pending_actions.check_anti_spam(sheet_pk, anti_spam_seconds)`.
   If a cooldown remains, raises `ActionDispatchError(ANTI_SPAM_COOLDOWN)`. The cooldown length
   comes from `get_scene_round_defaults_config().anti_spam_seconds`.
2. **Registry lookup** — key resolved from `ref.registry_key`.
3. **Round context branch** (when `ctx` is not None):
   a. Call `action_obj.round_declaration(ctx, **run_kwargs)`. If the context's `is_declaration_open`
      is True and a `(PlayerAction, decl_kwargs)` tuple is returned, record the declaration and return
      `deferred=True` immediately (STRICT combat round path).
   b. Otherwise call `ctx.is_repeat_blocked(sheet, ref, target_persona)`. If True, raise
      `ActionDispatchError(ROUND_REPEAT_BLOCKED)`.
4. **Immediate execution** — `action_obj.run(actor, **run_kwargs)`.
5. **Side-effects** (only when `result.success`):
   - `mark_acted(sheet_pk)` — records the timestamp for the anti-spam floor.
   - `ctx.record_immediate_action(sheet, ref, target_persona)` — writes the POSE_ORDER ledger row and
     advances the quorum when `mode==POSE_ORDER`.

### `Action.round_declaration` hook (`base.py`)

Default returns `None` (always immediate). Override to declare into a round:

```python
def round_declaration(self, ctx: Any, **kwargs: Any) -> tuple[PlayerAction, dict[str, Any]] | None:
    ...
```

`CastTechniqueAction` returns a `(PlayerAction, decl_kwargs)` tuple when `ctx` is a
`CombatRoundContext` (so `cast` inside combat declares into the combat round), and `None` otherwise
(immediate execution in social scene rounds).

### Anti-spam floor + pending-cast store (`commands/pending_actions.py`)

In-memory (no DB) transient stores:

- `check_anti_spam(sheet_pk, seconds) -> float | None` — remaining cooldown or None.
- `mark_acted(sheet_pk)` — records the timestamp.
- `PendingCast` dataclass — stores `(technique_id, target_persona_id, kwargs)` for soulfray-gated
  re-dispatch.
- `register_pending(sheet_pk, pending)` / `pop_pending(sheet_pk)` / `peek_pending(sheet_pk)` —
  manipulate the pending cast store for the `SoulfrayPendingHandler` offer flow.

### `CastTechniqueAction` (`actions/definitions/cast.py`)

Key: `"cast_technique"`. Resolves a standalone technique cast via `request_technique_cast`
(`world.scenes.cast_services`). Soulfray consent gate:

- When `get_soulfray_warning` is non-None and `confirm_soulfray_risk=False`, the action registers a
  `PendingCast` and returns `success=False` — the dispatcher does NOT record anti-spam or advance the
  pose-order quorum. The actor is prompted to `accept soulfray` or `decline soulfray` (handled by
  `SoulfrayPendingHandler` in `world/magic/offer_handlers.py`).
- When `confirm_soulfray_risk=True` (set by the offer-accept path), the cast proceeds immediately.

## Prerequisites

`get_prerequisites()` is **load-bearing** — `run()` calls `check_availability()`
against all returned prerequisites after enhancements are applied and before
`execute()` is ever reached. A non-empty list is a hard gate, not advisory.

### kwargs-via-context convention

`check_availability()` receives `context={"kwargs": context.kwargs, "scene_data": sdm}`.
Prerequisites that need to inspect action-specific kwargs (e.g., the `item` kwarg
on `UseItemAction`) read them from `context["kwargs"]`:

```python
item_obj = (context or {}).get("kwargs", {}).get("item")
```

This lets a prerequisite see a second target or any other kwarg without being
coupled to the action's kwarg names by the base class.

### Prerequisite implementations (`prerequisites.py`)

- **`StaffOnlyPrerequisite`** — actor's account must be staff.
- **`HoldsItemPrerequisite`** — actor holds the `item` kwarg.
- **`ItemUsablePrerequisite`** — item template has `on_use_pool` (is usable); consumables
  must have charges remaining. Delegates to `ItemTemplate.is_usable`.
- **`OnUseTargetPrerequisite`** — enforces `ItemTemplate.on_use_target_kind`: null ⇒
  self-use only (external target rejected); set ⇒ requires a target of that kind,
  reachable and visible. Visibility is currently a same-location MVP proxy
  (`_is_visible_to`); a real perception/stealth system will replace it.

## Adding a New Action

1. Create a new class in the appropriate `definitions/` file (or create a new file)
2. Subclass `Action`, set `key`, `name`, `icon`, `category`, `target_type`
3. Override `execute(actor, context, **kwargs)` with the action's logic
4. Override `get_prerequisites()` if the action has prerequisites — these are enforced
   by `run()` before `execute()` is called; read extra kwargs via `context["kwargs"]`
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

`context.kwargs` is also threaded into `check_availability()` as
`context={"kwargs": context.kwargs, "scene_data": sdm}` so prerequisites can read
action-specific kwargs (see "Prerequisites" above).

### Source Contract
Source models implement one method:
- `should_apply_enhancement(actor, enhancement) -> bool` — involuntary filtering

Sources only answer "does this actor have me right now?" The *effect* of the enhancement
lives on the config model rows attached to the `ActionEnhancement`, not on the source.

### Enhancement Flow in `run()`
1. Build `ActionContext` with SceneDataManager
2. Apply voluntary enhancements via `enh.apply(context)` → dispatches to handlers
3. Query and apply involuntary enhancements via `enh.apply(context)`
4. **Enforce prerequisites** — `check_availability()` is called against the
   post-enhancement kwargs; if any prerequisite is unmet, `run()` returns a failure
   `ActionResult` immediately (never reaches `execute()`). This is a hard gate, not
   advisory. See "Prerequisites" below for the kwargs-via-context convention.
5. Charge declarative AP + fatigue costs (`_charge_costs`) — fails if AP cannot be
   afforded.
6. Call `execute()` with context and kwargs
7. Run post-effects

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
