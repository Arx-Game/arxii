# Scope #4: Scene Magic — Technique-Enhanced Social Actions

## Purpose

Make magic visible and usable in scenes. The technique use pipeline
(Scopes #1–3) is mechanically complete but has no player-facing entry
point. This scope wires technique enhancement into the existing scene
social action system so players can use magic to augment social
interactions — an enchanted flirt, a magically-reinforced intimidation,
a poisonous kiss.

Simultaneously, this upgrades all social actions (mundane and enhanced)
to use the full action resolution pipeline with consequence pools, so
that social actions produce real mechanical effects (conditions,
property changes) rather than bare pass/fail outcomes.

## Key Design Principles

- **Magic enhances actions, it doesn't replace them.** A technique is
  never a standalone action in a social scene — it modifies a base
  social action (flirt, intimidate, etc.). The action is the verb; the
  technique is the adjective.
- **Enhancement is authored, not arbitrary.** An `ActionEnhancement`
  record explicitly pairs a specific technique with a specific base
  action. No record, no option. Content authors decide what's possible.
- **Layered results, not merged.** The social action outcome and the
  technique outcome are displayed as two distinct but simultaneous
  results. Players see what each part contributed.
- **Soulfray is rare in social scenes.** The math naturally makes most
  social-context technique use free or cheap. Soulfray warnings only
  appear for characters already carrying the condition who would incur
  anima cost. Dangerous Soulfray stages are a combat/mission concern,
  not a social scene tax.
- **Mundane actions get teeth too.** The full consequence pipeline
  applies to all social actions, not just enhanced ones. A mundane
  Flirt can apply "Smitten"; a mundane Intimidate can apply "Shaken."
  This makes the enhancement decision meaningful: spend anima for
  better odds and magical effects, or rely on mundane skill.
- **Warning before commitment.** Soulfray warnings appear when the
  player selects a technique enhancement, before the action request is
  sent to the target. The warning is cost-gated: if effective cost is
  0 (control exceeds intensity enough), no warning. The pipeline runs
  straight through once the player has committed.

## What This Builds

### 1. Technique FK Wiring in SceneActionRequest

The `SceneActionRequest.technique` FK exists but is dead code — the
frontend passes `technique_id` but `create_action_request()` never
stores it. Fix:

- Add `technique` parameter to `create_action_request()`
- Validate that an `ActionEnhancement` record exists for the
  technique + action_key combination
- Validate that the character knows the technique
  (`CharacterTechnique` exists)
- Store the technique FK on the created `SceneActionRequest`

No new fields. The existing FK is sufficient.

### 2. Full Pipeline for All Social Actions

Replace the minimal `resolve_scene_action()` call with
`start_action_resolution()` in `respond_to_action_request()`. This
gives all social actions:

- Gate checks (if the `ActionTemplate` has gates)
- Consequence pool selection based on check outcome
- `ConsequenceEffect` application (conditions, property changes, etc.)
- Character loss filtering (always applied)

The six existing social actions (intimidate, persuade, deceive, flirt,
perform, entrance) each have an `ActionTemplate` with `check_type` and
`consequence_pool` FKs. The consequence pools determine what happens
on success/failure — these are authored content, not code concerns.

`resolve_scene_action()` remains available for any future callers that
need the lightweight path but is no longer used by scene actions.

### 3. Technique Enhancement Integration

When a `SceneActionRequest` has a technique attached,
`respond_to_action_request()` calls `use_technique()` with the full
action resolution as its `resolve_fn`:

```
resolution = use_technique(
    character=initiator,
    technique=request.technique,
    resolve_fn=lambda: start_action_resolution(
        character=initiator,
        template=action_template,
        target_difficulty=difficulty,
        context=resolution_context,
    ),
    confirm_soulfray_risk=True,  # already confirmed in frontend
)
```

The technique wraps the action: anima deducted first, then the social
check runs with consequences, then Soulfray accumulates if applicable,
then mishap fires if control deficit exists.

**check_result flow for Steps 7-8:** `use_technique()` currently
accepts `check_result` as an external parameter, but for this
integration the check result is produced *inside* `resolve_fn()` —
it lives at `PendingActionResolution.main_result.check_result`.
`use_technique()` needs a small refactor: after `resolve_fn()` returns,
extract the `CheckResult` from the resolution result and use it for
Soulfray outcome modifiers (Step 7) and mishap resolution (Step 8).
The extraction is type-checked: if `resolution_result` is a
`PendingActionResolution` with a `main_result`, use
`main_result.check_result`. Otherwise fall back to the explicit
`check_result` parameter (for non-scene callers). This keeps the
existing `use_technique()` API compatible while enabling the wrapper
pattern.

**ActionTemplate must be non-null:** `start_action_resolution()`
requires a valid `ActionTemplate` with `check_type` FK.
`create_action_request()` must validate that an `ActionTemplate`
exists for the given `action_key` at creation time, rejecting the
request early if not. This prevents null `action_template` from
reaching the resolution pipeline.

**How the technique modifies the action check:** The technique's
runtime stats (intensity, control) can feed `extra_modifiers` into
`perform_check()` via the `ActionTemplate` resolution. The exact
modifier formula is an authoring decision per `ActionEnhancement` —
some techniques boost the check, others add their own effect layer
without changing the base check.

### 4. Available Actions Endpoint with Enhancement Data

The available-actions endpoint (currently a frontend placeholder
returning empty results) returns per-action enhancement options:

For each base social action available to the character:
1. Query `ActionEnhancement` records where `source_type=TECHNIQUE`
   and `base_action_key` matches
2. Filter to techniques the character knows (`CharacterTechnique`)
3. For each valid enhancement, call `should_apply_enhancement()` for
   runtime eligibility
4. Pre-calculate effective anima cost via
   `calculate_effective_anima_cost()` using the character's current
   anima and technique's runtime stats
5. Check for Soulfray warning via `get_soulfray_warning()` if
   effective cost > 0

Response shape per action:

```python
@dataclass
class AvailableEnhancement:
    enhancement: ActionEnhancement  # carries technique FK, variant_name
    technique: Technique            # the character's known technique
    effective_cost: int             # pre-calculated from runtime stats
    soulfray_warning: SoulfrayWarning | None  # only if cost > 0 and has condition
```

Serialization to `technique_id`, `technique_name`, `variant_name` etc.
is the serializer's responsibility, not the dataclass's. The dataclass
carries model instances per project convention.

**Query optimization:** Runtime stats are calculated once per technique
(not per enhancement), the Soulfray warning is fetched once per request,
and `CharacterTechnique` records are pre-fetched in a single query.
`ActionEnhancement` records are fetched with `select_related("technique")`
to avoid N+1 queries.

**Non-magical characters:** The endpoint checks for `CharacterAnima`
existence early. Characters without an anima record have no technique
enhancements — the enhancement list is empty for all actions. No error,
just no magical options.

The endpoint lives on the existing scene actions API, scoped to the
character's current scene.

### 5. Enhanced Result Type

A new dataclass carries both layers:

```python
@dataclass
class EnhancedSceneActionResult:
    """Combined result of a social action, optionally technique-enhanced."""
    # Action resolution (always present)
    action_resolution: PendingActionResolution
    action_key: str

    # Technique layer (None if unenhanced)
    technique_result: TechniqueUseResult | None
```

This replaces `SceneActionResult` as the return type from
`respond_to_action_request()`. The existing `SceneActionResult` is
retired — it was a thin wrapper that the full pipeline supersedes.

**Consequence targeting:** Social actions are targeted (initiator vs
target). The existing `ResolutionContext` carries the initiator
`character`. For consequence effects that apply to the target (e.g.,
"target gains Smitten"), the target persona's character is passed via
the `action_context` field's `target` attribute, which `ActionContext`
already supports. No changes to `ResolutionContext` needed.

**Transaction boundary:** The entire enhanced resolution — anima
deduction, action check, consequence application, Soulfray
accumulation — runs inside a single `transaction.atomic()` block in
`respond_to_action_request()`. If any step fails, the entire
operation rolls back. This prevents partial state where anima is
deducted but no action resolved.

### 6. Frontend: Enhancement Selection

The `ActionPanel` component gains enhancement selection per action:

- Each action button expands to show available technique enhancements
  (from the available-actions endpoint)
- Each enhancement shows: variant name, anima cost (or "Free"),
  Soulfray warning icon if applicable
- Selecting an enhancement with a Soulfray warning shows a
  confirmation dialog scaled to warning severity
- The action request is submitted with the selected `technique_id`
  (or null for mundane)

Presentation details (dropdown, toggle, cards) will iterate — the API
contract is what matters.

### 7. Frontend: Layered Result Display

The `ActionResult` component renders the `EnhancedSceneActionResult`:

- **Social outcome line:** action name, outcome tier, consequences
  applied (e.g., "Enchanted Flirt: Dazzling Success — target gains
  Smitten")
- **Technique line (if enhanced):** technique name, anima spent, and
  if relevant: Soulfray accumulation, mishap result

Color coding from the social outcome tier (green/red/yellow). The
technique line is secondary/subordinate in the visual hierarchy.

### 8. Soulfray Warning Flow

The warning happens at technique selection time in the frontend, not
mid-pipeline:

1. Player opens action panel, sees enhancement options
2. Available-actions endpoint already includes `soulfray_warning` and
   `effective_cost` per enhancement
3. If `effective_cost > 0` and `soulfray_warning` is present:
   - Mild warning (early stage): subtle caution text, confirm button
   - Severe warning (late stage): red alert, explicit death risk
     disclosure, confirm button
   - Warning severity scales with `SoulfrayWarning.has_death_risk`
     and `stage_name`
4. If `effective_cost == 0`: no warning, technique is free
5. Player confirms → action request submitted with technique attached
6. `use_technique()` runs with `confirm_soulfray_risk=True` — no
   pipeline pause

### 9. Interaction Recording

`_create_result_interaction()` is updated to serialize the
`EnhancedSceneActionResult` into the scene's interaction stream.
The interaction content includes both layers so the scene log reads
as a coherent narrative.

The interaction stores a structured result (the serialized
`EnhancedSceneActionResult`), not a format string. The frontend
`ActionResult` component renders this structured data into the
appropriate display. The raw interaction content serves as a
human-readable fallback for telnet clients.

## What This Does NOT Build

- **Challenge resolution endpoint (Phase 6b)** — room challenges are
  a separate scope
- **Cooperative actions** — single initiator + single target only
- **Post-CG progression** — handled separately
- **Soulfray recovery/decay** — separate system
- **Magical alteration resolution** — MAGICAL_SCARS stub unchanged
- **GM Situation builder** — no authoring UI
- **Standalone technique use** — techniques only fire as action
  enhancements in this scope
- **Reroll/negation mechanics** — consequence intervention is future
- **New social actions** — existing 6 only (intimidate, persuade,
  deceive, flirt, perform, entrance)
- **Authored content** — consequence pools, ActionEnhancements, and
  conditions for social actions are authored data. Integration tests
  use mock versions via factories.

## Integration Test Strategy

Integration tests use FactoryBoy to create mock data:

- **ActionEnhancement factory** — pairs a test technique with a base
  action key
- **ConsequencePool factory** — success/failure pools for social
  actions with condition effects
- **Technique factory** — test technique with known intensity/control/
  cost values

Test paths:

1. **Mundane action with consequences** — Flirt without technique,
   verify consequence pool fires, condition applied
2. **Enhanced action, full pipeline** — Flirt with technique, verify
   anima deducted, social check runs, consequence applied, technique
   result returned
3. **Enhancement validation** — attempt to attach a technique without
   a matching ActionEnhancement record, verify rejection
4. **Free technique, no warning** — technique where control > intensity,
   verify no Soulfray warning, no anima cost
5. **Soulfray warning flow** — character with Soulfray condition and
   costly technique, verify warning data returned in available-actions
6. **Soulfray accumulation on enhanced action** — depleted character
   uses technique, verify Soulfray severity increases
7. **Mishap on enhanced action** — technique with control deficit,
   verify mishap fires alongside social outcome
8. **Available actions endpoint** — verify enhancements filtered by
   character's known techniques and ActionEnhancement records

## Deferred Items

- **Technique modifier formula per ActionEnhancement** — how exactly
  each enhancement modifies the base check (flat bonus? technique
  intensity as extra_modifiers?). Currently deferred to authoring —
  the pipeline passes extra_modifiers through, the value comes from
  content. May need a formula field on ActionEnhancement if authoring
  alone isn't sufficient.
- **ActionEnhancement for non-technique sources** — the model supports
  `distinction` and `condition` source types. This scope only wires
  the technique path. Other sources follow the same pattern.
- **Involuntary enhancements** — `ActionEnhancement.is_involuntary`
  exists for enhancements that activate without player choice (e.g.,
  a curse that corrupts all your social actions). Not wired in this
  scope.
- **Context consequence pools** — environmental effects that fire as
  riders on actions. The pipeline supports them via
  `_run_context_pools()` but this scope doesn't author or surface
  them.
- **Escalating warning UX** — the backend provides warning severity
  data; the exact frontend treatment for dangerous-stage warnings in
  non-combat contexts can iterate.

## Files Involved

### Backend (modify)
- `src/world/scenes/action_services.py` — integrate technique and full pipeline
- `src/world/scenes/action_views.py` — available-actions endpoint, fix implicit first-item persona selection
- `src/world/scenes/action_serializers.py` — enhancement data serialization, add technique_id to create serializer, response serializer for EnhancedSceneActionResult
- `src/actions/services.py` — ensure start_action_resolution works for scene context
- `src/world/magic/services.py` — refactor use_technique to extract check_result from resolve_fn output

### Backend (new types)
- `src/world/scenes/types.py` — EnhancedSceneActionResult, AvailableEnhancement

### Frontend (modify)
- `frontend/src/scenes/actionQueries.ts` — wire available-actions endpoint
- `frontend/src/scenes/actionTypes.ts` — enhancement type definitions
- `frontend/src/scenes/components/ActionPanel.tsx` — enhancement selection UI
- `frontend/src/scenes/components/ActionResult.tsx` — layered result display
- `frontend/src/scenes/components/ConsentPrompt.tsx` — show technique info

### Frontend (new)
- `frontend/src/scenes/components/SoulfrayWarning.tsx` — warning dialog

### Tests (new)
- `src/integration_tests/test_scene_magic_integration.py` — full pipeline tests
