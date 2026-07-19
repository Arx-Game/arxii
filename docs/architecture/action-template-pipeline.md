# Consequence Pools & Action Templates

**Date:** 2026-03-21
**Phase:** 5.5 of capabilities-and-challenges roadmap
**Status:** Design approved, pending implementation

## Problem

The generic consequence pipeline (`select_consequence` + `apply_resolution`) works but
consequence pools are only authorable via `ChallengeTemplateConsequence` and
`ApproachConsequence` — tightly coupled to challenges. Magic in social scenes, technique
mishaps, environmental hazards, and combat consequences all need authored consequence
pools with no challenge involved.

Additionally, the concept of "a character does something that requires a check and has
consequences" is split across three systems with no unifying abstraction:
- **Actions app** — code-defined behavioral units (look, say, move)
- **ChallengeApproach** — data-authored check specs tied to challenges
- **Consequence pipeline** — generic but with no standard attachment point

Most interesting gameplay actions (spells, combat techniques, rituals) will be
data-authored, not code-defined. These need a shared resolution specification.

## Design Decisions

Decisions reached through collaborative design session:

1. **Freestanding ConsequencePool container model** — pools are reused across multiple
   sources (many techniques share a "wild magic surge" base pool). Container model
   pays for itself.

2. **Single-depth inheritance** — a pool has at most one parent. Child pools add,
   exclude, or override weights from the parent. No grandparent chains.

3. **ActionTemplate as resolution specification** — lives in the actions app. Defines
   "what happens when you do this" (check type + consequence pool). ChallengeApproach
   and Technique FK to it.

4. **App responsibility split:**
   - **Actions** — "what happens when you do it" (ActionTemplate, resolution, pools).
     ConsequencePool lives here (not in checks) because pools are about action
     resolution composition; individual Consequences live in checks because they're
     about check outcomes.
   - **Mechanics** — "when is it available and in what context" (availability, eligibility, context pools)
   - **Checks** — "how rolls work" (check resolution, Consequence/ConsequenceEffect records)

5. **Pipeline patterns, not arbitrary sequences** — action resolution follows one of
   a small set of code-defined patterns (SINGLE, GATED). Data is injected into the
   pattern via ActionTemplate and ActionTemplateGate. Not flows.

6. **Independent action and context pools** — an action's pool and the environmental
   context pool resolve independently using the same check result (one roll, two
   consequence selections).

7. **Reactive processing is receiver-side** — the actor's action resolves its own
   pipeline. If effects target another character, that character's reactive checks
   are a separate concern (future design).

8. **State machine for pause points** — resolution produces intermediate state that
   supports pre-check confirmation and post-selection intervention (reroll). Reroll
   resource mechanics are future work; the architecture accommodates them. The state
   machine is in-memory during a single request/response cycle; pause points are
   communicated to the frontend via response data, and the frontend sends a follow-up
   request with the player's decision. State between requests is stored as PKs and
   enum values (not live model instances) so it can be cached or sessioned.

## New Models

### Actions App

New models live in the `actions/models/` package (following the existing pattern —
the app uses a package, not a single `models.py`).

#### ConsequencePool

Named, reusable collection of consequences with optional single-depth inheritance.

| Field | Type | Description |
|-------|------|-------------|
| `name` | CharField(100), unique | Human-readable name ("Wild Magic Surge") |
| `description` | TextField, blank | GM authoring context |
| `parent` | FK(self), nullable | Inherit consequences from this pool |

SharedMemoryModel. Lookup table authored by GMs, read frequently.

**Validation (`clean()`):**
- `parent.parent` must be null — single depth only.
- `parent` must not be self.

#### ConsequencePoolEntry

Links a Consequence to a Pool with optional overrides. For child pools, entries can
exclude or re-weight inherited consequences.

| Field | Type | Description |
|-------|------|-------------|
| `pool` | FK(ConsequencePool), CASCADE | The pool this entry belongs to |
| `consequence` | FK(Consequence), CASCADE | The consequence record (checks app) |
| `weight_override` | PositiveIntegerField, nullable | Overrides Consequence.weight for this pool |
| `is_excluded` | BooleanField, default False | Suppresses this consequence when inherited |

