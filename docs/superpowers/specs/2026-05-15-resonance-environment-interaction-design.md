# Resonance-Environment Interaction — Design

**Status:** Draft (brainstorm complete 2026-05-15)
**Owner:** Tehom (magic + core infrastructure)
**Supersedes the affinity portion of:** `docs/superpowers/specs/2026-05-14-magic-story-pipeline-slice-design.md`
**Builds on:** brother's `docs/plans/2026-05-14-room-cascade-resonance-unification.md` (merged as #444)

## Why this spec exists

Brother's PR #444 collapsed `magic.RoomAuraProfile`/`RoomResonance` into the `locations`
cascade and **explicitly deferred** a "technique pre-cast backfire trigger" follow-up. The
magic-story slice's affinity-intensity mechanism (originally T6 `has_affinity_resonance`
filter operator, T7 `compute_intensity_difficulty`, T13e seeded rooms, T15 wrappers) was
built against the now-deleted models and must be reworked. Rather than re-port the thin
single-factor helper, this spec designs the **resonance-environment interaction primitive**
— a core magic-physics mechanism that subsumes brother's deferred backfire trigger and is
the seam his richer formula later extends without changing call sites.

This is a foundational magic primitive, not slice-local content. The magic-story slice is
its first consumer.

## Terminology

