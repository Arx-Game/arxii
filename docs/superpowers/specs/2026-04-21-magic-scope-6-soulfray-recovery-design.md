# Magic Scope 6 — Soulfray Recovery & Decay

**Status:** Design
**Author:** Dave Brannigan (with Claude)
**Date:** 2026-04-21
**Related specs:**
- `2026-04-12-scope5-magical-alteration-resolution-design.md` (Mage Scars / PendingAlteration pipeline)
- `2026-04-16-reactive-layer-design.md` (`CONDITION_STAGE_CHANGED` event)
- `2026-04-18-resonance-pivot-spec-a-threads-and-currency-design.md` (Threads + resonance currency)

## 1. Summary

Scope 6 completes the Soulfray lifecycle by delivering the **recovery half** of the condition: how a character escapes Soulfray once they've fallen into it, how their anima pool refills over time, and how allies can help mitigate the worst aftermath of deep Soulfray during a scene.

Scope 6 ships three primary mechanisms:

1. **Anima Ritual** — the primary magical recovery mechanism. Not yet implemented (only the data models exist). A character performs their personalised ritual in-scene, rolls a check, and spends an outcome-tiered recovery budget on (a) reducing Soulfray severity and (b) refilling their anima pool.
2. **Stabilization (via the generalised Treatment system)** — an in-scene, thread-gated emergency-care attempt by another character. Reduces the severity of nasty aftermath conditions granted by deep Soulfray, or reduces the tier of a pending Mage Scar for the current scene. Failure risks giving the helper Soulfray severity of their own.
3. **Passive decay + daily anima regen** — slow background recovery. Only recovers characters at the lowest Soulfray stage; anyone stage ≥2 is gated on ritual recovery. Daily anima regen is blocked while any "blocks_anima_regen" stage property is active.

Scope 6 generalises recovery primitives wherever the logic is not intrinsically about Soulfray:

- **Condition passive decay** becomes a data-driven capability of any `Condition` template.
- **Treatment** becomes a generic system (`TreatmentTemplate` + `TreatmentAttempt`) — Soulfray stabilization is the first authored user.
- **Stage-entry aftermath** becomes a generic capability (`ConditionStage.on_entry_conditions`) — any condition's stage can grant other conditions when entered.

Anima ritual itself stays Soulfray-aware (it is the Soulfray recovery mechanism), but the generic decay and treatment pieces operate without any knowledge of Soulfray.

## 2. Goals & Non-Goals

### Goals

- Deliver `perform_anima_ritual` as a complete service with outcome-tiered recovery budget.
- Give characters a ritual-free slow recovery path at the lowest Soulfray stage so players aren't hard-stuck without a ritual.
- Deliver stabilization so deep-Soulfray characters have an in-scene safety net that other players contribute to.
- Generalise passive decay, treatment, and stage-entry aftermath so future conditions (and future treatments) can reuse the infrastructure without new scheduler code.
- Extend the Soulfray authored stage list from 3 to 5 for tuning headroom. Audere-gating moves to stage 3+ via existing infrastructure.
- Seed reference aftermath conditions so stabilization has something meaningful to reduce in integration tests.

### Non-Goals

- No healing magic (post-scene, out-of-combat restoration) — deferred.
- No changes to Scope 5 Mage Scar authoring or resolution semantics; stabilization feeds into the existing PendingAlteration resolution path.
- No changes to Audere's gate logic — only the seeded `AudereThreshold.minimum_warp_stage` value updates.
- No refactor of the Scope 5 PendingAlteration model or of Scope 5.5 reactive-layer internals.
- No player-facing UI changes in Scope 6 (web surfaces land in a later scope).
- No new player command authoring for ritual/stabilization at the CLI level (service-layer only; commands or API endpoints land in a later scope).

## 3. Design Principles

