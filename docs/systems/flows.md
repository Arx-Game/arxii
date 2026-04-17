# Flows System

Database-driven game logic engine. Two layers live here:

1. **Flow execution** — `FlowDefinition` rows whose `FlowStepDefinition` children are walked by `FlowExecution`. Used for complex branching sequences (set context, evaluate, call service, emit). Today this layer is *infrastructure only* — no `FlowDefinition` rows ship with the codebase.
2. **Reactive layer** *(Scope 5.5, branch `design/reactive-layer`)* — `Event` + `TriggerDefinition` + `Trigger` plus the per-owner `TriggerHandler`, the `emit_event` API, the JSON filter DSL, and the new flow action steps. This is the wedge that lets conditions, items, and techniques attach reactive behavior. Existing service functions emit events at damage, attack, move, examine, condition-lifecycle, and technique-cast moments.

**Source:** `src/flows/`

---

## Reactive Layer Quick Reference

### Emitting an event

```python
from flows.emit import emit_event
from flows.events.names import EventNames
from flows.events.payloads import DamageAppliedPayload

emit_event(
    EventNames.DAMAGE_APPLIED,
    DamageAppliedPayload(
        target=character,
        amount_dealt=12,
        damage_type="physical",
        source=damage_source,
        hp_after=character.combat_state.hp,
    ),
    personal_target=character,
    room=character.location,
)
```

- ROOM dispatches first; if a ROOM-scope trigger calls `CANCEL_EVENT`, PERSONAL is skipped entirely.
- Returns a `FlowStack`. Call `.was_cancelled()` to detect veto from a PRE-event.
- Pass `parent_stack=` when emitting from inside a flow so the recursion cap is enforced on the originating chain.

### Cancellable PRE events

PRE-event payloads are mutable dataclasses. `MODIFY_PAYLOAD` flow steps can amend them (e.g. a fire-resistance scar lowering `DamagePreApplyPayload.amount`). `CANCEL_EVENT` aborts the originating action — the calling service function checks `stack.was_cancelled()` and bails. POST-event payloads are frozen — reactive flows cannot rewrite history.

### Trigger ownership and lifecycle

`Trigger` rows have:

- `obj` — the typeclass owner (Character / Room / Object) the trigger lives on
- `trigger_definition` — the reusable template (event + flow + base filter + priority)
- `source_condition` / `source_stage` — optional cascade source. When set, deleting the `ConditionInstance` cascades the row away. `source_stage` makes the trigger active only while the condition is at that stage.
- `scope` — `PERSONAL` (delivered to `personal_target`) or `ROOM` (delivered to `room`)
- `additional_filter_condition` — JSON DSL evaluated per dispatch; restricts which payloads match

Service functions install triggers from `ConditionTemplate.reactive_triggers` (M2M to `TriggerDefinition`) when `apply_condition` runs and call `handler.on_trigger_added(...)` to keep the cached handler in sync.

### TriggerHandler (per-owner cache)

Installed as `cached_property` on Character/Room/Object via `ObjectParent`. First access populates from the DB once and joins event/flow/condition/stage in a single query. Subsequent dispatches are O(active triggers for event_name) with zero queries. Sync hooks (`on_trigger_added`, `on_trigger_removed`, `on_stage_changed`) keep the cache fresh — service functions must call them after persisting the row.

### Filter DSL

JSON shape, evaluated against the event payload:

```python
{"path": "source.type", "op": "==", "value": "character"}
{"and": [
    {"path": "damage_type", "op": "==", "value": "fire"},
    {"path": "amount", "op": ">=", "value": 5},
]}
{"path": "target", "op": "has_property", "value": "warded"}
{"path": "attacker", "op": "==", "value": "self"}  # self-ref to handler owner
```

Supported ops: `==`, `!=`, `<`, `<=`, `>`, `>=`, `in`, `contains`, `has_property`. Logical combinators: `and`, `or`, `not`. Values prefixed with `self.` (or the literal `"self"`) resolve against the trigger's owner.

### Player prompts (Twisted Deferred, no DB rows)

`flows/execution/prompts.py` keeps a module-level dict of `(account_id, prompt_key) -> (Deferred, default_answer)`. `PROMPT_PLAYER` flow steps register a prompt and return a Deferred; the player answers via the `@reply` account command (`resolve_pending_prompt`) or the prompt times out (`timeout_pending_prompt` fires the Deferred with `default_answer`). Prompt state is process-local and ephemeral — restart of the Evennia portal drops in-flight prompts to their defaults.

### AE topology

For area-of-effect events, the caller emits PERSONAL once per target plus ROOM once. Each PERSONAL dispatch gets its own `FlowStack` so recursion caps don't leak between targets. ROOM cancellation propagates to suppress *all* subsequent PERSONAL dispatches in that emission.

### Damage source discrimination

`world/combat/damage_source.py:classify_source(obj)` returns a `DamageSource(type, ref)` discriminated union:

| `type` | `ref` is | Trigger filter example |
|--------|----------|------------------------|
| `"character"` | a Character | `{"path": "source.ref", "op": "==", "value": "self"}` retaliates against attacker |
| `"technique"` | a Technique | `{"path": "source.ref.affinity", "op": "==", "value": "fire"}` |
| `"scar"` | a `ConditionInstance` | distinguishes scar damage from raw weapon damage |
| `"environment"` | a Room | "lava room" damage |
| `"item"` | anything else (fallback) | trap/projectile damage |

---

## Event Catalog (MVP)

All names live in `flows.events.names.EventNames`; payload dataclasses in `flows.events.payloads`; mapping in `PAYLOAD_FOR_EVENT`.

