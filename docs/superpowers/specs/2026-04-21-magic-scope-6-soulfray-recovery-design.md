# Magic Scope 6 — Soulfray Recovery & Decay

**Status:** Design
**Author:** Dave Brannigan (with Claude)
**Date:** 2026-04-21
**Related specs:**
- `2026-04-12-scope5-magical-alteration-resolution-design.md` (Mage Scars / `PendingAlteration` pipeline)
- `2026-04-16-reactive-layer-design.md` (`CONDITION_STAGE_CHANGED` event)
- `2026-04-18-resonance-pivot-spec-a-threads-and-currency-design.md` (Threads + resonance currency)

## 1. Summary

Scope 6 completes the Soulfray lifecycle by delivering the **recovery half** of the condition: how a character escapes Soulfray once they've fallen into it, how their anima pool refills over time, and how allies can help mitigate the worst aftermath of deep Soulfray during a scene.

Scope 6 ships three primary mechanisms:

1. **Anima Ritual** — the primary magical recovery mechanism. Not yet implemented (only the data models exist). A character performs their personalised ritual in-scene, rolls a check, and spends an outcome-tiered recovery budget on (a) reducing Soulfray severity and (b) refilling their anima pool.
2. **Stabilization (via the generalised Treatment system)** — an in-scene, thread-gated emergency-care attempt by another character. Reduces the severity of nasty aftermath conditions granted by deep Soulfray, or reduces the tier of a pending Mage Scar for the current scene. Failure risks giving the helper Soulfray severity of their own.
3. **Passive decay + daily anima regen** — slow background recovery. Only recovers characters at the lowest Soulfray stage; anyone at stage ≥2 is gated on ritual recovery. Daily anima regen is blocked while any "blocks_anima_regen" stage property is active.

Scope 6 generalises recovery primitives wherever the logic is not intrinsically about Soulfray:

- **Condition passive decay** becomes a data-driven capability of any `ConditionTemplate`.
- **Treatment** becomes a generic system (`TreatmentTemplate` + `TreatmentAttempt`) — Soulfray stabilization is the first authored user.
- **Stage-entry aftermath** becomes a generic capability (`ConditionStage.on_entry_conditions`) — any condition's stage can grant other conditions when entered.

Anima ritual itself stays Soulfray-aware (it is the Soulfray recovery mechanism), but the generic decay and treatment pieces operate without any knowledge of Soulfray.

## 2. Goals & Non-Goals

### Goals

- Deliver `perform_anima_ritual` as a complete service with outcome-tiered recovery budget.
- Give characters a ritual-free slow recovery path at the lowest Soulfray stage so players aren't hard-stuck without a ritual.
- Deliver stabilization so deep-Soulfray characters have an in-scene safety net that other players contribute to.
- Generalise passive decay, treatment, and stage-entry aftermath so future conditions (and future treatments) can reuse the infrastructure without new scheduler code.
- Extend the Soulfray authored stage list from 3 to 5 for tuning headroom. Audere-gating re-seeds to stage 3+ via the existing `AudereThreshold.minimum_warp_stage` pointer.
- Seed reference aftermath conditions so stabilization has something meaningful to reduce in integration tests.

### Non-Goals

- No healing magic (post-scene, out-of-combat restoration) — deferred.
- No changes to Scope 5 Mage Scar authoring or resolution semantics; stabilization feeds into the existing `PendingAlteration` resolution path.
- No changes to Audere's gate logic — only the seeded `AudereThreshold.minimum_warp_stage` value updates.
- No refactor of the Scope 5 `PendingAlteration` model or of Scope 5.5 reactive-layer internals.
- No player-facing UI changes in Scope 6 (web surfaces land in a later scope).
- No new player command authoring for ritual/stabilization at the CLI level (service-layer only; commands or API endpoints land in a later scope).

## 3. Design Principles

- **Condition-generic where possible.** If a behaviour could apply to a future condition (e.g. passive decay, treatment, stage-entry aftermath), author it on `ConditionTemplate` / `ConditionStage` / `TreatmentTemplate` rather than on `SoulfrayConfig`.
- **Anima ritual is a Soulfray-aware service.** The ritual is culturally and mechanically tied to anima/Soulfray; trying to make it generic would create speculative abstraction. It lives in `magic/services/anima.py` as a first-class service.
- **Properties tag stages, not conditions.** `blocks_anima_regen` lives on `ConditionStage.properties`, not on the parent `ConditionTemplate`. Soulfray stage 1 doesn't carry it; stages 2+ do.
- **Scheduler is data-driven.** Daily ticks iterate conditions that opt-in via `passive_decay_per_day > 0` and characters whose active stage properties include `blocks_anima_regen`. No Soulfray FK in scheduler code.
- **Threads as bonds, not combat tool.** Stabilization's bond requirement uses an existing Thread anchored to a relationship track or capstone pointing at the target; reuses Spec A infrastructure, no new bond primitive.
- **Resonance is currency, not scalar.** Treatments cost a flat resonance amount, debited from the helper's `CharacterResonance.balance` for the Resonance on the bond Thread. No severity-scaled or pool-percentage costs.
- **AP is not an in-scene gate.** Ritual and stabilization do not cost AP. Ritual is scene-gated (once per scene per character); stabilization is helper-gated (once per helper per target per scene).
- **Ritual runs in-scene, outside engagement.** Principle 3 from Section 1 made explicit: a character must be in an active Scene and not in a `CharacterEngagement` to invoke the ritual. Stabilization carries the same out-of-engagement gate.

## 4. Model Changes

All concrete models are `SharedMemoryModel`.

### 4.1 `world/conditions` — new fields on existing models

#### `ConditionTemplate`

```python
parent_condition = models.ForeignKey(
    "self", null=True, blank=True, on_delete=models.SET_NULL,
    related_name="aftermath_children",
)
# aftermath conditions point at their primary parent (e.g., soul_ache → soulfray).
# FK is authoritative even before the aftermath is wired into any stage's
# on_entry_conditions — a ConditionTemplate can be authored as "child of
# soulfray" and later wired to specific stages without changing this field.

passive_decay_per_day = models.PositiveIntegerField(default=0)
passive_decay_max_severity = models.PositiveIntegerField(null=True, blank=True)
passive_decay_blocked_in_engagement = models.BooleanField(default=True)
```

Semantics:
- `passive_decay_per_day == 0` opts out of passive decay entirely.
- `passive_decay_max_severity == None` decays at any severity; otherwise decays only when `instance.severity <= this value`. Soulfray sets this to stage 1's ceiling so stages 2+ don't decay passively.
- `passive_decay_blocked_in_engagement == True` halts decay while a **character** target has an active `CharacterEngagement`. Non-character targets (rooms, items) are never engagement-gated regardless of the flag's value.