SharedMemoryModel. Unique constraint: `(pool, consequence)`.

**Semantics:**
- On a **parent pool**: `is_excluded` must be False (enforced in `clean()`). An entry
  on a parent pool with `is_excluded=True` is a validation error — exclusion only makes
  sense for child pools suppressing inherited consequences. `weight_override` sets a
  pool-specific weight differing from the Consequence's default.
- On a **child pool**: an entry for a consequence that exists in the parent either
  overrides its weight (`weight_override` set) or excludes it (`is_excluded=True`).
  An entry for a consequence NOT in the parent adds it to the effective pool.

#### ActionTemplate

Data-driven resolution specification. The counterpart to code-defined Actions for
authored content (techniques, challenge approaches, combat abilities).

| Field | Type | Description |
|-------|------|-------------|
| `name` | CharField(100), unique | Human-readable ("Fire Bolt", "Pick Lock") |
| `description` | TextField, blank | Narrative description |
| `check_type` | FK(CheckType), PROTECT | What kind of check for the main step |
| `consequence_pool` | FK(ConsequencePool), PROTECT | Main step consequence pool |
| `pipeline` | CharField, choices=Pipeline | Resolution pattern (SINGLE, GATED) |
| `target_type` | CharField, choices=ActionTargetType | self, single, area, filtered_group |
| `icon` | CharField(50), blank | Frontend icon identifier |
| `category` | CharField(50) | Grouping ("magic", "combat", "exploration") |

SharedMemoryModel. These are authored content — a moderate number of templates
reused across many techniques and approaches.

**Pipeline choices** (`Pipeline` TextChoices in `actions/constants.py`):
- `SINGLE` — one check, one pool. No gates.
- `GATED` — one or more gates must pass before the main step. Each gate can abort.

**Validation (`clean()`):** If `pipeline=SINGLE`, no ActionTemplateGate rows may exist.
If `pipeline=GATED`, at least one gate must exist. (Checked at save time; admin inlines
handle the UX for creating gates alongside the template.)

**target_type note:** The existing `TargetType` StrEnum in `actions/types.py` defines
the values (SELF, SINGLE, AREA, FILTERED_GROUP). For the model field, create a parallel
`ActionTargetType` TextChoices in `actions/constants.py` with the same values. The
StrEnum remains for code-defined Actions; the TextChoices is for the database field.

**Technique relationship:** Technique (magic app) is per-character — many character-
specific Technique records can FK to the same ActionTemplate. A Technique named "Fire
Bolt" on Character A and Character B are separate records both pointing to
ActionTemplate("Fire Bolt"). This is intentional.

#### ActionTemplateGate

Optional extra check steps that gate or supplement the main ActionTemplate resolution.
Most ActionTemplates have zero gates (SINGLE pipeline). GATED templates have one or
more gates that run before (or after) the main step.

| Field | Type | Description |
|-------|------|-------------|
| `action_template` | FK(ActionTemplate), CASCADE | Parent template |
| `gate_role` | CharField, choices=GateRole | Semantic role (ACTIVATION, etc.) |
| `step_order` | PositiveIntegerField | Execution order (lower = earlier) |
| `check_type` | FK(CheckType), PROTECT | Check for this gate |
| `consequence_pool` | FK(ConsequencePool), nullable, PROTECT | Gate-specific consequences |
| `failure_aborts` | BooleanField, default True | Does failing this gate stop the pipeline? |

SharedMemoryModel. Unique constraint: `(action_template, gate_role)`.

**GateRole choices** (`GateRole` TextChoices in `actions/constants.py`, initial):
- `ACTIVATION` — can you gather/channel/initiate? (pre-main)
- Future roles added as needed without schema changes.

**step_order** determines execution sequence. Gates with `step_order` < 0 run before
the main step; gates with `step_order` > 0 run after. Convention, not enforced — the
pipeline runner just sorts by `step_order`.

**Null consequence_pool:** If a gate has no consequence pool, it acts as a pure go/no-go
check. On failure with `failure_aborts=True`, the pipeline stops with no consequence
(just an abort). On success, the pipeline advances. On failure with `failure_aborts=False`,
the pipeline continues (the gate was advisory).

