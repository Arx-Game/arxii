# Anima Ritual UI Design

**Date:** 2026-05-07
**Status:** Approved (design conversation)
**Related:**
- `src/world/magic/services/anima.py` — existing `perform_anima_ritual()` service
- `src/world/scenes/action_models.py` — existing `SceneActionRequest` substrate
- `src/world/codex/models.py` — pattern reference for knowledge + grant tables
- `docs/superpowers/specs/2026-05-05-soul-tether-ui-design.md` — generic ritual UI established by prior work

---

## Goal

Make the Anima ritual playable in the React frontend as a **social hook** — a mechanism that requires creating fun roleplay content for other players in order for magic to work. Surface it as a contextual scene action where the initiator picks a target PC, the target consents (with full disguise — they don't see "anima" labeling), and a contested check resolves into anima recovery for the initiator and Kudos for the target.

This work also unifies player-authored personal rituals with the existing staff-authored `Ritual` model (introduced in the Soul Tether UI work), and introduces the knowledge layer that gates which characters know which rituals.

## Background

### What exists today

- **`CharacterAnimaRitual`** (`src/world/magic/models/anima.py`) — OneToOne to CharacterSheet. Stores stat/skill/specialization/check_type/resonance/description/target_difficulty. Authored at character creation.
- **`perform_anima_ritual(character_sheet, scene)`** (`src/world/magic/services/anima.py`) — fully implemented service. Rolls a check, calculates a "budget" from the outcome tier, spends it on Soulfray severity first then anima recovery. Once-per-scene-per-character cap.
- **`AnimaRitualPerformance`** — audit row per performance (FK to ritual + scene, outcome, recovery values).
- **`Ritual` model** (`src/world/magic/models/rituals.py`) — staff-authored, dispatched via `POST /api/magic/rituals/perform/` with `input_schema` form. `execution_kind` enum: `SERVICE | FLOW`. The Soul Tether work established this as the generic ritual concept.
- **`SceneActionRequest`** (`src/world/scenes/action_models.py`) — PC-vs-PC contested check with consent flow. Initiator creates → target accepts/denies → check resolves via `perform_check()` → result Interaction recorded. REST API at `/api/action-requests/`. Frontend pieces (`ActionPanel`, `ConsentPrompt`, `ActionResult`) exist.
- **Codex knowledge / grants** (`src/world/codex/models.py`) — `CharacterCodexKnowledge` per RosterEntry, plus `BeginningsCodexGrant`, `PathCodexGrant`, `DistinctionCodexGrant`, `TraditionCodexGrant`. Direct FKs, no polymorphism. **The pattern this design mirrors for ritual knowledge.**
- **`CodexTeachingOffer` / `ThreadWeavingTeachingOffer`** — established teaching-offer pattern. Mirrored later for ritual teaching.
- **Kudos** (`src/world/progression/services/kudos.py`) — `award_kudos(account, amount, source_category, ...)` is a clean atomic call. No anti-abuse machinery to navigate.

### Design intent (from brainstorm with user)

- Anima ritual is **explicitly a social hook**: the player has to create fun content for another player for the magic to work. Not a personal/solo magic act.
- The activity is a **contested check between two PCs** with target consent (similar to other social checks). Examples: drinking the tears of shame from a conquest (Charm-driven seduction), telling fortunes from a tarot reading (Wits-driven), arm-wrestling, dueling, dancing, playing chess. The check axis is fixed per character (chosen at CG); the IC framing is freeform but constrained narratively by the player's authored description.
- **Disguise is full:** the target sees a generic SceneActionRequest with no anima labeling. The system knows it's an anima ritual; the target experiences a normal contested check.
- **Magic only works if they engage:** if the target denies, no anima recovery happens. The target receives Kudos for accepting (a small token reward), making the social hook materially incentivized rather than goodwill-only.
- **Rituals are cultural and gated by background:** they aren't universally known. Knowledge is granted by paths, beginnings, distinctions, codex entries, traditions, or by authorship/teaching.

## Design Decisions

### 1. Unify player-authored and staff-authored rituals under `Ritual`

`CharacterAnimaRitual` is removed. The player's anima ritual is a `Ritual` row authored by them, with a `RitualSceneActionConfig` sidecar holding the check spec.

Rationale: the conceptual shape ("a named, described ritual that can be performed") is identical. The data shape (name, description, narrative prose, author) is mostly shared. The differences (how it's dispatched, what configuration drives the firing) are sidecar concerns. Maintaining two parallel models leads to proliferation when more personal-ritual types arrive (imbuing flavors, divinations, etc.).

`Ritual` gains:
- `execution_kind`: extended with `SCENE_ACTION` value (alongside existing `SERVICE | FLOW`).
- `author_account`: nullable FK to Account. `null` = staff-authored.

`RitualSceneActionConfig`: OneToOne sidecar to Ritual, holding `stat`, `skill`, `specialization`, `resonance`, `check_type`, `target_difficulty`. Only present when `execution_kind=SCENE_ACTION`.

Database is dev-empty; no data migration concerns.

### 2. Disguise is full at the system level (Approach B from brainstorm)

The Anima ritual is a *usage label* on a generic `SceneActionRequest`. The target's UI, the result Interaction, and the kudos award all look identical to any other action request. The only "Anima ritual" labeling appears on the *initiator's* side: the entry point in the scene action menu, and the result panel showing anima recovery.

The substrate stays generic. Anima-specific logic lives in `world.magic` and reaches into the generic substrate via the action-key resolver registry (Decision 4).

### 3. Modify state on SceneActionRequest is deferred

Current substrate supports accept/deny only. The user listed "modify" (target negotiates difficulty) as a v2 feature — a nice-to-have, not core. v1 ships accept/deny.

### 4. Action-key resolver registry as the extensibility seam

`SceneActionRequest.action_key` is already a string. We register `"anima_ritual"` as a known action key. A small registry module (`src/world/scenes/action_resolvers.py`) maps `action_key → resolver function`. Each resolver is a function `(request, check_outcome) -> None` that runs *after* `perform_check()` resolves the request, applying any side-effects specific to that action key.

`respond_to_action_request()` calls the registered resolver post-check (no-op if none registered). Each registered resolver also exposes a `contribute_menu_entries(roster_entry, scene)` callable that the available-actions builder uses to populate the scene action menu.

This is deliberately a generic seam — future scene actions (Soul Tether ritual variants, divinations, bindings) each register their own action_key + resolver without touching `SceneActionRequest`.

### 5. Generic kudos award on accept (any SceneActionRequest)

`respond_to_action_request()` awards a small Kudos token (default 1) to the target on accept, regardless of action_key. New `KudosSourceCategory` row (`name="social_engagement"`, default_amount=1, created via data migration).

**Call signature:** `award_kudos(account=target.account, amount=category.default_amount, source_category=category, description=f"Engaged with action request from {initiator_persona.name}", awarded_by=initiator_persona.character.db_account)`. The `source_category` argument is a `KudosSourceCategory` model instance, not a string — the caller must look it up first (`KudosSourceCategory.objects.get(name="social_engagement")`). Cache the lookup at module level if it becomes a per-request cost.

Anima ritual benefits from this; future scene actions also benefit retroactively. Anima-specific Kudos awards (e.g., bonus Kudos for an Anima ritual specifically) are out of scope for v1.

### 6. Knowledge layer mirrors codex pattern

Every ritual is knowledge-gated. Knowledge is tracked at the **RosterEntry** level (matches `CharacterCodexKnowledge`; survives player changes).

```
CharacterRitualKnowledge
├── roster_entry: FK RosterEntry
├── ritual: FK Ritual
├── learned_from: FK RosterTenure, nullable    # null = self-authored or background grant
├── learned_at: DateTimeField (auto_now_add)
└── unique_together(roster_entry, ritual)
```

Grant tables (direct FKs, OR semantics — any matching grant creates a knowledge row):

```
BeginningsRitualGrant   (beginning, ritual)
PathRitualGrant         (path, ritual)
DistinctionRitualGrant  (distinction, ritual)
TraditionRitualGrant    (tradition, ritual)
CodexEntryRitualGrant   (codex_entry, ritual)
```

A reconciliation service walks the grant tables for a roster entry and creates `CharacterRitualKnowledge` rows for matches. Idempotent. Called at character creation. (Triggers on data changes beyond character creation are deferred — see Out of Scope.)

**Authorship and teaching bypass grants.** When a player authors their anima ritual at CG, a knowledge row is created directly. Future teaching mechanic creates knowledge rows directly with `learned_from=teacher`.

There is **no `requires_knowledge` flag**. Per user direction: rituals "definitely shouldn't just be global." Universal rituals don't exist; broadly-known rituals live on broadly-applicable grants.

**Interim handling for `accept_soul_tether`:** the existing `accept_soul_tether` Ritual (shipped with the Soul Tether work) currently has no grant rows. When the knowledge layer ships, that Ritual would silently disappear from `/rituals` for every character — a regression. To prevent this, this work also includes a **placeholder grant** in the same migration batch: `accept_soul_tether` is granted via every existing `Path` (i.e., we create a `PathRitualGrant` row for each Path × the soul-tether Ritual). This preserves visibility without making a content judgment about which paths "should" know it; replacing the placeholder with intentional cultural grants is content/lore follow-up and explicitly out of scope for this work.

### 7. Snapshot ritual config on SceneActionRequest creation

When a player fires an anima ritual, the SceneActionRequest stores a snapshot of the resolved check spec at creation time. The resolver reads from the snapshot, not live from the ritual.

**Storage shape — structured fields, not JSON.** Per CLAUDE.md "No JSON Fields" rule, snapshot fields are added directly to `SceneActionRequest`. **All fields are FKs (since `CheckType` is a SharedMemoryModel in `world.checks.models`, not a TextChoices enum):**

```
snapshot_ritual: FK Ritual, nullable                # which ritual fired (audit)
snapshot_stat: FK Trait, nullable
snapshot_skill: FK Trait, nullable
snapshot_specialization: FK Specialization, nullable
snapshot_resonance: FK Resonance, nullable
snapshot_check_type: FK CheckType, nullable
snapshot_target_difficulty: PositiveSmallIntegerField, nullable
```

All snapshot fields are nullable (only populated when `action_key` is a ritual-driven key). The resolver consumes them via the existing `perform_check()` pipeline using these snapshot values rather than re-reading the ritual.

Rationale: decouples in-flight requests from ritual edits (player edits their ritual mid-scene → in-flight requests resolve with original config); ritual deletion doesn't crash the resolver; structured FKs satisfy the "no JSON" rule and remain queryable for audit.

**Interaction with existing `Ritual.clean()` `CheckConstraint`:** `Ritual` already has a `CheckConstraint` enforcing payload shape per `execution_kind`. This work extends both the constraint and `Ritual.clean()` to require a `RitualSceneActionConfig` sidecar present when `execution_kind=SCENE_ACTION`, and to require it absent when `execution_kind` is `SERVICE` or `FLOW`. Validation enforces this in both Python (`clean()`) and the database (constraint).

### 8. Once-per-scene cap consumed only on accept

If the target denies, the cap is **not consumed** — initiator can re-fire with a different target (or after negotiation). Rationale: don't block legitimate RP patterns where characters say no repeatedly during negotiation.

The risk of spam (initiator fires repeatedly until someone accepts) is acknowledged but deferred — flagged as a generic SceneActionRequest concern, not Anima-specific.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    /rituals page (existing)                      │
│  Browses Ritual rows where the character has knowledge.          │
│  - Authored by you: edit form (PATCH /api/magic/rituals/{id}/)   │
│  - Known rituals: read-only display.                             │
│  Perform button only for SERVICE/FLOW rituals; SCENE_ACTION      │
│  rituals say "performable in scene."                             │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│             Scene action menu (existing infrastructure)          │
│  GET /api/action-requests/available/                             │
│  Backend builder asks each registered resolver to contribute.    │
│  Anima resolver contributes one entry per known SCENE_ACTION     │
│  ritual (subject to once-per-scene cap).                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ Player picks "Anima Ritual"
                              │
┌─────────────────────────────────────────────────────────────────┐
│       Frontend target picker (small new dialog or inline)        │
│  Pick target from scene participants → fire request.             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ POST /api/action-requests/
                              │ { scene, target_persona, action_key="anima_ritual",
                              │   ritual_id, check_spec_snapshot }
                              │
┌─────────────────────────────────────────────────────────────────┐
│        SceneActionRequest (existing, unchanged model)            │
│  status=PENDING, snapshot of check spec stored.                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ Target accept/deny via existing ConsentPrompt
                              │
┌─────────────────────────────────────────────────────────────────┐
│  respond_to_action_request() (modified — small additions)        │
│  - On accept:                                                    │
│      perform_check() (existing) → check_outcome                  │
│      get_resolver(action_key)(request, check_outcome)            │
│            ─→ anima resolver: apply_anima_ritual_outcome(...)    │
│      award_kudos(target.account, source=SOCIAL_ENGAGEMENT)       │
│      Create result Interaction (existing)                        │
│  - On deny: mark DENIED, return.                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Result rendering                                                │
│  - Initiator sees the anima_recovery payload (recovery, soulfray │
│    reduction). Target sees the standard action result + kudos.   │
└─────────────────────────────────────────────────────────────────┘
```

## Components

### Backend

| File | Status | Description |
|---|---|---|
**Substrate (scenes):**

| File | Status | Description |
|---|---|---|
| `src/world/scenes/action_resolvers.py` | NEW | Registry: `register_resolver(action_key, fn)`, `get_resolver(action_key)`. |
| `src/world/scenes/action_services.py` | MODIFIED | `respond_to_action_request()` calls registered resolver post-check; awards generic Kudos on accept. `create_action_request()` populates the snapshot fields. `_build_available_actions()` (or equivalent) asks each resolver for menu entries. |
| `src/world/scenes/action_models.py` | MODIFIED | Add structured snapshot fields (`snapshot_ritual`, `snapshot_stat`, `snapshot_skill`, `snapshot_specialization`, `snapshot_resonance`, `snapshot_check_type`, `snapshot_target_difficulty`) to `SceneActionRequest`. All nullable. |
| `src/world/scenes/tests/test_action_resolvers.py` | NEW | Resolver registry behavior (register/lookup/no-op-on-miss). |
| `src/world/scenes/tests/test_action_services.py` | MODIFIED | Add tests for: generic Kudos-on-accept (any action_key), snapshot population at fire time, resolver invocation on accept, no resolver call on deny. |

**Ritual model unification:**

| File | Status | Description |
|---|---|---|
| `src/world/magic/models/rituals.py` | MODIFIED | Add `SCENE_ACTION` value to `execution_kind` TextChoices. Add `author_account` nullable FK to Account. Extend `clean()` and the existing `ritual_execution_payload` `CheckConstraint` to require `RitualSceneActionConfig` sidecar present when `execution_kind=SCENE_ACTION` and absent when SERVICE/FLOW. |
| `src/world/magic/models/ritual_scene_action.py` | NEW | `RitualSceneActionConfig` sidecar (OneToOne Ritual). Holds `stat`, `skill`, `specialization`, `resonance`, `check_type`, `target_difficulty`. |
| `src/world/magic/admin.py` | MODIFIED | Replace `CharacterAnimaRitualAdmin`/inline with `RitualSceneActionConfig` inline on Ritual; expose `author_account` filter on Ritual admin. |
| `src/world/magic/factories.py` | MODIFIED | Replace `CharacterAnimaRitualFactory` with `RitualFactory` variants for SCENE_ACTION (and a `RitualSceneActionConfigFactory`). Update existing tests' factory usage. |

**`CharacterAnimaRitual` removal — call sites:**

| File | Status | Description |
|---|---|---|
| `src/world/magic/models/anima.py` | MODIFIED | Remove `CharacterAnimaRitual`. Retain `CharacterAnima`. Remove inverse FK from anima models. |
| `src/world/magic/models/anima.py` (`AnimaRitualPerformance`) | MODIFIED | Retarget `ritual` FK from `CharacterAnimaRitual` to `Ritual`. (DB is dev-empty; drop-and-recreate via migration.) |
| `src/world/magic/views.py` | MODIFIED | Remove `CharacterAnimaRitualViewSet` (functionality folded into `RitualViewSet` with author-filtered creation/edit). `RitualViewSet.get_queryset()` filters by `known_by_records__roster_entry=current`. New action (or extended create) for player-authored rituals. |
| `src/world/magic/urls.py` | MODIFIED | Remove `character-anima-rituals` router registration. |
| `src/world/magic/serializers.py` | MODIFIED | Remove `CharacterAnimaRitualSerializer`. Update `RitualSerializer` to include sidecar config when `execution_kind=SCENE_ACTION`. New `RitualSceneActionConfigSerializer`. |
| `src/world/character_sheets/serializers.py` | MODIFIED | `_build_magic_anima_ritual()` (or equivalent) now reads from the player's authored Ritual + sidecar instead of `CharacterAnimaRitual`. |
| `src/world/character_sheets/types.py` | MODIFIED | `AnimaRitualSection` dataclass updated to reflect new field source (still presents same shape to consumers). |
| `src/world/character_sheets/tests/test_viewset.py` | MODIFIED | Update test fixtures + assertions to use Ritual + sidecar. |
| `src/world/magic/tests/test_anima_ritual.py` | MODIFIED | Update factory + setup to use Ritual + sidecar. Service-level behavior tests preserved. |
| `src/world/magic/tests/test_anima_ritual_service.py` | MODIFIED | Same — service tests preserved, fixtures updated. |
| `src/world/magic/tests/test_models.py` | MODIFIED | Remove `CharacterAnimaRitual` model tests; add `Ritual` SCENE_ACTION + sidecar invariant tests. |
| `src/world/magic/tests/integration/test_soulfray_recovery_flow.py` | MODIFIED | Fixture rework. |

**Anima ritual behavior:**

| File | Status | Description |
|---|---|---|
| `src/world/magic/services/anima.py` | MODIFIED | Refactor `perform_anima_ritual()` to split: keep entry point that rolls its own check (for backward compat / non-scene-action use), extract outcome-applier as `apply_anima_ritual_outcome(ritual, outcome, scene)`. |
| `src/world/magic/services/anima_ritual_action.py` | NEW | Defines + registers the `"anima_ritual"` resolver. Provides `contribute_menu_entries(roster_entry, scene)`. |
| `src/world/magic/apps.py` | MODIFIED | `ready()` imports `anima_ritual_action` to trigger resolver registration. |
| `src/world/magic/tests/test_anima_ritual_action.py` | NEW | End-to-end via SceneActionRequest. |

**Knowledge layer:**

| File | Status | Description |
|---|---|---|
| `src/world/magic/models/knowledge.py` | NEW | `CharacterRitualKnowledge` model (mirrors `CharacterCodexKnowledge`). |
| `src/world/magic/models/grants.py` | NEW | `BeginningsRitualGrant`, `PathRitualGrant`, `DistinctionRitualGrant`, `TraditionRitualGrant`, `CodexEntryRitualGrant`. |
| `src/world/magic/services/ritual_knowledge.py` | NEW | Reconciliation service: walks grant tables for a roster entry and creates knowledge rows. Idempotent. |
| `src/world/magic/tests/test_ritual_knowledge.py` | NEW | Reconciliation, grant table behavior, knowledge uniqueness. |
| `src/world/magic/tests/test_models/test_ritual_scene_action_config.py` | NEW | Sidecar model invariants (paired with parent execution_kind). |

**Character creation:**

| File | Status | Description |
|---|---|---|
| `src/world/character_creation/...` | MODIFIED | The "Anima Ritual" CG step (and any backing service) now creates `Ritual` + `RitualSceneActionConfig` + `CharacterRitualKnowledge`. (Implementation note: there is no current direct reference to `CharacterAnimaRitual` in `character_creation/` — but the CG step wires the ritual via the magic viewset/serializer; those callsites are listed above. Verify the actual integration point at planning time.) |

**Kudos:**

| File | Status | Description |
|---|---|---|
| `src/world/progression/migrations/00XX_social_engagement_category.py` | NEW | Data migration creating `KudosSourceCategory(name="social_engagement", default_amount=1, display_name="Social Engagement", description="Awarded for accepting another character's action request.")`. |

**Migrations:**

| File | Status | Description |
|---|---|---|
| `src/world/magic/migrations/00XX_*.py` | NEW (multiple) | Schema migrations for: new models (`RitualSceneActionConfig`, `CharacterRitualKnowledge`, all five grant tables), `Ritual.execution_kind` enum extension, `Ritual.author_account` field, `Ritual.clean()` constraint update, `AnimaRitualPerformance.ritual` FK retarget, `CharacterAnimaRitual` removal. |
| `src/world/scenes/migrations/00XX_*.py` | NEW | Schema migrations for the new SceneActionRequest snapshot fields. |

### Frontend

| File | Status | Description |
|---|---|---|
| `frontend/src/scenes/components/ActionResult.tsx` | MODIFIED | Initiator-side: render `anima_recovery` panel when present. Target-side: standard action result. |
| `frontend/src/scenes/actionTypes.ts` | MODIFIED | Add optional `anima_recovery: { recovered, soulfray_reduced, new_pool }` to `ActionResult`. |
| `frontend/src/scenes/components/ActionPanel.tsx` | UNCHANGED | Existing rendering of `AvailableSceneAction[]` includes the new entry automatically. |
| `frontend/src/scenes/components/ConsentPrompt.tsx` | UNCHANGED | Target sees generic check prompt. **Disguise.** |
| `frontend/src/magic/components/AnimaRitualEditDialog.tsx` | NEW | Form to author/edit the Anima ritual: description, stat, skill, specialization, resonance, check_type, target_difficulty. |
| `frontend/src/magic/__tests__/AnimaRitualEditDialog.test.tsx` | NEW | Form validation + PATCH submit. |
| `frontend/src/rituals/pages/RitualsListPage.tsx` | MODIFIED | Section split: "Authored by you" + "Known rituals." Card actions differ by `execution_kind`. |
| `frontend/src/rituals/components/RitualCard.tsx` | MODIFIED | For `SCENE_ACTION` rituals, show "Performable in scene" indicator and edit/manage button (no perform button). |
| `frontend/src/rituals/components/RitualSceneActionDetailPanel.tsx` | NEW | Detail view of a SCENE_ACTION ritual showing the check spec + edit option (if author). |
| Generated types (`frontend/src/generated/api.d.ts`) | REGEN | After backend changes, via `just gen-api-types`. |

### Notable non-changes

- No new endpoint for "perform anima ritual" — it goes through existing `POST /api/action-requests/`.
- No new `RitualForm`/`input_schema`-driven dialog. Anima ritual fires through the action-request flow, not the perform-ritual flow.
- No changes to the existing Soul Tether UI components.

## Data Flow

### A. Character creation: player authors anima ritual

1. CG step "Anima Ritual" loads existing form: description, stat, skill, specialization, resonance, check_type, target_difficulty.
2. On submit → `POST /api/magic/rituals/personal/` (or `RitualViewSet` extension). Body = form fields.
3. Backend, in a single transaction:
   - Creates `Ritual` (`name`, `description`, `narrative_prose`, `execution_kind=SCENE_ACTION`, `author_account=request.user.account`).
   - Creates `RitualSceneActionConfig` sidecar with check spec.
   - Creates `CharacterRitualKnowledge(roster_entry=current, ritual, learned_from=null)`.
4. Returns the full Ritual representation.

### B. Player browses /rituals + edits their ritual

1. `useRituals()` → `GET /api/magic/rituals/` filtered by `Ritual.objects.filter(known_by_records__roster_entry=current)`.
2. Page renders sections: "Authored by you" (where `author_account=request.user.account`) + "Known rituals" (rest).
3. Each card's action depends on `execution_kind`:
   - `SERVICE` / `FLOW` → "Perform" button → existing `RitualPerformDialog`.
   - `SCENE_ACTION` → "Manage" button → opens detail panel + edit dialog (author only) → `PATCH /api/magic/rituals/{id}/`.

### C. Player performs anima ritual in scene

1. Player joins scene. `GET /api/action-requests/available/?scene=<id>` returns `AvailableSceneAction[]` including the player's anima ritual entry (when known + cap not spent).
2. Existing `ActionPanel.tsx` renders the entry. Player clicks → frontend opens target picker dialog (scene participants, excluding self).
3. Player picks target → `POST /api/action-requests/` with `{ scene, target_persona, action_key="anima_ritual", ritual_id, check_spec_snapshot }`.
4. Backend `create_action_request()` validates (knowledge, participation, cap, snapshot). Creates `SceneActionRequest(status=PENDING)`.
5. Target sees request via existing polling on `GET /api/action-requests/?scene=<id>&status=pending&target_persona=mine`. `ConsentPrompt` renders generic check info. **No anima labeling.**
6. Target accepts → `POST /api/action-requests/{id}/respond/` `{decision: "accept"}`.
7. Backend resolves:
   - `perform_check()` (existing) using snapshot → `check_outcome`.
   - Result Interaction created (existing, generic).
   - `get_resolver("anima_ritual")(request, check_outcome)` → anima resolver applies recovery via `apply_anima_ritual_outcome(ritual, outcome, scene)` → creates `AnimaRitualPerformance` audit row → marks once-per-scene cap.
   - `award_kudos(target.account, amount=1, source=SOCIAL_ENGAGEMENT, ...)`.
   - Response serializer adds `anima_recovery` block **only when viewer is initiator AND action_key="anima_ritual"**.
8. Initiator sees recovery panel; target sees standard result + Kudos toast.
9. Target denies → `SceneActionRequest` marked `DENIED`. No anima change, no Kudos. Cap not consumed. Initiator can re-fire.

## Edge Cases

| Case | Handling |
|---|---|
| No `Ritual` configured for character | "Anima Ritual" not in scene action menu. No error. |
| Once-per-scene cap spent | Entry filtered out. |
| Target leaves scene before response | `SceneActionRequest` lifecycle handles (verify against existing substrate). |
| Initiator leaves before response | Same — substrate handles. Resolver sees invalidated request and skips. |
| Target denies | No recovery, no Kudos, cap not consumed, initiator may re-fire. |
| Target accepts but check fails | Resolver fires with failure outcome — `apply_anima_ritual_outcome` handles (zero/minimal recovery). Audit row created. Cap consumed. Kudos still awarded. |
| Initiator picks self as target | Substrate validation rejects. |
| Player edits ritual mid-scene with pending request | Snapshot on the request resolves with original config; new requests use updated config. |
| Ritual deleted while request pending | Snapshot keeps request resolvable. |
| Knowledge gates not yet wired for `accept_soul_tether` | Soul Tether ritual doesn't appear on /rituals until grants land. **Surfaced as content follow-up.** |

## Testing

### Backend

- **Unit:** `RitualSceneActionConfig` defaults, sidecar uniqueness; `CharacterRitualKnowledge` uniqueness, nullable `learned_from`; each grant table FK + uniqueness; resolver registry register/lookup/no-op; reconciliation idempotency.
- **Integration:** anima ritual end-to-end via `SceneActionRequest` API (fire+accept+success, fire+accept+failure, fire+deny, cap-spent, non-participant rejection); /rituals viewset filters by knowledge (player sees own + granted); generic Kudos on accept for non-anima requests.
- **Backward-compat:** existing `perform_anima_ritual()` tests continue to pass.

### Frontend

- **Unit:** `AnimaRitualEditDialog` validation + PATCH; `ActionResult` renders `anima_recovery` panel only when present.
- **Integration:** /rituals page sections render with mocked data; scene action menu includes new entry from mocked `AvailableSceneAction[]`.

### Regression

- Full backend regression on `world.magic`, `world.scenes`, `world.character_sheets`, `world.codex`, `world.progression` — affected suites due to model changes and resolver additions.
- Full frontend test suite (1199+ tests baseline).
- Production build (`pnpm build`) — catches TS schema drift that `pnpm typecheck` misses.
- One regression run without `--keepdb` before pushing (per CLAUDE.md).

## Out of Scope / Future Work

1. **Spam / rate limiting on repeated SceneActionRequests** — generic substrate concern.
2. **`RitualTeachingOffer`** — mirror `CodexTeachingOffer` / `ThreadWeavingTeachingOffer`. Creates `CharacterRitualKnowledge` rows with `learned_from=teacher`.
3. **Reconciliation triggers on data changes** — beyond character creation, when does reconciliation refire? On path change? On codex unlock? Defer until first concrete use case.
4. **"Modify" state on SceneActionRequest** — target negotiates difficulty. Universal substrate improvement.
5. **Inline pose / required RP content on SceneActionRequest fire** — universal improvement that solves "did any RP actually happen." Helps with the spam concern in (1).
6. **Replacing the placeholder `accept_soul_tether` grant with intentional cultural grants** — see Decision 6. The placeholder ships in the same migration batch (every Path grants it, preventing regression); replacing it with curated grants per actual lore is content/lore follow-up.
7. **Display of past `AnimaRitualPerformance` rows** — audit/history surface for the player.
8. **Per-resonance Strain UI** — already deferred from soul-tether-ui.
9. **Anima-ritual-specific Kudos awards** — bonus Kudos for an Anima ritual specifically, beyond the generic engagement award.

## Acceptance Criteria

A player can:
1. Author or edit their Anima ritual at `/rituals` (or via the CG step).
2. Join a scene and see "Anima Ritual" as an available scene action when their once-per-scene cap is unspent.
3. Pick a target and fire the ritual. Target sees a generic action-request consent prompt with no anima labeling.
4. On accept: see anima recovery and Soulfray reduction in their result panel; target receives 1 Kudos.
5. On deny: re-fire with a different target within the scene.
6. See their authored ritual on `/rituals` alongside other rituals they know.
7. Not see other players' anima rituals on `/rituals` unless their character has knowledge of them (e.g., taught — future).

A developer can:
1. Add a new scene-action ritual type (or other action key) by registering a resolver — no changes to the SceneActionRequest substrate.
2. Wire a new ritual to a Path/Beginning/Distinction/Tradition/CodexEntry grant by adding rows in the appropriate grant table.
3. Run `arx test world.magic world.scenes world.codex world.progression` cleanly.
4. Run frontend regression cleanly: `pnpm typecheck && pnpm test --run && pnpm lint && pnpm build`.
