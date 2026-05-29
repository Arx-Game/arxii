# Combat consequences — consequence-pool reconciliation (PR B)

**Issues:** #560 (knockout/death/wound rolls into combat), #561 (permanent-wound application)
**Branch:** `feature-560-knockout-death-wound-roll-services-in-vi`
**Status:** design refreshed post-#595-merge (verify-against-code pass complete); ready for plan
**Date:** 2026-05-29 (refreshed)

> **Builds on merged #595.** #595 decoupled life-state into `life_state`
> (ALIVE/DEAD), made knockout/dying *condition-driven* (Unconscious /
> Bleeding-Out), and wired dying→dead via `advance_bleed_out`. PR B reconciles
> the *resolution* of those consequences onto the existing rank → `CheckOutcome`
> tier → `ConsequencePool` pipeline, replacing the binary-pass/fail +
> ad-hoc-difficulty internals that #595 deliberately left in place.

## Problem (current state, verified against merged main)

`process_damage_consequences` (`world/vitals/services.py`) applies the right
*conditions* now (Unconscious on knockout, Bleeding-Out on death), but its
resolution is still the parallel implementation #595 left for PR B:

- Binary `success_level <= 0` branches, not `CheckOutcome`-tiered pool selection.
- Ad-hoc point-difficulty constants (`KNOCKOUT/DEATH/WOUND_BASE_DIFFICULTY`).
- `_select_and_apply_wound` is a stub returning `None`.
- The three checks are **dormant**: the `knockout/death/wound_check_type`
  params exist but combat call sites don't pass them and no CheckTypes are
  seeded — so no rolls fire today.

## Verify-against-code ledger (per CLAUDE.md Anti-Reinvention Pass / #599)

| Surface | Verdict | Evidence |
|---|---|---|
| consequence-pool pipeline (`select_consequence`, `select_consequence_from_result`, `apply_resolution`, `resolve_pool_consequences`) | BUILT & WIRED | `world/checks/consequence_resolution.py:26-164`; used by challenges/clash |
| `filter_character_loss`, `select_weighted`, `build_outcome_display` | BUILT & WIRED | `world/checks/outcome_utils.py:43-123` |
| `ConsequencePool`/`Entry`, `Consequence`/`ConsequenceEffect.condition_template` | BUILT & WIRED | `actions/models/consequence_pools.py:14-142`; `world/checks/models.py:129-287` |
| `DamageType`, `ConditionTemplate(PERMANENT)`, `ConditionStage` resist | BUILT & WIRED | `world/conditions/models.py` (DamageType 114; DurationType.PERMANENT; stage resist 400-410) |
| death → DEAD via Bleeding-Out + `advance_bleed_out` | BUILT & WIRED | `world/vitals/services.py` (`advance_bleed_out`, `_mark_dead`); called `world/combat/services.py:2490` |
| `process_damage_consequences` binary/ad-hoc internals + dormant checks | BUILT, NOT WIRED | `world/vitals/services.py:161-260`; call sites omit check_type kwargs (`combat/services.py:1969`, `mechanics/effect_handlers.py:187`) |
| `_select_and_apply_wound` | BUILT (stub) | `world/vitals/services.py:433` returns None |
| `DamageType.wound_pool` / `death_pool` FK | ABSENT | not on the model |
| `VitalsConsequenceConfig` singleton | ABSENT | grep 0 hits |
| `resolve_vitals_consequence` wrapper | ABSENT | — |
| `EffectType.SET_LIFE_STATE` / `ConsequenceEffect.life_state` | ABSENT — and must STAY absent | death is condition-driven; do not add |

## Design (ratified)

A thin wrapper `resolve_vitals_consequence(character, check_type, target_difficulty, pool)`
over the existing pipeline:

```python
pool_consequences = resolve_pool_consequences(pool)            # full list, all tiers
pending = select_consequence(character, check_type, target_difficulty, pool_consequences)
applied = apply_resolution(pending, ResolutionContext(character=character))
```

