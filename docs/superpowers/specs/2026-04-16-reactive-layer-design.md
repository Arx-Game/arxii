# Scope 5.5: Reactive Layer (Flows, Triggers, and Typeclass Hooks)

## Purpose

Light up the dormant `flows` app so conditions, items, environments, and
techniques can install reactive effects — the "walking on holy ground burns
you," "the thorn-scar retaliates when struck," "the ward cancels incoming
abyssal fire" gameplay that Arx 1 players expect from magic and curses.

Scope 5 established that mage scars are `ConditionTemplate` rows with
passive effects. Scope 5.5 gives those same conditions a reactive surface:
a `TriggerDefinition` M2M on `ConditionTemplate` plus the dispatcher,
handler cache, and flow-execution plumbing required to actually fire them.

The design is deliberately condition-agnostic. Scars, buffs, debuffs, cursed
items, sanctified ground, and environmental hazards all install the same
kind of `Trigger` row. Reactive behavior is a property of the condition
system, not of magic.

## Key Design Principles

- **Conditions own reactive effects.** `Trigger` rows are sourced from a
  `ConditionInstance` (non-null FK) and optionally narrowed to a
  `ConditionStage` (nullable FK). Removing the condition cascades; advancing
  the stage swaps which rows are active.
- **Commands and service functions emit events, not triggers.** The typeclass
  hooks (`at_pre_move`, `at_attacked`, etc.) and the combat pipeline remain
  authoritative for game logic. The reactive layer listens in via events
  emitted from those hooks.
- **Dual emission by scope.** Events fire at `PERSONAL` scope (delivered to
  the subject's trigger handler) and `ROOM` scope (delivered to the room's
  trigger handler). Authors pick the scope that matches "where does this
  trigger live."
- **Populate once, mutate in place.** Each `TriggerHandler` is a
  `cached_property` on a typeclass. It reads its Trigger rows on first
  access, then is kept in sync via explicit service-function hooks when
  conditions apply/remove or stages change. No repeated queries.
- **In-memory flow execution.** `FlowExecution` is not a model. Flow state
  lives in Python objects. Player prompts suspend via Twisted Deferreds
  held in a module-level dict; timeouts fire default branches.
- **PRE cancellable, POST reactive.** PRE-events can cancel the originating
  action. POST-events cannot — but their trigger flows may do anything
  (deal damage, apply conditions, move objects). Payload is read-only
  on POST.
- **Risk transparency as authoring rule.** Triggers cannot silently increase
  character-loss risk. If a trigger adds a fatal consequence branch, the
  player must have been warned before committing. Enforced through review,
  not code.
- **Minimize new surface area.** Extend existing `flows` models where
  possible (`Trigger`, `TriggerDefinition`, `Event`) rather than inventing
  parallel reactive infrastructure.

## What This Builds

### 1. Event catalog

New `Event` rows for the MVP reactive surface. Each event has a canonical
name, a payload dataclass (authored in `flows/events/payloads.py`), and
scope semantics documented in the catalog.

Events are FKs everywhere — never free-text strings — so typo drift is
impossible.

**Design note — Event-as-model vs Event-as-enum:** If every emit site is a
typed service function (`emit_damage_pre_apply(payload)`), a Python enum
would cover the typo-prevention need. Keeping `Event` as a model adds:
admin visibility (GMs can browse the event catalog and attach
TriggerDefinitions via admin FK dropdowns without a code change) and
conventional FK wiring for `TriggerDefinition.event`. This is mild
over-engineering for MVP — a future refactor to an enum is viable if the
admin surface turns out to be unused. Keeping as-is for Scope 5.5.

MVP events (see Section 7 below for full table):

- Combat: `attack_pre_resolve`, `attack_landed`, `attack_missed`,
  `damage_pre_apply`, `damage_applied`, `character_incapacitated`,
  `character_killed`
- Movement: `move_pre_depart`, `moved`
- Perception: `examine_pre`, `examined`
- Conditions: `condition_pre_apply`, `condition_applied`,
  `condition_stage_changed`, `condition_removed`
- Techniques: `technique_pre_cast`, `technique_cast`, `technique_affected`

### 2. Trigger model extensions

