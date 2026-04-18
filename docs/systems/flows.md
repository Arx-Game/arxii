# Flows System

Database-driven game logic engine. Two layers live here:

1. **Flow execution** — `FlowDefinition` rows whose `FlowStepDefinition` children are walked by `FlowExecution`. Used for complex branching sequences (set context, evaluate, call service, emit). Today this layer is *infrastructure only* — no `FlowDefinition` rows ship with the codebase.
2. **Reactive layer** *(Scope 5.5, branch `design/reactive-layer`)* — `Event` + `TriggerDefinition` + `Trigger` plus the per-owner `TriggerHandler`, the `emit_event` API, the JSON filter DSL, and the new flow action steps. Dispatch is **unified**: a single location walk gathers every trigger in the room, priority-sorts them globally, and runs them on one `FlowStack`. Self-vs-target-vs-bystander semantics come from JSON filters, not a scope field. This is the wedge that lets conditions, items, and techniques attach reactive behavior. Existing service functions emit events at damage, attack, move, examine, condition-lifecycle, and technique-cast moments.

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
    character.location,
)
```

- Signature: `emit_event(event_name, payload, location, *, parent_stack=None)`. `location` is a Room — almost always the subject's current location.
- **One location walk.** `emit_event` iterates `[location, *location.contents]`, calls `owner.trigger_handler.triggers_for(event_name)` on each owner, collects every matching trigger, and priority-sorts the combined list (descending) globally. There is no separate ROOM vs PERSONAL pass.
- **Single FlowStack.** All triggers for the emission run synchronously on one `FlowStack`, in priority order. If any trigger calls `CANCEL_EVENT`, dispatch stops — no later trigger fires.
- Returns the `FlowStack`. Call `.was_cancelled()` to detect veto from a PRE-event.
- Pass `parent_stack=` when emitting from inside a flow so the recursion cap is enforced on the originating chain.
- `EMIT_FLOW_EVENT` flow action steps route through this same function — there is one dispatch path for service functions, typeclass hooks, and flow-authored emits.

### Cancellable PRE events

PRE-event payloads are mutable dataclasses. `MODIFY_PAYLOAD` flow steps can amend them (e.g. a fire-resistance scar lowering `DamagePreApplyPayload.amount`). `CANCEL_EVENT` aborts the originating action — the calling service function checks `stack.was_cancelled()` and bails. POST-event payloads are frozen — reactive flows cannot rewrite history.

### Trigger ownership and lifecycle

`Trigger` rows have:

- `obj` — the typeclass owner (Character / Room / Object) the trigger lives on
- `trigger_definition` — the reusable template (event + flow + base filter + priority)
- `source_condition` — **required**. Every trigger must be scoped to a source `ConditionInstance` for provenance and cascade. Room-owned triggers use a pseudo-`ConditionInstance` whose target is the room.
- `source_stage` — optional. Makes the trigger active only while the source condition is at that stage.
- `additional_filter_condition` — JSON DSL evaluated per dispatch; restricts which payloads match. **This is how you express self-vs-target-vs-bystander semantics** — there is no `scope` field. See Filter Idioms below.

Service functions install triggers from `ConditionTemplate.reactive_triggers` (M2M to `TriggerDefinition`) when `apply_condition` runs and call `handler.on_trigger_added(...)` to keep the cached handler in sync.

### TriggerHandler (per-owner cache)

Installed as `cached_property` on Character/Room/Object via `ObjectParent`. First access populates from the DB once and joins event/flow/condition/stage in a single query. Subsequent calls are O(active triggers for event_name) with zero queries.

The handler is a **pure provider**: its sole public method is `triggers_for(event_name) -> list[Trigger]`. It does not dispatch. `emit_event` queries the handler on every owner in the location walk, concatenates results, priority-sorts globally, and dispatches itself. Sync hooks (`on_trigger_added`, `on_trigger_removed`, `on_stage_changed`) keep the cache fresh — service functions must call them after persisting the row.

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

Supported ops: `==`, `!=`, `<`, `<=`, `>`, `>=`, `in`, `contains`, `has_property`. Logical combinators: `and`, `or`, `not`. Values prefixed with `self.` (or the literal `"self"` alone) resolve against the trigger's owner (`trigger.obj`).

### Filter Idioms

Since dispatch is unified (every trigger in the room is collected on every emission), filters are how you scope a trigger's effective audience. Three common patterns:

**Self-only (`scope=SELF` replacement).** Fires only when the trigger owner *is* the payload target. Use for reactive wards, "I take damage" scars, personal defenses:

```python
{"path": "target", "op": "==", "value": "self"}
```

Example: a fire-resistance scar on the caster should fire when the caster is attacked, not when a bystander is. The evaluator resolves bare `"self"` to `trigger.obj`, which is the caster.

**Bystander-only (not-self).** Fires on every owner in the room *except* the target. Use for ally reactions, witness effects, crowd observations:

```python
{"path": "target", "op": "!=", "value": "self"}
```

Example: an ally with a "Defend the Weak" reactive trigger watches someone else get hit and counterattacks — but doesn't fire when the ally themselves is the target (that's a different trigger).

**Room-wide (`scope=ROOM`/`scope=ANY` replacement).** Omit the target filter entirely. Fires on every owner the location walk reaches — the room itself, every character, every object:

```python
{}  # or any filter that doesn't constrain `target`
```

Example: a room aura that reacts to *any* technique being cast in the room, regardless of caster or target.

Combine with other predicates (`damage_type`, `source.ref.affinity`, `has_property`) as needed. Because dispatch is synchronous and priority-ordered, a high-priority self-filtered trigger can cancel the event before any bystander-filtered trigger runs.

### Player prompts (Twisted Deferred, no DB rows)

`flows/execution/prompts.py` keeps a module-level dict of `(account_id, prompt_key) -> (Deferred, default_answer)`. `PROMPT_PLAYER` flow steps register a prompt and return a Deferred; the player answers via the `@reply` account command (`resolve_pending_prompt`) or the prompt times out (`timeout_pending_prompt` fires the Deferred with `default_answer`). Prompt state is process-local and ephemeral — restart of the Evennia portal drops in-flight prompts to their defaults.

### AE topology

Area-of-effect events carry a `targets: list` field on the payload (e.g. `AttackPreResolvePayload.targets`) and emit **once** — the single unified dispatch walks the location, runs every trigger on one `FlowStack` in priority order, and stops on cancellation. A self-filtered trigger on one target can cancel the whole AE event if it runs at high enough priority; reactive flows that need per-target behavior should inspect the payload's `targets` list themselves.

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

| Event | Payload | Location | Cancellable |
|-------|---------|----------|-------------|
| `attack_pre_resolve` | `AttackPreResolvePayload` | room of attacker | yes |
| `attack_landed` | `AttackLandedPayload` | room of target | no |
| `attack_missed` | `AttackMissedPayload` | room of target | no |
| `damage_pre_apply` | `DamagePreApplyPayload` | room of target | yes (mutable amount) |
| `damage_applied` | `DamageAppliedPayload` | room of target | no |
| `character_incapacitated` | `CharacterIncapacitatedPayload` | room of target | gate (see below) |
| `character_killed` | `CharacterKilledPayload` | room of target | gate (see below) |
| `move_pre_depart` | `MovePreDepartPayload` | origin room | yes |
| `moved` | `MovedPayload` | destination room | no |
| `examine_pre` | `ExaminePrePayload` | room of target | yes |
| `examined` | `ExaminedPayload` | room of target | no (frozen — pending follow-up) |
| `condition_pre_apply` | `ConditionPreApplyPayload` | room of target | yes |
| `condition_applied` | `ConditionAppliedPayload` | room of target | no |
| `condition_stage_changed` | `ConditionStageChangedPayload` | room of target | no |
| `condition_removed` | `ConditionRemovedPayload` | room of target | no |
| `technique_pre_cast` | `TechniquePreCastPayload` | room of caster | yes |
| `technique_cast` | `TechniqueCastPayload` | room of caster | no |
| `technique_affected` | `TechniqueAffectedPayload` | room of caster | no |

The "Location" column is the room passed to `emit_event`. Dispatch walks that room plus its contents — so a single emission reaches the room, the subject, and every other character/object colocated with them. Payloads that carry multiple targets (`AttackPreResolvePayload.targets: list`, `TechniqueAffectedPayload`) still emit once; per-target behavior is a filter concern.

`character_incapacitated` and `character_killed` fire only when the combat service detects `knockout_eligible` / `death_eligible` on the participant (or when `force_death=True` is passed). They are not raw "HP <= 0" emissions.

---

## Flow Action Steps

Defined in `flows.consts.FlowActionChoices`. The reactive-layer additions are:

| Action | Purpose |
|--------|---------|
| `CANCEL_EVENT` | Mark the current `FlowStack` as cancelled — `emit_event` stops processing remaining triggers and the calling service function should bail |
| `MODIFY_PAYLOAD` | Mutate a field on the (mutable) PRE-event payload — e.g. `set min: 0` clamps damage |
| `PROMPT_PLAYER` | Suspend flow, register a Deferred, resume when player replies via `@reply` |
| `EMIT_FLOW_EVENT` | Emit an event from inside a flow. Routes through `emit_event()` — the same single unified dispatch path used by service functions and typeclass hooks. Pass `parent_stack=` so the recursion cap follows the originating chain |
| `EMIT_FLOW_EVENT_FOR_EACH` | Variant that emits once per item in a context list. Each emission goes through `emit_event()`; each gets its own `FlowStack` so per-item cancellation doesn't leak |

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
| `Trigger` | Installed instance on a typeclass owner | `obj`, `trigger_definition`, `source_condition` (required), `source_stage`, `additional_filter_condition`, `priority` |
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