#### `ConditionInstance`

Add a resolved-at timestamp so decay can mark an instance completed when severity reaches zero. The existing model only tracks `expires_at` (absolute) and `rounds_remaining` (relative); it has no "fully recovered" field.

```python
resolved_at = models.DateTimeField(
    null=True, blank=True,
    help_text="Set when severity decays to 0. Used to filter out completed instances.",
)
# index for scheduler scans:
indexes = [models.Index(fields=["resolved_at"])]
```

Existing filters that assume "active" instances currently query for `expires_at__gt=...` or similar; Scope 6 adds `resolved_at__isnull=True` as the idiomatic "is-active" gate for recovery flows. Existing callers are unaffected since the field defaults to `NULL`.

#### `ConditionStage`

```python
properties = models.ManyToManyField(
    "mechanics.Property", blank=True, related_name="condition_stages_carrying",
)

on_entry_conditions = models.ManyToManyField(
    "conditions.ConditionTemplate",
    through="conditions.ConditionStageOnEntry",
    related_name="applied_on_entry_of",
    blank=True,
)
```

#### `ConditionStageOnEntry` (new through model)

```python
class ConditionStageOnEntry(SharedMemoryModel):
    stage = models.ForeignKey(
        ConditionStage, on_delete=models.CASCADE,
        related_name="on_entry_assocs",
    )
    condition = models.ForeignKey(
        ConditionTemplate, on_delete=models.PROTECT,
    )
    severity = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["stage", "condition"],
                name="unique_on_entry_condition_per_stage",
            ),
        ]
```

### 4.2 `world/conditions` — new models

#### `TreatmentTemplate`

Authored catalog. A treatment defines how one character can attempt to mitigate another character's condition (or a related alteration).

```python
class TreatmentTargetKind(models.TextChoices):
    PRIMARY = "primary", "Primary condition severity"
    AFTERMATH = "aftermath", "Aftermath child condition severity"
    PENDING_ALTERATION = "pending_alteration", "Pending alteration tier"


class TreatmentTemplate(SharedMemoryModel):
    key = models.SlugField(unique=True, max_length=64)
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True)

    target_condition = models.ForeignKey(
        "conditions.ConditionTemplate", on_delete=models.PROTECT,
        related_name="treatments",
    )
    target_kind = models.CharField(max_length=32, choices=TreatmentTargetKind.choices)

    check_type = models.ForeignKey("checks.CheckType", on_delete=models.PROTECT)
    target_difficulty = models.PositiveIntegerField(default=0)
    requires_bond = models.BooleanField(default=False)

    resonance_cost = models.PositiveIntegerField(default=0)
    anima_cost = models.PositiveIntegerField(default=0)

    once_per_scene_per_helper = models.BooleanField(default=True)
    scene_required = models.BooleanField(default=True)

    backlash_severity_on_failure = models.PositiveIntegerField(default=0)
    backlash_target_condition = models.ForeignKey(
        "conditions.ConditionTemplate", null=True, blank=True,
        on_delete=models.PROTECT, related_name="treatment_backlash_source",
    )
    # When null, perform_treatment falls back to target_condition (see 5.2).

    reduction_on_crit = models.PositiveIntegerField(default=0)
    reduction_on_success = models.PositiveIntegerField(default=0)
    reduction_on_partial = models.PositiveIntegerField(default=0)
    reduction_on_failure = models.PositiveIntegerField(default=0)

    def clean(self) -> None:
        # Resonance cost requires a bond, because the resonance is debited from
        # the helper's CharacterResonance row keyed to bond_thread.resonance.
        # Without a bond, there is no Resonance row to debit and the service
        # would crash. Enforce the invariant at the data layer.
        super().clean()
        if self.resonance_cost > 0 and not self.requires_bond:
            from django.core.exceptions import ValidationError  # noqa: PLC0415
            raise ValidationError(
                {"resonance_cost": "resonance_cost > 0 requires requires_bond=True."}
            )
```

> **Note on `prerequisite_key`:** an earlier draft proposed a `prerequisite_key` CharField for plug-in prerequisite callables. There is no project-wide prerequisite registry today (progression uses inheritance-based `AbstractClassLevelRequirement.is_met_by_character`, not a string registry). Scope 6's two seeded treatments don't need a prerequisite hook, so the field is dropped from Scope 6. A future scope that needs treatment-side prerequisite plugins can either add a typed `prerequisite_callable_path` field with a registry, or extend `TreatmentTemplate` via inheritance.

Target-kind choices are placed in `world/conditions/constants.py` per project convention.

#### `TreatmentAttempt`

Audit log of a treatment attempt, one row per invocation.

```python
class TreatmentAttempt(SharedMemoryModel):
    helper = models.ForeignKey(
        "objects.ObjectDB", on_delete=models.PROTECT,
        related_name="treatment_attempts_as_helper",
    )
    target = models.ForeignKey(
        "objects.ObjectDB", on_delete=models.PROTECT,
        related_name="treatment_attempts_as_target",
    )
    scene = models.ForeignKey(
        "scenes.Scene", on_delete=models.PROTECT,
        related_name="treatment_attempts",
    )
    treatment = models.ForeignKey(
        "conditions.TreatmentTemplate", on_delete=models.PROTECT,
        related_name="attempts",
    )

    thread_used = models.ForeignKey(
        "magic.Thread", null=True, blank=True,
        on_delete=models.PROTECT,
        related_name="treatment_attempts",
    )

    target_condition_instance = models.ForeignKey(
        "conditions.ConditionInstance", null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="treatment_attempts_targeting_instance",
    )
    target_pending_alteration = models.ForeignKey(
        "magic.PendingAlteration", null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="treatment_attempts_targeting_alteration",
    )

    outcome = models.CharField(max_length=32, choices=CheckOutcome.choices)
    severity_reduced = models.IntegerField(default=0)
    tiers_reduced = models.IntegerField(default=0)
    helper_backlash_applied = models.IntegerField(default=0)
    resonance_spent = models.IntegerField(default=0)
    anima_spent = models.IntegerField(default=0)

    created_at = models.DateTimeField()
    # Stamped at save with get_ic_now() in the service; no auto_now_add
    # because IC time diverges from real time. See 5.2 step 9.

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["helper", "target", "scene", "treatment"],
                condition=Q(treatment__once_per_scene_per_helper=True),
                name="unique_treatment_attempt_per_helper_scene",
            ),
        ]
```

`helper` and `target` FK `ObjectDB` (not `CharacterSheet`) to match `ConditionInstance.target`'s shape. The service resolves `CharacterSheet` ↔ `ObjectDB` at the service boundary (see Section 5.2).

### 4.3 `world/magic` — `SoulfrayConfig` changes and new model

#### `SoulfrayConfig` — fields added, none removed

