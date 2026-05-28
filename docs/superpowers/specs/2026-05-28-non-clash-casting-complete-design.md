# Non-clash casting complete — design

**Bundles:** GitHub issues #547, #541, #542
**Branch:** `feature-547-regular-cast-strain-integration-ui-non-c`
**Goal:** make regular (non-clash) magical casting fully player-driven end-to-end — one unified actions endpoint, proper target picker UI, and Strain commitment with canonical audit.

## Motivation

Today, three deferred seams block "regular casting" outside of clashes:

1. **Strain only works in clashes (#547).** `use_technique` accepts `strain_commitment`, but only `commit_to_clash` passes it. A player can't push harder on a normal cast.
2. **ActionPanel joins two endpoints client-side (#541).** Enhancement data lives on `/api/action-requests/available/`; PlayerAction descriptors live on `/api/actions/characters/<id>/available/`. The client joins by lowercased template name — fragile.
3. **Targeted actions are reachable only by accident (#542).** `ActionPanel` uses `!prerequisite_met` as a proxy for "this action needs a target." The "target picker" today is a tooltip that says "right-click a character." Real picker missing.

Closing these three gaps coherently delivers the cast-to-pose-log-outcome loop for non-combat magic — the project's stated north star.

## Scope

**In:**
- Strain commitment on non-clash casts (intent + audit).
- One unified actions endpoint; old enhancement endpoint deleted.
- `is_targeted` + `target_spec` as data-driven fields on `PlayerAction`.
- New `<TargetPicker />` modal and `<StrainSlider />` component.
- `<ConsentPrompt />` displays strain commitment.
- Test coverage: backend integration (4 paths) + frontend Vitest (4 components).

**Out of scope (filed/documented for follow-ups, not implemented here):**
- Ephemeral consent/declaration storage (separate epic — declarations stay DB-backed in this PR).
- Other cost levers: fury (#567), resonance, etc. The `CommittingDeclaration` mixin makes them easy to add later.
- WebSocket push for consent prompts (#557 is the dedicated issue; this PR stays on polling).
- Combat clash UI changes — strain in clash already works; not touched beyond the mixin extraction.
- Polymorphic models / `GenericForeignKey` — categorical "no" per [[feedback-no-polymorphic-models]].
- Parallel implementations of strain — see [[feedback-no-parallel-implementations]].

## Architecture overview

```
┌──────────────────────────────────────────────────────────────────┐
│  Frontend                                                        │
│                                                                  │
│   ActionPanel.tsx ──► fetch /api/actions/characters/<id>/avail   │
│        │                                                         │
│        ├─ renders enhancements (folded into PlayerAction)        │
│        ├─ renders <StrainSlider /> when strain.cap > 0           │
│        ├─ opens <TargetPicker /> when is_targeted=true           │
│        └─ dispatches via POST /api/action-requests/              │
│                                                                  │
│   ConsentPrompt.tsx ──► polls /api/action-requests/pending/      │
│        └─ displays strain_commitment if > 0                      │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  Backend                                                         │
│                                                                  │
│   get_player_actions(character) ──► PlayerAction[] with          │
│        is_targeted, target_spec, enhancements, strain folded in  │
│                                                                  │
│   create_action_request(strain_commitment=X) ──► SceneActionReq  │
│        with CommittingDeclaration.strain_commitment persisted    │
│                                                                  │
│   resolve_enhanced_action ──► use_technique(strain_commitment=X) │
│        ──► Interaction.strain_committed = X  (canonical audit)   │
│                                                                  │
│   Mirror path (no behavior change):                              │
│   commit_to_clash ──► use_technique(strain_commitment=X)         │
│        ──► Interaction.strain_committed = X  (canonical audit)   │
└──────────────────────────────────────────────────────────────────┘
```

## Data model

### New: `CommittingDeclaration` abstract mixin

Location: `src/world/magic/models/commitments.py`

```python
class CommittingDeclaration(models.Model):
    """Player-declared cost commitments attached to an action declaration.

    Sits on declaration models (clash + scene-action). Scalar levers only;
    list/M2M-shaped commitments (thread pulls) live on their own related model.
    """
    strain_commitment = PositiveIntegerField(
        default=0,
        help_text=(
            "Extra anima the player commits beyond base cost. "
            "Bounded by available anima at resolution time."
        ),
    )
    # Future scalar commitments (fury #567, resonance enhancement, ...) go here.

    class Meta:
        abstract = True
```

### Modified: `ClashContributionDeclaration`

Adds `CommittingDeclaration` to its bases. The existing `strain_commitment` field is removed from the concrete model body (mixin owns it from now on). No data migration needed — column name + type + default are identical. Django's `makemigrations` should produce either a no-op or an `AlterField` with no schema change.

### Modified: `SceneActionRequest`

Adds `CommittingDeclaration` to its bases. Gains `strain_commitment` column via migration.

### Modified: `Interaction`

Gains `strain_committed = PositiveIntegerField(default=0)` — canonical post-resolution audit, populated by **both** clash and non-clash paths. Single queryable column for cross-path queries like "all high-strain casts in scene X this week."

### Modified: `PlayerAction` dataclass

Location: `src/actions/types.py`

**Reused surfaces (no new dataclasses, no new enums for these):**
- `AvailableEnhancement` dataclass already lives at `src/world/scenes/action_availability.py` with fields `enhancement`, `technique`, `effective_cost`, `soulfray_warning`. **Reuse it.** Re-export from `src/actions/types.py` if cross-app import friction comes up.
- `TargetType` StrEnum at `src/actions/types.py:27-33` and `ActionTargetType` TextChoices at `src/actions/constants.py:36-42` already describe target cardinality (`SELF | SINGLE | AREA | FILTERED_GROUP`). **Reuse them for cardinality.**
- `Action` base class at `src/actions/base.py` already has `target_type` as a class field (alongside `get_prerequisites`, `execute`, `check_availability`). **Extend with class fields** — no new method needed.

**New dataclasses (only the genuinely missing surfaces):**

```python
@dataclass(frozen=True)
class TargetFilters:
    in_same_scene: bool = False
    in_same_zone: bool = False
    exclude_self: bool = False
    must_be_conscious: bool = False

@dataclass(frozen=True)
class TargetSpec:
    kind: TargetKind          # NEW TextChoices below — entity type axis
    cardinality: TargetType   # REUSED existing enum — SELF/SINGLE/AREA/FILTERED_GROUP
    filters: TargetFilters

@dataclass(frozen=True)
class StrainAvailability:
    cap: int
    default: int = 0
```

**PlayerAction extensions** (note: `is_targeted` deliberately omitted — `target_spec is None` is the source of truth; `multi` deliberately omitted — `cardinality in {AREA, FILTERED_GROUP}` covers it):

```python
@dataclass(frozen=True)
class PlayerAction:
    # ...existing fields...
    target_spec: TargetSpec | None = None       # None = self-action
    enhancements: tuple[AvailableEnhancement, ...] = ()  # reusing existing dataclass
    strain: StrainAvailability | None = None
```

### New: `TargetKind` TextChoices

Location: `src/actions/constants.py` (sibling to existing `ActionTargetType`)

```python
class TargetKind(TextChoices):
    PERSONA = "persona", "Persona"
    CHARACTER = "character", "Character"
    ITEM = "item", "Item"
    ROOM = "room", "Room"
```

This is orthogonal to `ActionTargetType` (cardinality). Kind = *what type of entity*; cardinality = *how many / how selected*.

### Migrations

One migration per affected app:
- `magic` — no migration (abstract models don't create tables; the mixin lives in a regular module).
- `combat` — `ClashContributionDeclaration` mixin extraction. Django's `makemigrations` is expected to produce nothing (the column already exists with identical name/type/default; abstract base inheritance is a Python-side concern). If `makemigrations` does emit an AlterField, verify it's schema-identical and squash before commit.
- `scenes` — `SceneActionRequest` AddField `strain_commitment`; `Interaction` AddField `strain_committed`.

All numbered chronologically; only AddField operations. No data migrations.

## API contract

### Unified actions endpoint (folds in enhancement data)

`GET /api/actions/characters/<id>/available/`

```json
{
  "actions": [
    {
      "backend": "challenge",
      "display_name": "Intimidate",
      "description": "Use force of presence to coerce.",
      "difficulty": "moderate",
      "check_type": {"id": 12, "name": "Social"},
      "action_template": {"id": 7, "name": "Intimidate"},
      "ref": {"backend": "challenge", "challenge_instance_id": 42},

      "prerequisite_met": true,
      "prerequisite_reasons": [],

      "target_spec": {
        "kind": "persona",
        "cardinality": "single",
        "filters": {
          "in_same_scene": true,
          "in_same_zone": false,
          "exclude_self": true,
          "must_be_conscious": true
        }
      },

      "enhancements": [
        {
          "technique_id": 42,
          "technique_name": "Aura of Terror",
          "variant_name": "Eldritch Variant",
          "effective_cost": 8,
          "soulfray_warning": {
            "stage_name": "Whispers",
            "stage_description": "...",
            "has_death_risk": false
          }
        }
      ],

      "strain": {"cap": 14, "default": 0}
    }
  ]
}
```

`strain` is `null` when the action doesn't support strain (non-magical registry actions). Always present as a key, never omitted.

### Dispatch endpoint (extended)

`POST /api/action-requests/`

```json
{
  "action_key": "intimidate",
  "technique_id": 42,
  "target_persona_id": 17,
  "target_persona_ids": [17, 18],
  "strain_commitment": 3,
  "difficulty_choice": "STANDARD"
}
```

- `target_persona_id` required when `target_spec.kind == "persona"` and `cardinality == "single"`.
- `target_persona_ids` required when `target_spec.cardinality in ("area", "filtered_group")`.
- `strain_commitment` optional, default 0; serializer validates `0 ≤ strain_commitment ≤ initiator.anima.current`.
- Validation errors raise `serializers.ValidationError` with `user_message` per the typed-exception pattern.

### Deletions

The following are deleted in this PR (no deprecation window — repo policy is no-backwards-compatibility in dev):

- `SceneActionRequestViewSet.available` action method
- URL route `/api/action-requests/available/`
- `AvailableSceneActionSerializer`
- `get_available_scene_actions` service function
- Frontend `useAvailableSceneActions` hook + `fetchAvailableSceneActions`

### Consent prompt response shape (extended)

The existing `SceneActionRequestSerializer` (used by `ConsentPrompt`) gains a `strain_commitment` field, exposing the initiator's commitment to the target before they accept/deny.

## Service layer

### `use_technique` — no signature change

Already accepts `strain_commitment: int = 0`. No changes; both paths call it.

### `create_action_request` — extended

Location: `src/world/scenes/action_services.py`

```python
def create_action_request(
    *,
    scene: Scene,
    initiator_persona: Persona,
    target_persona: Persona | None,
    action_template: ActionTemplate | None,
    action_key: str,
    technique: Technique | None = None,
    strain_commitment: int = 0,           # NEW
    difficulty_choice: DifficultyChoice = DifficultyChoice.STANDARD,
) -> SceneActionRequest:
    # ... existing validation ...
    # NEW: 0 <= strain_commitment <= initiator's available anima
    # Creates SceneActionRequest with strain_commitment persisted via mixin
```

### `_resolve_enhanced_action` — passes strain through

Reads `request.strain_commitment`, passes to `use_technique`, then writes the value to the result `Interaction` via `_create_result_interaction(..., strain_committed=...)`.

### `_create_result_interaction` — gains kwarg

```python
def _create_result_interaction(
    *,
    ...,
    strain_committed: int = 0,  # NEW
) -> Interaction:
    return Interaction.objects.create(
        ...,
        strain_committed=strain_committed,
    )
```

### `commit_to_clash` — one new arg on Interaction creation

Already reads `declaration.strain_commitment` and passes to `use_technique`. Add: when creating the result Interaction, pass `strain_committed=declaration.strain_commitment`.

### `create_action_interaction` — gains kwarg

Location: `src/world/combat/interaction_services.py`. Same pattern as `_create_result_interaction`.

### `Action` subclass extensions — class fields, not methods

Existing pattern: `Action` base class at `src/actions/base.py` already has `target_type` as a class field. Mirror that — add `target_kind` and `target_filters` as class fields on action subclasses that target other entities. No new method introduced.

```python
class IntimidateAction(Action):
    target_type = TargetType.SINGLE         # existing class field, reused
    target_kind = TargetKind.PERSONA        # NEW class field
    target_filters = TargetFilters(         # NEW class field
        in_same_scene=True,
        exclude_self=True,
        must_be_conscious=True,
    )
```

Self-actions leave `target_kind` and `target_filters` at their defaults (`None`). `get_player_actions(character)` reads the three class fields; if `target_type == SELF` (or `target_kind is None`), the descriptor's `target_spec` is `None`. Otherwise it assembles `TargetSpec(kind=target_kind, cardinality=target_type, filters=target_filters)`.

### Performance budget

`get_player_actions(character)` should fire ≤ 5 queries total:
- PlayerAction sources (Challenge/Combat/Registry)
- Character techniques + enhancements (one prefetch)
- Anima value
- Scene members (for target_spec resolution)
- Prerequisite checks

Asserted via `CaptureQueriesContext` in the unified endpoint test.

## UI

### `ActionPanel.tsx` — refactored

- Drop `useAvailableSceneActions` hook and the lowercased-template-name join.
- Read `enhancements`, `target_spec`, `strain` directly off each PlayerAction.
- Action row layout:
  - Label + description
  - Expand button → enhancements list (sourced from unified payload)
  - If `strain.cap > 0`, inline `<StrainSlider />` in the dispatch flow
  - Dispatch button enabled when `prerequisite_met === true`. Targeted-check is driven by `target_spec !== null` (no separate `is_targeted` field).

### `<TargetPicker />` — new component

Location: `frontend/src/scenes/components/TargetPicker.tsx`

**Reused primitives:** `<Popover>` from `frontend/src/components/ui/popover.tsx`; `<Dialog>` from `frontend/src/components/ui/dialog.tsx` for small-screen fallback. No new modal/popover infra.

- Popover anchored to action button (Dialog fallback on small screens).
- Reads scene members from existing React Query cache (`useScene(sceneId)`).
- Filters by `target_spec.kind` + `target_spec.filters` client-side.
- For `kind="persona"`: lists scene-present personas with avatar + display name.
- Keyboard nav: arrow keys + Enter. Search-on-typing if >10 candidates.
- Single-select (`cardinality === "single"`): click → `dispatchAction(playerAction, { target_persona_id })` and closes.
- Multi-select (`cardinality in ("area", "filtered_group")`): checkboxes + "Confirm" button → `dispatchAction(playerAction, { target_persona_ids })`.
- Right-click character shortcut (existing `PersonaContextMenu`) stays as a fast path; the popover is the primary discoverable UI.

### `<StrainSlider />` — new component

Location: `frontend/src/scenes/components/StrainSlider.tsx`

**Reused primitives:** `<Slider>` from `frontend/src/components/ui/slider.tsx`; `<SoulfrayWarning>` from `frontend/src/scenes/components/SoulfrayWarning.tsx`. No new range-input or warning UI.

- Range slider `0…strain.cap` ("Strain (extra anima)").
- Live readout: `Effective cost: X anima` (recomputed via shared utility — see below).
- If projected cost > current anima → render `<SoulfrayWarning>` inline with the projected severity.
- Default 0; persists per-action across Action Panel session; resets on dispatch.

### Effective-cost utility — new hook/util

Location: `frontend/src/scenes/lib/computeEffectiveCost.ts`

Today, `ActionPanel.tsx` line 108 statically renders `enh.effective_cost`. The strain slider needs dynamic recomputation as the user moves the slider. The backend formula (from `use_technique`) is:

```ts
function computeEffectiveCost(baseEffectiveCost: number, strain: number): number {
  return baseEffectiveCost + Math.max(strain, 0);
}
```

(Backend's full formula already accounts for `control - intensity` adjustments; the API returns `effective_cost` post-adjustment, so the frontend only needs to add strain.)

### `<ConsentPrompt />` — extended (not rewritten)

Existing component at `frontend/src/scenes/components/ConsentPrompt.tsx`. **Reuse as-is**, with one conditional line added after the action/technique display:

```tsx
{req.strain_commitment > 0 && (
  <span className="text-xs text-muted-foreground">
    {req.initiator_persona.name} is committing {req.strain_commitment} strain.
  </span>
)}
```

No structural refactor.

## Testing strategy

### Backend integration tests

1. **Strain-pushed non-clash cast → Soulfray accrual** (`src/world/magic/tests/test_non_clash_strain.py`)
   - Factory chain: Character(anima.current=10), CharacterTechnique(Flame Lance), SceneActionRequest(strain_commitment=8).
   - Resolve via `_resolve_enhanced_action`.
   - Assert: `Interaction.strain_committed == 8`, `SceneActionRequest.strain_commitment == 8` (intent), `Character.anima.current` decremented, `ConditionInstance(name=SOULFRAY)` advanced.
   - Doubles as factory-as-seed-data ([[factories-as-seed-data]]).

2. **Strain exceeds available anima → 400 ValidationError** — dispatch rejects `strain_commitment=20` when `anima.current=5`.

3. **Unified endpoint contract** (`src/actions/tests/test_unified_player_actions.py`)
   - GET `/api/actions/characters/<id>/available/` returns `target_spec`, `enhancements`, `strain` on appropriate rows; `target_spec is null` for self-actions.
   - GET `/api/action-requests/available/` returns 404 (deleted route).
   - Performance: ≤ 5 queries via `CaptureQueriesContext`.

4. **End-to-end targeted action flow** (`src/world/scenes/tests/test_targeted_action_e2e.py`)
   - Initiator dispatches with `target_persona_id` + `strain_commitment=3`.
   - Target GETs pending requests, sees strain value in serialized response.
   - Target responds with `decision=accept, difficulty=standard`.
   - Assert: SceneActionRequest.status=RESOLVED, Interaction with `strain_committed=3`, Character.anima decremented.

5. **Clash strain still works post-mixin-extraction** — existing clash strain tests must continue to pass unchanged. Add explicit case: ClashContributionDeclaration with `strain_commitment=5` resolves to Interaction.strain_committed=5.

### Frontend Vitest tests

Location: `frontend/src/scenes/components/__tests__/`

6. **ActionPanel** — renders enhancements + strain slider from unified endpoint; doesn't call deleted endpoint; targeted action opens TargetPicker.
7. **TargetPicker** — filters by `target_spec`; multi-select; keyboard nav; calls dispatch with `target_persona_id`.
8. **StrainSlider** — slider updates effective-cost readout; Soulfray badge appears when projected cost > current anima.
9. **ConsentPrompt** — displays strain when `request.strain_commitment > 0`; renders without strain when 0.

### Tagging and tiers

None of these tests are PG-specific. They run on both the SQLite inner-loop tier (`just test-fast`) and PG parity tier (`just test-parity`). No `@tag("postgres")` decorators expected.

### Pre-push regression

Per [[feedback-run-full-suites-pre-push]], before opening the PR: `pnpm test --run` and `just regression` (no-keepdb, fresh DB) both pass locally.

## Anti-reinvention pass (per CLAUDE.md)

Scan executed 2026-05-28 against the codebase. Outcome:

**Reused (no new code):**
- `<Slider>` — `frontend/src/components/ui/slider.tsx`
- `<Popover>`, `<Dialog>` — `frontend/src/components/ui/`
- `<SoulfrayWarning>` — `frontend/src/scenes/components/SoulfrayWarning.tsx`
- `<ConsentPrompt>` — `frontend/src/scenes/components/ConsentPrompt.tsx` (one conditional line added, no refactor)
- `AvailableEnhancement` dataclass — `src/world/scenes/action_availability.py`
- `TargetType` StrEnum — `src/actions/types.py:27-33`
- `ActionTargetType` TextChoices — `src/actions/constants.py:36-42`
- `available_strain` pattern from `CombatParticipant` — `src/world/combat/models.py:569-583`
- `Action.target_type` class field pattern — `src/actions/base.py`
- `use_technique` signature — `src/world/magic/services/techniques.py:241` (already accepts `strain_commitment`)
- `PersonaContextMenu` right-click flow — stays as fast-path shortcut

**Built new (legitimately missing):**
- `CommittingDeclaration` abstract mixin — no shared base class exists for declaration models
- `TargetKind` TextChoices — orthogonal axis to existing `ActionTargetType`; no entity-type enum exists
- `<TargetPicker>` component — no popover-based target picker exists today (`PersonaContextMenu` is context-menu only)
- `<StrainSlider>` component — composes `<Slider>` + `<SoulfrayWarning>`; no equivalent composite exists
- `computeEffectiveCost` utility — no shared util for dynamic cost recomputation client-side
- `Interaction.strain_committed` field — no canonical audit column today (clash uses `anima_committed` for total spent, not strain isolated)
- `SceneActionRequest.strain_commitment` field — inherited via the new mixin
- `Action.target_kind` + `Action.target_filters` class fields — pattern mirrors existing `target_type`; declared on action subclasses

**Surfaces removed in this PR (reuse-by-deletion):**
- `SceneActionRequestViewSet.available` method
- `AvailableSceneActionSerializer`
- `get_available_scene_actions` service function
- `useAvailableSceneActions` frontend hook + `fetchAvailableSceneActions`

## Risk and rollback

- **Risk:** removing `/api/action-requests/available/` is irreversible in a single PR. Mitigated by repo policy (no backwards compat in dev) and by the fact that only `ActionPanel.tsx` and its tests consume the endpoint (verified during exploration).
- **Risk:** mixin extraction on `ClashContributionDeclaration` could cause Django migration churn. Mitigated by the column being identical; a no-op `AlterField` is expected.
- **Rollback:** standard git revert. No data destruction; only ADD operations on the schema.

## Open follow-ups (file as separate issues post-PR)

- Ephemeral consent/declaration storage (architectural follow-up; user is interested in revisiting).
- `fury_commitment` field on `CommittingDeclaration` when #567 ships.
- Resonance commitment field on `CommittingDeclaration` once resonance-paid enhancements have a UI.

## References

- Issue #547, #541, #542
- `docs/roadmap/magic.md` (Scope #4 deferred items)
- `docs/roadmap/combat.md` (Phase 7 'Known deferred seams')
- `src/world/magic/services/techniques.py` (`use_technique` signature)
- `src/world/scenes/action_services.py` (`create_action_request`, `_resolve_enhanced_action`)
- `src/world/combat/clash.py` (`commit_to_clash`)
- Memory: [[feedback-no-polymorphic-models]], [[feedback-no-parallel-implementations]], [[feedback-abstract-base-classes-for-dry]]