**Gate failure with consequence_pool set:** The gate's consequence resolves (effects
apply) and THEN the pipeline aborts if `failure_aborts=True`. The consequence fires
before the abort — e.g., a failed activation gate applies backlash damage, then the
spell fizzles.

### Mechanics App

#### ContextConsequencePool

Links a ConsequencePool to a Property for environmental/contextual consequences.
When an action resolves in a location with matching Properties, these pools resolve
independently alongside the action's own pool.

| Field | Type | Description |
|-------|------|-------------|
| `property` | FK(Property), CASCADE | Environmental property ("crowded", "ley-line") |
| `consequence_pool` | FK(ConsequencePool), PROTECT | The pool to resolve |
| `check_type` | FK(CheckType), nullable, PROTECT | If set, pool can fire reactively (no player action) |
| `description` | TextField, blank | GM-facing note |

SharedMemoryModel. Unique constraint: `(property, consequence_pool)`.

**Two modes:**
- **Rider mode** (`check_type` is null) — fires alongside a player-initiated action.
  Uses the action's check result. "Using magic in a crowded tavern."
- **Reactive mode** (`check_type` is set) — fires without player action. System
  resolves the pool against the character using this check type. "Trap triggers
  when character enters room." Difficulty comes from the source (trap severity,
  poison potency — stored elsewhere, not on this model).

### FK Additions to Existing Models

#### ChallengeApproach (mechanics app)
- Add `action_template` — nullable FK to ActionTemplate. When set, resolution uses the
  template's check_type and pool instead of the approach's own fields. Existing
  `check_type` field and consequence through-models continue working for approaches
  without a template (gradual migration, no breaking changes).

#### Technique (magic app)
- Add `action_template` — nullable FK to ActionTemplate. Defines what happens when
  this technique is used outside a challenge context (social scenes, freeform magic).

## Resolution Pipeline

### get_effective_consequences(pool) → list[WeightedConsequence]

Resolves pool inheritance into a flat list carrying effective weights. Returns
`WeightedConsequence` dataclass (defined in `actions/types.py`):

```python
@dataclass
class WeightedConsequence:
    """A Consequence with its effective weight for a specific pool."""
    consequence: Consequence
    effective_weight: int
```

This is necessary because `select_weighted()` reads `.weight` from objects directly,
and pool entries can override the Consequence's default weight. The resolution function
must produce objects with the correct effective weight attached.

**Algorithm:**

```
1. If pool has no parent: return pool's non-excluded entries with effective weights.
   Empty pool (no entries) → return empty list.
2. Start with parent's entries (excluding any the parent excludes — enforced in
   clean() but defensive here too)
3. For each child entry:
   a. is_excluded=True → remove that consequence from the list
   b. weight_override set → replace weight for that consequence
   c. Otherwise → add as new consequence
4. Return flat list of WeightedConsequence
```

Effective weight priority: child's `weight_override` > parent entry's `weight_override`
> `Consequence.weight` default.

**Empty list handling:** If the effective list is empty (child excluded everything and
added nothing), the pipeline treats this as a no-op for that pool — no consequence
selected, no effects applied. This is an authoring error but not a crash.

### select_consequence_from_result() → PendingResolution

New function in `checks/consequence_resolution.py`. Same as `select_consequence()` but
takes an already-resolved `CheckResult` instead of performing a new check. Used when
multiple pools share one roll (action pool + context pools).

```python
def select_consequence_from_result(
    character: ObjectDB,
    check_result: CheckResult,
    consequences: list[WeightedConsequence],
) -> PendingResolution:
    """Select a consequence using an existing check result.

    Same tier filtering, weighted selection, and character loss filtering
    as select_consequence(), but skips perform_check() — reuses the
    provided result. Used for context pools that share the main action's
    roll.
    """
```

The `character` parameter is needed for `filter_character_loss()`. The function
extracts `outcome` from `check_result`, filters consequences by tier, runs
`select_weighted()` using the effective weights from `WeightedConsequence`, and
applies character loss filtering.