| Event | Payload | Scope | Cancellable |
|-------|---------|-------|-------------|
| `attack_pre_resolve` | `AttackPreResolvePayload` | ROOM + PERSONAL | yes |
| `attack_landed` | `AttackLandedPayload` | PERSONAL (target) | no |
| `attack_missed` | `AttackMissedPayload` | PERSONAL (target) | no |
| `damage_pre_apply` | `DamagePreApplyPayload` | PERSONAL (target) | yes (mutable amount) |
| `damage_applied` | `DamageAppliedPayload` | PERSONAL (target) + ROOM | no |
| `character_incapacitated` | `CharacterIncapacitatedPayload` | PERSONAL + ROOM | gate (see below) |
| `character_killed` | `CharacterKilledPayload` | PERSONAL + ROOM | gate (see below) |
| `move_pre_depart` | `MovePreDepartPayload` | PERSONAL + ROOM (origin) | yes |
| `moved` | `MovedPayload` | PERSONAL + ROOM (destination) | no |
| `examine_pre` | `ExaminePrePayload` | PERSONAL (target) | yes |
| `examined` | `ExaminedPayload` | PERSONAL (target) | no (frozen — pending follow-up) |
| `condition_pre_apply` | `ConditionPreApplyPayload` | PERSONAL (target) | yes |
| `condition_applied` | `ConditionAppliedPayload` | PERSONAL (target) | no |
| `condition_stage_changed` | `ConditionStageChangedPayload` | PERSONAL (target) | no |
| `condition_removed` | `ConditionRemovedPayload` | PERSONAL (target) | no |
| `technique_pre_cast` | `TechniquePreCastPayload` | PERSONAL (caster) | yes |
| `technique_cast` | `TechniqueCastPayload` | PERSONAL (caster) + ROOM | no |
| `technique_affected` | `TechniqueAffectedPayload` | PERSONAL (each target) | no |

`character_incapacitated` and `character_killed` fire only when the combat service detects `knockout_eligible` / `death_eligible` on the participant (or when `force_death=True` is passed). They are not raw "HP <= 0" emissions.

---

## Flow Action Steps

Defined in `flows.consts.FlowActionChoices`. The reactive-layer additions are:

| Action | Purpose |
|--------|---------|
| `CANCEL_EVENT` | Mark the current `DispatchResult` as cancelled — calling service function should bail |
| `MODIFY_PAYLOAD` | Mutate a field on the (mutable) PRE-event payload — e.g. `set min: 0` clamps damage |
| `PROMPT_PLAYER` | Suspend flow, register a Deferred, resume when player replies via `@reply` |

Two action steps were **deferred** during Scope 5.5:

- `DEAL_DAMAGE` — emit a flow event that calls `world.combat.services.apply_damage_to_participant` instead
- `REMOVE_CONDITION` — emit a flow event that calls `world.conditions.services.remove_condition` instead

These can be added later without breaking existing trigger content.

---

## Models

### Flow Definition

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `FlowDefinition` | Reusable workflow definition | `name`, `description` |
| `FlowStepDefinition` | One step of a flow (set/eval/call/emit/cancel/modify/prompt) | `flow`, `parent`, `action`, `variable_name`, `parameters` (JSON) |
| `FlowStack` | Per-execution recursion-capped stack | `owner`, `originating_event`, `depth`, `cap` |

### Reactive

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `Event` | Catalog row matching an `EventNames` constant | `name`, `description` |
| `TriggerDefinition` | Reusable template (event + flow + base filter + priority) | `name`, `event`, `flow_definition`, `base_filter_condition`, `priority` |
| `Trigger` | Installed instance on a typeclass owner | `obj`, `trigger_definition`, `source_condition`, `source_stage`, `scope`, `additional_filter_condition`, `priority` |
| `TriggerData` | Per-trigger runtime data (e.g. usage counters — fields pending) | `trigger`, `key`, `value` |

---

## Object States and Service Functions

The non-reactive flow infrastructure also exposes:

- **Object States** — `BaseState`, `CharacterState`, `RoomState`, `ExitState`. Ephemeral wrappers with permission methods (`can_move`, `can_traverse`) and appearance rendering. Used by service functions instead of raw typeclass calls.
- **Service Functions** — `send_message`, `message_location`, `send_room_state`, `move_object`, `check_exit_traversal`, `traverse_exit`, `get_formatted_description`, `show_inventory`. Accept a `BaseState` (no `FlowExecution` dependency).
- **SceneDataManager** — manages per-execution scene state.

---

## Tests

29 reactive-layer integration tests live across:

- `src/flows/tests/test_reactive_integration.py`
- `src/world/combat/tests/test_reactive_integration.py`
- `src/world/conditions/tests/test_reactive_integration.py`
- `src/world/magic/tests/test_reactive_scars.py`

10 are authored-but-skipped pending follow-up infrastructure: covenant relationships, Property M2M on Technique, trigger usage-cap fields, mutable `ExaminedPayload`. Skip reasons document what each test will cover when the missing piece lands.

Run all reactive tests:

```bash
arx test flows.tests.test_reactive_integration world.combat.tests.test_reactive_integration world.conditions.tests.test_reactive_integration world.magic.tests.test_reactive_scars --keepdb
```

---

## See Also

- **Plan:** `docs/superpowers/plans/2026-04-17-reactive-layer-implementation.md`
- **Spec:** `docs/superpowers/specs/2026-04-16-reactive-layer-design.md`
- **Roadmap context:** `docs/roadmap/magic.md` (Scope 5.5)