Per `docs/roadmap/combat.md`: **"clash" is reserved** for the planned combat
clash-of-wills feature and MUST NOT be used here. The opposing-resonance outcome is
**"backfire"** (matching brother's deferred trigger name); the aligned outcome is
**"amplification"**; the caster-degrades-the-place outcome is **"defilement"**. Never "clash".

## The magic lore this encodes

- **The Abyss corrupts.** Abyssal magic infects/corrupts the worldly — both primal *casters*
  and primal *places*. It is the aggressor toward Primal.
- **The Celestial is too pure for the world.** It does not corrupt; it is repelled by
  worldly things and only ever gets rejected/pushed out when away from celestial places.
  Celestial places reject all worldly magic.
- **Rock-paper-scissors, not symmetric opposition:** Primal beats Celestial beats Abyssal
  beats Primal. The interaction is a *directed* relationship, asymmetric per ordered
  (caster-affinity, place-affinity) pair.

## The 9 directed affinity interactions

Stated as "**caster's magic affinity** casting in **place affinity** → outcome." These are
authored `AffinityInteraction` rows (data; staff-tunable). No off-diagonal NEUTRAL cells —
every pairing interacts.

| # | Caster | Place | valence | kind | aggressor (default direction) | severity |
|---|--------|-------|---------|------|-------------------------------|----------|
| 1 | Celestial | Celestial | ALIGNED | AMPLIFY | environment (boon to caster) | 1.0 |
| 2 | Celestial | Abyssal | OPPOSED | REJECT | environment (room harms working) | strong (1.0) |
| 3 | Celestial | Primal | OPPOSED | REPEL | environment (room harms working) | mild (0.3) |
| 4 | Abyssal | Celestial | OPPOSED | REJECT | environment (room harms working) — *Hallowed Rejection* | strong (1.0) |
| 5 | Abyssal | Abyssal | ALIGNED | AMPLIFY | environment (boon to caster) | 1.0 |
| 6 | Abyssal | Primal | OPPOSED | CORRUPT | **caster** (caster defiles the place) | strong (1.0) |
| 7 | Primal | Celestial | OPPOSED | REJECT | environment (room harms working) | strong (1.0) |
| 8 | Primal | Abyssal | OPPOSED | CORRUPT | environment (place corrupts the caster) | strong (1.0) |
| 9 | Primal | Primal | ALIGNED | AMPLIFY | environment (boon to caster) | 1.0 |

Asymmetries this encodes: Abyssal corrupts Primal in *both* arrangements (#6 defiles a
primal place; #8 a primal caster is corrupted by an abyssal place) — same `kind=CORRUPT`,
default direction differs by which side is the environment. Celestial only ever gets
rejected/repelled when away from celestial places (#2 strong, #3 mild) and never corrupts.
Celestial places reject all worldly magic (#4 abyssal strong, #7 primal).

**Runtime relative-magnitude can flip the CORRUPT pairs' direction.** A weak abyssal caster
in a *strong* primal place cannot defile it (the place's magnitude dominates → no
defilement, possibly mild backlash); a vastly stronger abyssal caster in a weak primal
place defiles it (caster→area). The `AffinityInteraction.aggressor` is the *default*
direction; the primitive computes the actual direction by comparing caster opposing-strength
to place magnitude.

## Architecture — three layers

| Layer | What | Form |
|---|---|---|
| **Mechanism** | `evaluate_resonance_environment()` | core service in `world/magic/services/resonance_environment.py` (sibling of `accrue_corruption`) |
| **Tuning** | the 9 `AffinityInteraction` rows + scalar coefficients | `AffinityInteraction` model (seeded, admin-editable) + `ResonanceEnvironmentConfig` singleton |
| **Content** | the authored scars/boons that react | data-driven: ConditionTemplate + reactive TriggerDefinition + FlowDefinition |

This honors "no service functions for authored content": the primitive is a core
magic-physics mechanism (peer of corruption/soulfray), and authored content stays
data-driven and merely `CALL_SERVICE_FUNCTION`s into it.

### The primitive

```python
# src/world/magic/services/resonance_environment.py

class ResonanceValence(models.TextChoices):
    ALIGNED  = "aligned",  "Aligned (amplifies)"
    OPPOSED  = "opposed",  "Opposed"

class ResonanceDirection(models.TextChoices):
    ENVIRONMENT_DOMINANT = "environment", "Environment affects the caster/working"
    CASTER_DOMINANT      = "caster",      "Caster affects the place (defilement)"
    BALANCED             = "balanced",    "Mutual backlash"

@dataclass(frozen=True)
class ResonanceEnvironmentEffect:
    valence: str                 # ResonanceValence value; "" when no interaction
    kind: str                    # AffinityInteractionKind value; "" when none
    direction: str               # ResonanceDirection value
    magnitude: int               # 0 when no interaction; >0 scales boon or harm
    source_affinity: Affinity | None
    environment_affinity: Affinity | None

def evaluate_resonance_environment(
    *,
    caster: ObjectDB,
    room: ObjectDB,
    technique: Technique | None = None,
) -> ResonanceEnvironmentEffect:
    """How a place of power's resonance reacts to a caster/working.

    `technique=None` → presence-time evaluation (no technique-resonance factor;
    used by the deferred presence-escalation work). `technique=...` →
    cast-time evaluation (the slice's path).

    Mechanism only. Returns the interaction; never applies effects. The
    reactive flow branches on the result and applies authored content.
    """
```

**v1 formula** (coefficients live in `ResonanceEnvironmentConfig`, staff-tunable):

1. Determine the working's affinity: from `technique.gift.resonances` → dominant
   affinity (cast-time); or `caster.aura` dominant affinity (presence-time, `technique=None`).
2. Determine the place's dominant resonance affinity: over the room's cascade resonance
   rows, the affinity whose summed `effective_value(room, resonance=r)` is largest.
   Tiebreak on equal sums by `Affinity.name` ascending (deterministic, reproducible tests).
3. Look up the `AffinityInteraction` row for (working_affinity, place_affinity). Diagonal →
   ALIGNED/AMPLIFY. Off-diagonal → the authored row.
4. `place_magnitude` = summed `locations.effective_value(room, resonance=r)` over the
   place-affinity resonances.
5. `caster_alignment` = `caster.aura.<working_affinity>` percentage (0–100) / 100.
   `CharacterAura` is a OneToOne that may not exist for non-character ObjectDBs (NPCs,
   constructs). Missing aura → treat `caster_alignment` as 0 (no interaction; inert
   effect). Documented in the primitive's docstring + an explicit unit test.
6. `raw = place_magnitude * caster_alignment * interaction.severity_multiplier *
   config.base_coefficient`.
7. `direction`: start from `interaction.aggressor`. For CORRUPT pairs, compare a
   caster-strength proxy (caster aura% × an authored caster-power scalar) to
   `place_magnitude`: caster ≫ place → CASTER_DOMINANT (defilement); place ≫ caster →
   ENVIRONMENT_DOMINANT; within `config.balanced_band` → BALANCED.
8. `magnitude = round(raw)`. If 0 → return an inert effect (`valence=""`, `magnitude=0`):
   the flow short-circuits, no condition applied.

All scalars (`base_coefficient`, `caster_power_scalar`, `balanced_band`, and the
OPPOSED-magnitude→check-difficulty mapping) are `ResonanceEnvironmentConfig` fields.
Brother's richer follow-up replaces steps 5–7's body; call sites and authored content
do not change.

### Data models

```python
# world/magic/constants.py
class AffinityInteractionKind(models.TextChoices):
    AMPLIFY = "amplify", "Amplify"
    REJECT  = "reject",  "Reject"
    REPEL   = "repel",   "Repel"
    CORRUPT = "corrupt", "Corrupt"

class AffinityInteractionAggressor(models.TextChoices):
    ENVIRONMENT = "environment", "Environment"
    CASTER      = "caster",      "Caster"

# world/magic/models/ (new module, e.g. resonance_environment.py)
class AffinityInteraction(SharedMemoryModel):
    source_affinity = FK(Affinity, on_delete=PROTECT, related_name="interactions_as_source")
    environment_affinity = FK(Affinity, on_delete=PROTECT, related_name="interactions_as_environment")
    valence = CharField(choices=ResonanceValence.choices)
    kind = CharField(choices=AffinityInteractionKind.choices)
    aggressor = CharField(choices=AffinityInteractionAggressor.choices)
    severity_multiplier = DecimalField(max_digits=4, decimal_places=2, default=Decimal("1.00"))
    class Meta:
        constraints = [UniqueConstraint(fields=["source_affinity", "environment_affinity"],
                                        name="unique_affinity_interaction_pair")]

class ResonanceEnvironmentConfig(SharedMemoryModel):
    """Singleton (pk=1), lazy-created — mirrors CorruptionConfig / ResonanceGainConfig."""
    base_coefficient = DecimalField(...)        # raw scaling
    caster_power_scalar = DecimalField(...)     # caster-strength proxy for defilement
    balanced_band = PositiveIntegerField(...)   # |caster-place| within this → BALANCED
    backfire_base_difficulty = PositiveIntegerField(...)   # OPPOSED → perform_check base
    backfire_difficulty_per_magnitude = DecimalField(...)  # + magnitude * this
```

Access via `get_resonance_environment_config()` (lazy-create pk=1), the established pattern.

## Bounded slice scope (the magic-story rework)

The slice ships **cast-time, both poles**, replacing the dead T6/T7/T13e code:

1. **Universal cast subscriber via a ubiquitous baseline condition (no infra change).**
   There is no global/non-condition Trigger mechanism in the codebase (verified: even
   soul tether's `CORRUPTION_ACCRUING` subscriber is a `TriggerDefinition` row installed
   via a condition's `reactive_triggers` M2M — `source_condition` is always satisfied).
   Rather than add a global-trigger schema+dispatch path, universality is achieved by a
   **ubiquitous baseline `ConditionTemplate` "Magically Attuned"** whose
   `reactive_triggers` M2M holds the resonance-environment `TECHNIQUE_CAST`
   `TriggerDefinition`. Every magic-capable character receives "Magically Attuned" (granted
   at CG finalization / first cast — for the slice's pipeline test it is applied in
   `setUp` exactly as the marker condition is today). The reactive Trigger then
   auto-installs through the **existing T4/T8/T10 plumbing** with a valid
   `source_condition`. Scars (Hallowed Rejection etc.) are SEPARATE conditions that
   **modulate** severity (via `AffinityInteraction` / config), NOT separate trigger
   installers. Zero schema change; the "Infra addition" section is removed.
2. **Reactive flow rework.** Event timing: v1 subscribes to **`TECHNIQUE_CAST`**
   (post-resolve — the environment reacts *after* the working fires; the backfire is the
   place's response to a completed working). Brother's plan said "pre-cast"; a true
   `TECHNIQUE_PRE_CAST` variant that could *block or modify* the cast before it resolves
   is a deferred refinement (it needs cancel/modify-payload semantics out of scope here).
   The seeded FlowDefinition's first step calls
   `evaluate_resonance_environment(caster, room, technique)`. Branches:
   - inert (magnitude 0) → end (no effect).
   - OPPOSED → `perform_check` at config-derived difficulty → branch by `CheckOutcome`
     → apply authored backfire conditions (the existing T13b/f Hallowed Rejection
     content: Tempered/Singed/Burning/Hallowed Burn) — only when `kind` ∈ {REJECT, REPEL}.
   - ALIGNED → apply an authored amplification condition (new: "Empowered by Resonant
     Ground" — a boon ConditionTemplate; magnitude scales it). No check (a boon).
   - OPPOSED/CORRUPT with CASTER_DOMINANT → **deferred** (defilement); the flow treats it
     as inert for now (documented).
3. **Both poles authored.** OPPOSED: existing Hallowed Threshold story content (the
   abyssal-caster-in-celestial-place case, pair #4). ALIGNED: a minimal aligned boon
   (abyssal caster in an abyssal place, pair #5) — one boon ConditionTemplate + an
   `AffinityInteraction` ALIGNED row + a pipeline subtest asserting the boon condition.
4. **Seeded content via the cascade.** Rooms author resonance via
   `magic.services.gain.tag_room_resonance(room_profile, resonance)` then adjust the
   cascade row's `value` for intensity tiers (low vs high place magnitude) — NOT the
   deleted `RoomResonance`. Seed the 9 `AffinityInteraction` rows + the
   `ResonanceEnvironmentConfig` singleton.
5. **Pipeline test rework.** `expected_difficulty` per subtest is recomputed from the
   formula (place magnitude × caster aura% × multiplier × config) instead of the old
   count×5. Caster is seeded with an abyssal-dominant `CharacterAura`. Subtests cover
   OPPOSED (4 outcomes × 2 place-intensity tiers) + an ALIGNED amplification subtest +
   a NEUTRAL-equivalent short-circuit (caster casting in an aligned/own place at low
   magnitude, or a primal caster where no authored backfire content exists) + the
   second-earner Discovery test.

### No infra change to the Trigger model

The earlier draft proposed making `Trigger.source_condition` nullable + an `is_global`
flag. **Removed** — verification showed no global-trigger dispatch path exists
(`TriggerHandler._populate()` filters `Trigger.objects.filter(obj=self.owner)`; `obj` is
also non-null), so a global trigger would be structurally invisible *and* require
touching the dispatch path. The ubiquitous-baseline-condition approach (above) achieves
universality with **zero** Trigger-model change, reusing the proven T4/T8/T10 install path
and the soul-tether precedent exactly. A true global-trigger mechanism is neither needed
nor built here.

### Working-affinity derivation (resolves the multi-affinity gift ambiguity)

A `Gift` has an M2M to `Resonance` (1–2 resonances); two resonances can belong to two
different `Affinity`s, so "the technique's affinity" is not always single-valued. Rule
(deterministic, thematically sound): for a cast-time evaluation, collect the distinct
affinities of `technique.gift.resonances`. For each, look up the `AffinityInteraction`
row against the place's dominant-resonance affinity. **Select the interaction with the
highest `severity_multiplier`** (a mixed working is judged by its most-reactive
component). Tiebreak on equal multipliers by `Affinity.name` ascending (canonical, makes
tests reproducible). Presence-time (`technique=None`) uses the caster's dominant
`CharacterAura` affinity instead (no gift). This rule is part of the v1 formula (step 1)
and is brother-extensible (he may later weight by per-resonance `CharacterResonance`
balance — the call sites and data don't change).

## Out of scope — deferred, but the primitive supports them

These are **not** built in the slice. The primitive's shape (the `direction` field,
`technique`-optional signature) makes them additive, not re-architecture.

1. **Presence-escalation.** Heavily-opposing-scarred/corrupted characters are affected on
   mere *entry* (`MOVED`/arrival), not only on cast. Delivered as a **scar-gated** MOVED
   `TriggerDefinition` installed via the **existing `ConditionTemplate.reactive_triggers`
   M2M** (T4/T8/T10 plumbing — already built). `evaluate_resonance_environment(..., technique=None)`
   already supports presence evaluation. Cheap follow-on; no primitive change.
2. **Defilement (CASTER_DOMINANT).** When a strong opposing caster overpowers a weak place,
   the caster degrades the place's cascade resonance (writes down its `effective_value`).
   The primitive already returns `direction=CASTER_DOMINANT`; the deferred work authors the
   defilement effect.
   - **Soul-tether integration lever (must be preserved by the deferred work):** the
     defilement's caster→world corruption MUST be emitted through the **existing
     interceptable `CORRUPTION_ACCRUING` event** (the one `soul_tether_redirect_handler`
     already subscribes to, per Spec B). Then a Sinner's Hollow can absorb
     world-defilement corruption with zero new wiring — the soul tether bond gains a
     "contains the damage they would do to the world" social-responsibility layer for
     free. Whoever builds defilement routes corruption through the interceptable event,
     never writing corruption directly.
3. **Brother's richer formula.** Steps 5–7 of the v1 formula are deliberately simple.
   Brother's deferred follow-up enriches the primitive's body (e.g. technique-resonance
   opposition weighting, multi-resonance places, consequence-pool routing). Call sites,
   `AffinityInteraction` data, `ResonanceEnvironmentConfig`, and authored content do not
   change when he does.

## Files this rework touches

- **Delete/replace:** `src/flows/filters/evaluator.py` (`has_affinity_resonance` operator
  — remove; the universal trigger filter no longer needs it), `src/flows/tests/test_filters/test_has_affinity_resonance.py`.
- **Replace:** `src/flows/service_functions/affinity.py` (`compute_intensity_difficulty` +
  `compute_intensity_difficulty_for_character`) → the flow now calls the new primitive via
  `CALL_SERVICE_FUNCTION`. Keep the module only if a thin flow-callable wrapper is needed.
- **New:** `src/world/magic/services/resonance_environment.py` (the primitive),
  `src/world/magic/models/resonance_environment.py` (`AffinityInteraction`,
  `ResonanceEnvironmentConfig`), constants, factory, admin, migration.
- **Rework seed:** `src/integration_tests/game_content/magic.py` — T13e room authoring via
  `tag_room_resonance` + cascade magnitude tuning; seed the 9 `AffinityInteraction` rows +
  config singleton; add the ALIGNED boon ConditionTemplate; the universal cast
  TriggerDefinition + reworked FlowDefinition steps.
- **Rework test:** `src/integration_tests/test_magic_story_pipeline.py` — recomputed
  `expected_difficulty`, abyssal-aura caster setup, ALIGNED subtest, an inert/short-circuit
  subtest, and a **CASTER_DOMINANT stub subtest** (strong abyssal caster in a weak primal
  place → primitive returns `direction=CASTER_DOMINANT`; flow short-circuits as inert; the
  test asserts the inert short-circuit and stands as the fill-in point for the deferred
  defilement work).
- **Conditions:** NO change to the `Trigger` model and NO migration for it (the earlier
  nullable/is_global idea is removed). The baseline "Magically Attuned"
  `ConditionTemplate` is authored *seed content* (no schema change) whose
  `reactive_triggers` M2M holds the cast `TriggerDefinition`; it installs via the
  existing T4/T8/T10 path. No trigger-handler change.
- **Docs:** add the magic lore (Abyss corrupts; Celestial too pure; RPS cycle; the 9
  pairs) to `docs/roadmap/magic.md`. Update `docs/roadmap/seed-and-integration-tests.md`.

## Design principles honored

- No "clash" terminology anywhere (combat-reserved).
- Primitive is a core mechanism (peer of corruption); authored content stays data-driven —
  honors "no service functions for authored content."
- Tuning is data (`AffinityInteraction` rows + `ResonanceEnvironmentConfig` singleton),
  staff-editable, no code change to re-tune — honors the user's "levers as data" intent.
- Bridge-direction dep: magic → locations (`effective_value`), the same direction
  `tag_room_resonance` already takes. Locations does not import magic-story content.
- No new SlugField. SharedMemoryModel on all new models. `cached_property` from
  `django.utils.functional` if used.
- The deferred pieces (presence, defilement) reuse already-built plumbing
  (`reactive_triggers` M2M; `CORRUPTION_ACCRUING` event) — no parallel systems, no
  architectural debt.