**Reroll semantics:** A reroll re-runs weighted random selection on the same tier
with the same pool — the check result does not change. If the tier has only one
consequence, a reroll produces the same result. This is intentional: the check
determined the outcome tier, the reroll is about which specific consequence within
that tier you get. If the tier has one entry, spending a reroll is wasteful — the
frontend should communicate this before the player commits.

### resolve_action_template() — State Machine

`resolve_action_template()` in the actions app does NOT run to completion in one call.
It produces a `PendingActionResolution` that captures pipeline state, supports pause
points for player confirmation/intervention, and can be resumed.

#### PendingActionResolution

In-memory state object (dataclass). Between requests, stored as serializable data
(PKs + enum values) in cache or session — not live model instances:

```python
@dataclass
class PendingActionResolution:
    """State of an in-progress action template resolution."""

    template_id: int
    character_id: int
    target_difficulty: int
    resolution_context_data: dict  # PKs for re-hydrating ResolutionContext:
                                   # {"challenge_instance_id": int | None,
                                   #  "action_context_key": str | None}

    # Pipeline progress
    current_phase: ResolutionPhase  # enum: GATE_PENDING, GATE_RESOLVED,
                                    #        MAIN_PENDING, MAIN_RESOLVED,
                                    #        CONTEXT_PENDING, COMPLETE
    gate_results: list[StepResult]  # completed gate outcomes
    main_result: StepResult | None  # main step outcome (after selection, before apply)
    context_results: list[StepResult]  # context pool outcomes

    # Pause state
    awaiting_confirmation: bool  # pre-check: "this is dangerous, confirm?"
    awaiting_intervention: bool  # post-selection: "reroll available"
    intervention_options: list[str]  # what the player can do (future: reroll types)

@dataclass
class StepResult:
    """Outcome of a single resolution step."""

    step_label: str
    check_result: CheckResult  # from perform_check
    consequence_id: int | None  # PK of selected Consequence (None for no-op)
    applied_effect_ids: list[int] | None  # PKs of created instances, None until applied
    was_rerolled: bool
```

**ResolutionPhase** (`ResolutionPhase` StrEnum in `actions/constants.py`):
- `GATE_PENDING` — about to run a gate (may need confirmation)
- `GATE_RESOLVED` — gate completed, advancing to next gate or main
- `MAIN_PENDING` — about to run main step
- `MAIN_RESOLVED` — main consequence selected, not yet applied (intervention window)
- `CONTEXT_PENDING` — about to resolve context pools
- `COMPLETE` — all steps done

**Concurrency:** Only one PendingActionResolution may exist per character at a time.
Starting a new resolution while one is pending cancels the previous one. Enforced by
the cache key (keyed on character PK).

#### Pipeline Execution Flow

```
start_action_resolution(character, template, difficulty, context)
  → PendingActionResolution (phase=GATE_PENDING or MAIN_PENDING)

advance_resolution(pending, player_decision=None)
  → PendingActionResolution (next phase, possibly paused)

# Repeat advance_resolution until phase=COMPLETE
```

**Context pool discovery:** During the CONTEXT_PENDING phase, the pipeline queries
`ContextConsequencePool.objects.filter(property__in=location_properties)` where
`location_properties` comes from `ObjectProperty.objects.filter(obj=context.location)`.
If no matching context pools exist, the phase advances to COMPLETE immediately.

**Pause points:**
1. **Pre-gate confirmation** — if the gate's check is dangerous (character loss
   possible in the pool), pause with `awaiting_confirmation=True`. Player confirms
   or aborts.
2. **Post-gate failure** — gate failed with `failure_aborts=True`. Gate's consequence
   (if pool exists) is applied, then pipeline stops. Result includes gate failure
   consequence.
3. **Post-main selection** — main step consequence selected but not applied. If
   intervention mechanics are available (future), pause with
   `awaiting_intervention=True`. Player can reroll or accept.
4. **Post-main, pre-context** — main effects applied. Context pools about to resolve.
   No pause here for MVP (context pools auto-resolve).

