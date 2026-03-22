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
   - **Actions** — "what happens when you do it" (ActionTemplate, resolution, pools)
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

8. **State machine for pause points** — resolution produces serializable intermediate
   state that supports pre-check confirmation and post-selection intervention (reroll).
   Reroll resource mechanics are future work; the architecture accommodates them.

## New Models

### Actions App

#### ConsequencePool

Named, reusable collection of consequences with optional single-depth inheritance.

| Field | Type | Description |
|-------|------|-------------|
| `name` | CharField(100), unique | Human-readable name ("Wild Magic Surge") |
| `description` | TextField, blank | GM authoring context |
| `parent` | FK(self), nullable | Inherit consequences from this pool |

SharedMemoryModel. Lookup table authored by GMs, read frequently.

**Constraint:** `parent.parent` must be null (enforced in `clean()`). Single depth only.

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
- On a **parent pool**: `is_excluded` is always False (no-op). `weight_override` sets
  a pool-specific weight differing from the Consequence's default.
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
| `target_type` | CharField, choices=TargetType | self, single, area, filtered_group |
| `icon` | CharField(50), blank | Frontend icon identifier |
| `category` | CharField(50) | Grouping ("magic", "combat", "exploration") |

SharedMemoryModel. These are authored content — a moderate number of templates
reused across many techniques and approaches.

**Pipeline choices:**
- `SINGLE` — one check, one pool. No gates.
- `GATED` — one or more gates must pass before the main step. Each gate can abort.

#### ActionTemplateGate

Optional extra check steps that gate or supplement the main ActionTemplate resolution.
Most ActionTemplates have zero gates (SINGLE pipeline). GATED templates have one or
more gates that run before (or after) the main step.

| Field | Type | Description |
|-------|------|-------------|
| `action_template` | FK(ActionTemplate), CASCADE | Parent template |
| `step_role` | CharField, choices=GateRole | Semantic role (ACTIVATION, etc.) |
| `step_order` | PositiveIntegerField | Execution order (lower = earlier) |
| `check_type` | FK(CheckType), PROTECT | Check for this gate |
| `consequence_pool` | FK(ConsequencePool), nullable, PROTECT | Gate-specific consequences (null = no consequences, just abort) |
| `failure_aborts` | BooleanField, default True | Does failing this gate stop the pipeline? |

SharedMemoryModel. Unique constraint: `(action_template, step_role)`.

**GateRole choices (initial):**
- `ACTIVATION` — can you gather/channel/initiate? (pre-main)
- Future roles added as needed without schema changes.

**step_order** determines execution sequence. Gates with `step_order` < 0 run before
the main step; gates with `step_order` > 0 run after. Convention, not enforced — the
pipeline runner just sorts by `step_order`.

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

### get_effective_consequences(pool) → list[Consequence]

Resolves pool inheritance into a flat consequence list.

```
1. If pool has no parent: return pool's non-excluded entries with effective weights
2. Start with parent's entries (excluding any the parent excludes — shouldn't happen
   but defensive)
3. For each child entry:
   a. is_excluded=True → remove that consequence from the list
   b. weight_override set → replace weight for that consequence
   c. Otherwise → add as new consequence
4. Return flat list
```

Effective weight priority: child's `weight_override` > parent entry's `weight_override`
> Consequence.weight default.

### select_consequence_from_result(check_result, consequences) → PendingResolution

New function in `checks/consequence_resolution.py`. Same as `select_consequence()` but
takes an already-resolved `CheckResult` instead of performing a new check. Used when
multiple pools share one roll (action pool + context pools).

### resolve_action_template() — State Machine

`resolve_action_template()` in the actions app does NOT run to completion in one call.
It produces a `PendingActionResolution` that captures pipeline state, supports pause
points for player confirmation/intervention, and can be resumed.

#### PendingActionResolution

Serializable state object (dataclass, stored in cache or session):

```python
@dataclass
class PendingActionResolution:
    """State of an in-progress action template resolution."""

    template_id: int
    character_id: int
    target_difficulty: int
    resolution_context_data: dict  # serialized ResolutionContext refs

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
    pending_resolution: PendingResolution  # from select_consequence
    applied_effects: list[AppliedEffect] | None  # None until applied
    was_rerolled: bool
```

#### Pipeline Execution Flow

```
start_action_resolution(character, template, difficulty, context)
  → PendingActionResolution (phase=GATE_PENDING or MAIN_PENDING)

advance_resolution(pending, player_decision=None)
  → PendingActionResolution (next phase, possibly paused)

# Repeat advance_resolution until phase=COMPLETE
```

**Pause points:**
1. **Pre-gate confirmation** — if the gate's check is dangerous (character loss
   possible in the pool), pause with `awaiting_confirmation=True`. Player confirms
   or aborts.
2. **Post-gate failure** — gate failed with `failure_aborts=True`. Pipeline stops.
   Result includes gate failure consequence.
3. **Post-main selection** — main step consequence selected but not applied. If
   intervention mechanics are available (future), pause with
   `awaiting_intervention=True`. Player can reroll or accept.
4. **Post-main, pre-context** — main effects applied. Context pools about to resolve.
   No pause here for MVP (context pools auto-resolve).

**Reroll support (architecture only):**
- When `awaiting_intervention=True`, the player can request a reroll.
- `advance_resolution(pending, decision="reroll")` re-runs `select_consequence_from_result()`
  on the same check result with the same pool. New consequence selected.