- **Condition-generic where possible.** If a behaviour could apply to a future condition (e.g. passive decay, treatment, stage-entry aftermath), author it on `Condition` / `ConditionStage` / `TreatmentTemplate` rather than on `SoulfrayConfig`.
- **Anima ritual is a Soulfray-aware service.** The ritual is culturally and mechanically tied to anima/Soulfray; trying to make it generic would create speculative abstraction. It lives in `magic/services/anima.py` as a first-class service.
- **Properties tag stages, not conditions.** `blocks_anima_regen` lives on `ConditionStage.properties`, not on the parent `Condition`. Soulfray stage 1 doesn't carry it; stages 2+ do.
- **Scheduler is data-driven.** Daily ticks iterate conditions that opt-in via `passive_decay_per_day > 0` and characters whose active stage properties include `blocks_anima_regen`. No Soulfray FK in scheduler code.
- **Threads as bonds, not combat tool.** Stabilization's bond requirement uses an existing Thread anchored to a relationship track or capstone pointing at the target; reuses Spec A infrastructure, no new bond primitive.
- **Resonance is currency, not scalar.** Treatments cost a flat resonance amount from the bond thread's balance. No severity-scaled or pool-percentage costs.
- **AP is not an in-scene gate.** Ritual and stabilization do not cost AP. Ritual is scene-gated (once per scene per character); stabilization is helper-gated (once per helper per target per scene).

## 4. Model Changes

All concrete models are `SharedMemoryModel`.

### 4.1 `world/conditions` — new fields on existing models

#### `Condition`

```python
parent_condition = models.ForeignKey(
    "self", null=True, blank=True, on_delete=models.SET_NULL,
    related_name="aftermath_children",
)  # for aftermath conditions; aftermath of Soulfray points at Soulfray

passive_decay_per_day = models.PositiveIntegerField(default=0)
passive_decay_max_severity = models.PositiveIntegerField(null=True, blank=True)
passive_decay_blocked_in_engagement = models.BooleanField(default=True)
```

