# Magic System — Playable-Loop Status

**Status:** engine essentially complete; blocked on onboarding/content, not mechanics.
**North star:** a player can **cast → see it posed into the scene → it's logged → it
resolves an outcome**, in a live RP scene in the web client.

This is the **status map** — the one place to answer "where are we / what's left." The
full scope-by-scope build record lives in
[`magic-build-history.md`](magic-build-history.md) (archive; consult it before designing
anything new, to avoid reinventing existing surfaces). When this doc and the archive
disagree, this doc and the code win.

**Capability tiers + MVP sequencing:** [`player-capability-ledger.md`](player-capability-ledger.md)
(DO / GROW / COMBINE pillars). **Gift/resonance economy decisions:** ADR-0050–0057 — Major/Minor
gifts (species abilities as Minor Gifts), gift-thread strength + resonance, XP-unlocks-gate-never-grant,
the one specialization engine, fall/redemption, Covenant of the Court.

## The playable loop, stage by stage

| Stage | Status | Where |
|-------|--------|-------|
| Cast initiation — REST `POST /api/action-requests/cast/`, WebSocket, `ActionPanel` UI | ✅ wired | `world/scenes/cast_services.py:request_technique_cast`; `frontend/src/scenes/actionQueries.ts:castTechnique` |
| Check resolution — anima, soulfray, mishap, corruption, environment | ✅ wired | `world/magic/services/techniques.py:use_technique` |
| Effects / outcome — conditions, combat damage, thread pulls, mage scars | ✅ wired | `world/combat/services.py`; `world/magic/services/` |
| Pose / narration into the scene | ✅ wired | `world/scenes/cast_services.py:create_cast_outcome_pose` → `world/magic/narration.py` |
| Logging — `SceneActionRequest` + `Interaction` + power ledger | ✅ wired | `world/scenes/action_models.py`; `cast_services.py:persist_power_ledger` |
| Resonance / progression feedback | ✅ by design | earned from RP perception (endorsements), **not** from casting — see "By design" below |
| **A real character actually being able to cast** | ✅ wired | `#1306` — shared template + per-character check; see below |

The backend cast→pose→log→outcome loop is fully wired and resolves end-to-end (verified
by tracing + a throwaway smoke test). The remaining frontier is **assembly, content, and
integration**, not engine mechanics.

## What's left (the real gaps)

Ordered by priority. These are the gaps between "the engine works" and "a player can do
magic." Each is a filed issue — work these, not micro-hardening tickets.

1. **✅ #1306 — RESOLVED: every technique is now castable** (`priority:now` → done).
   `create_technique` defaults `action_template` to the shared **Technique Cast**
   `ActionTemplate` seeded by `seeds_cast.ensure_technique_cast_content()`. Cast
   resolution rolls the **caster's own per-character magic check**
   (`ensure_character_magic_check_type` / `get_character_cast_check` in
   `seeds_checks.py` / `services/anima.py`); the same check is used by the anima ritual
   (wired via `provision_player_anima_ritual`). A graded **"Magic: Technique Cast"**
   `ConsequencePool` routes outcomes. No schema migration required.
   **Follow-ups from #1306:** technique designer (player picks a consequence pool from a
   curated catalog). The targeting model gaps (listed below) were closed by #1321.

