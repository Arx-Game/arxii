# Incapacitation & dying foundation — agency gate, condition-driven

**Issue:** #595 (PR A — foundation; blocks #560/#561)
**Branch:** `feature-595-decouple-incapacitation-dying-from-vital`
**Status:** design approved; spec under user review
**Date:** 2026-05-29

## Problem

`CharacterVitals.status` (`ALIVE → UNCONSCIOUS → DYING → DEAD`, plus a
`dying_final_round` boolean) conflates two orthogonal axes — **mortality**
(alive/dying/dead) and **consciousness / ability to act**. The single ladder
makes *dying + conscious* unrepresentable, forces "fight while dying" through
the `dying_final_round` hack (`combat/services.py:799-801, 1335-1337`), and
models a subset of capability-impairment (unconscious) on vitals when
impairment is properly a **conditions** concern.

## Goal & boundary

Establish the correct **state model** so any damage source can produce
coherent incapacitation/dying, and combat gates actions on it. This PR:

- **In scope:** a coarse, condition-driven **agency gate**; an `incapacitates`
  signal on conditions; a staged **bleed-out (Dying) condition** with
  worsening stabilization; the combat action-gating refactor; the
  `CharacterVitals` slim-down + data migration; retargeting the *existing*
  damage path to apply the new condition states.