Semantics:
- `passive_decay_per_day == 0` opts out of passive decay entirely.
- `passive_decay_max_severity == None` decays at any severity; otherwise decays only when `instance.severity <= this value` (Soulfray sets this to stage 1's ceiling).
- `passive_decay_blocked_in_engagement == True` halts decay while the target has an active `CharacterEngagement`.

#### `ConditionStage`

```python
properties = models.ManyToManyField(
    "mechanics.Property", blank=True, related_name="condition_stages_carrying",
)

# Many-to-many via a thin through model so we can carry severity per assignment
on_entry_conditions = models.ManyToManyField(
    "conditions.Condition", through="ConditionStageOnEntry",
    related_name="applied_on_entry_of", blank=True,
)
```

`ConditionStageOnEntry` captures `stage` + `condition` + `severity` (the severity at which the granted condition is instantiated when the stage is entered).

### 4.2 `world/conditions` — new models

#### `TreatmentTemplate`

Authored catalog. A treatment defines how one character can attempt to mitigate another character's condition (or a related alteration).

```python
class TreatmentTemplate(SharedMemoryModel):
    key = models.SlugField(unique=True, max_length=64)
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True)

    target_condition = models.ForeignKey("conditions.Condition", on_delete=models.PROTECT,
                                        related_name="treatments")
    target_kind = models.CharField(max_length=32, choices=TreatmentTargetKind.choices)

    check_type = models.ForeignKey("traits.CheckType", on_delete=models.PROTECT)
    prerequisite_key = models.CharField(max_length=64, blank=True, default="")
    requires_bond = models.BooleanField(default=False)

    resonance_cost = models.PositiveIntegerField(default=0)
    anima_cost = models.PositiveIntegerField(default=0)

    once_per_scene_per_helper = models.BooleanField(default=True)
    scene_required = models.BooleanField(default=True)

    backlash_severity_on_failure = models.PositiveIntegerField(default=0)
    backlash_target_condition = models.ForeignKey(
        "conditions.Condition", null=True, blank=True,
        on_delete=models.PROTECT, related_name="treatment_backlash_source",
    )  # defaults to target_condition if null

    reduction_on_crit = models.PositiveIntegerField(default=0)
    reduction_on_success = models.PositiveIntegerField(default=0)
    reduction_on_partial = models.PositiveIntegerField(default=0)
    reduction_on_failure = models.PositiveIntegerField(default=0)
```

`TreatmentTargetKind` choices:
- `PRIMARY` — reduce severity of the target condition directly.
- `AFTERMATH` — reduce severity of a child condition granted by `on_entry_conditions` on the target condition.
- `PENDING_ALTERATION` — reduce tier of a Scope-5 `PendingAlteration` linked to the target condition.

#### `TreatmentAttempt`

Audit log of a treatment attempt, one row per invocation.

```python
class TreatmentAttempt(SharedMemoryModel):
    helper = models.ForeignKey("character_sheets.CharacterSheet", on_delete=models.PROTECT,
                                related_name="treatment_attempts_as_helper")
    target = models.ForeignKey("character_sheets.CharacterSheet", on_delete=models.PROTECT,
                                related_name="treatment_attempts_as_target")
    scene = models.ForeignKey("scenes.Scene", on_delete=models.PROTECT,
                                related_name="treatment_attempts")
    treatment = models.ForeignKey("conditions.TreatmentTemplate", on_delete=models.PROTECT,
                                related_name="attempts")

    thread_used = models.ForeignKey("magic.Thread", null=True, blank=True,
                                    on_delete=models.PROTECT,
                                    related_name="treatment_attempts")

    target_condition_instance = models.ForeignKey(
        "conditions.ConditionInstance", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="treatment_attempts_targeting",
    )
    target_pending_alteration = models.ForeignKey(
        "magic.PendingAlteration", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="treatment_attempts_targeting",
    )

    outcome_tier = models.IntegerField()
    severity_reduced = models.IntegerField(default=0)
    tiers_reduced = models.IntegerField(default=0)
    helper_backlash_applied = models.IntegerField(default=0)
    resonance_spent = models.IntegerField(default=0)
    anima_spent = models.IntegerField(default=0)

    created_at = models.DateTimeField()  # IC time; stamped at call

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["helper", "target", "scene", "treatment"],
                condition=Q(treatment__once_per_scene_per_helper=True),
                name="unique_treatment_attempt_per_helper_scene",
            ),
        ]
```

### 4.3 `world/magic` — new fields / new models

#### `SoulfrayConfig` (extended)

New fields — ritual budgets only. Other Soulfray tunables move to the Soulfray `Condition` template where possible.

```python
ritual_budget_critical_success = models.PositiveIntegerField()
ritual_budget_success = models.PositiveIntegerField()
ritual_budget_partial = models.PositiveIntegerField()
ritual_budget_failure = models.PositiveIntegerField()
ritual_severity_cost_per_point = models.PositiveIntegerField(default=1)
```

#### `AnimaConfig` (new singleton)

```python
class AnimaConfig(SharedMemoryModel):
    daily_regen_percent = models.PositiveIntegerField(default=5,
        help_text="% of CharacterAnima.maximum regenerated per daily tick")
    daily_regen_blocking_property_key = models.SlugField(default="blocks_anima_regen")
```

Lives in `magic/models/anima.py`. Keeping it a separate singleton avoids coupling anima knobs to `SoulfrayConfig`.

### 4.4 File layout — convert `magic/models.py` and `magic/services.py` into packages

This scope converts the flat modules into topically-split packages. Every existing model and service moves into a thematic submodule; `__init__.py` re-exports the full public surface so external callers are unaffected.

#### `magic/models/` submodule split

| File | Contents |
|------|----------|
| `affinity.py` | `Affinity`, `Resonance` |
| `aura.py` | `CharacterAura`, `CharacterResonance`, `CharacterAffinityTotal` |
| `anima.py` | `CharacterAnima`, `CharacterAnimaRitual`, `AnimaRitualPerformance`, **new** `AnimaConfig` |
| `gifts.py` | `Gift`, `CharacterGift`, `Tradition`, `CharacterTradition` |
| `techniques.py` | `EffectType`, `TechniqueStyle`, `Restriction`, `IntensityTier`, `Technique`, `TechniqueCapabilityGrant`, `CharacterTechnique` |
| `cantrips.py` | `Cantrip` |
| `motifs.py` | `Facet`, `CharacterFacet`, `Motif`, `MotifResonance`, `MotifResonanceAssociation` |
| `soulfray.py` | `SoulfrayConfig` (+ new ritual-budget fields), `MishapPoolTier`, `TechniqueOutcomeModifier` |
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
| `alterations.py` | `create_pending_alteration`, `validate_alteration_resolution`, `resolve_pending_alteration`, `has_pending_alterations`, `staff_clear_alteration`, `get_library_entries` |
| `soulfray.py` | `calculate_soulfray_severity`, `get_soulfray_warning`, `select_mishap_pool`, `_handle_soulfray_accumulation`, `_resolve_mishap` |
| `resonance.py` | `grant_resonance`, `spend_resonance_for_imbuing`, `spend_resonance_for_pull`, `resolve_pull_effects`, `preview_resonance_pull`, private pull/anchor helpers |
| `threads.py` | `weave_thread`, `accept_thread_weaving_unlock`, cap/lock math, `imbue_ready_threads`, thread queries, damage reduction |

`types.py` converts to `types/` only if Scope 6 adds new typed dataclasses; otherwise stays flat. Scope 6 does add new dataclasses (see Section 7), so this scope converts `types.py` to a `types/` package with topical submodules.

## 5. Service Behaviour

### 5.1 `perform_anima_ritual(character, scene) -> RitualOutcome`

Lives in `magic/services/anima.py`.

**Preflight gates:**
1. `character` has a `CharacterAnimaRitual` configured; else raise `MagicError("no_ritual_configured")`.
2. `character` is not in an active `CharacterEngagement`; else raise.
3. `scene` is active and `character` is a participant; else raise.
4. No `AnimaRitualPerformance` already exists for `(target_character=character, scene=scene)`; else raise.

**Execute:**
1. Resolve check via `perform_check(character, check_type=ritual.check_type, check_rank=derived_from_stat_skill_resonance)`.
2. Look up budget from outcome tier:
   - CRIT → `SoulfrayConfig.ritual_budget_critical_success`
   - SUCCESS → `...budget_success`
   - PARTIAL → `...budget_partial`
   - FAILURE → `...budget_failure` (always > 0; never zero)
3. **Spend severity first:** while budget > 0 and Soulfray `ConditionInstance` exists with severity > 0:
   - Call `decay_condition_severity(soulfray_instance, amount=1)`.
   - Deduct `SoulfrayConfig.ritual_severity_cost_per_point` from budget.
4. **Refill anima with leftover:** `CharacterAnima.current_anima += min(remaining_budget, maximum - current)`.
5. **Crit override:** if outcome tier is CRIT, force `current_anima = maximum` after step 4 regardless of leftover budget (crits always fully refill anima on top of clearing severity).
6. Persist `AnimaRitualPerformance` with target_character, scene, was_successful (tier >= SUCCESS), anima_recovered, outcome_tier, severity_reduced.
7. Return `RitualOutcome`.

**Transactional boundary:** entire service wrapped in `transaction.atomic()` with `select_for_update()` on `CharacterAnima` row.

### 5.2 `perform_treatment(helper, target, scene, treatment, target_effect, bond_thread=None) -> TreatmentOutcome`

Lives in `world/conditions/services.py`.

**Signature:**
- `helper`: `CharacterSheet` (the character offering treatment)
- `target`: `CharacterSheet` (the recipient)
- `scene`: `Scene`
- `treatment`: `TreatmentTemplate`
- `target_effect`: `ConditionInstance | PendingAlteration` (must match `treatment.target_kind`)
- `bond_thread`: `Thread | None` (required when `treatment.requires_bond`)

**Preflight gates:**
1. Validate `target_effect` type matches `treatment.target_kind` (ConditionInstance for PRIMARY/AFTERMATH; PendingAlteration for PENDING_ALTERATION). Raise type-mismatch on failure.
2. For `AFTERMATH`: verify `target_effect.condition.parent_condition == treatment.target_condition`.
3. For `PENDING_ALTERATION`: verify the alteration is tied to `treatment.target_condition` (via its source ConditionInstance).
4. If `treatment.requires_bond`: require `bond_thread`, with `bond_thread.owner == helper`, anchored to a relationship-track or capstone pointing at `target`. Else raise `no_supporting_thread`.
5. If `treatment.scene_required`: `scene` must be active and both `helper` and `target` must be participants.
6. Both `helper` and `target` must not have an active `CharacterEngagement` (stabilization is aftercare, not mid-combat).
7. If `treatment.once_per_scene_per_helper`: no prior `TreatmentAttempt` exists for `(helper, target, scene, treatment)`.
8. If `treatment.prerequisite_key`: look up registered callable via the prerequisite registry, call it with `(helper, target, scene, treatment, target_effect)`; raise on failure.
9. Resonance: deduct `treatment.resonance_cost` from `bond_thread.resonance` balance (`CharacterResonance` row); raise on insufficient.
10. Anima: deduct `treatment.anima_cost` from `helper.character_anima`; raise on insufficient.

**Execute:**
1. Resolve check via `perform_check(helper, check_type=treatment.check_type, check_rank=derived)`.
2. Map outcome tier to `reduction_on_*`:
   - CRIT → `reduction_on_crit`
   - SUCCESS → `reduction_on_success`
   - PARTIAL → `reduction_on_partial`
   - FAILURE → `reduction_on_failure` (typically 0)
3. **Apply reduction**:
   - `PRIMARY`: `decay_condition_severity(target_effect, amount=reduction)`.
   - `AFTERMATH`: `decay_condition_severity(target_effect, amount=reduction)` on the aftermath `ConditionInstance`.
   - `PENDING_ALTERATION`: `target_effect.scar_tier = max(0, target_effect.scar_tier - reduction)`; if tier reaches 0, resolve without escalation via Scope-5's resolution helper.
4. **Failure backlash:** if outcome tier is FAILURE and `treatment.backlash_severity_on_failure > 0`:
   - Determine target condition: `treatment.backlash_target_condition` or fall back to `treatment.target_condition`.
   - Get or create helper's `ConditionInstance` for that condition.
   - `advance_condition_severity(helper_instance, amount=backlash_severity_on_failure)`.
5. Persist `TreatmentAttempt`.
6. Return `TreatmentOutcome`.

**Transactional boundary:** service wrapped in `transaction.atomic()` with `select_for_update()` on helper's resonance row, helper's anima row, and the `target_effect`.

### 5.3 `decay_condition_severity(instance, amount) -> SeverityDecayResult`

Lives in `world/conditions/services.py`. Mirror of `advance_condition_severity`.

**Behaviour:**
1. `new_severity = max(0, instance.severity - amount)`.
2. Resolve the new stage: the `ConditionStage` with the largest `severity_threshold <= new_severity`, or `None` if no stage matches (pre-first-stage).
3. Assign and save `severity`, `current_stage`.
4. If the stage actually changed, emit `CONDITION_STAGE_CHANGED` with old stage, new stage, and direction (`DESCENDING`).
5. If `new_severity == 0`, set `resolved_at = get_ic_now()` and emit resolution event.
6. Return `SeverityDecayResult(old_stage, new_stage, resolved=(new_severity == 0))`.

### 5.4 `decay_all_conditions_tick() -> DecayTickSummary`

Lives in `world/conditions/services.py`. Scheduler entry point.

**Behaviour:**
1. Query `ConditionInstance.objects.filter(resolved_at__isnull=True, condition__passive_decay_per_day__gt=0).select_related("condition", "current_stage", "target__character_sheet")`.
2. For each instance:
   - If `instance.condition.passive_decay_blocked_in_engagement` and target has active `CharacterEngagement`, skip (increment "engagement-blocked" counter).
   - If `instance.condition.passive_decay_max_severity is not None` and `instance.severity > instance.condition.passive_decay_max_severity`, skip (increment "severity-gated" counter).
   - Call `decay_condition_severity(instance, instance.condition.passive_decay_per_day)`.
3. Return summary dataclass with total instances examined, ticked, engagement-blocked, severity-gated counts.

### 5.5 `anima_regen_tick() -> AnimaRegenTickSummary`

Lives in `magic/services/anima.py`. Scheduler entry point.

**Behaviour:**
1. Query `CharacterAnima.objects.filter(current_anima__lt=models.F("maximum")).select_related("character_sheet__character").prefetch_related(Prefetch("character_sheet__condition_instances__current_stage__properties", ..., to_attr="cached_regen_blockers"))`.
2. For each row:
   - If target has active `CharacterEngagement`, skip.
   - If any active condition's `current_stage.properties` includes a property with key `AnimaConfig.daily_regen_blocking_property_key`, skip.
   - Compute `regen_amount = floor(maximum * AnimaConfig.daily_regen_percent / 100)`; clamp `current_anima + regen_amount` at `maximum`; save.
3. Return summary dataclass with total examined, regenerated, engagement-blocked, condition-blocked counts.

### 5.6 Stage-entry aftermath hook

A reactive-layer handler registered against the `CONDITION_STAGE_CHANGED` event fires when a stage is entered in the ASCENDING direction:

```python
def apply_stage_entry_conditions(character_sheet, new_stage):
    for assoc in new_stage.on_entry_assocs.select_related("condition").all():
        # Update-or-create: if the character already has this aftermath instance,
        # raise its severity to at least `assoc.severity` (don't stack beyond that).
        existing = ConditionInstance.objects.filter(
            target=character_sheet.character,
            condition=assoc.condition,
            resolved_at__isnull=True,
        ).first()
        if existing is None:
            create_condition_instance(character_sheet, assoc.condition, severity=assoc.severity)
        elif existing.severity < assoc.severity:
            advance_condition_severity(existing, assoc.severity - existing.severity)
```

Lives in `world/conditions/services.py` (service function) and is registered as a trigger handler via the existing Scope 5.5 pattern.

## 6. Scheduler Integration

Both new tasks register via `world/game_clock/tasks.py` during `register_all_tasks()`:

```python
register_task(CronDefinition(
    key="anima_regen_daily",
    callable_path="world.magic.services.anima.anima_regen_tick",
    cron="0 6 * * *",
    description="Daily anima pool regeneration (skips engaged characters and characters with blocks_anima_regen stage property)",
))
register_task(CronDefinition(
    key="condition_decay_daily",
    callable_path="world.conditions.services.decay_all_conditions_tick",
    cron="15 6 * * *",
    description="Passive decay for conditions with passive_decay_per_day > 0",
))
```

Cron times staggered by 15 minutes to avoid batch contention. Both ticks are daily; no intra-day ticking.

Task entries in `ScheduledTaskRecord` auto-create on first tick.

## 7. Types

New dataclasses (lives in `magic/types/ritual.py`, `world/conditions/types.py`). All carry model instances per project convention, never bare PKs.

```python
@dataclass
class RitualOutcome:
    performance: AnimaRitualPerformance
    outcome_tier: int
    severity_reduced: int
    anima_recovered: int
    soulfray_stage_after: ConditionStage | None
    soulfray_resolved: bool


@dataclass
class TreatmentOutcome:
    attempt: TreatmentAttempt
    outcome_tier: int
    effect_applied: bool
    severity_reduced: int
    tiers_reduced: int
    helper_backlash_applied: int
    target_resolved: bool


@dataclass
class SeverityDecayResult:
    old_stage: ConditionStage | None
    new_stage: ConditionStage | None
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

Stage thresholds are tunable during implementation — spec locks the 5-stage count and ordering, not exact numbers.

### 8.2 Soulfray `Condition` configuration

```python
Condition(
    name="soulfray",
    passive_decay_per_day=1,
    passive_decay_max_severity=<stage_1_ceiling>,
    passive_decay_blocked_in_engagement=True,
    parent_condition=None,  # Soulfray is a root
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
    target_kind=AFTERMATH,
    check_type=<TBD seed check type>,
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
    target_kind=PENDING_ALTERATION,
    check_type=<TBD seed check type>,
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

Existing `AudereThreshold` row's `minimum_warp_stage` retargets to the Ripping (stage 3) `ConditionStage`. No code change; factory/seed update only.

### 8.7 `SoulfrayConfig` ritual budgets

Tuning target for integration tests and initial balance:
- `ritual_budget_critical_success`: enough severity reduction + anima refill to fully clear a stage-1 Soulfray and fully refill anima; fully clears anima on crit regardless via override.
- `ritual_budget_success`: ~60% of crit budget.
- `ritual_budget_partial`: ~30%.
- `ritual_budget_failure`: ~10%.
- `ritual_severity_cost_per_point`: 1.

Exact numbers set during implementation against the stage-threshold tuning.

### 8.8 `AnimaConfig`

- `daily_regen_percent`: 5.
- `daily_regen_blocking_property_key`: `blocks_anima_regen`.

## 9. Testing Plan

### 9.1 Unit tests

**`magic/tests/test_anima_ritual.py`**
- Crit (Soulfray 0) → anima max, no severity change.
- Crit (Soulfray stage 2, severity mid-range) → severity fully paid down, anima max (override).
- Success (Soulfray stage 2) → severity reduced, partial anima refill.
- Partial (Soulfray stage 5) → small severity reduction, minimal anima refill.
- Failure (Soulfray 0) → small anima refill.
- Gate: no `CharacterAnimaRitual` → raises.
- Gate: character engaged → raises.
- Gate: second ritual same scene → raises.
- `AnimaRitualPerformance` row persisted with accurate fields.

**`magic/tests/test_anima_regen_tick.py`**
- Character at max → skipped.
- Character below max, no blocking conditions → regens.
- Character below max, Soulfray stage 2 → skipped (blocks_anima_regen).
- Character below max, Soulfray stage 1 → regens.
- Character engaged → skipped.
- N characters → single-digit query count (no N+1).

**`world/conditions/tests/test_decay_severity.py`**
- Decay within stage → stage unchanged.
- Decay across stage boundary → stage walks down, `CONDITION_STAGE_CHANGED` emitted with DESCENDING direction.
- Decay to 0 → `resolved_at` set, resolution event emitted.
- Decay amount > severity → clamps at 0.
- Symmetry: advance then decay by same amount returns to starting stage.

**`world/conditions/tests/test_decay_tick.py`**
- Mix of decaying and non-decaying conditions → only opt-in subset ticks.
- Engagement gate honored per-condition flag.
- `passive_decay_max_severity` gate honored (Soulfray stage 2+ instances not decayed).
- N instances → single-digit query count.

**`world/conditions/tests/test_treatment.py`** (Soulfray aftermath variant):
- Success → aftermath severity reduced.
- Partial → smaller reduction.
- Failure → no reduction, helper gains +1 Soulfray severity.
- Crit → large reduction; aftermath may resolve.
- Gate: already treated this target this scene → raises.
- Gate: no bond thread → raises.
- Gate: target_effect type mismatches target_kind → raises.
- Gate: prerequisite callable rejects → raises.
- Resonance debited from bond thread.
- `TreatmentAttempt` persisted accurately.

**`world/conditions/tests/test_treatment_mage_scar.py`**
- Success → `PendingAlteration.scar_tier` reduced.
- Tier reaches 0 → alteration resolves without escalation.
- Failure backlash to helper.

**`world/conditions/tests/test_stage_entry_aftermath.py`**
- Entering stage with `on_entry_conditions` → aftermath instances appear on character.
- Descending through stages → aftermath instances not auto-removed.
- Same stage entered twice → idempotent, no duplicates.
- Multi-condition stage → all configured aftermaths applied in one hook fire.

### 9.2 Integration test

**`magic/tests/integration/test_soulfray_recovery_flow.py`**

Full scenario:
1. Character accumulates Soulfray to stage 3 (Ripping) → aftermath conditions appear via stage-entry hook.
2. Engagement ends.
3. Bonded helper performs stabilization on one aftermath → severity reduces.
4. Target performs anima ritual → Soulfray severity drops, anima partially refilled.
5. N scheduled-tick cycles → residual aftermath decays passively (if opt-in), Soulfray completes recovery, anima regens when stage drops to 1.
6. Boundary: at Soulfray stage 2, repeated decay ticks alone never recover the character — ritual is required.

### 9.3 Regression scope before push

All suites that Scope 6 plausibly touches:
- `world.magic`
- `world.conditions`
- `world.game_clock`
- `world.mechanics`
- `world.combat` (Mage Scar pipeline)
- `flows` (generic regression)

Run once with `--keepdb` for fast iteration, then once without `--keepdb` to match CI before push.

## 10. Migration & Rollout

- All model changes land as a single coordinated migration pair (one in `conditions`, one in `magic`) produced via `arx manage makemigrations conditions magic` at implementation time.
- No data migrations. Seed updates land via factory module edits and the seed-reload flow.
- File layout conversion (magic models.py → models/ package, services.py → services/ package) is an in-place refactor with no renamed public symbols; `__init__.py` re-exports preserve all import paths.
- Reactive-layer handler registration for `apply_stage_entry_conditions` wires into the existing Scope 5.5 trigger registration path in `conditions`' AppConfig.

## 11. Open Items (deferred, not blocking)

These are called out for future scopes; Scope 6 does not attempt them.

1. **Healing magic** — out-of-scene restoration; explicitly deferred.
2. **Stabilization UI** — player command / web API surface for `perform_treatment` lands with the next magic surfaces scope.
3. **Anima ritual UI** — same; command/API surface deferred.
4. **Additional aftermath content** — the three reference conditions prove the pipeline; design settles and more author over time.
5. **Cross-stage property effects** — `blocks_anima_regen` is the only stage property Scope 6 seeds; future properties (e.g. `blocks_thread_imbuing`, `reduces_check_rank`) may follow the same pattern.