2. **✅ #1321 — RESOLVED: targeting model + behavior-consent + AoE + standalone condition
   application** (`priority:now` → done). Closed the four gaps deferred from #1306:
   - **Targeting validity enforcement:** `Technique.target_type` (new field,
     `ActionTargetType` choices: SELF/SINGLE/AREA/FILTERED_GROUP, default SINGLE) stores
     per-technique cardinality. `validate_cast_target` (`world/magic/services/targeting.py`)
     enforces cardinality and relationship rules, raising `InvalidCastTarget` on violation.
   - **Behavior-consent routing:** `ConditionCategory.alters_behavior` (new boolean, default
     False) marks behavior-altering categories (compulsion, charm, fear). The consent gate
     is now **behavior-based**: hostile → combat; benign + behavior-altering → PENDING
     consent; benign + capability/stat → resolves immediately (including on other PCs).
     `cast_requires_consent` in `targeting.py` implements this predicate.
   - **AoE expansion:** standalone AREA auto-expands via `resolve_targets` to all eligible
     personas in the scene (relationship-derived: SELF→caster only, ALLY/ENEMY→all others).
     Combat AoE uses the new `CombatRoundActionTarget` join table (`world/combat/models.py`);
     AREA auto-expands to all active opponents, FILTERED_GROUP uses the stored/supplied subset.
   - **Frontend target picker:** the existing `TargetPicker.tsx` (multi-select capable) is now
     driven by a technique's `target_spec`. `_target_spec_for_technique_action` in
     `actions/player_interface.py` builds the spec from `Technique.target_type` and
     `derive_target_relationship`. The `TargetSpec`/`TargetType`/`TargetKind`/`TargetFilters`
     model in `actions/` was **reused** (already existed and wired) — not reinvented.
   - **Standalone condition application:** `apply_technique_conditions`
     (`world/magic/services/condition_application.py`) extracted from combat's
     `_apply_conditions`. Standalone casts now apply technique-authored conditions to
     resolved targets. `AppliedConditionResult` still lives in `world/combat/types.py` as a
     known follow-up to relocate.

   **Still deferred (follow-ups):**
   - Resonance → aspect mapping (all magic checks still use the Arcana aspect).
   - Relocate `AppliedConditionResult` out of `world/combat/types.py`.
   - Standalone hostile/behavior-altering FILTERED_GROUP multi-consent state machine.
3. **🟠 #1307 — seed produces no playable character or scene** (`priority:next`). The
   "Big Button" (`world/seeds/database.py:seed_dev_database`, #651) seeds rules content
   only — 0 CharacterSheets / Personas / Scenes. Needs a playable-slice path (demo
   character via `create_character_with_sheet` + CG finalize, placed in a scene). Child
   of epic #1220.
4. **🟡 #1308 — the web cast loop is never tested live** (`priority:next`). Frontend cast
   tests mock `castTechnique`; backend tested only at service level. No test drives
   `POST /api/action-requests/cast/` against a seeded + CG'd character. Add one as the
   regression guard. Cross-refs #617.
5. **🟢 #1309 — frictionless scene start** (`priority:later`). Casting needs an active
   scene; a player should be able to start/auto-join one without staff setup (the
   "implicit scene start" intent).

## By design — do not re-file these as gaps

A code read flags these as "missing"; they are intentional. Verify against the design
before treating any as a bug:

- **Casting does not grant resonance.** Resonance is earned from *perception* — pose
  endorsements, scene entry, residence/outfit trickle (the four `grant_resonance`
  surfaces in Spec C, `docs/architecture/resonance-gain.md`). You earn it when others
  endorse your dramatic cast pose, not mechanically from the cast.
- **Non-combat casts deal no damage.** A hostile cast at a PC routes into combat
  (`seed_or_feed_encounter_from_cast`), where damage applies. Non-combat = benign / self
  / room. Consistent with the non-lethal-PvP invariant.
- **Non-combat thread pulls are passive-only** (VITAL_BONUS inactive outside combat) —
  Resonance Spec §7.4.

## Design resolution — #1306 (castability, RESOLVED)

**Was:** Is castability (the `action_template`) auto-provisioned per technique, shared
per effect-type/style, or authored staff content?

**Resolved:** A single shared **Technique Cast** `ActionTemplate` is seeded by
`seeds_cast.ensure_technique_cast_content()`. `create_technique` defaults `action_template`
to it; the per-technique FK remains as a staff-only override. Cast resolution rolls the
**caster's own per-character magic check** (synthesized from their stat + skill via
`ensure_character_magic_check_type`), not a technique-level authored check. Outcomes route
through a graded **"Magic: Technique Cast"** `ConsequencePool`. The anima ritual and
technique casts always share the same personal check (`provision_player_anima_ritual`
in `services/anima.py`).