**Reroll support (architecture only):**
- When `awaiting_intervention=True`, the player can request a reroll.
- `advance_resolution(pending, decision="reroll")` re-runs weighted random selection
  on the same check result with the same pool. New consequence selected from the
  same outcome tier.
- `was_rerolled=True` set on the StepResult for audit/display.
- Resource cost validation happens in the caller (future Kudos/PlayerTrust system),
  not in the resolution pipeline. The pipeline just accepts "reroll" as a valid decision.
- A reroll rewinds the state machine to the selection step for the current phase
  (gate or main). Effects from the previous selection are NOT applied — only the
  final accepted consequence gets applied.

**Non-challenge difficulty:** When an ActionTemplate is used outside a challenge context
(e.g., a Technique in a social scene), the caller must provide `target_difficulty`.
There is no default — the system requires an explicit difficulty for every resolution.
For GM-driven scenes, the GM sets difficulty. For self-targeted actions (rituals),
the Technique's intensity or a fixed baseline provides it. The specific source of
difficulty is context-dependent and determined by the caller, not the pipeline.

## Integration Map

### App Responsibilities

```
+-----------------------------------------------------------+
| ACTIONS APP - "What happens when you do it"               |
|                                                           |
| ConsequencePool / ConsequencePoolEntry                    |
| ActionTemplate / ActionTemplateGate                       |
| resolve_action_template() - state machine                 |
| get_effective_consequences() - pool inheritance            |
| Action base class - code-defined actions (look, say)      |
| ActionEnhancement - modifications from sources            |
| PendingActionResolution - pipeline state                  |
+--------------+--------------------------------------------+
               | ActionTemplate FK
               | ConsequencePool FK
+--------------v--------------------------------------------+
| MECHANICS APP - "When is it available, in what context"   |
|                                                           |
| Property / Application - eligibility layer                |
| ChallengeTemplate / ChallengeApproach - authored          |
|   problems with approaches (FK to ActionTemplate)         |
| ChallengeInstance - live challenges at locations           |
| ContextConsequencePool - environmental riders             |
| get_available_actions() - what can you do right now?       |
|   TWO sources (#2503): authored ChallengeInstance rows,    |
|   PLUS lazy bare-object synthesis (ObjectProperty matched  |
|   against Application.default_template) — see below        |
| resolve_challenge() - thin wrapper adding bookkeeping     |
| Effect handlers - dispatch ConsequenceEffects              |
+--------------+--------------------------------------------+
               | CheckType FK
               | Consequence / ConsequenceEffect
+--------------v--------------------------------------------+
| CHECKS APP - "How rolls work"                             |
|                                                           |
| CheckType / CheckTypeTrait - what gets rolled             |
| Consequence / ConsequenceEffect - outcome records         |
| perform_check() - roll resolution                         |
| select_consequence() - pick from pool by outcome tier     |
| select_consequence_from_result() - reuse existing roll    |
| apply_resolution() - dispatch effects                     |
+-----------------------------------------------------------+

+-----------------------------------------------------------+
| MAGIC APP - "Techniques and their capabilities"           |
|                                                           |
| Technique - FK to ActionTemplate                          |
| TechniqueCapabilityGrant - feeds availability AND agency  |
|   (one-oracle merge #2504; prereq-null grants only)       |
| Authors content; actions app defines resolution           |
+-----------------------------------------------------------+

+-----------------------------------------------------------+
| FLOWS APP - "Complex multi-step sequences"                |
|                                                           |
| Triggered by ConsequenceEffect (LAUNCH_FLOW)              |
| For elaborate narrative sequences, not basic resolution   |
+-----------------------------------------------------------+

+-----------------------------------------------------------+
| CONDITIONS APP - "Status effects"                         |
|                                                           |
| Applied/removed by ConsequenceEffects                     |
| Grant Properties (expanding eligibility)                  |
| Grant Capabilities (expanding available actions)          |
+-----------------------------------------------------------+
```

### End-to-End Example: Fire Spell in a Crowded Tavern

1. **Mechanics** — `get_available_actions(character, room)` finds a ChallengeInstance
   (locked door). Character has fire_generation capability (from Technique via
   TechniqueCapabilityGrant). ChallengeApproach links Application("Burn Through")
   to an ActionTemplate("Fire Bolt"). Returns AvailableAction.

