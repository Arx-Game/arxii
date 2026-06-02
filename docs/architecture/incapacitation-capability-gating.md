# Incapacitation & dying foundation — capability-gated agency

**Issue:** #595 (PR A — foundation; blocks #560/#561)
**Branch:** `feature-595-decouple-incapacitation-dying-from-vital`
**Status:** design approved (scope revised after code-verified capability audit); spec under user review
**Date:** 2026-05-29

> **Revision note:** an earlier draft of this spec proposed a *coarse
> `incapacitates` boolean gate*. That is superseded. A code-verified audit
> (see "Verified system state") showed the capability→action-availability
> pipeline largely **exists and is wired**, and that "can I act" must be
> **per-technique**, not a global boolean (an immobilized-but-conscious mage can
> still cast a consciousness-only spell). This spec reflects the corrected,
> grounded design.

## Problem

Two coupled problems:

1. **`CharacterVitals.status`** (`ALIVE→UNCONSCIOUS→DYING→DEAD` + a
   `dying_final_round` boolean) conflates **mortality** with
   **consciousness/ability to act**, so *dying + conscious* is unrepresentable
   and "fight while dying" is a hack (`combat/services.py:794-801`).
2. **Combat action-eligibility is hardcoded on `vitals.status`** and bypasses
   the capability/condition system entirely. A condition that should
   incapacitate does not stop a combat declaration today.

## Verified system state (what exists, what doesn't)

Code-verified 2026-05-29 (the architecture doc was stale):

- **[BUILT & WIRED]** Capability → available-action pipeline:
  `get_capability_sources_for_character` → `get_available_actions` →
  `_match_approaches` → the **CHALLENGE backend** in
  `actions/player_interface.py` → dispatch → `resolve_challenge`.
- **[BUILT & WIRED]** Conditions impairing capabilities already gate
  availability: a `ConditionCapabilityEffect` driving a capability to ≤0 drops
  its sources (`mechanics/services.py:575-595`), removing capability-derived
  actions.
- **[GAP] Combat bypasses this** — `_combat_actions` surfaces techniques
  directly; eligibility is hardcoded on `vitals.status`
  (`combat/services.py:565, 794, 1236, 2495`). Combat techniques are not gated
  by capability impairment.
- **[GAP] Presence-only gating** — capabilities gate by `value > 0`; there is
  **no `min_value` threshold** on `Application`/`ChallengeApproach`/`Technique`.
  Graduated per-technique requirements ("movement ≥ N for a running start") do
  not exist.
- **[GAP] No unified effective-value fn** — condition / trait-derivation /
  technique-grant sources are siloed; conditions' `get_capability_value`
  returns *condition-only* (0 baseline for an un-impaired capability).
- **[BUILT, NOT WIRED]** `SituationInstance`/`ChallengeInstance` (no
  instantiation service; test-factory only) — out of scope here.

## Scope

**In scope (the full "accommodate it" build, grounded in reality):**
1. Per-technique **capability-requirement model** (the missing threshold gap).
2. Combat eligibility routed through **capability/agency**, reusing the
   existing condition→capability mechanism.
3. **Vitals decouple** to a mortality marker.
4. **Dying = staged bleed-out condition.**
5. **Foundational capability baselines** so an un-impaired character is "able."

**Out of scope (consume / defer):** the challenge content layer
(`Situation`/`ChallengeInstance` instantiation service), unifying trait/technique
capability sources for the challenge backend, the `CharacterModifier`→capability
wiring, graduated requirements beyond what combat needs. The consequence-pool
roll reconciliation is **PR B** (#560/#561).

## Design

### 1. Foundational capabilities + composable baselines

Foundational capacities — `awareness`, `movement`, `limb_use`, … (extensible)
— modeled as `CapabilityType` rows. A character's value for one is **composed
from multiple sources**, not a single innate constant:

`get_effective_capability_value(character, capability) -> int` =
`innate_baseline + CharacterModifier(target_capability) + condition_modifiers`,
floored at 0.

- **Innate baseline** — the default every character has (primitive/default-
  backed, per "so basic they may be enums").
- **`CharacterModifier` on a capability-typed `ModifierTarget`** — this is how
  **distinctions** (e.g. "Crippled" → negative `movement`) and, later,
  **species** (winged → grants `flight`; aquatic → `swim`; extra limbs →
  higher `limb_use`) impair or enhance foundational capabilities. The
  `ModifierTarget.target_capability` link and `create_distinction_modifiers`
  **already exist** — they are just not yet read into capability values. This
  PR wires that link for foundational capabilities (closing a BUILT-NOT-WIRED
  gap). Species itself is unbuilt, but the model accommodates it the moment it
  grants `CharacterModifier`s or capability sources — no new mechanism needed.
- **Condition modifiers** — the existing `ConditionCapabilityEffect` (transient
  impairment).

This effective value is the agency/requirement value (intrinsic capacity from
identity + transient state). It is distinct from the challenge backend's
*per-source* action paths (unchanged). Trait-derivation contributions
(`TraitCapabilityDerivation`) to baselines remain a follow-up — additive when
wired, no re-architecture.

### 2. Per-technique capability requirements (new model)

`TechniqueCapabilityRequirement` (SharedMemoryModel, in `world/magic` alongside
`TechniqueCapabilityGrant`):
- `technique` FK → `Technique`
- `capability` FK → `conditions.CapabilityType`
- `minimum_value` PositiveIntegerField (default 1 = presence)

A technique declares what capacities it needs: "Flame Lance requires
`awareness ≥ 1`"; "Two-handed cleave requires `limb_use ≥ 2`"; "Charge requires
`movement ≥ N`". (Style-level requirements that techniques inherit are a noted
future extension; v1 is technique-level.)

