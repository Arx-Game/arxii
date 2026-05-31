# Reactive Layer — Unified Dispatch Redesign

> Supersedes parts of `docs/superpowers/specs/2026-04-16-reactive-layer-design.md`. Applied to branch `design/reactive-layer` before the PR is opened.

## Why

The original spec split dispatch into PERSONAL-scope (delivered to the subject) and ROOM-scope (delivered to the room model itself, for wards/environmental effects). That misses the primary use case we actually want for "room-scope" events: **bystander reactions** — character A reacts when magic is cast in their location, whether or not A is the target.

Installing character-owned triggers on the room and migrating them on movement (the old `TriggerRegistry` pattern, DB-backed) would preserve the current dispatch semantics but re-introduces stale-cache risk. Instead we flatten dispatch: an event is delivered to the room *and every object in it*, and each owner's triggers decide via filter whether to fire.

This is both simpler (no scope field, no migration on movement, no parallel stacks for AE) and covers the missing use case natively.

---

## What Changes

### 1. `Trigger.scope` field — removed

The `scope` column, the `TriggerScope` enum, and all validation around scope are removed. Triggers no longer self-describe as PERSONAL or ROOM. Their filter expresses whatever targeting semantics the author needs.

Common filter idioms replace the old scopes:

```python
# "I react when I'm the target" (old PERSONAL)
{"path": "target", "op": "==", "value": "self"}

# "I react when I'm the attacker" (old PERSONAL for offensive reactions)
{"path": "attacker", "op": "==", "value": "self"}

# "I react whenever any fire damage happens near me" (old ROOM)
{"path": "damage_type", "op": "==", "value": "fire"}

# "I react to attacks targeting anyone with the undead property" (old ROOM with target filter)
{"path": "target", "op": "has_property", "value": "undead"}
```

No scope-based validation. Authors who want "personal" semantics write the `self` filter.

### 2. `emit_event(...)` — unified dispatch

New signature:

```python
def emit_event(
    event_name: str,
    payload: Any,
    location: Any,
    *,
    parent_stack: FlowStack | None = None,
) -> FlowStack:
```

- `location` is the room (or container) the event happens in. Required.
- Dispatches to `[location, *location.contents]`.
- `personal_target` / `room` keyword args are **removed**.
- Callers that previously emitted separately for PERSONAL and ROOM now emit once.

### 3. Dispatch algorithm — priority-sorted global walk

`emit_event` gathers all triggers across all owners for this event, sorts by priority (desc), and walks them synchronously:

```python
def emit_event(event_name, payload, location, *, parent_stack=None):
    stack = parent_stack or FlowStack(owner=location, originating_event=event_name)
    owners = [location, *location.contents]
    triggers = []
    for owner in owners:
        handler = getattr(owner, "trigger_handler", None)
        if handler is None:
            continue
        triggers.extend(handler.triggers_for(event_name))
    triggers.sort(key=lambda t: -t.priority)
    for trigger in triggers:
        if not evaluate_filter(trigger.additional_filter_condition, payload, self_ref=trigger.obj):
            continue
        execute_flow(trigger, payload, stack)
        if stack.was_cancelled():
            break
    return stack
```

Cancellation stops the walk. There's no scope-based preemption — authors express ordering by assigning priorities.

**No more parallel FlowStacks for AE.** A single emission produces a single stack. The AE attack is one event with `targets: list` in its payload; each trigger filters on its own self-relevance.

### 4. `TriggerHandler` — becomes a provider

`TriggerHandler.dispatch(...)` is removed. The handler's responsibility shrinks to:

- Populate once from DB on first access (unchanged).
- Sync hooks on trigger add/remove/stage-change (unchanged).
- `triggers_for(event_name) -> list[Trigger]` — returns active triggers for this owner (unchanged semantics; this is what `emit_event` now consumes).

`DispatchResult` moves to `FlowStack` (or stays as a stack-level concept). The "dispatch loop" becomes the `emit_event` function.

### 5. AE attacks — single emission

Old: attacker calls `emit_event(ATTACK_LANDED, personal_target=t)` once per target, plus one ROOM emit. New: one call with `AttackLandedPayload.targets=[t1, t2, ...]`. Every trigger in the room sees it once. Target-specific triggers filter via `{"path": "targets", "op": "contains", "value": "self"}`. Bystander triggers don't filter on targets at all.

Per-target damage application still emits `damage_pre_apply` / `damage_applied` once per target (those events are inherently per-target), but they too dispatch to the whole room — a character with a "friend hurt" trigger can react to damage done to an ally.

### 6. Payload changes

- `AttackPreResolvePayload.target_or_targets` renamed to `targets: list` (always a list; single-target attacks are a 1-element list). Consistency > ergonomics for this codepath.
- Other payloads unchanged.

### 7. `TriggerRegistry` — deleted

`src/flows/trigger_registry.py` is removed. The `trigger_registry` property on rooms (in `typeclasses/mixins.py`) is removed. `FlowStack` / `FlowExecution` stop accepting a `trigger_registry` parameter.

### 8. `EMIT_FLOW_EVENT` flow action — reroute

The existing `EMIT_FLOW_EVENT` / `EMIT_FLOW_EVENT_FOR_EACH` flow actions are rewritten to call `emit_event()` instead of `trigger_registry.process_event()`. Mid-flow event emission is preserved; its implementation changes. The `FlowEvent` class becomes a lightweight wrapper that converts the legacy event-data dict into the new payload model when the action runs — or, preferred, we remove `FlowEvent` and the flow step takes `(event_name, payload_source_vars)` parameters, building the right payload dataclass from context.

### 9. Non-narrative events don't emit

Login, anima regen, XP awards, OOC state — these do not call `emit_event`. Event emission is reserved for narrative moments that other characters can plausibly react to. The event catalog in §10 of the original spec already matches this (attack / damage / condition / technique / move / examine).

### 10. `source_condition` — still required

Every `Trigger` row still FKs a `ConditionInstance`. Room-owned triggers need a pseudo-condition on the room ("Unruly Crowd", "Ambient Static", "Lit Candle"). Minor authoring wart, but the cascade semantics (condition removed → triggers cascade away) are worth keeping.

---

## What Doesn't Change

- `Event` / `TriggerDefinition` / `Trigger` / `TriggerData` models (minus `scope`).
- Payload dataclass shapes (except `AttackPreResolvePayload`).
- Filter DSL operators and semantics.
- Twisted-Deferred player prompts.
- `source_condition` / `source_stage` fields.
- SharedMemoryModel identity map reliance.
- Recursion cap on `FlowStack` (single stack per emission still has a cap).
- Hooks on typeclass methods (`at_attacked`, `at_pre_move`, `at_examined`); their emit calls just collapse to one.
- Existing Evennia integration patterns.

---

## Success Criteria

1. `Trigger.scope` is gone from the schema and no code references it.
2. `emit_event(name, payload, location)` is the single dispatch entry point.
3. No `TriggerRegistry` in the tree.
4. Bystander triggers work: a test where character A has a trigger that fires when any fire technique is used in A's location, and the trigger fires even when A isn't the target.
5. Target-specific triggers still work: a test where a scar on character B fires on damage-to-B but not damage-to-C in the same room.
6. Priority-ordered dispatch: a test where a room ward priority 9 cancels an attack before a personal shield priority 3 runs.
7. `EMIT_FLOW_EVENT` flow action still works via the new path (existing tests pass, possibly rewritten).
8. AE attack: one emission, everyone gets it, filters distinguish.
9. Full regression (`echo "yes" \| uv run arx test`) without `--keepdb` green.