2. **Player selects the action.** Frontend calls resolution endpoint.

3. **Mechanics** — `resolve_challenge()` validates challenge state, delegates to
   `start_action_resolution()` with the approach's ActionTemplate and challenge
   severity as difficulty.

4. **Actions** — Pipeline is GATED. ActionTemplateGate with role=ACTIVATION runs first:
   - Gate has character_loss consequences in pool -> `awaiting_confirmation=True`
   - Returns PendingActionResolution paused at GATE_PENDING
   - Frontend shows: "Channeling fire at this intensity risks backlash. Confirm?"

5. **Player confirms.** Frontend calls `advance_resolution(pending, decision="confirm")`.

6. **Actions** — Gate check runs. Passes. Pipeline advances to MAIN_PENDING.
   - `select_consequence()` with Fire Bolt's pool (inherits from "Wild Magic Surge",
     adds fire-specific effects). Roll succeeds.
   - `apply_resolution()` fires effects: door gets REMOVE_PROPERTY(locked),
     ADD_PROPERTY(burning).

7. **Actions** — Context pool phase. Room has Property("crowded") ->
   ContextConsequencePool with a "Collateral Damage" pool.
   - `select_consequence_from_result()` using the main step's check result.
   - Consequence: APPLY_CONDITION(panicked) on nearby NPCs.

8. **Mechanics** — Challenge bookkeeping: door challenge deactivated (DESTROY),
   CharacterChallengeRecord created.

9. **Flows** — If any consequence had a LAUNCH_FLOW effect, the flow engine picks
   up the sequence (e.g., "tavern fire spreads" narrative).

This example walks the **authored-instance** path — a GM (or seed content)
placed a `ChallengeInstance` (the locked door) in the room ahead of time. See
below for the second path: a bare object with no authored instance at all.

### Bare-Object Affordances — the Second Availability Source (#2503)

The locked-door example above assumes someone already placed a
`ChallengeInstance` in the room. Most everyday objects never get that
treatment — nobody is going to hand-place a `ChallengeInstance` for every
flammable torch or dark room a GM improvises mid-scene. `get_available_actions`
therefore has a **second source**, `_bare_object_actions`
(`world/mechanics/services.py`), that runs after the authored-instance scan on
every call:

1. **Mechanics** — `_bare_object_actions` reads `ObjectProperty` rows off
   every object at the location (plus the location itself, so a room's own
   properties like "dark" count) and matches them against `Application`s whose
   `default_template` is set (the curated gate from `ADR-0147` — most
   Applications leave this null and never produce a bare-object affordance) and
   whose `capability_id` the character has a source for. A torch carrying
   `ObjectProperty(flammable)` matches `Application("Ignite")` when the
   character has a `generation` capability source. No `ChallengeInstance` row
   exists yet.
2. Any pair already covered by an authored, active `ChallengeInstance` for
   that `(target_object, template)` is skipped — an authored instance always
   wins over lazy synthesis.
3. The synthesized `AvailableAction` carries `challenge_instance_id=None` and
   a resolved `target_object` + `resolved_default_template` instead. When
   `player_interface.py`'s `_avail_to_player_action` sees
   `challenge_instance_id is None`, it builds a `WORLD_INTERACTION` `ActionRef`
   (`application_id` + `target_object_id` — both stable before any instance
   exists) instead of a `CHALLENGE` one.
4. **Player selects the action.** `dispatch_player_action` re-validates the
   `(application_id, target_object_id)` pair against a fresh
   `get_available_actions()` call (never trusts a stale/forged ref), then mints
   the real `ChallengeInstance` via
   `instantiate_challenge(resolved_default_template, location, target_object)`.
5. **Mechanics** — resolves through the *exact same*
   `resolve_challenge()` used by the CHALLENGE backend — zero reimplementation.
   `ResolutionContext.target` is populated from `ChallengeInstance.target_object`
   (previously always `None` on this path), so an `EffectTarget.TARGET`
   consequence lands on the torch, not the character — e.g. Ignite adds `lit`
   to the torch itself.