- **Out of scope (consume / defer):** the graduated capability machinery
  (`force`/`movement`/…), the `CharacterCapabilities` facade, trait-derivation
  wiring, and the Application/Situation/Property generalization — all described
  in `docs/architecture/property-capability-action.md`, all separate future
  work. The consequence-pool reconciliation of the *rolls* is **PR B**
  (#560/#561).

## Design decisions (ratified)

- **Agency is a coarse STATE, not a capability.** The architecture doc is
  emphatic that capabilities are ways to *affect the world* and "passive
  effects are not capabilities." So "can act at all" is a gate, not a
  `CapabilityType`. Granular impairments (slowed, grounded) keep riding the
  existing `ConditionCapabilityEffect` on real capabilities — untouched here.
- **Mortality and consciousness are orthogonal.** `{dying + conscious}` is a
  first-class state: a dying-but-conscious character can act (fights until they
  drop). Retires `dying_final_round`.
- **Dying is a staged bleed-out condition**, stabilizable, with worsening odds
  per stage — reusing `ConditionStage.resist_check_type` / `resist_difficulty`.
- **PR A keeps the current damage logic** (binary, existing difficulty) but
  retargets its *output* from `vitals.status` writes to condition application,
  so it ships without a functional gap. PR B replaces the internals with the
  consequence-pool pipeline.

## Architecture

### Agency gate

A character **can act** iff `life_state != DEAD` **and** they have no active
**incapacitating** condition.

- New `ConditionTemplate.incapacitates` (BooleanField, default False). True for
  Unconscious / Slept / Stunned / Paralyzed-style total-incapacitation
  conditions. (Stage-level incapacitation — a stun that only incapacitates at
  higher severity — is a future extension via a `ConditionStage.incapacitates`
  override; not in v1.)
- `world/conditions/services.py: is_incapacitated(character) -> bool` — true if
  any active `ConditionInstance` has `condition.incapacitates`. Reuses
  `get_active_conditions`.
- `world/vitals/services.py: can_act(character) -> bool` — composes
  `not is_dead(character) and not is_incapacitated(character)`.

No new `CapabilityType`, no dependency on the capability-value query.

### Mortality on vitals (slim-down)

`CharacterVitals` keeps `health`, `max_health`, `base_max_health`, `died_at`.
The 4-state `status` enum is reduced to a **mortality marker**:

- New `life_state` field: `CharacterLifeState` = `ALIVE` / `DEAD` only.
- **Remove** `UNCONSCIOUS` / `DYING` from the life-state vocabulary (now
  conditions), and drop `dying_final_round` and `unconscious_at` (now
  condition-derived: an Unconscious condition's `applied_at` replaces
  `unconscious_at`).
- `is_dead(character)` / `is_alive(character)` read `life_state`.

### Dying (bleed-out) condition

A staged `ConditionTemplate` ("Bleeding Out"):

- Stages model worsening peril; each `ConditionStage` carries
  `resist_check_type` + `resist_difficulty` (already exist), difficulty rising
  per stage.
- **Progression:** during combat round resolution, each active bleed-out
  condition rolls its stage's resist check; failure advances a stage; the
  terminal stage sets `life_state = DEAD`. Success holds. This reuses the
  conditions stage-advancement/resist machinery and replaces the
  `dying_final_round → DEAD` consumption at `combat/services.py:2495-2509`.
- **Stabilization:** curing/reducing the condition (first aid, magic) via the
  existing condition cure/dispel path halts progression. (Authored stabilize
  actions are content/follow-up; the mechanism is the condition being
  removable.)
- Bleed-out does **not** set `incapacitates` — a dying character stays
  conscious and able to act unless *separately* incapacitated.
- Non-combat dying progression (time-based bleed-out outside encounters) is a
  follow-up (#523); v1 drives progression from the combat round loop.

The Unconscious and Bleeding-Out `ConditionTemplate`s themselves are authored
content (admin/seed), not committed fixtures. This PR provides the
**mechanism** + factory-built conditions for tests.

### Retargeting the existing damage path

`process_damage_consequences` (`world/vitals/services.py`) keeps its current
binary checks and difficulty math (PR B reconciles those) but changes its
*effects*:

- knockout → apply the Unconscious condition (instead of `vitals.status =
  UNCONSCIOUS`).
- death-threshold → apply the Bleeding-Out condition (instead of
  `vitals.status = DYING` + `dying_final_round`).
- `DamageConsequenceResult` keeps its fields (`knocked_out`, `dying`,
  `final_status` → re-expressed via `life_state` + flags) so callers/tests keep
  working.

### Combat action-gating refactor

Replace the ~8 `vitals.status` / `dying_final_round` read sites
(`combat/services.py:578-582, 799-801, 1220-1240, 1321-1337, 1966-1975, 2117,
2495-2509`) with the new gate:

- Declare-action gate → `can_act(character)` (dying+conscious now passes
  naturally; no `dying_final_round` special case).
- Round-order / passive-target filters → `can_act` / `is_alive` as appropriate.
- Encounter loss condition → all PCs `not can_act` (down or dead).
- Dying→dead consumption → driven by bleed-out condition progression (above).

## Anti-reinvention ledger

| Surface | Verdict |
|---|---|
| `ConditionTemplate` / `ConditionInstance` / `ConditionStage` (stages, resist, cure) | REUSE |
| `get_active_conditions`, condition apply/cure services | REUSE |
| `ConditionCapabilityEffect` (granular impairment) | REUSE — untouched |
| graduated capability query / facade / trait-derivation | DEFER — not built here |
| `ConditionTemplate.incapacitates` boolean | NEW (small flag) |
| `CharacterVitals.life_state` (ALIVE/DEAD) replacing 4-state `status` | NEW (slim) |
| `is_incapacitated` / `can_act` / `is_dead` service fns | NEW (thin) |
| Unconscious + Bleeding-Out condition definitions | NEW (mechanism; content authored) |

## Migration

`CharacterVitals` data migration: `ALIVE → ALIVE`; `UNCONSCIOUS → ALIVE` +
apply Unconscious condition; `DYING → ALIVE` + apply Bleeding-Out condition;
`DEAD → DEAD`. Drop `dying_final_round`, `unconscious_at`. Preserve the dev DB
(migrate, don't reset). Watch the SQLite/PG two-tier behavior for the enum
change.

## Testing

- `can_act` / `is_incapacitated` / `is_dead` unit tests (conscious, unconscious,
  dying-conscious, dying-unconscious, dead).
- Bleed-out progression: staged resist advances to death on repeated failure;
  stabilization (cure) halts; dying+conscious can still act mid-progression.
- Combat gating: a dying-but-conscious participant can declare an action; an
  unconscious one cannot; loss condition fires when all PCs are down.
- `process_damage_consequences` now applies conditions (not status writes).
- Migration test: existing rows map correctly.
- Two-tier (SQLite inner loop; `@tag("postgres")` only where forced); full
  no-keepdb regression before push. Suites: `world.vitals`, `world.combat`,
  `world.conditions`, plus any reading `CharacterStatus`.

## Deferred follow-ups (file at PR time)

- PR B (#560/#561): consequence-pool reconciliation of the rolls that produce
  these states.
- Non-combat / time-based bleed-out progression (#523).
- Stage-level `incapacitates` override (severity-gated stun).
- Read-model updates for the new state (#521 status panel, #522 `{status}`
  slot, #553 conditions on CombatantsList).
- The broader capability facade / trait-derivation wiring / Application-Situation
  models (`docs/architecture/property-capability-action.md`).
