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
from flows.constants import EventName
from flows.events.payloads import DamageAppliedPayload

emit_event(
    EventName.DAMAGE_APPLIED,
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
- `source_condition` - optional (`null=True, blank=True` on the model). Set when a `ConditionInstance` installed the trigger, for provenance and cascade; null for system-installed triggers (e.g. combat escalation room triggers).
- `source_stage` — optional. Makes the trigger active only while the source condition is at that stage.
- `additional_filter_condition` — JSON DSL evaluated per dispatch; restricts which payloads match. **This is how you express self-vs-target-vs-bystander semantics** — there is no `scope` field. See Filter Idioms below.

Service functions install triggers from `ConditionTemplate.reactive_triggers` (M2M to `TriggerDefinition`) when `apply_condition` runs and call `handler.on_trigger_added(...)` to invalidate the cached handler (on commit) so the next read re-picks up the new row.

Staff wire this M2M from the flows authoring UI's TriggerDefinition editor via `PATCH /api/conditions/templates/{id}/set_reactive_triggers/` (`.set()` semantics — replaces the whole set). `ConditionTemplateSerializer.reactive_trigger_ids` (read-only, #3417 task 12) exposes a template's current set so the picker can read-modify-write it safely instead of clobbering a template's other wired triggers.

### TriggerHandler (per-owner cache)

Installed as `cached_property` on Character/Room/Object via `ObjectParent`. First access populates from the DB once and joins event/flow/condition/stage in a single query. Subsequent calls are O(active triggers for event_name) with zero queries.

The handler is a **pure provider**: its sole public method is `triggers_for(event_name) -> list[Trigger]`. It does not dispatch. `emit_event` queries the handler on every owner in the location walk, concatenates results, priority-sorts globally, and dispatches itself. Sync hooks (`on_trigger_added`, `on_trigger_removed`, `on_stage_changed`) keep the cache fresh — service functions must call them after persisting the row. The add/remove hooks call `invalidate()`, which registers a `transaction.on_commit` callback to drop the cache; the next read re-populates from committed rows. Deferring to commit makes the cache rollback-safe (#964) — a phantom trigger would double-fire, so the cache must never retain an uncommitted or rolled-back row. (Within a `TestCase`, wrap install-then-dispatch in `transaction.captureOnCommitCallbacks(execute=True)`.)

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

Supported ops: `==`, `!=`, `<`, `<=`, `>`, `>=`, `in`, `contains`, `has_property`, `has_capability`. Logical combinators: `and`, `or`, `not`. Values prefixed with `self.` (or the literal `"self"` alone) resolve against the trigger's owner (`trigger.obj`).

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

All names live in `flows.constants.EventName` (a `TextChoices`, growing as new domains wire in
events — includes the generic `ACTION_INTENT`/`ACTION_RESULT` pair every `Action.run()` emits,
#3418/ADR-0243); payload dataclasses in `flows.events.payloads`; mapping in `PAYLOAD_FOR_EVENT`.
This table documents the originally-shipped MVP subset, not the full current enum.

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

All three reactive-layer definition models (`FlowDefinition`, `FlowStepDefinition`, `TriggerDefinition`) carry `NaturalKeyMixin` and are in `CONTENT_MODELS` (#2663), so the lore repo can author the trigger→flow→step wiring as fixtures. Flow step parameters use name-based lookups (not raw PKs) for entity references, keeping fixtures identity-stable across environments.

### Reactive

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `Event` | Catalog row matching an `EventName` constant | `name`, `description` |
| `TriggerDefinition` | Reusable template (event + flow + base filter + priority) | `name`, `event`, `flow_definition`, `base_filter_condition`, `priority` |
| `Trigger` | Installed instance on a typeclass owner | `obj`, `trigger_definition`, `source_condition` (optional; null = system-installed), `source_stage`, `additional_filter_condition`, `priority` |
| `TriggerData` | Per-trigger runtime data (e.g. usage counters — fields pending) | `trigger`, `key`, `value` |

---

## Authoring API (#3417)

Staff-facing DRF surface mounted at `api/flows/` (`src/web/urls.py`), plus one
write endpoint mounted under `api/conditions/`. Read at `src/flows/catalog.py`,
`step_validation.py`, `serializers.py`, `views.py`, `urls.py`.

### Catalog contract

`FlowStepDefinition.parameters` is a bare JSONField whose shape is only
implicit in each `_execute_*` handler body (e.g. `params.get("attribute")`);
there is no way to introspect a handler and recover its parameter schema. So
`flows.catalog` hand-declares one `StepActionSpec` per `FlowActionChoices`
member (19 total: the 6 `evaluate_*` conditional actions share one builder,
plus 13 non-conditional actions each with their own), each carrying:

- `variable_name_role` (`VariableNameRole` enum: `flow_variable`,
  `object_pk_variable`, `service_function_name`, `event_store_key`,
  `unused`) - what the step's `variable_name` field means for that action.
- `params: tuple[ParamSpec, ...]` - name, `type` tag (`str`/`int`/`float`/
  `bool`/`json`/`dict`), `required`, `description`, `choices`, and
  `accepts_reference`. `accepts_reference=True` only when the matching
  handler resolves the param through `FlowExecution.resolve_flow_reference`
  (directly, or via `resolve_modifier`); a param the handler reads as a raw
  literal (an attribute name, an op string) is `accepts_reference=False`, so
  the frontend never lets an author type `@some_variable` into a field the
  runtime treats as a literal.
- `allows_extra_params` - set on `CALL_SERVICE_FUNCTION`, whose extra
  parameters are the target service function's own kwargs, not a fixed set.

`STEP_ACTION_SPECS: dict[str, StepActionSpec]` is the single source of truth,
consumed by both `step_validation.validate_step_tree` (server-side) and
`DslCatalogViewSet` (frontend palette) - one dict, so the two cannot drift.
`test_catalog.py` enforces completeness against `FlowActionChoices`, so a new
action can't ship without a catalog entry.

The catalog also exposes:

- `event_catalog()` - every `EventName` with its `PAYLOAD_FOR_EVENT` payload
  dataclass fields (`None` when a name has no payload mapped), for the
  `TriggerDefinition` filter builder.
- `service_function_catalog()` - every name in
  `flows.service_functions.list_service_functions()` with its keyword-capable
  parameter names and type tags (`inspect.signature` + `typing.get_type_hints`,
  falling back to a `json` tag when an annotation can't be resolved), for the
  `CALL_SERVICE_FUNCTION` step editor.
- `FILTER_OPS` - the comparison operators `flows.filters.evaluator` supports,
  for the `TriggerDefinition`/`Trigger` filter condition builder.

### Endpoint table

| Endpoint | Viewset | Read permission | Write permission |
|---|---|---|---|
| `GET /api/flows/catalog/` | `DslCatalogViewSet` (list only; no write action) | `IsAuthenticated` + `IsGMOrStaff` | n/a |
| `/api/flows/flows/` | `FlowDefinitionViewSet` | `IsGMOrStaff` (list/retrieve) | `IsAdminUser` (create/update/destroy) |
| `/api/flows/trigger-definitions/` | `TriggerDefinitionViewSet` | `IsGMOrStaff` | `IsAdminUser` |
| `/api/flows/triggers/` | `TriggerViewSet` | `IsGMOrStaff` | `IsAdminUser` |
| `PATCH /api/conditions/templates/{id}/set_reactive_triggers/` | `ConditionTemplateViewSet` action | n/a (write-only action) | `IsAuthenticated` + `IsAdminUser` |

`FlowDefinitionViewSet.list` returns lightweight rows (`id`, `name`,
`description`, `step_count` from an annotated `Count("steps")`, not a
per-row query). `.retrieve` returns the full step tree in depth-first
authored order plus an `interactions` block (see below).
`TriggerDefinitionViewSet` filters on `event_name`, searches `name`;
`TriggerViewSet` filters on `trigger_definition`/`obj`, searches
`trigger_definition__name`.

### Permission tiers

Every authoring viewset (catalog included) requires `IsGMOrStaff` just to
read, since the catalog leaks event/service-function vocabulary that is a
mechanics spoiler and is never player-visible. Writes on flows, trigger
definitions, and triggers are `IsAdminUser` (staff-only) in this v1: per the
issue's ratified decision, flow authoring stays staff-only while GM/builder
access is a scoped follow-up (builders will get a narrower surface to build
triggers on their own content and *select* existing flows, never author
flow step trees). `StaffWriteGMReadPermissionMixin` (`views.py`) is the
shared implementation of this split.

### Step-tree write semantics

`FlowDefinitionWriteSerializer.steps` is a write-only nested list
(`FlowStepWriteSerializer`) addressed by an author-chosen `client_id`, not a
DB pk, since the tree may mix brand-new steps with renames of existing ones
in one save. Each entry: `client_id`, `parent_client_id` (nullable),
`action`, `variable_name`, `parameters` (JSON object; a non-dict payload is
rejected before it reaches validation).

- **Full-tree replace.** `_replace_steps` deletes every existing
  `FlowStepDefinition` on the flow, then re-creates the authored tree
  depth-first (parent before children) so the saved rows' pk order matches
  authored order. `FlowDefinitionViewSet.get_queryset` fetches
  `prefetched_steps` with an explicit `.order_by("pk")` for the same reason:
  sibling execution order is queryset order (no order column exists), so it
  must never depend on undocumented table-scan order.
- **`steps` omitted vs. `steps: []`.** On create, omitting `steps` starts an
  empty tree (there is no "existing tree" to preserve). On update, omitting
  `steps` from the payload leaves the current steps untouched; `steps: []`
  (or a populated list) replaces the entire tree.
- **Single root, zero-step drafts.** `step_validation.validate_step_tree`
  returns immediately (valid) for an empty list, so a flow with no steps yet
  is a valid draft. Once there is at least one step, exactly one must have
  `parent_client_id: null` (the runtime enters at the single parentless step;
  a second root would be an unreachable dead row); every other
  `parent_client_id` must reference a `client_id` in the same payload; and no
  parent chain may cycle back on itself.
- **Per-step validation.** `action` must be a known `STEP_ACTION_SPECS` key;
  `variable_name` is required iff the spec's `variable_name_required` is set;
  every `required` param in the spec must be present; every supplied param is
  type-checked against its `ParamSpec.type` (a string starting with `@` is
  exempted from the type check when `accepts_reference` allows it, since the
  runtime resolves it as a flow-variable reference rather than a literal); a
  param outside the declared set is rejected unless the spec sets
  `allows_extra_params`. `step_validation.py` has no DRF import, so it can be
  called directly by non-serializer callers too.

### Interactions block

`FlowDefinitionDetailSerializer.interactions` (`flows.interactions.
flow_interactions`) cross-references what the raw step/trigger rows don't
show on their own: `run_by` (every `TriggerDefinition` with
`flow_definition=this flow`, each with the `ConditionTemplate`s that install
it via `reactive_triggers`), `emits` (event names produced by the flow's
`EMIT_FLOW_EVENT`/`EMIT_FLOW_EVENT_FOR_EACH` steps, each with the
`TriggerDefinition`s listening for that `event_name`), and `calls` (service
function names invoked by the flow's `CALL_SERVICE_FUNCTION` steps).

### Condition wiring

See "Trigger ownership and lifecycle" above for `PATCH
/api/conditions/templates/{id}/set_reactive_triggers/` and
`ConditionTemplateSerializer.reactive_trigger_ids`. The `by_category` and
default list querysets on `ConditionTemplateViewSet` prefetch
`reactive_triggers` so serializing `reactive_trigger_ids` across an unpaginated
template list doesn't N+1.

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
- **Spec:** `docs/architecture/reactive-layer-foundation.md`
- **Roadmap context:** `docs/roadmap/magic.md` (Scope 5.5)