Existing fields remain unchanged in Scope 6. New fields:

```python
ritual_budget_critical_success = models.PositiveIntegerField()
ritual_budget_success = models.PositiveIntegerField()
ritual_budget_partial = models.PositiveIntegerField()
ritual_budget_failure = models.PositiveIntegerField(
    validators=[MinValueValidator(1)],
    help_text="Must be > 0; failure always returns some anima.",
)
ritual_severity_cost_per_point = models.PositiveIntegerField(default=1)
```

No existing fields move. The earlier draft's aspirational phrasing "other tunables move to the Soulfray template where possible" is withdrawn — the only field conceptually re-homed in Scope 6 is the anima-regen gate, which is expressed via the `blocks_anima_regen` Property on `ConditionStage.properties` (new Property, not a config field migration).

#### `AnimaConfig` (new, lives in `magic/models/anima.py`)

```python
class AnimaConfig(SharedMemoryModel):
    daily_regen_percent = models.PositiveIntegerField(
        default=5,
        help_text="% of CharacterAnima.maximum regenerated per daily tick",
    )
    daily_regen_blocking_property_key = models.SlugField(
        default="blocks_anima_regen",
        help_text="Property key on a ConditionStage that blocks anima regen",
    )

    @classmethod
    def get_singleton(cls) -> "AnimaConfig":
        # Singleton-by-convention pattern matching SoulfrayConfig:
        # fetch-or-create with pk=1.
        obj, _ = cls.objects.get_or_create(pk=1, defaults={})
        return obj
```

#### `CharacterAnimaRitual.target_difficulty` (new field)

A per-character ritual difficulty:

```python
target_difficulty = models.PositiveIntegerField(default=0)
```

Difficulty is a property of the per-character ritual (some rituals are harder than others) rather than a property of Soulfray, so it lives on `CharacterAnimaRitual`, not on `SoulfrayConfig`.

### 4.4 File layout — convert `magic/models.py` and `magic/services.py` into packages

This scope converts the flat modules into topically-split packages. Every existing model and service moves into a thematic submodule; `__init__.py` re-exports the full public surface so external callers are unaffected.

#### `magic/models/` submodule split

| File | Contents |
|------|----------|
| `affinity.py` | `Affinity`, `Resonance` |
| `aura.py` | `CharacterAura`, `CharacterResonance`, `CharacterAffinityTotal` |
| `anima.py` | `CharacterAnima`, `CharacterAnimaRitual`, `AnimaRitualPerformance`, **new** `AnimaConfig` |
| `gifts.py` | `Gift`, `CharacterGift`, `Tradition`, `CharacterTradition` |
| `techniques.py` | `EffectType`, `TechniqueStyle`, `Restriction`, `IntensityTier`, `Technique`, `TechniqueCapabilityGrant`, `CharacterTechnique`, `TechniqueOutcomeModifier` |
| `cantrips.py` | `Cantrip` |
| `motifs.py` | `Facet`, `CharacterFacet`, `Motif`, `MotifResonance`, `MotifResonanceAssociation` |
| `soulfray.py` | `SoulfrayConfig` (+ new ritual-budget fields), `MishapPoolTier` |
| `alterations.py` | `MagicalAlterationTemplate`, `PendingAlteration`, `MagicalAlterationEvent` |
| `threads.py` | `Thread`, `ThreadLevelUnlock`, `ThreadPullCost`, `ThreadXPLockedLevel`, `ThreadPullEffect` |
| `weaving.py` | `ThreadWeavingUnlock`, `CharacterThreadWeavingUnlock`, `ThreadWeavingTeachingOffer` |
| `rituals.py` | `Ritual`, `RitualComponentRequirement`, `ImbuingProseTemplate` |
| `reincarnation.py` | `Reincarnation` |

#### `magic/services/` submodule split

| File | Contents |
|------|----------|
| `aura.py` | `calculate_affinity_breakdown`, `get_aura_percentages` |
| `anima.py` | `deduct_anima`, **new** `perform_anima_ritual`, **new** `anima_regen_tick` |
| `techniques.py` | `get_runtime_technique_stats`, `calculate_effective_anima_cost`, `use_technique`, private technique helpers |
| `alterations.py` | `create_pending_alteration`, `validate_alteration_resolution`, `resolve_pending_alteration`, `has_pending_alterations`, `staff_clear_alteration`, `get_library_entries`, **new** `reduce_pending_alteration_tier` |
| `soulfray.py` | `calculate_soulfray_severity`, `get_soulfray_warning`, `select_mishap_pool`, `_handle_soulfray_accumulation`, `_resolve_mishap`. **Move-only refactor** — Scope 6 does not change these callers' behaviour. |
| `resonance.py` | `grant_resonance`, `spend_resonance_for_imbuing`, `spend_resonance_for_pull`, `resolve_pull_effects`, `preview_resonance_pull`, private pull/anchor helpers |
| `threads.py` | `weave_thread`, `accept_thread_weaving_unlock`, cap/lock math, `imbue_ready_threads`, thread queries, damage reduction |

`types.py` converts to `types/` because Scope 6 adds new dataclasses (see Section 7).

### 4.5 Exceptions — typed, per project convention

New exceptions in `magic/exceptions.py` (or a new `magic/exceptions/recovery.py` module if the flat file grows too large):

```python
class NoRitualConfigured(MagicError): user_message = "You don't have an anima ritual configured."
class RitualAlreadyPerformedThisScene(MagicError): user_message = "You've already performed your ritual in this scene."
class CharacterEngagedForRitual(MagicError): user_message = "You cannot perform a ritual during combat."
class AnimaPoolAtMaximum(MagicError): user_message = "Your anima pool is already full."
```

New exceptions in `world/conditions/exceptions.py` (new file if not present):

```python
class TreatmentError(Exception):
    user_message = "Treatment failed."

class TreatmentTargetMismatch(TreatmentError): user_message = "This treatment cannot target that effect."
class TreatmentParentMismatch(TreatmentError): user_message = "The targeted aftermath isn't linked to this treatment's parent condition."
class NoSupportingBondThread(TreatmentError): user_message = "You need a supporting bond with the target to attempt this treatment."
class TreatmentAlreadyAttempted(TreatmentError): user_message = "You've already attempted this treatment on the target this scene."
class TreatmentScenePrerequisiteFailed(TreatmentError): user_message = "You cannot attempt this treatment right now."
class TreatmentResonanceInsufficient(TreatmentError): user_message = "You don't have enough resonance to attempt this."
class TreatmentAnimaInsufficient(TreatmentError): user_message = "You don't have enough anima to attempt this."
class HelperEngagedForTreatment(TreatmentError): user_message = "You cannot treat someone while engaged in combat."
```

Views expose `exc.user_message` per project convention; never `str(exc)`.