**The last mile — where does the torch come from?** A GM's improv verb,
`stage prop <template>` (`StagePropAction`, `actions/definitions/gm_props.py`),
materializes a curated `ItemTemplate` directly into the room
(`world.items.services.staging.stage_prop` →
`materialize_item_game_object_in_room`) carrying its template's default
`ObjectProperty` rows (`apply_template_properties`, the same chokepoint every
crafted item passes through at materialization). The very next
`get_available_actions` read at that room picks the staged prop up via the
bare-object scan above with zero extra wiring — see
`docs/architecture/property-capability-action.md`'s "GM stage-prop improv"
note for the full authorization/telnet detail.

### Non-Challenge Example: Technique in a Social Scene

1. Character wants to perform an anima ritual during a social scene.
2. Technique has FK to ActionTemplate("Anima Ritual").
3. Caller provides GM-set or default difficulty.
4. `start_action_resolution(character, template, difficulty, context)` runs.
5. Same pipeline (gates, main step, context pools) — no challenge bookkeeping.
6. Results display inline in scene narrative.

### Reactive Example: Trap

1. Character enters room with Property("trapped").
2. ContextConsequencePool for "trapped" has `check_type` set (reactive mode).
3. System calls `select_consequence(character, pool.check_type, trap_severity, consequences)`.
4. `apply_resolution()` — trap effects fire (damage, condition, etc.).
5. No ActionTemplate involved. No player-initiated action.

## Migration Strategy

### Phase 1: New Models (no breaking changes)
- Add ConsequencePool, ConsequencePoolEntry, ActionTemplate, ActionTemplateGate to actions app
- Add ContextConsequencePool to mechanics app
- Add nullable `action_template` FK to ChallengeApproach and Technique
- Add `select_consequence_from_result()` to checks app
- Add `get_effective_consequences()` to actions app
- Add `WeightedConsequence` dataclass to actions types
- All existing code continues working unchanged

### Phase 2: Resolution Pipeline
- Implement `resolve_action_template()` state machine in actions app
- Implement `PendingActionResolution`, `StepResult`, and pipeline execution
- Add `advance_resolution()` for pause/resume
- Add reroll rewind support (accept "reroll" decision, re-run selection)

### Phase 3: Integration
- Update `resolve_challenge()` to delegate to `resolve_action_template()` when
  approach has an ActionTemplate
- Add context pool resolution (query ContextConsequencePool by location Properties)
- Existing challenge resolution without ActionTemplates continues working

### Phase 4: Admin & Authoring
- Django admin for ConsequencePool with inline ConsequencePoolEntry
- Django admin for ActionTemplate with inline ActionTemplateGate
- Pool inheritance preview (show effective consequences after inheritance)

### Future Work (not in this spec)
- **Intent/result event emission** — the resolution pipeline should emit events at
  key points that triggers can intercept. This is critical infrastructure for wards,
  protective effects, and environmental reactions. See "Event Integration" section
  below for architecture.
- **Reroll resource mechanics** — Kudos/PlayerTrust system determines when rerolls
  are available and what they cost. Pipeline already supports reroll as a decision.
- **Reactive processing** — when effects target another character, receiver-side
  checks and reactions. Separate design.
- **SyntheticAction** — wrapping ActionTemplate into a full Action with `run()`
  lifecycle, prerequisites, and enhancements. Bridges the code-defined and
  data-driven action systems fully.
- **ChallengeApproach migration** — gradually move all approaches to use
  ActionTemplate, eventually making the FK non-nullable and removing the direct
  check_type/consequence through-models from ChallengeApproach.
- **Combat integration** — combat techniques as ActionTemplates with GATED pipelines.

## Event Integration (Deferred — Architecture Notes)

The resolution pipeline must support event emission at defined points so that
triggers, wards, and environmental effects can intercept, prevent, or modify
actions. The Action base class already has `intent_event` and `result_event` fields
and TODO placeholders for this in `Action.run()`. ActionTemplate resolution needs
the same pattern.

**Event points in the pipeline:**