`Trigger` (existing, `flows/models/triggers.py`) gains:

| Field | Type | Description |
|-------|------|-------------|
| `source_condition` | FK(ConditionInstance, CASCADE) | The condition that installed this trigger. Non-null. |
| `source_stage` | FK(ConditionStage, CASCADE, nullable) | If set, trigger is active only while condition is at this stage. |
| `scope` | CharField(choices=PERSONAL/ROOM) | Dispatch scope. |

Cascade rules:
- Condition removed → all its triggers removed.
- Stage advanced → triggers with a matching `source_stage` become active;
  others with a different `source_stage` become inactive (filtered by the
  handler without re-query).

`clean()` validates:
- `source_stage.template == source_condition.template` when `source_stage`
  is set.
- `scope` must be valid for the bound event (some events only emit at one
  scope).

### 3. TriggerHandler

A `cached_property` on typeclasses that own trigger surfaces. Replaces
the existing `flows/trigger_registry.py` — the registry's `cached_property`
pattern on rooms is preserved, but its internals are reworked to handle
the new `source_condition` / `source_stage` / `scope` fields and the
sync-hook protocol below. `trigger_registry.py` does not coexist with
`TriggerHandler`; it is removed.

Owners:

- `Character.trigger_handler` (PERSONAL scope — scars, buffs, carried item
  triggers)
- `Room.trigger_handler` (ROOM scope — wards, aura effects, environmental)
- `Object.trigger_handler` (for items that react even when not held)

Handler responsibilities:

- **First access:** query `Trigger` rows for the owner, grouped by
  `event_id`. Also maintains an active/inactive split keyed on
  `source_stage` vs the condition's current stage.
- **Dispatch:** `handler.dispatch(event, payload) -> DispatchResult` walks
  the active triggers for that event, evaluates filters, executes flows,
  returns cancellation/propagation state.
- **Sync hooks:** `on_trigger_added(trigger)`, `on_trigger_removed(pk)`,
  `on_stage_changed(condition, new_stage)`. Called by service functions
  that apply conditions, remove them, or advance stages. Mutate the
  handler's in-memory structures in place. Never re-query.
- **Invalidation:** handlers do not invalidate. They stay in sync via the
  explicit hooks above. This is the SharedMemoryModel-trusting pattern.

Different typeclasses may have different handler subclasses (e.g., rooms
might do additional filtering for line-of-sight triggers).

### 4. Event emission

Events are emitted in two layers:

**Typeclass hooks** — primary emission point for anything the Evennia
framework already hooks. Our typeclasses gain companion methods where
needed. Example: `Character.at_attacked(attacker, weapon, result)` emits
`attack_landed` at PERSONAL scope for `self` and ROOM scope for
`self.location`.

**Service functions** — for events without a natural typeclass hook (magic
casting, condition application). The service function calls
`emit_event(event_name, payload, personal_target=..., room=...)`.

Combat already owns the attack pipeline in `world/combat/services.py`. The
reactive layer adds hook calls inside combat's existing resolution — it
does not duplicate damage/attack logic. Specifically:

- `resolve_npc_attack` / `_resolve_pc_action` call
  `target.at_attacked(...)` after the damage calculation but before
  applying damage. That hook emits `attack_landed` and
  `damage_pre_apply`.
- `apply_damage_to_participant` emits `damage_applied` after the HP
  mutation, and emits `character_incapacitated` / `character_killed`
  when HP crosses the incapacitation / lethal thresholds.

No service function duplicates combat's arithmetic. The reactive layer
observes and optionally cancels/modifies via the PRE events.

### 5. Event payloads

Payloads are Python dataclasses (see `flows/events/payloads.py`). They
carry model instances, not PKs — the identity map guarantees cheap
attribute walks.

```python
@dataclass
class DamagePreApplyPayload:
    target: Character
    amount: int
    damage_type: str
    source: DamageSource  # discriminated union below

@dataclass
class DamageSource:
    type: Literal["character", "technique", "scar", "environment", "item"]
    ref: Union[Character, Technique, ConditionInstance, Room, ObjectDB]
```

Payloads are not JSON-serializable. Flow steps work on live model
instances throughout execution.