## 5. Service Behaviour

### 5.1 `perform_anima_ritual(character_sheet, scene) -> RitualOutcome`

Lives in `magic/services/anima.py`.

**Boundary translation:** Callers pass `CharacterSheet`; the service resolves `character_sheet.character` to the `ObjectDB` instance needed for `perform_check` and engagement queries.

**Preflight gates:**
1. Resolve the configured ritual via the reverse accessor: `ritual = getattr(character_sheet, "anima_ritual", None)`. (`CharacterAnimaRitual.character` is a OneToOneField to `CharacterSheet` with `related_name="anima_ritual"`, per `world/magic/models.py:600`.) If `ritual is None`, raise `NoRitualConfigured`.
2. `CharacterEngagement.objects.filter(character=character_sheet.character).exists()` is `False`; else raise `CharacterEngagedForRitual`.
3. `scene` is active and the character is a participant; else raise `TreatmentScenePrerequisiteFailed` (or a ritual-side equivalent — both use the same precondition helper).
4. `AnimaRitualPerformance.objects.filter(ritual=ritual, scene=scene).exists()` is `False`; else raise `RitualAlreadyPerformedThisScene`. (Performer is derivable via `performance.ritual.character`; `AnimaRitualPerformance.target_character` per the existing model means "other character the ritual was performed with" and is intentionally unset by `perform_anima_ritual` for solo rituals.)

**Execute:**
1. Resolve check via `perform_check(character_sheet.character, check_type=ritual.check_type, target_difficulty=ritual.target_difficulty)`. (`CharacterAnimaRitual.target_difficulty` is the new field added in Section 4.3.) The check returns a `CheckResult` with `.outcome: CheckOutcome`.
2. Look up budget from outcome:
   - `CheckOutcome.CRITICAL_SUCCESS` → `SoulfrayConfig.ritual_budget_critical_success`
   - `CheckOutcome.SUCCESS` → `...budget_success`
   - `CheckOutcome.PARTIAL` (or the nearest equivalent outcome — exact mapping settled during implementation against `world.traits` outcome names) → `...budget_partial`
   - Any failure outcome → `...budget_failure` (validator ensures > 0)
3. **Spend severity first** while budget > 0 and an active Soulfray `ConditionInstance` has `severity > 0`:
   - Call `decay_condition_severity(soulfray_instance, amount=1)` (new helper, Section 5.3).
   - Deduct `SoulfrayConfig.ritual_severity_cost_per_point` from budget.
4. **Refill anima with leftover:** `CharacterAnima.current_anima = min(current + remaining_budget, maximum)`.
5. **Crit override:** if outcome is `CheckOutcome.CRITICAL_SUCCESS`, force `current_anima = maximum` after step 4 regardless of leftover budget. On a crit, the budget effectively governs only severity reduction; anima always tops up. This interaction is called out here and in the tuning section (8.7) so balance tuning accounts for it.
6. Persist `AnimaRitualPerformance` with `ritual=ritual`, `scene=scene`, `was_successful=(outcome in {CRITICAL_SUCCESS, SUCCESS})`, `anima_recovered`, `outcome` (CheckOutcome value), `severity_reduced`. `target_character` left unset (solo ritual; field semantics belong to a future co-performance scope).
7. Return `RitualOutcome`.

**Transactional boundary:** entire service wrapped in `transaction.atomic()` with `select_for_update()` on the `CharacterAnima` row and the active Soulfray `ConditionInstance` (if any).

### 5.2 `perform_treatment(helper_sheet, target_sheet, scene, treatment, target_effect, bond_thread=None) -> TreatmentOutcome`

Lives in `world/conditions/services.py`.

**Signature:**
- `helper_sheet`: `CharacterSheet` (the character offering treatment)
- `target_sheet`: `CharacterSheet` (the recipient)
- `scene`: `Scene`
- `treatment`: `TreatmentTemplate`
- `target_effect`: `ConditionInstance | PendingAlteration`
- `bond_thread`: `Thread | None` (required when `treatment.requires_bond`)

Internally resolves `helper = helper_sheet.character` and `target = target_sheet.character` for ObjectDB-keyed queries.

**Preflight gates (in order):**
1. **Type match:**
   - `target_kind == PENDING_ALTERATION` requires `isinstance(target_effect, PendingAlteration)`; else raise `TreatmentTargetMismatch`.
   - `target_kind in {PRIMARY, AFTERMATH}` requires `isinstance(target_effect, ConditionInstance)`; else raise `TreatmentTargetMismatch`.
2. **Parent/primary match** (discriminates PRIMARY vs AFTERMATH since both use `ConditionInstance`):
   - `target_kind == PRIMARY`: `target_effect.condition == treatment.target_condition`; else raise `TreatmentParentMismatch`.
   - `target_kind == AFTERMATH`: `target_effect.condition.parent_condition == treatment.target_condition`; else raise `TreatmentParentMismatch`.
   - `target_kind == PENDING_ALTERATION`: no parent-match check is performed. `PendingAlteration` (in `world.magic.models`) has no FK back to a source `ConditionTemplate` or `ConditionInstance` — Mage Scars are produced by the Scope 5 alteration pipeline, which today only sources from Soulfray. The `treatment.target_condition` field still serves as the "kind of effect this treatment is meant for" for authoring/querying purposes (i.e. `target_condition=soulfray, target_kind=PENDING_ALTERATION` reads as "Mage Scar treatment"), but at the service level the parent-match check is a no-op. If a future scope adds non-Soulfray-sourced `PendingAlteration` rows, add an explicit FK on `PendingAlteration` to its source condition and re-introduce a real parent-match check here.
3. **Bond gate:** if `treatment.requires_bond`:
   - `bond_thread` is not None and `bond_thread.owner == helper_sheet` and the thread is anchored to a relationship-track or capstone whose subject is `target_sheet`; else raise `NoSupportingBondThread`.