1. **Pre-resolution intent** — "character is about to attempt X." Emitted before any
   checks run. Triggers can prevent the action entirely (a ward that blocks magic,
   a condition that prevents movement, a target-specific protection). If interrupted,
   the pipeline never starts. This maps to the existing `intent_event` on Action.

2. **Post-selection, pre-application** — "check resolved, consequence Y was selected."
   Emitted after `select_consequence()` but before `apply_resolution()`. Triggers
   can modify or replace the selected consequence (a protective amulet downgrades
   a critical hit, a blessing converts a failure). This dovetails with the reroll
   pause point — both happen in the same window.

3. **Post-resolution result** — "action completed with these effects." Emitted after
   all effects are applied. Triggers can react (a fire spell triggers a sprinkler
   system, an attack triggers a counterattack flow). This maps to the existing
   `result_event` on Action.

**Design considerations for implementation:**

- Triggers are data-driven (database records, not code). They watch for specific
  event types on specific targets/locations and fire registered callables or flows.
- The `ActionInterrupted` exception in `actions/types.py` already exists for
  stopping actions mid-flight.
- Event emission must work for both code-defined Actions (`Action.run()`) and
  data-driven ActionTemplates (`resolve_action_template()`). The same trigger
  should fire regardless of which path initiated the action.
- For ActionTemplates, intent events add another pause point: the pipeline pauses
  to check triggers before running the first gate or main step. If a trigger
  interrupts, the PendingActionResolution moves to a BLOCKED phase.

**Use cases this enables:**

- "Powerful ward stops someone from activating magic" — intent event trigger on
  location checks if action category is "magic", blocks if ward is active
- "Target has a protection that stops this type of action" — intent event trigger
  on target checks action template or capability type
- "Blessing modifies consequence on failure" — post-selection trigger replaces
  selected consequence with a milder alternative
- "Environmental reaction to spell effects" — post-resolution trigger on location
  launches a flow when fire effects are applied in a flammable area

This is deferred because the trigger/event system itself needs design (how triggers
are registered, how callables are looked up, what data the event carries). But the
pipeline's pause-point architecture is designed to accommodate it — adding event
checks at pause points is additive, not a restructure.

## Glossary

- **ConsequencePool** — named, reusable collection of Consequences with optional
  single-parent inheritance
- **ConsequencePoolEntry** — a line item in a pool: links a Consequence with optional
  weight override or exclusion flag
- **WeightedConsequence** — dataclass pairing a Consequence with its effective weight
  after pool inheritance resolution; consumed by `select_weighted()`
- **ActionTemplate** — data-driven resolution specification: check type + consequence
  pool + pipeline pattern. The main step's check and pool live on the template itself.
- **ActionTemplateGate** — optional extra check step gating or supplementing an
  ActionTemplate's main resolution. Most templates have zero gates.
- **ContextConsequencePool** — links a ConsequencePool to a Property for environmental
  consequences that fire alongside or independently of player actions
- **PendingActionResolution** — state of an in-progress resolution pipeline, supporting
  pause/resume for player confirmation and intervention
- **Pipeline** — code-defined resolution pattern (SINGLE, GATED) that ActionTemplate
  data is injected into
- **Rider pool** — a ContextConsequencePool that fires alongside a player action
  (uses the action's check result)
- **Reactive pool** — a ContextConsequencePool with its own check_type that fires
  without player action (traps, hazards)
- **Bare-object affordance (#2503)** — an `AvailableAction` synthesized straight
  from an `ObjectProperty` match, with no authored `ChallengeInstance` behind
  it until the player actually acts. See "Bare-Object Affordances" above and
  ADR-0147.
- **World-interaction template (#2503)** — a `ChallengeTemplate` wired onto an
  `Application.default_template`; the authored resolution content (approaches,
  check type, consequence pool) a bare-object affordance mints into a real
  `ChallengeInstance` at dispatch time.
- **WORLD_INTERACTION backend (#2503)** — the `ActionBackend` for bare-object
  affordances, keyed on `(application_id, target_object_id)` instead of a
  `challenge_instance_id`; dispatch mints then resolves through the same
  `resolve_challenge()` the CHALLENGE backend uses.