PRE-event payloads are mutable via explicit `modify_payload` flow steps.
POST-event payloads are frozen (`@dataclass(frozen=True)`).

### 6. Filter DSL

`Trigger.additional_filter_condition` is a JSON object evaluated against
the event payload at dispatch time. Grammar:

```json
{
    "and": [
        {"path": "source.technique.affinity", "op": "==", "value": "abyssal"},
        {"path": "damage_type", "op": "in", "value": ["fire", "flame"]},
        {"not": {"path": "target.covenant", "op": "==", "value": "self.covenant"}}
    ]
}
```

Operators: `==`, `!=`, `<`, `<=`, `>`, `>=`, `in`, `contains`, `has_property`.

Paths are dotted traversals against the payload and resolve via attribute
access on model instances. `self` resolves to the handler owner (so a
scar can compare the attacker against its own character).

A validator runs at `Trigger.save()` time, introspecting the bound event's
payload dataclass to catch unknown paths. Runtime evaluator raises
`FilterPathError` on unresolved paths; tests catch misauthored filters.

Future work: a GM-facing UI that builds these JSON objects from a form.
Authors never hand-write JSON in production.

### 7. Flow execution

`FlowExecution` is an in-memory Python object created per dispatch. It:

- Holds a `context` dict (payload fields, intermediate state).
- Walks `FlowDefinition.steps` one at a time.
- On `PromptPlayerStep`, returns a Twisted `Deferred` and stores
  `(account_id, deferred)` in the module-level `_pending_prompts` dict
  in `flows/execution/prompts.py`.
  The Deferred fires when the player responds or times out.
- On `ApplyConditionStep`, `DealDamageStep`, etc., calls the relevant
  service function with payload objects.

No FlowExecution rows are persisted. Flow state is ephemeral.

Flow steps are Python classes (registered via the `package_hooks` pattern)
rather than `getattr`-by-name. Step types are authored, not string-matched.

### 8. FlowStack and nested dispatch

Each dispatch creates or inherits a `FlowStack` tracking:

- `depth`: integer, starts at 1 on top-level emission, increments on nested
  emission.
- `cap`: 8 by default (configurable per `TriggerDefinition`).
- `originating_event`: the event that started the chain.

**Stack topology for AE effects:**

- Each `PERSONAL` scope dispatch from a single emission gets its own
  `FlowStack` (parallel). Alice's scar chain runs on stack A; Bob's on
  stack B.