Deferred to follow-up issues: technique designer (player selects a consequence pool
from a curated catalog built on `ConsequencePool.parent`); optional resonance→aspect
mapping for the per-character check (today all magic checks use the Arcana aspect).

The targeting model gaps (validity enforcement, AoE, frontend picker, standalone condition
application) were resolved in #1321 — see the #1321 entry above.

## Telnet technique-authoring workbench (#1496 — BUILT, staff/GM-only)

Closes the `#1328` telnet-coverage gap for technique authoring. Surfaces built:

- **`TechniqueDraft`** + three payload child models (`TechniqueDraftCapabilityGrant`,
  `TechniqueDraftDamageProfile`, `TechniqueDraftAppliedCondition`) in
  `src/world/magic/models/technique_draft.py`. Payload children inherit abstract bases
  (`AbstractCapabilityGrant` / `AbstractDamageProfile` / `AbstractAppliedCondition` in
  `models/techniques.py`) shared with the committed `Technique*` rows.
- **Draft services** (`services/technique_draft.py`): `get_or_start_draft`, `discard_draft`,
  `set_draft_fields`, restriction + payload add/remove helpers, `draft_to_design`.
- **`validate_design_for_character`** (`services/technique_builder.py`) — gift-ownership
  gate extracted from the serializer; now the single gate for both telnet and web.
- **`AuthorTechniqueAction`** (key `"author_technique"`, category `"magic"`,
  `actions/definitions/technique_authoring.py`) — the single commit seam. Both the web
  `TechniqueViewSet.author` endpoint and `CmdTechnique` converge on `action.run()`.
- **Web convergence** — `TechniqueViewSet.author` now dispatches `AuthorTechniqueAction.run()`
  for the player path (HTTP contract preserved: 201/400/403). Staff-without-character retains
  a direct `author_staff_technique()` fallback.
- **`CmdTechnique`** (`commands/technique.py`, key `"technique"`, `cmd:perm(Builder)`) —
  staff/GM-only telnet workbench with subcommands:
  `draft show set restrict grant damage condition price author discard`.
  `author` dispatches `AuthorTechniqueAction` with `as_staff=True` (`StaffPolicy`, advisory
  budget, no `CharacterTechnique` binding).

**Deferred `needs-design` follow-up:** when and how ordinary players earn technique authoring
(CG design step, magical-research unlock, or other unlock mechanism — never on-demand).
The `PlayerPolicy` seam and web `author` endpoint are already wired; the player-tier gate
is a permissive `TODO` in `technique_builder.py`.

## Ritual of the Durance (#1352 — BUILT)

The within-tier class-level advancement ceremony is complete. Magic's contribution:

- **`RitualLiturgy`** (`models/liturgy.py`) — OneToOne on `Ritual`; `opening_call` TextField
  holds the authored officiant invocation (public, non-spoiler).
- **`RitualOfTheDuranceFactory`** (`factories.py`) — seeds the `Ritual` row (SERVICE /
  INDUCTION, `service_function_path` → `world.progression.services.advancement.advance_class_level_via_session`,
  `min_participants=2`) and its companion `RitualLiturgy` via a `@post_generation` hook.
- `AudereMajoraCrossing` now inherits `AbstractClassLevelAdvancement` (from
  `world.progression.models.advancement`), sharing shape with `ClassLevelAdvancement`.
  `cross_threshold` calls `apply_class_level_advance` (the shared spine) instead of
  inlining a level write.

**Telnet Durance (#1700) — BUILT.** Telnet drivability of the Ritual of the Durance is now
complete. Both a live-officiant ceremony (`ritual draft` → inductee `ritual join` → `ritual fire`)
and a site-convened session (`durance convene` → inductee `ritual join`, auto-fires) are
supported. See `docs/roadmap/character-progression.md` and ADR-0065 for the full build record.

---

## Deeper design & history

- Scope-by-scope build record: [`magic-build-history.md`](magic-build-history.md)
- Architecture references: `docs/architecture/` (power-derivation, resonance-threads,
  resonance-gain, reactive-layer-foundation, magical-alteration, non-clash-casting, …)
- System reference: `docs/systems/magic.md`