`select_consequence` performs the check → filters to the rolled `CheckOutcome`
tier → `select_weighted` → `filter_character_loss` → `PendingResolution`;
`apply_resolution` fires the selected `Consequence`'s `ConsequenceEffect`s.
`build_outcome_display` is built from the **full** resolved pool (all tiers),
independent of which outcome `select_consequence` selected.

- **Knockout** (resulting health ≤ 20%): resolve the **global knockout pool**
  (`VitalsConsequenceConfig.knockout_pool`). Outcomes apply the **Unconscious**
  ConditionTemplate (and milder variants). Endurance check.
- **Permanent wound** (single hit ≥ 50% max health): resolve
  `DamageType.wound_pool` (fallback `VitalsConsequenceConfig.default_wound_pool`).
  Tiered permanent-wound ConditionTemplates (`duration_type=PERMANENT`).
  Endurance check. Replaces the `_select_and_apply_wound` stub.
- **Death** (resulting health ≤ 0): resolve `DamageType.death_pool` (fallback
  default). Tiered by outcome: milder tiers apply **Bleeding-Out** /
  survival-but-grievous conditions; the `character_loss=True` tier is the
  terminal outcome. As with every pool, `select_consequence` runs the standard
  `filter_character_loss` modifier step (a positive `rollmod` substitutes the
  worst non-loss outcome in the rolled tier). Death check (distinct, supports
  modifiers). Bleeding-Out remains one outcome; `advance_bleed_out` still drives
  dying→dead (unchanged).

**Checks (seed via get_or_create, name-constants):** **Endurance** (shared:
knockout + wound) and **Death** (distinct). Pattern mirrors
`fatigue/services.py` endurance seeding; combat never crashes on a fresh DB.

**New surfaces:** `DamageType.wound_pool` + `death_pool` FKs → `ConsequencePool`
(nullable); `VitalsConsequenceConfig` singleton (mirrors `StrainConfig`/
`ClashConfig`) holding `knockout_pool` (global) + `default_wound_pool` +
`default_death_pool`; `resolve_vitals_consequence` wrapper. **Schema migrations
only — no data migration** (no production data; dev DB is disposable, per
CLAUDE.md). **No `SET_LIFE_STATE`.**

**Difficulty:** keep the existing thresholds (50%/20%/0%) and point-difficulty
constants — `perform_check` converts points → rank as today. Not re-tuned here.

## Call-site wiring

- `combat/services.py:_resolve_npc_action` (~1969): pass the threat's real
  `damage_type` (currently `None`) and the seeded CheckTypes.
- `mechanics/effect_handlers.py:_apply_deal_damage` (~187): same.

`process_damage_consequences` keeps its system-agnostic signature; internally it
selects the right pool + check per consequence kind and calls
`resolve_vitals_consequence`. `DamageConsequenceResult` flags
(`knocked_out`/`dying`/`wounds_applied`) preserved for callers.

## Testing

- Pool resolution per kind: factory-built pools (no committed fixtures); tiered
  selection + effect application (Unconscious applied; permanent wound persists;
  death pool applies Bleeding-Out on a survivable tier).
- **Modifier-filter test:** a `character_loss` outcome + a positive-`rollmod`
  character → the non-loss tier outcome is applied (standard `filter_character_loss`
  behavior), and `build_outcome_display` reflects the full resolved pool.
- Combat integration: lethal NPC hit → death pool resolves → Bleeding-Out (or
  true death) → `advance_bleed_out` to DEAD.
- Two-tier: SQLite inner loop; `@tag("postgres")` for progressive-condition
  (`apply_condition` DISTINCT ON) tests; full no-keepdb regression before push.
  Suites: `world.vitals`, `world.combat`, `world.conditions`, `world.checks`,
  `world.mechanics`.

## Deferred follow-ups (file at PR time)

- Catalog of `rollmod` modifier *sources* + their authoring surface.
- Frontend consequence-outcome display (consumes the full resolved pool).
- Authored pool/condition *content* (admin-created; not committed fixtures).
- Non-combat / time-based bleed-out progression (#523).