4. **Scene gate:** if `treatment.scene_required`, `scene` is active and both `helper` and `target` are participants; else raise `TreatmentScenePrerequisiteFailed`.
5. **Engagement gate:** neither helper nor target has an active `CharacterEngagement` (imported from `world.mechanics.engagement`); else raise `HelperEngagedForTreatment`. (Stabilization is in-scene aftercare, not mid-combat.)
6. **Duplicate gate:** if `treatment.once_per_scene_per_helper`, no prior `TreatmentAttempt` exists for `(helper, target, scene, treatment)`; else raise `TreatmentAlreadyAttempted`. The pre-check is racy under concurrent calls; the partial-unique constraint on `TreatmentAttempt` (Section 4.2) is the authoritative gate. The service wraps the final INSERT in `try/except IntegrityError → raise TreatmentAlreadyAttempted` to give a clean exception across both paths.
7. **Resonance cost:** if `treatment.resonance_cost > 0`, then `bond_thread` MUST be set (enforced by `TreatmentTemplate.clean()` in §4.2: `resonance_cost > 0 ⇒ requires_bond=True`, and step 3 validates `bond_thread`). Debit via `CharacterResonance.objects.select_for_update().get(character_sheet=helper_sheet, resonance=bond_thread.resonance)`; raise `TreatmentResonanceInsufficient` if `balance < resonance_cost`. (`bond_thread.resonance` is the `Resonance` FK on the Thread; the helper's spendable currency row is `CharacterResonance`.)
8. **Anima cost:** if `treatment.anima_cost > 0`, debit via `deduct_anima(helper, treatment.anima_cost)`; raise `TreatmentAnimaInsufficient` on shortfall.

**Execute:**
1. Resolve check via `perform_check(helper, check_type=treatment.check_type, target_difficulty=treatment.target_difficulty)`. (`TreatmentTemplate.target_difficulty` is the new field added in §4.2.)
2. Map `check_result.outcome` to reduction:
   - `CRITICAL_SUCCESS` → `reduction_on_crit`
   - `SUCCESS` → `reduction_on_success`
   - `PARTIAL` (nearest equivalent) → `reduction_on_partial`
   - any failure outcome → `reduction_on_failure` (typically 0)
3. **Apply reduction:**
   - `PRIMARY` or `AFTERMATH`: `decay_condition_severity(target_effect, amount=reduction)`.
   - `PENDING_ALTERATION`: call **new** service `reduce_pending_alteration_tier(pending=target_effect, amount=reduction, reason="treatment")` (added in this scope, lives in `magic/services/alterations.py`). This is **NOT** `resolve_pending_alteration` — that helper authors a new alteration template, which is a different operation. The new helper updates `PendingAlteration.tier` (clamped at 0) and, when `tier` reaches 0, marks `status=PendingAlterationStatus.RESOLVED` with `resolved_alteration=None` and `resolved_at=get_ic_now() or timezone.now()` to indicate the pending was cleared without an authored alteration. Return shape is `PendingAlterationTierReduction(pending, previous_tier, new_tier, resolved)` (added to §7).
4. **Failure backlash:** if `check_result.outcome` is a failure outcome and `treatment.backlash_severity_on_failure > 0`:
   - Determine target condition: `treatment.backlash_target_condition or treatment.target_condition`.
   - Find helper's active `ConditionInstance` for that condition; if none, call `apply_condition(helper, condition=backlash_target, severity=treatment.backlash_severity_on_failure, source_description="stabilization backlash")`.
   - If present, call `advance_condition_severity(helper_instance, amount=treatment.backlash_severity_on_failure)`.
5. Persist `TreatmentAttempt` with `created_at=get_ic_now() or timezone.now()` (fallback because `get_ic_now()` returns `None` when the IC clock is unconfigured — see `world/game_clock/services.py:19`), outcome, reductions, backlash applied, costs debited, target FK populated per target_kind. Wrap the INSERT in `try/except IntegrityError → raise TreatmentAlreadyAttempted` per step 6.
6. Return `TreatmentOutcome`.

**Transactional boundary:** entire service wrapped in `transaction.atomic()`. `select_for_update()` on helper's resonance row (if `resonance_cost > 0`), helper's anima row (if `anima_cost > 0`), target's `ConditionInstance` or `PendingAlteration`, and helper's backlash-target `ConditionInstance` (if present).

### 5.3 `decay_condition_severity(instance, amount) -> SeverityDecayResult`

Lives in `world/conditions/services.py`. Inverse of `advance_condition_severity`.

**Behaviour:**
1. Snapshot `previous_stage = instance.current_stage`.
2. `new_severity = max(0, instance.severity - amount)`.
3. Resolve new stage: the `ConditionStage` for this template with the largest `severity_threshold <= new_severity`, or `None` if no stage matches (pre-first-stage). When `new_severity == 0` and the lowest authored stage has `severity_threshold >= 1`, `new_stage` is `None`. Consumers of `CONDITION_STAGE_CHANGED` must tolerate `new_stage is None`; the §5.6 stage-entry handler already does.
4. Assign `instance.severity`, `instance.current_stage`.
5. If `new_severity == 0`, set `instance.resolved_at = get_ic_now() or timezone.now()`. The fallback to `timezone.now()` covers the case where the IC clock is unconfigured (see `world/game_clock/services.py:19` which returns `datetime | None`).
6. `instance.save(update_fields=["severity", "current_stage", "resolved_at"])`.
7. If the stage actually changed, emit `CONDITION_STAGE_CHANGED` via the existing `ConditionStageChangedPayload(target, instance, old_stage, new_stage)` — no new fields on the payload. **Decay paths (this service) emit descending events; ascent paths (`advance_condition_severity`) emit ascending events; neither carries a `direction` field.** Downstream handlers must derive ascending vs descending from `old_stage.stage_order` vs `new_stage.stage_order`. The §5.6 stage-entry handler is the reference example.
8. Return `SeverityDecayResult(previous_stage, new_stage, new_severity, resolved=(new_severity == 0))`.

### 5.4 `decay_all_conditions_tick() -> DecayTickSummary`

Lives in `world/conditions/services.py`. Scheduler entry point.

**Behaviour:**
1. Query `ConditionInstance.objects.filter(resolved_at__isnull=True, condition__passive_decay_per_day__gt=0).select_related("condition", "current_stage", "target")`.
2. For each instance:
   - If `instance.condition.passive_decay_blocked_in_engagement`:
     - Use a typeclass-aware check: `CharacterEngagement.objects.filter(character=instance.target).exists()` returns False if the target isn't a character (no engagement row exists for non-character ObjectDBs), so the filter is naturally safe. No extra guard needed.
   - If blocked: increment "engagement-blocked" counter, skip.
   - If `instance.condition.passive_decay_max_severity is not None` and `instance.severity > instance.condition.passive_decay_max_severity`, increment "severity-gated" counter, skip.
   - Call `decay_condition_severity(instance, instance.condition.passive_decay_per_day)`.
3. Return `DecayTickSummary(examined, ticked, engagement_blocked, severity_gated)`.

### 5.5 `anima_regen_tick() -> AnimaRegenTickSummary`

Lives in `magic/services/anima.py`. Scheduler entry point.

**Behaviour:**
1. Fetch `config = AnimaConfig.get_singleton()`.
2. Resolve the blocking-property Property once: `blocker = Property.objects.get(key=config.daily_regen_blocking_property_key)`.
3. Query `CharacterAnima.objects.filter(current_anima__lt=models.F("maximum")).select_related("character_sheet__character")`.
4. **Bulk pre-fetch** the two skip sets in two queries before the loop (avoids N+1):
   - `engaged_ids = set(CharacterEngagement.objects.values_list("character_id", flat=True))`
   - `blocked_ids = set(ConditionInstance.objects.filter(resolved_at__isnull=True, current_stage__properties=blocker).values_list("target_id", flat=True).distinct())`
5. For each row:
   - If `row.character_sheet.character_id in engaged_ids`, increment "engagement_blocked" counter, skip.
   - If `row.character_sheet.character_id in blocked_ids`, increment "condition_blocked" counter, skip.
   - Compute `regen = floor(row.maximum * config.daily_regen_percent / 100)`; `row.current_anima = min(row.current_anima + regen, row.maximum)`; save.
6. Return `AnimaRegenTickSummary(examined, regenerated, engagement_blocked, condition_blocked)`.

### 5.6 Stage-entry aftermath hook

A reactive-layer handler registered against `CONDITION_STAGE_CHANGED`:

```python
def apply_stage_entry_aftermath(payload: ConditionStageChangedPayload) -> None:
    """Fires on ascending stage changes; applies on_entry_conditions."""
    old, new = payload.old_stage, payload.new_stage
    if new is None:
        return
    if old is not None and new.stage_order <= old.stage_order:
        return  # descending or sideways — do not apply on_entry aftermath
    target = payload.target  # ObjectDB
    for assoc in new.on_entry_assocs.select_related("condition").all():
        existing = ConditionInstance.objects.filter(
            target=target,
            condition=assoc.condition,
            resolved_at__isnull=True,
        ).first()
        if existing is None:
            apply_condition(
                target,
                assoc.condition,
                severity=assoc.severity,
                source_description=f"on_entry of {new.name}",
            )
        elif existing.severity < assoc.severity:
            advance_condition_severity(existing, assoc.severity - existing.severity)
        # else: existing severity >= assoc.severity — leave alone.
```

**Aftermath severity cap is intentional.** Re-entering an aftermath-granting stage never escalates an existing aftermath instance past `assoc.severity`. The design treats aftermath as "you have it or you don't, plus some scaling per stage" — repeat exposure to the same stage doesn't keep ratcheting severity upward. Players who want to push aftermath higher must reach a higher Soulfray stage that authors a higher-severity aftermath association.

Lives in `world/conditions/services.py` (service function) and is registered as a trigger handler via the existing Scope 5.5 pattern in the app's `AppConfig.ready()`.

### 5.7 `reduce_pending_alteration_tier(pending, amount, reason) -> PendingAlterationTierReduction`

Lives in `magic/services/alterations.py`. New service introduced by Scope 6.

**Purpose:** the Scope 5 helper `resolve_pending_alteration` *authors a new alteration template* and applies it as a condition. That is the wrong operation for treatment, which only wants to reduce the tier-debt the helper already owes (potentially clearing the pending entirely). This helper is the missing primitive.

**Behaviour:**
1. `pending = PendingAlteration.objects.select_for_update().get(pk=pending.pk)`.
2. If `pending.status != PendingAlterationStatus.OPEN`: raise `AlterationResolutionError` (consistent with `resolve_pending_alteration`).
3. `previous_tier = pending.tier`; `new_tier = max(0, previous_tier - amount)`; `resolved = (new_tier == 0)`.
4. If `resolved`:
   - `pending.status = PendingAlterationStatus.RESOLVED`
   - `pending.resolved_alteration = None` (no alteration template was authored — treatment cleared the debt)
   - `pending.resolved_at = get_ic_now() or timezone.now()`
   - Do **not** create a `MagicalAlterationEvent` (no alteration was applied).
5. Else: `pending.tier = new_tier`.
6. `pending.save(update_fields=[...])`.
7. Return `PendingAlterationTierReduction(pending, previous_tier, new_tier, resolved)`.

The Scope 5 escalation pipeline is unaffected: a same-scene escalation that fires after a treatment-induced tier reduction can still raise the tier. There is no "suppress_escalation" flag — escalation is keyed off scope-5 logic, not off this helper.

## 6. Scheduler Integration

Both new tasks register via `world/game_clock/tasks.py` during `register_all_tasks()`:

```python
from datetime import timedelta

register_task(
    CronDefinition(
        task_key="magic.anima_regen_daily",
        callable=anima_regen_tick,
        interval=timedelta(hours=24),
        description="Daily anima pool regeneration (skips engaged characters and "
                    "characters whose active condition stages carry blocks_anima_regen).",
    )
)
register_task(
    CronDefinition(
        task_key="conditions.decay_daily",
        callable=decay_all_conditions_tick,
        interval=timedelta(hours=24),
        description="Passive decay for conditions with passive_decay_per_day > 0.",
    )
)
```

`CronDefinition` uses `interval: timedelta` + `callable:` callable reference, per existing `game_clock/tasks.py` convention (no cron string, no callable path string). Ticks are registered at server start. Intervals are rolling 24h from last run time; two ticks register separately, so they naturally don't fire simultaneously across server runs — no cron-time staggering necessary with this scheduler model.

`ScheduledTaskRecord` auto-creates on first tick, per existing infrastructure.

## 7. Types

New dataclasses (lives in `magic/types/ritual.py`, `world/conditions/types.py`). All carry model instances per project convention, never bare PKs.

```python
from world.checks.types import CheckOutcome  # or wherever the project canonical lives

@dataclass
class RitualOutcome:
    performance: AnimaRitualPerformance
    outcome: CheckOutcome
    severity_reduced: int
    anima_recovered: int
    soulfray_stage_after: ConditionStage | None
    soulfray_resolved: bool


@dataclass
class TreatmentOutcome:
    attempt: TreatmentAttempt
    outcome: CheckOutcome
    effect_applied: bool
    severity_reduced: int
    tiers_reduced: int
    helper_backlash_applied: int
    target_resolved: bool


@dataclass
class SeverityDecayResult:
    previous_stage: ConditionStage | None
    new_stage: ConditionStage | None
    new_severity: int
    resolved: bool


@dataclass
class PendingAlterationTierReduction:
    pending: PendingAlteration
    previous_tier: int
    new_tier: int
    resolved: bool


@dataclass
class DecayTickSummary:
    examined: int
    ticked: int
    engagement_blocked: int
    severity_gated: int


@dataclass
class AnimaRegenTickSummary:
    examined: int
    regenerated: int
    engagement_blocked: int
    condition_blocked: int
```

## 8. Seed Content

Authored via factory module, not data migrations (per project convention). Seed data is loaded in test setup and via dev fixture tooling.

### 8.1 Soulfray stages

Five stages (working names; tunable):

| Stage order | Name | Severity threshold (tunable) | Notes |
|-------------|------|------------------------------|-------|
| 1 | Fraying | 1 | `passive_decay_max_severity` ceiling; passive decay allowed up to stage 1's top |
| 2 | Tearing | (e.g. 6) | `blocks_anima_regen` property; ritual-gated |
| 3 | Ripping | (e.g. 16) | Audere-reachable floor; first aftermath content |
| 4 | Sundering | (e.g. 36) | Denser aftermath content |
| 5 | Unravelling | (e.g. 66) | Worst-case aftermath; 2+ real-weeks of ritual recovery per tuning |

Stage thresholds are tunable during implementation — spec locks the 5-stage count and ordering, not exact numbers. Mage Scar risk spans all stages; scar severity scales with stage at time of creation.

### 8.2 Soulfray `ConditionTemplate` configuration

```python
ConditionTemplate(
    name="soulfray",
    passive_decay_per_day=1,
    # passive_decay_max_severity == (stage_2.severity_threshold - 1).
    # i.e. the highest severity that still maps to stage 1. With the tuning
    # numbers in §8.1, this is 6 - 1 = 5. Decay applies only while severity
    # is in the stage-1 band (1..5); stage 2+ requires ritual to escape.
    passive_decay_max_severity=<stage_2.severity_threshold - 1>,
    passive_decay_blocked_in_engagement=True,
    parent_condition=None,
)
```

### 8.3 Aftermath conditions

Three reference aftermath conditions, each `parent_condition=soulfray`:

| Condition key | Wired into stages (via `on_entry_conditions`) | Severity | Flavor |
|---------------|-----------------------------------------------|----------|--------|
| `soul_ache` | Ripping (3), Sundering (4) | 1 | Dull persistent pain |
| `arcane_tremor` | Sundering (4), Unravelling (5) | 1 | Jittery hands/voice, disruption |
| `aura_bleed` | Unravelling (5) | 2 | Visible magical leak |

Further aftermath authoring happens outside Scope 6 as design settles.

### 8.4 `blocks_anima_regen` property

Single `Property` row with key `blocks_anima_regen`. Attached to Soulfray stages 2+ via `ConditionStage.properties`.

### 8.5 `TreatmentTemplate` authored rows

Two Soulfray-facing treatments:

```python
TreatmentTemplate(
    key="soulfray_stabilize_aftermath",
    name="Stabilize Soulfray Aftermath",
    target_condition=soulfray,
    target_kind=TreatmentTargetKind.AFTERMATH,
    check_type=<seed picks the catalog CheckType — choice deferred to seed-tuning PR; both rows can share or diverge>,
    requires_bond=True,
    resonance_cost=1,
    anima_cost=0,
    once_per_scene_per_helper=True,
    backlash_severity_on_failure=1,
    backlash_target_condition=soulfray,
    reduction_on_crit=3, reduction_on_success=2, reduction_on_partial=1, reduction_on_failure=0,
)

TreatmentTemplate(
    key="soulfray_stabilize_mage_scar",
    name="Stabilize Pending Mage Scar",
    target_condition=soulfray,
    target_kind=TreatmentTargetKind.PENDING_ALTERATION,
    check_type=<seed picks the catalog CheckType — choice deferred to seed-tuning PR; both rows can share or diverge>,
    requires_bond=True,
    resonance_cost=2,
    anima_cost=0,
    once_per_scene_per_helper=True,
    backlash_severity_on_failure=1,
    backlash_target_condition=soulfray,
    reduction_on_crit=2, reduction_on_success=1, reduction_on_partial=1, reduction_on_failure=0,
)
```

### 8.6 `AudereThreshold` re-seed

The existing `AudereThreshold` row's `minimum_warp_stage` retargets to the Ripping (stage 3) `ConditionStage`. No code change in `audere.py`; factory/seed update only. **Existing audere tests** currently assert against stage-2 gating (see `world/magic/tests/test_audere.py`) — those test fixtures must update to the new stage mapping or override the fixture per-test. Called out in Section 10.

### 8.7 `SoulfrayConfig` ritual budgets

Tuning target:
- `ritual_budget_critical_success`: enough severity reduction to clear a stage-1 Soulfray fully; anima also force-refills to max via the crit override (Section 5.1 step 5) regardless of budget leftover.
- `ritual_budget_success`: ~60% of crit budget.
- `ritual_budget_partial`: ~30%.
- `ritual_budget_failure`: ~10% (validator enforces ≥ 1).
- `ritual_severity_cost_per_point`: 1.

On a crit, the budget effectively governs only severity reduction — anima always tops up regardless of leftover. This is a deliberate feel choice; tuning should assume crit = "full recovery of whatever severity the budget can pay down + full anima".

Exact numbers set during implementation against the stage-threshold tuning.

### 8.8 `AnimaConfig`

- `daily_regen_percent`: 5.
- `daily_regen_blocking_property_key`: `blocks_anima_regen`.
- Singleton by convention — `AnimaConfig.get_singleton()` fetches or creates `pk=1`, matching the `SoulfrayConfig` pattern.

## 9. Testing Plan

### 9.1 Unit tests

**`magic/tests/test_anima_ritual.py`**
- Crit (Soulfray absent) → anima max, no severity change.
- Crit (Soulfray stage 2, mid-severity) → severity fully paid down, anima max (override).
- Success (Soulfray stage 2) → severity reduced, partial anima refill.
- Partial (Soulfray stage 5) → small severity reduction, minimal anima refill.
- Failure (no active Soulfray) → small anima refill.
- Gate: no `CharacterAnimaRitual` → raises `NoRitualConfigured`.
- Gate: character engaged → raises `CharacterEngagedForRitual`.
- Gate: second ritual same scene → raises `RitualAlreadyPerformedThisScene`.
- `AnimaRitualPerformance` row persisted with accurate fields (outcome enum, severity_reduced, anima_recovered).

**`magic/tests/test_anima_regen_tick.py`**
- Character at max anima → not examined.
- Character below max, no blocking conditions → regen applied.
- Character below max, Soulfray stage 2 → skipped (blocks_anima_regen).
- Character below max, Soulfray stage 1 → regen applied.
- Character engaged → skipped.
- N characters (≥10) → single-digit query count (no N+1).

**`world/conditions/tests/test_decay_severity.py`**
- Decay within stage → stage unchanged.
- Decay across stage boundary downward → stage walks down, `CONDITION_STAGE_CHANGED` emitted; callers can derive descending direction from stage_order comparison.
- Decay to 0 → `resolved_at` set, stage resolution event emitted.
- Decay amount > severity → clamps at 0.
- Symmetry: `advance_condition_severity(+N)` then `decay_condition_severity(-N)` returns to starting stage and severity.

**`world/conditions/tests/test_decay_tick.py`**
- Mix of decaying and non-decaying conditions → only opt-in subset ticks.
- Engagement gate honored per `passive_decay_blocked_in_engagement=True`.
- **Positive test:** condition with `passive_decay_blocked_in_engagement=False` decays even when target is engaged.
- `passive_decay_max_severity` gate honored (Soulfray stage 2+ instances not decayed).
- Non-character target (room-anchored condition) never engagement-gated regardless of flag.
- N instances (≥10) → single-digit query count.

**`world/conditions/tests/test_treatment_aftermath.py`** (Soulfray aftermath treatment):
- Success → aftermath severity reduced by `reduction_on_success`.
- Partial → reduced by `reduction_on_partial`.
- Crit → reduced by `reduction_on_crit`; aftermath may resolve.
- Failure → no reduction, helper gains `backlash_severity_on_failure` on Soulfray.
- **Parent mismatch:** AFTERMATH treatment with `target_condition=soulfray` rejects a `ConditionInstance` whose `condition.parent_condition != soulfray` → raises `TreatmentParentMismatch`.
- Gate: already treated this (helper, target, treatment, scene) → raises `TreatmentAlreadyAttempted`.
- Gate: no bond thread provided → raises `NoSupportingBondThread`.
- Gate: bond thread doesn't anchor to target → raises `NoSupportingBondThread`.
- Gate: target_effect type mismatch (PendingAlteration passed) → raises `TreatmentTargetMismatch`.
- Gate: prerequisite callable returns False → raises `TreatmentScenePrerequisiteFailed`.
- Gate: insufficient resonance balance → raises `TreatmentResonanceInsufficient`.
- Resonance debited from `CharacterResonance` row matching `bond_thread.resonance`.
- `TreatmentAttempt` persisted accurately.

**`world/conditions/tests/test_treatment_mage_scar.py`**
- Success on tier-3 pending Mage Scar → tier reduced by `reduction_on_success` via `reduce_pending_alteration_tier`.
- Tier reaches 0 → `PendingAlteration.status` becomes `RESOLVED` with `resolved_alteration=None` and `resolved_at` populated; no `MagicalAlterationEvent` is created (treatment cleared the pending without authoring an alteration).
- Failure backlash adds Soulfray severity to helper.
- Concurrency: two simultaneous helper invocations under the partial unique constraint — one INSERT succeeds, the other surfaces `TreatmentAlreadyAttempted` (not `IntegrityError`).

**`world/conditions/tests/test_stage_entry_aftermath.py`**
- Ascending stage entry with `on_entry_conditions` → aftermath instances appear on target.
- Descending through stages → pre-existing aftermath instances are *not* auto-removed (treatment is cleanup path).
- Sideways / same-stage (no change) → hook is a no-op.
- Idempotency: ascending to same stage twice → aftermath severity does not stack beyond `assoc.severity`.
- Multi-condition stage → all configured aftermaths applied in one hook fire.

### 9.2 Integration test

**`world/magic/tests/integration/test_soulfray_recovery_flow.py`**

Full scenario:
1. Character accumulates Soulfray to stage 3 (Ripping) → aftermath conditions appear via stage-entry hook.
2. Engagement ends.
3. Bonded helper performs stabilization on one aftermath → severity reduces.
4. Target performs anima ritual → Soulfray severity drops, anima partially refilled.
5. Scheduled-tick cycles (simulated): at Soulfray stage 2, `anima_regen_tick` produces zero regen (blocks_anima_regen property). Pay severity down to stage 1; next tick regens. Assert both behaviours explicitly.
6. Boundary: at Soulfray stage 2, repeated decay ticks alone never recover the character — ritual is required to cross the `passive_decay_max_severity` boundary.

### 9.3 Regression scope before push

All suites that Scope 6 plausibly touches:
- `world.magic`
- `world.conditions`
- `world.game_clock`
- `world.mechanics`
- `world.combat` (Mage Scar pipeline, threads/pulls)
- `world.scenes` (stabilization scene-gate, treatment scene FK)
- `flows` (reactive-layer trigger registration)

Run once with `--keepdb` for fast iteration, then once without `--keepdb` to match CI before push.

## 10. Migration & Rollout

- **Schema migrations** land as a single coordinated pair: one in `conditions` (new fields on `ConditionTemplate`, `ConditionInstance`, `ConditionStage`; new `ConditionStageOnEntry`, `TreatmentTemplate`, `TreatmentAttempt`) and one in `magic` (new fields on `SoulfrayConfig`, new `AnimaConfig`). Produced via `arx manage makemigrations conditions magic` at implementation time.
- **No data migrations.** Seed updates land via factory module edits and the seed-reload flow.
- **File layout conversion** (`magic/models.py` → `magic/models/` package, `magic/services.py` → `magic/services/` package) is an in-place refactor with no renamed public symbols. `__init__.py` re-exports preserve all import paths. **Migration-graph risk:** moving `Model` classes to different Python modules can cause Django to emit spurious migrations (it tracks model location for some introspection paths). After the move, run `arx manage makemigrations magic` and verify the output contains ONLY the intended schema diff (the new `SoulfrayConfig` fields and `AnimaConfig`). If Django produces a model-move migration, collapse or discard it; do not ship a noise migration. Capture a no-`--keepdb` test run before push to confirm fresh-DB parity.
- **Reactive-layer handler registration** for `apply_stage_entry_aftermath` wires into the existing Scope 5.5 trigger registration path in the `conditions` `AppConfig.ready()`.
- **Existing Audere test fixtures** that seed `AudereThreshold.minimum_warp_stage=stage2` need updating to the new Ripping stage when Soulfray goes from 3 to 5 stages. Either update the shared `AudereThresholdFactory` or override per-test.
- **`_handle_soulfray_accumulation` and `_resolve_mishap`** are move-only refactors in Section 4.4's service split — Scope 6 does not change their behaviour. Any callers rely on their current signatures.

## 11. Open Items (deferred, not blocking)

These are called out for future scopes; Scope 6 does not attempt them.

1. **Healing magic** — out-of-scene restoration; explicitly deferred.
2. **Stabilization UI** — player command / web API surface for `perform_treatment` lands with the next magic surfaces scope.
3. **Anima ritual UI** — same; command/API surface deferred.
4. **Additional aftermath content** — the three reference conditions prove the pipeline; design settles and more author over time.
5. **Cross-stage property effects** — `blocks_anima_regen` is the only stage property Scope 6 seeds; future properties (e.g. `blocks_thread_imbuing`, `reduces_check_rank`) may follow the same pattern.
6. **`ConditionTemplate.parent_condition` vs `ConditionStageOnEntry` denormalization check** — the parent FK is retained because an aftermath condition can be authored as "child of soulfray" before being wired into any specific stage's `on_entry_conditions`. If we later decide aftermath conditions must always be wired to at least one stage of their parent, the FK could be recomputed and removed — but that's a future cleanup, not a Scope 6 concern.