- The `ROOM` scope dispatch gets one `FlowStack` (shared with the
  originating action's causal chain).
- When a flow spawns a nested action (e.g., a scar calls `deal_damage`),
  the new emission inherits the current stack; depth increments on that
  stack only.
- Independent PERSONAL dispatches from the new emission start fresh stacks
  — UNLESS the spawning flow was itself in a nested context, in which case
  the descendant dispatches inherit the current stack.

This means the recursion cap trips per-character-reaction-chain for AE
effects, not globally across all victims. A fireball hitting 5 people
does not immediately burn 5 levels of depth.

### 9. Cancellation tiers

Cancellation granularity matches event scope:

- **`attack_pre_resolve`** (ROOM) — cancels the entire attack before
  per-target resolution. Wards, counterspells, disarm effects live here.
  If any ROOM trigger cancels, no per-target events fire.
- **`damage_pre_apply`** (PERSONAL) — cancels damage for one target only.
  Personal shields, damage-type immunities.
- **PRE cancellation** sets `cancelled=True` on the result and stops
  propagation within the same scope. Does not cross scope boundaries
  — cancelling at PERSONAL doesn't cancel a ROOM-scope trigger on the
  same event.
- **POST events are not cancellable.** Their trigger flows may still
  retaliate, apply conditions, etc. — they just can't undo the event.

### 10. Safety

- **Recursion cap:** FlowStack.depth capped at 8. Exceeding the cap logs
  a warning (with the stack's event chain) and drops the nested
  dispatch. The originating event completes normally.
- **Per-trigger usage limits:** existing `TriggerData.max_uses_per_scene`,
  `max_uses_per_day`, `max_uses_total` gate dispatch. Usage caps are
  evaluated *before* filters (pre-filter gating).
- **Risk transparency invariant:** triggers cannot introduce character-loss
  risk the player wasn't warned about. Authoring rule, not automated
  check. Enforced via review.
- **Validation at boundaries:** `Trigger.clean()` validates
  condition/stage/scope consistency. `TriggerDefinition.save()` validates
  filter DSL against payload schema. Handler sync hooks assert trigger
  ownership.

### 11. Denormalization trade-offs

The reactive layer sacrifices some normalization for flexibility. What's
intentional:

- `Trigger` rows duplicate per-condition and per-stage. Cascade FKs
  prevent orphans, but the denormalization is the price of stage-scoped
  triggers without a join table.
- Filter DSL is JSONB. Can't FK-enforce filter targets; relies on save-time
  validation and runtime error propagation.
- Payload schemas are Python dataclasses, not DB rows. Type-checked but not
  DB-enforced.

What's preserved:

- `source_condition` FK is non-null with CASCADE — no orphan Triggers.
- `event` is a FK to canonical `Event` rows, not a string.
- `scope` is an enum.
- Usage caps are proper integer columns with validation.

## Integration Points

### Combat
Combat remains authoritative for attack/damage resolution. The reactive
layer adds:
- `Character.at_attacked(attacker, weapon, result)` called from
  combat's existing resolution path (both telnet and web API flow through
  the same service functions).
- `emit_event("damage_pre_apply", ...)` inside `apply_damage_to_participant`
  before the HP mutation.
- `emit_event("damage_applied", ...)` after.

No combat arithmetic moves. The reactive layer observes and optionally
cancels via the PRE events.

### Conditions
Condition service functions (`apply_condition`, `remove_condition`,
`advance_condition_stage`) gain calls to the affected character's
`trigger_handler.on_trigger_*` sync methods, and emit
`condition_applied` / `condition_removed` / `condition_stage_changed`
events.

### Movement
`Character.at_pre_move` and `Character.at_post_move` (existing Evennia
hooks) emit `move_pre_depart` and `moved`. PERSONAL-scope handlers on the
character and ROOM-scope handlers on origin/destination all get a chance
to listen.

### Magic
Technique execution (existing `world/magic/services.py` paths) emits
`technique_pre_cast` and `technique_cast`. Per-target effects emit
`technique_affected`.

### Perception
`examine` command (and its web-API equivalent) emits `examine_pre` /
`examined` with observer + target payload. Mage Sight, Soul Sight, and
similar conditions install triggers here to enrich or replace the
rendered description.

## MVP Event Reference

| Event | Scope | Cancellable | Payload |
|---|---|---|---|
| `attack_pre_resolve` | ROOM | yes | `attacker, target_or_targets, weapon, action` |
| `attack_landed` | PERSONAL(target) + ROOM | no | `attacker, target, weapon, damage_result, action` |
| `attack_missed` | PERSONAL(target) + ROOM | no | `attacker, target, weapon, action` |
| `damage_pre_apply` | PERSONAL(target) | yes | `target, amount, damage_type, source` |
| `damage_applied` | PERSONAL(target) + ROOM | no | `target, amount_dealt, damage_type, source, hp_after` |
| `character_incapacitated` | PERSONAL + ROOM | no | `character, source_event` |
| `character_killed` | PERSONAL + ROOM | no | `character, source_event` |
| `move_pre_depart` | PERSONAL + ROOM(origin) | yes | `character, origin, destination, exit_used` |
| `moved` | PERSONAL + ROOM(both) | no | `character, origin, destination, exit_used` |
| `examine_pre` | PERSONAL(target) | yes | `observer, target` |
| `examined` | PERSONAL(target) | no | `observer, target, result` |
| `condition_pre_apply` | PERSONAL | yes | `target, template, source, stage` |
| `condition_applied` | PERSONAL | no | `target, instance, stage` |
| `condition_stage_changed` | PERSONAL | no | `target, instance, old_stage, new_stage` |
| `condition_removed` | PERSONAL | no | `target, instance_id, template, source` |
| `technique_pre_cast` | PERSONAL(caster) + ROOM | yes | `caster, technique, targets, intensity` |
| `technique_cast` | PERSONAL(caster) + ROOM | no | `caster, technique, targets, intensity, result` |
| `technique_affected` | PERSONAL(target) | no | `caster, technique, target, effect` |

## Integration Test Plan

All tests use FactoryBoy — no fixture data required. Tests live in
`src/flows/tests/test_reactive_integration.py` and
`src/world/magic/tests/test_reactive_scars.py`.

### Factories
- `EventFactory` (extend for new MVP events)
- `TriggerDefinitionFactory`
- `TriggerFactory` — with `scope`, `source_condition`, `source_stage`
- `FlowDefinitionFactory` — with steps that exercise context and service
  functions (`ApplyCondition`, `DealDamage`, `PromptPlayer`,
  `ModifyPayload`)
- `ReactiveConditionFactory` — helper creating a `ConditionTemplate` with
  attached `TriggerDefinition`, applying it to a character, returning the
  `Trigger` row

### Damage-source discrimination
1. **Abyssal-only ward** — filter `source.technique.affinity == "abyssal"`.
   Fires on abyssal fireball; does NOT fire on mundane fireball (same
   damage type) or celestial holy fire.
2. **Not-celestial vulnerability** — filter
   `damage_type == "fire" AND source.technique.affinity != "celestial"`.
   Doubles damage from mundane/abyssal fire; holy fire passes unchanged.
3. **Attacker property required** — filter
   `attacker.has_property("flesh-and-blood")`. Fires on human attackers;
   does NOT fire on constructs or incorporeal attackers.
4. **Weapon-tag filter** — filter `weapon.tags contains "silvered"`.
   Werewolf-bane scar fires only on silvered hits.

### Condition-specific protection
5. **Charm-immunity amulet** — `condition_pre_apply` filter
   `template.category == "mind_control"`. Cancels charm/dominate/fear;
   does NOT cancel buffs or physical conditions.
6. **Curse-resistance by source** — filter
   `template.name == "withering" AND source.type == "scar"`. Protects
   only from scar-sourced withering; item-sourced withering still lands.
7. **Stage-specific vulnerability** — filter
   `source_condition.current_stage.severity >= 3`. Fires only at severe
   stages.

### Cross-character specificity
8. **Bonded-enemy retaliation** — filter `attacker.id in self.bonded_enemies`.
   Fires only against specific bonded foes.
9. **Covenant-allegiance filter** — filter
   `attacker.covenant != self.covenant`. Intra-covenant duels pass
   through; outsider attacks trip the scar.

### Payload-modifier specificity
10. **Elemental conversion** — filter `damage_type == "cold"` →
    `modify_payload(damage_type="fire", amount *= 0.5)`. Cold becomes
    weakened fire; downstream PERSONAL fire-vulnerability scar now fires
    on the converted damage.
11. **Conditional intensity cap** — filter
    `intensity > 5 AND technique.school == "evocation"` → cap intensity.
    Evocations capped; equal-intensity enchantments uncapped.

### AE chaos monkey
12. **Mixed AE with selective immunity** — 5 characters hit by abyssal
    fireball. Alice has abyssal-ward (cancels damage). Bob has generic
    fire-resist (halves). Carol has celestial-only-ward (doesn't fire —
    wrong affinity). Dave is a construct (no retaliation triggers but
    takes damage). Eve is unprotected. Each character's FlowStack is
    independent.
13. **AE retaliation pileup** — AE attack, three victims have retaliation
    scars with different filters (abyssal-only, melee-only, unconditional).
    Only unconditional and abyssal-only fire (AE is abyssal-but-not-melee).
    Attacker takes two parallel retaliation hits on separate stacks.

### Attack-level cancellation tier
14. **Ward cancels whole AE attack** — ROOM-scope trigger on
    `attack_pre_resolve` cancels the attack before per-target resolution.
    Assert no `damage_pre_apply` events fire for any victim.
15. **Personal shield cancels only one target** — PERSONAL-scope trigger
    on `damage_pre_apply` cancels for one target. Other targets in the
    AE still take damage.

### Stage/source cascade edge cases
16. **Stage-scoped trigger loss on advance** — trigger scoped to stage 1.
    Advance to stage 2 → trigger not in handler. Regress to stage 1 →
    trigger back.
17. **Condition removal mid-dispatch** — Alice's scar trigger dispatches,
    flow removes the scar condition. In-flight flow completes; subsequent
    emission of same event finds no trigger.
18. **Multi-source same-event** — Alice has two ReactiveConditions both
    listening on `damage_applied`, one filtered to fire, one to cold.
    Fire attack fires only first; cold fires only second; lightning
    fires neither.

### Examine / perception filters
19. **Mage Sight sees abyssal only** — observer has Mage Sight condition,
    `examine_pre` trigger filtered `target.has_condition("abyssally_tainted")`.
    Reveals tainted; plain target plain description; celestial-blessed
    target unrevealed.
20. **Soul Sight ignores illusions** — filter
    `target.has_property("illusory") == false`. Soul Sight on illusion
    returns normal examine; real target gets enhanced reveal.

### Affinity/resonance/property layering
21. **Affinity-broad vs resonance-narrow** — Alice wards all Abyssal;
    Bob wards only Praedari (an abyssal resonance). Abyssal-but-not-Praedari
    attack: Alice fires, Bob doesn't. Praedari attack: both fire.
22. **Property-tagged technique** — filter
    `source.technique.properties contains "flame"`. Fires on any flame-tagged
    technique regardless of affinity (Celestial solar flame and Abyssal
    hellfire both trip it). Non-flame abyssal attack doesn't.

### Safety + filter interaction
23. **Recursion cap respects filters** — mutual retaliation scars, B's
    scar filters `attacker.hp < 10`. Chain terminates naturally when
    A's HP drops below threshold, before hitting cap. Filters eval
    each iteration, not cached.
24. **Usage cap is pre-filter** — scene-limited trigger checks
    `damage_type`. Fires once on fire, cap exhausted. Cold damage later
    in same scene does NOT fire even though filter would match — usage
    cap gates before filter evaluation.

### Async + filter
25. **Filtered player prompt** — trigger filter
    `caster.account.settings.confirm_expensive_casts == true` → prompt.
    Fires for opted-in players; opted-out players skip the prompt
    entirely.
26. **Prompt timeout** — prompt with timeout, no response. Flow resumes
    with default branch.
27. **Prompt resolution** — player responds. Flow resumes from same step
    with answer in context.

### Combat integration
28. **Typeclass hook dual-path** — telnet `attack` command and web API
    both route through combat's resolution. `attack_landed` fires
    exactly once per target in both cases.
29. **Damage source discrimination** — reactive filter
    `source.type == "scar"` fires only when damage source is a scar,
    not mundane weapon.

## What's NOT in Scope

- **No new reactive-effect authoring UI.** Players/GMs cannot author
  triggers from scratch in Scope 5.5. Staff authors TriggerDefinitions;
  conditions that install reactive effects are authored in Django admin.
  A GM/player-facing builder is future work.
- **No GM override mechanism.** If a trigger fires inappropriately in
  play, GMs resolve narratively; they cannot cancel dispatches from
  inside a scene. Future work.
- **No baseline-human Capability defaults.** Unrelated to reactive layer;
  noted only to reinforce scope.
- **No cooperative resolution details.** Cooperative Actions (from the
  Challenge system) are a separate work stream.
- **No side-effect auto-resolution.** Fire + darkness → light is
  Challenge-system work, not reactive-layer work.
- **No ongoing-harm THREAT mechanics.** Scheduled periodic damage
  (poison ticking, bleeding) is condition-tick work, not reactive-layer
  work.

## Success Criteria

- All 29 integration tests pass without fixture data, using only factories.
- `ConditionInstance` removal cascades all associated `Trigger` rows
  (tested via DB assertion).
- Handler `cached_property` populates once; sync hooks mutate in-memory
  state without re-query (tested via query-count assertion).
- AE attacks produce N parallel FlowStacks (one per PERSONAL target) plus
  one ROOM FlowStack; depth cap applies per-stack.
- Combat arithmetic is NOT duplicated in the reactive layer — all damage
  flows through existing `world/combat/services.py` service functions.
- PRE-event cancellation at ROOM scope prevents per-target PRE events
  from firing.
- Player prompts suspend via in-memory Deferreds; no `FlowExecution` DB
  rows exist.