- `was_rerolled=True` set on the StepResult for audit/display.
- Resource cost validation happens in the caller (future Kudos/PlayerTrust system),
  not in the resolution pipeline. The pipeline just accepts "reroll" as a valid decision.

## Integration Map

### App Responsibilities

```
┌─────────────────────────────────────────────────────────┐
│ ACTIONS APP — "What happens when you do it"             │
│                                                         │
│ ConsequencePool / ConsequencePoolEntry                  │
│ ActionTemplate / ActionTemplateGate                     │
│ resolve_action_template() — state machine               │
│ get_effective_consequences() — pool inheritance          │
│ Action base class — code-defined actions (look, say)    │
│ ActionEnhancement — modifications from sources          │
│ PendingActionResolution — serializable pipeline state   │
└──────────────┬──────────────────────────────────────────┘
               │ ActionTemplate FK
               │ ConsequencePool FK
┌──────────────┴──────────────────────────────────────────┐
│ MECHANICS APP — "When is it available, in what context" │
│                                                         │
│ Property / Application — eligibility layer              │
│ ChallengeTemplate / ChallengeApproach — authored        │
│   problems with approaches (FK to ActionTemplate)       │
│ ChallengeInstance — live challenges at locations         │
│ ContextConsequencePool — environmental riders           │
│ get_available_actions() — what can you do right now?     │
│ resolve_challenge() — thin wrapper adding bookkeeping   │
│ Effect handlers — dispatch ConsequenceEffects            │
└──────────────┬──────────────────────────────────────────┘
               │ CheckType FK
               │ Consequence / ConsequenceEffect
┌──────────────┴──────────────────────────────────────────┐
│ CHECKS APP — "How rolls work"                           │
│                                                         │
│ CheckType / CheckTypeTrait — what gets rolled           │
│ Consequence / ConsequenceEffect — outcome records       │
│ perform_check() — roll resolution                       │
│ select_consequence() — pick from pool by outcome tier   │
│ select_consequence_from_result() — reuse existing roll  │
│ apply_resolution() — dispatch effects                   │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ MAGIC APP — "Techniques and their capabilities"         │
│                                                         │
│ Technique — FK to ActionTemplate                        │
│ TechniqueCapabilityGrant — feeds into availability      │
│ Authors content; actions app defines resolution         │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ FLOWS APP — "Complex multi-step sequences"              │
│                                                         │
│ Triggered by ConsequenceEffect (LAUNCH_FLOW)            │
│ For elaborate narrative sequences, not basic resolution │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ CONDITIONS APP — "Status effects"                       │
│                                                         │
│ Applied/removed by ConsequenceEffects                   │
│ Grant Properties (expanding eligibility)                │
│ Grant Capabilities (expanding available actions)        │
└─────────────────────────────────────────────────────────┘
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
   - Gate has character_loss consequences in pool → `awaiting_confirmation=True`
   - Returns PendingActionResolution paused at GATE_PENDING
   - Frontend shows: "Channeling fire at this intensity risks backlash. Confirm?"

5. **Player confirms.** Frontend calls `advance_resolution(pending, decision="confirm")`.

6. **Actions** — Gate check runs. Passes. Pipeline advances to MAIN_PENDING.
   - `select_consequence()` with Fire Bolt's pool (inherits from "Wild Magic Surge",
     adds fire-specific effects). Roll succeeds.
   - `apply_resolution()` fires effects: door gets REMOVE_PROPERTY(locked),
     ADD_PROPERTY(burning).

7. **Actions** — Context pool phase. Room has Property("crowded") →
   ContextConsequencePool with a "Collateral Damage" pool.
   - `select_consequence_from_result()` using the main step's check result.
   - Consequence: APPLY_CONDITION(panicked) on nearby NPCs.

8. **Mechanics** — Challenge bookkeeping: door challenge deactivated (DESTROY),
   CharacterChallengeRecord created.

9. **Flows** — If any consequence had a LAUNCH_FLOW effect, the flow engine picks
   up the sequence (e.g., "tavern fire spreads" narrative).

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
- All existing code continues working unchanged

### Phase 2: Resolution Pipeline
- Implement `resolve_action_template()` state machine in actions app
- Implement `PendingActionResolution` and pipeline execution
- Add `advance_resolution()` for pause/resume

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

## Glossary

- **ConsequencePool** — named, reusable collection of Consequences with optional
  single-parent inheritance
- **ConsequencePoolEntry** — a line item in a pool: links a Consequence with optional
  weight override or exclusion flag
- **ActionTemplate** — data-driven resolution specification: check type + consequence
  pool + pipeline pattern
- **ActionTemplateGate** — optional extra check step gating or supplementing an
  ActionTemplate's main resolution
- **ContextConsequencePool** — links a ConsequencePool to a Property for environmental
  consequences that fire alongside or independently of player actions
- **PendingActionResolution** — serializable state of an in-progress resolution
  pipeline, supporting pause/resume for player confirmation and intervention
- **Pipeline** — code-defined resolution pattern (SINGLE, GATED) that ActionTemplate
  data is injected into
- **Rider pool** — a ContextConsequencePool that fires alongside a player action
  (uses the action's check result)
- **Reactive pool** — a ContextConsequencePool with its own check_type that fires
  without player action (traps, hazards)