`technique_performable(character, technique) -> bool` = `not is_dead(character)`
**and** every `TechniqueCapabilityRequirement` met against
`get_effective_capability_value`. Per-technique — the immobilized-but-conscious
mage keeps `awareness`, so consciousness-only techniques stay available while
movement techniques drop.

### 3. Combat uses capabilities for eligibility

Replace the hardcoded `vitals.status` gates (`combat/services.py:565, 794-801,
1236-1238, 2495-2509`):
- `_combat_actions` (player_interface) filters surfaced techniques by
  `technique_performable`.
- Participant declare-eligibility = `not dead` **and** has ≥1 performable
  technique (fully-incapacitated characters surface nothing → cannot act;
  dying+conscious can act if their techniques' requirements hold).
- `can_join_encounter` / target-validity = mortality (`not dead`) as
  appropriate.
- Dying→dead consumption replaced by bleed-out condition progression (below).

### 4. Incapacitation & dying as conditions

- **Unconscious / Slept / Stunned** = `ConditionTemplate`s whose
  `ConditionCapabilityEffect` drives `awareness` (and/or other foundational
  capabilities) to 0 — so all techniques requiring awareness become
  unperformable. No special vitals state, no `incapacitates` boolean.
- **Immobilized / Bound / Grounded** impair `movement` / `limb_use` / a flight
  capability — granularly removing only the techniques that need them.
- **Bleeding Out (Dying)** = a **staged** `ConditionTemplate`; `ConditionStage`
  per-stage `resist_check_type` + `resist_difficulty` give worsening
  stabilization odds; terminal stage sets `life_state = DEAD`. Does **not**
  impair `awareness` — dying characters stay able to act. Stabilization =
  curing the condition. Combat round resolution advances active bleed-out
  conditions (resist per stage; fail advances; terminal → dead). Non-combat
  progression deferred (#523).

These `ConditionTemplate`s + foundational `CapabilityType`s are authored content
(admin/seed); this PR provides the **mechanism** + factory-built rows for tests.

### 5. Vitals slim-down

`CharacterVitals` keeps `health`, `max_health`, `base_max_health`, `died_at`.
Replace the 4-state `status` with `life_state` ∈ `{ALIVE, DEAD}`. Drop
`dying_final_round`, `unconscious_at` (now condition-derived). `is_dead` /
`is_alive` read `life_state`. Data migration: `ALIVE→ALIVE`; `UNCONSCIOUS→ALIVE`
+ Unconscious condition; `DYING→ALIVE` + Bleeding-Out condition; `DEAD→DEAD`.

### Sequencing (no functional gap)

PR A keeps the *existing* damage logic but retargets its output: knockout →
apply Unconscious condition; death-threshold → apply Bleeding-Out condition
(instead of `vitals.status` writes). Combat still produces incapacitation/death
immediately, now condition-driven and capability-gated. PR B (#560/#561) later
swaps the binary/ad-hoc internals for the consequence-pool pipeline.

## Anti-reinvention ledger

| Surface | Verdict |
|---|---|
| capability→action pipeline, CHALLENGE backend | REUSE (untouched) |
| `ConditionCapabilityEffect`, `get_capability_value`, condition apply/cure, `ConditionStage` resist | REUSE |
| `CapabilityType`, `TechniqueCapabilityGrant` (pattern) | REUSE |
| `CharacterModifier` + `ModifierTarget.target_capability`, `create_distinction_modifiers` | REUSE + WIRE (distinctions/species impair/enhance foundational capabilities; link exists, now read into values) |
| `TechniqueCapabilityRequirement` (technique → capability + min_value) | NEW |
| `get_effective_capability_value` (innate + CharacterModifier + conditions) | NEW |
| foundational capability baselines (innate defaults, composable) | NEW |
| `technique_performable` + combat eligibility refactor | NEW |
| `CharacterVitals.life_state` (ALIVE/DEAD) replacing `status` | NEW (slim) |
| Unconscious / Bleeding-Out conditions + foundational capabilities | NEW (mechanism; content authored) |

## Testing

- `get_effective_capability_value` (baseline, condition-impaired, floored).
- `technique_performable` matrix: conscious/unconscious/immobilized vs
  awareness-only / movement / limb_use techniques; dead → nothing.
- Combat eligibility: dying+conscious can declare; unconscious cannot; loss
  condition fires when all PCs unperformable-or-dead.
- Bleed-out: staged resist advances to death; stabilization (cure) halts;
  dying+conscious still acts mid-progression.
- Damage path now applies conditions (not `vitals.status` writes).
- Migration test: existing rows map correctly.
- Two-tier (SQLite inner loop; `@tag("postgres")` only where forced); full
  no-keepdb regression. Suites: `world.vitals`, `world.combat`,
  `world.conditions`, `world.magic`, `world.mechanics`, `actions`.

## Deferred follow-ups (file at PR time)

- PR B (#560/#561): consequence-pool reconciliation of the rolls.
- Style-level technique requirements (inherited by techniques).
- **Species** capability grants (winged→`flight`, aquatic→`swim`, extra
  limbs→`limb_use`) — species is unbuilt; the composable effective-value model
  accommodates it via `CharacterModifier`/capability grants with no new
  mechanism. Distinctions impairing/enhancing foundational capabilities
  (e.g. "Crippled") are **in scope** here via the wired
  `CharacterModifier`→`target_capability` link.
- Trait-derivation (`TraitCapabilityDerivation`) contributions to foundational
  baselines, and a unified effective-value across the challenge backend's
  per-source paths — additive follow-ups.
- Non-combat / time-based bleed-out progression (#523).
- `Situation`/`ChallengeInstance` instantiation service (live challenge
  content) — separate from this PR.
- Read-model updates (#521 status panel, #522 `{status}` slot, #553 conditions
  on CombatantsList).
