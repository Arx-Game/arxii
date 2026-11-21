# Magic Scope #7 — Corruption — Design

**Status:** Design
**Date:** 2026-04-25
**Depends on:** Spec A (Resonance currency + Threads + Rituals — DONE), Scope 3 (Soulfray
Progression — DONE), Scope 5 (Magical Alterations — DONE), Scope 5.5 (Reactive
Foundations — DONE), Scope 6 (Soulfray Recovery & Decay — DONE)
**Blocks:** Resonance Pivot Spec B (Soul Tether + Relational Resilience + Ritual
Capstones)
**Related:** `docs/roadmap/magic.md`, `src/world/magic/CLAUDE.md`,
`docs/architecture/soulfray-recovery.md`

> **Updated by #5177 (ADR-5177), 2026-11-17.** This document was written as a design and parts of it
> described stage content the code never had. Read §2.4 and §6.2 for what the stages do in code:
> thresholds, resist checks, warning events at stages 3 and 4, and the protagonism lock at stage 5.
> The early stages now show as Intrusive Thoughts and Compulsion (§13). Corruption a character
> carries now comes down through Sineating, and a Sineater carries it as the Mire (§13.1). The
> Soul Tether redirect never passes overflow to a Sineater: what the Hollow cannot absorb accrues to
> the Sinner (§11.1, §11.5).

---

## 1. Context & Design Intent

### 1.1 What's missing today

Non-Celestial magic should carry an identity-loss risk that is currently undefined
in the codebase. Spec A established the resonance economy (currency, threads,
pulls); Scopes 3 + 6 established the magical-exhaustion arc (Soulfray accumulation,
recovery, decay). What's missing is the **resonance-corruption arc**: the cost of
using your magic isn't just exhaustion (Soulfray) — it's becoming subsumed by the
resonances you channel.

This scope defines Corruption as a parallel-but-distinct mechanic to Soulfray, and
delivers the foundation that Resonance Pivot Spec B (Soul Tether) will mediate
against.

### 1.2 Two distinct axes

| Axis | Mechanic | Source | Recovery |
|---|---|---|---|
| Anima ↔ Soulfray | Magical exhaustion injury | Overburn during cast | Anima ritual, Treatment, decay (Scope 6) |
| Resonance ↔ Corruption | Magical identity-twist drift | Casting Abyssal techniques over time (Primal casts stopped corrupting in #4751); a Sineater's carried corruption (§13.1); giving in to a Compulsion (§13.2) | Sineating (a Sineater takes it on, §13.1), a Sineater's rescue, daily decay. The Rite of Atonement was removed in #4751 (ADR-4751) |

These run in parallel. A character can carry Soulfray and Corruption simultaneously,
recover from one without the other, and reach character-loss-class consequences
through either independently. Both ride condition-instance staging from Scope 3+6.

### 1.3 Narrative pitch

Power flows from identity, but the tools you channel shape the wielder. Abyssal
magic offers tremendous strength at the cost of slow surrender — the resonance
you wield wields you back. Primal magic wears at you in lesser doses; you can
usually self-correct. Celestial magic is its own demanding aspirational practice,
but it does not corrupt — and Celestial alignment is rare to maintain.

The stakes for an Abyssal user grow with their power: a Prospect drips, a powerful
caster pours. A minimal Soul Tether is plenty for an early-tier caster; by mid-tier
it must deepen into a real bond, or the corruption outpaces it. Soul Tethers must
*grow with the bond* — that relational arc is the design promise this foundation
enables.

### 1.4 Pre-alpha posture

We have no players. All tuning values are placeholders, staff-editable via admin,
intended to be adjusted during playtest. The design does not lock specific
magnitudes; it locks the *shape* of the economy and the *mechanisms* by which
values are applied, so tuning is a config change rather than a code change.

### 1.5 What this scope does NOT cover

- **Soul Tether mechanics, redirect math, or Sineater-side authoring** — Spec B's
  responsibility. This foundation provides the interception hook (§3.2) and the
  reactive-event surface (§2.6, §3.5) Spec B builds on.
- **Tether-mediated rescue rituals for stages 3+** — Spec B authors. Foundation
  ships only `reduce_corruption` as the canonical primitive Spec B's rescue
  rituals call.
- **Mission-driven cleansing quests** — future content authoring; foundation
  exposes the same primitives missions will use.
- **Berserker, possession, mind control as parallel autonomy-loss systems** —
  future scopes. The protagonism-lock aggregator (§5.1) is shaped to absorb
  additional sources without retouching consumer-system gates.
- **Specific identity-twist alteration content per resonance** — content
  authoring. Spec ships 1–2 reference templates per non-Celestial affinity for
  canonical examples; broader content is a staff authoring task tracked separately.
- **Abyssal-affinity character creation gating** — existing CG flows.
- **Player-vs-player "put them down" mechanics** — existing combat death
  pipeline applies to subsumed characters without modification.

### 1.6 Existing infrastructure this scope leverages

- `MagicalAlterationTemplate` / `PendingAlteration` / `MagicalAlterationEvent`
  (Scope 5) — extended with `kind` discriminator for `CORRUPTION_TWIST`.
- `ConditionTemplate` / `ConditionInstance` / `ConditionStage` / severity-driven
  advancement / `on_entry_conditions` / passive decay (Scopes 3 + 6) —
  per-resonance corruption staging rides this.
- `Ritual` / `RitualComponentRequirement` SERVICE/FLOW dispatch (Spec A) —
  Spec B's rescue rituals ride it. (The Rite of Atonement was once planned here; it was removed, #4751.)
- `Resonance` / `Affinity` / `CharacterResonance` (Spec A) — counter fields live
  on `CharacterResonance`; affinity coefficient reads through `Resonance.affinity`.
- `get_runtime_technique_stats` (Scope 2) — used to measure resonance stat
  contribution per cast.
- Reactive layer (Scope 5.5) — used as the event surface; this scope adds new
  `EventName` variants (§3.5). The reactive infrastructure (TriggerHandler,
  emit_event, filter DSL) is the prior work; the event names listed in §3.5 are
  introduced here and added to the `EventName` TextChoices in `flows/constants.py`.
- `AlterationGateError` pattern (Scope 5) — extended to `ProtagonismLockedError`
  for consumer-system gates.

---

## 2. Data Model

All new content lives in `world/magic`. All concrete models use `SharedMemoryModel`.
No JSONField. No polymorphic models. All FKs to character data target
`CharacterSheet` (or via Resonance / Affinity) rather than ObjectDB.

### 2.1 `CharacterResonance` field additions

```
corruption_current     PositiveIntegerField  default=0  current load, mutable
corruption_lifetime    PositiveIntegerField  default=0  monotonic audit
```

Sibling to existing `balance` (currency, mutable) and `lifetime_earned` (currency
monotonic audit). Mirrors the established pattern: every facet of "character's
relationship to this resonance" gets both a current state and a lifetime audit.

`corruption_current` increments via `accrue_corruption` (§3.2) and decrements via
`reduce_corruption` (§3.3). Stage progression is driven by this field.

`corruption_lifetime` increments alongside `corruption_current` on every accrual
and never decreases. Pure audit — used for achievement tracking ("first character
to accrue 1000 Abyssal corruption" etc.). Recovery and decay do NOT touch this field, and the
Hollow's redirect only lowers an accrual before it is written. Corruption a Sineater takes on
(§13.1) is an accrual on the Sineater's own row, so it raises their `corruption_lifetime` too.

**Internal denormalization (acknowledged):** `ConditionInstance.severity` on the
per-resonance Corruption condition mirrors `corruption_current` while the condition
exists. Service-layer-managed (one canonical mutation path: `accrue_corruption`
and `reduce_corruption` update both atomically). This bridges two independent
infrastructures (per-resonance corruption fields + Scope 3 ConditionInstance
machinery) and is documented as a known compromise rather than hidden.

### 2.2 `MagicalAlterationTemplate` — `kind` discriminator

Extends Scope 5's `MagicalAlterationTemplate` with a discriminator following Spec
A's per-kind CheckConstraint pattern.

```
kind                 TextChoices(MAGE_SCAR, CORRUPTION_TWIST)  default=MAGE_SCAR
resonance            FK Resonance  null=True, blank=True, on_delete=PROTECT
stage_threshold      PositiveSmallIntegerField  null=True, blank=True  range 1-5
```

Per-discriminator CheckConstraints:

```
alteration_template_mage_scar_shape:
    kind=MAGE_SCAR  ⇒  resonance IS NULL AND stage_threshold IS NULL
alteration_template_corruption_twist_shape:
    kind=CORRUPTION_TWIST  ⇒  resonance IS NOT NULL AND stage_threshold IS NOT NULL
```

`clean()` mirrors the constraints for friendly admin/test errors.

Existing Mage Scar templates migrate to `kind=MAGE_SCAR` via data migration. The
`PendingAlteration` and `MagicalAlterationEvent` models need no field changes —
they FK to `MagicalAlterationTemplate` and inherit the kind via that FK.

The XP-spend gate (`AlterationGateError`, Scope 5's `has_pending_alterations`)
already gates ANY pending alteration regardless of kind, so Corruption Twists
block XP spend identically to Mage Scars without code changes.

### 2.3 `CorruptionConfig` (singleton tuning surface)

Singleton-by-convention (pk=1, lazy-create), matching `SoulfrayConfig` and
`ResonanceGainConfig`. All accrual-formula coefficients staff-tunable via Django
admin. Coefficients stored as integer-tenths (× 0.1 in formula) to avoid float
precision — project pattern. The per-affinity coefficient is not on this config: it is
`Affinity.corruption_coefficient` (Celestial 0, Primal 0, Abyssal 10 in the canonical
values, in tenths: only Abyssal casts corrupt since #4751, when Primal went from 2 to 0), edited on
the Affinity admin.

```
tier_1_coefficient       PositiveSmallIntegerField  default=10   (× 0.1 → 1.0)
tier_2_coefficient       PositiveSmallIntegerField  default=20
tier_3_coefficient       PositiveSmallIntegerField  default=40
tier_4_coefficient       PositiveSmallIntegerField  default=80
tier_5_coefficient       PositiveSmallIntegerField  default=160

deficit_multiplier       PositiveSmallIntegerField  default=20   (× 0.1 → 2.0)
mishap_multiplier        PositiveSmallIntegerField  default=15
audere_multiplier        PositiveSmallIntegerField  default=15

hasty_fall_multiplier / alternate_self_*   later additions to the accrual formula (§3.1)

intrusive_thoughts_stage     PositiveSmallIntegerField  default=1   (#5177, §13)
compulsion_stage             PositiveSmallIntegerField  default=2
sineater_max_stage           PositiveSmallIntegerField  default=2   (a Sineater's Mire stops here)
compulsion_condition         FK ConditionTemplate, null  (the Compulsion's condition)
compulsion_indulge_corruption PositiveIntegerField      default=5

updated_at               DateTimeField  auto_now=True
updated_by               FK AccountDB   null=True, on_delete=SET_NULL
```

Singleton enforcement: `get_corruption_config()` lazy-creates pk=1 on first read.
No DB-level constraint; matches the lightweight singleton pattern used by
`SoulfrayConfig` and `ResonanceGainConfig`.

Decay parameters are NOT stored on `CorruptionConfig` — they live per-resonance
on each `ConditionTemplate`'s `passive_decay_per_day`,
`passive_decay_max_severity`, and `passive_decay_blocked_in_engagement` fields
(Scope 6's per-template model). Staff tune decay independently per resonance.

Stage thresholds are also NOT in `CorruptionConfig` — they live on each
per-resonance `ConditionStage.severity_threshold` (Scope 3's model). This allows
per-resonance tuning of how steep each affinity's curve is.

### 2.4 Per-resonance Corruption authoring shape

No new model — uses existing `ConditionTemplate` + `ConditionStage` +
`MagicalAlterationTemplate` infrastructure.

**Per resonance with corruption authored:** one `ConditionTemplate` row, named
`corruption_<resonance_slug>` or similar. Each row carries:

```
name                                e.g., "Corrupted by Web of Spiders"
slug                                "corruption_web_of_spiders"
parent_condition                    null (Corruption is primary, not aftermath)
passive_decay_per_day               1 (default; tunable per-resonance)
passive_decay_blocked_in_engagement True (mirrors Soulfray)
passive_decay_max_severity          stage 2 threshold value (decay only at stages 1-2)
```

**Five `ConditionStage` rows** per template. The names, thresholds and resist checks are staff-authored
per resonance. What the code does with a stage is short; everything else is content a stage can carry:

| Stage | What the code does |
|---|---|
| Any | `severity_threshold` is when `advance_condition_severity` moves the condition to that stage. With `advancement_resist_failure_kind=HOLD_OVERFLOW` and a `resist_check_type`, crossing the next threshold rolls a resist check against `resist_difficulty` first (§2.6). Whatever the stage's `on_entry_conditions` name is applied on entering it by the generic `apply_stage_entry_aftermath`, so staff may attach any condition to a stage. |
| 3 and 4 | Entering the stage emits `CORRUPTION_WARNING` (`ADVISORY` at stage 3, `URGENT` at stage 4), which authored content listens on (§3.5). |
| 5 | Entering the stage emits `PROTAGONISM_LOCKED`, and `is_protagonism_locked` is true while any corruption condition is at stage 5 (§5). |

The design once sketched more than this: a stage-1 cosmetic "Whispers" condition, and a
Corruption Twist alteration queued when stages 2, 3 and 4 were entered. The code never had either.
No code queues a `CORRUPTION_TWIST` `MagicalAlterationTemplate` on a stage entry; the `kind`
discriminator and the template rows exist (§2.2) and the test-fixture builder
`author_reference_corruption_content()` authors some, but nothing reads them when a character
advances. A stage-1 aftermath condition is content staff may attach through `on_entry_conditions`;
none ships. The early stages are shown to the player as **Intrusive Thoughts** and **Compulsion**
instead (§13): that is display by `CorruptionConfig`'s `intrusive_thoughts_stage` and
`compulsion_stage`, not a rename of any template, and the Compulsion's penalty is a separate
condition the config names.

`MagicalAlterationTemplate` rows with `kind=CORRUPTION_TWIST` can still be authored per
(resonance, stage_threshold) pair. Nothing in the engine creates a pending alteration from one
when a stage is entered.

**Coverage policy:** A Resonance with no authored Corruption ConditionTemplate is
a no-op for accrual — `accrue_corruption` logs an audit event and returns without
creating a phantom condition. Spec ships with reference templates for 1–2
non-Celestial resonances per non-Celestial affinity (Primal + Abyssal); broader
content is a staff authoring task tracked separately.

**Lazy condition creation:** The per-resonance Corruption `ConditionInstance` is
created only when `corruption_current` first crosses stage 1's `severity_threshold`.
Below that threshold, accrual lives only on `CharacterResonance.corruption_current`
— no condition row is written. Characters who casually cast non-Celestial magic
do not accumulate dormant condition rows for every resonance they've touched.

**Auto-removal on full decay:** `decay_condition_severity` (Scope 6) calls
`resolve_condition` when severity drops below stage 1's threshold. The condition
row is removed; trace counter remains on `CharacterResonance` as audit. The
character's mechanical state is clean again; their history is preserved on
`corruption_lifetime`.

### 2.5 `CharacterSheet` methods

No handler class — methods directly on `CharacterSheet`. Single-bool aggregator
queries are `cached_property`; multi-row queries are explicit methods.

```python
class CharacterSheet(...):
    def get_corruption_stage(self, resonance: Resonance) -> int:
        """Return current Corruption stage for one resonance (0 = no condition,
        1-5 = stage). Reads via the per-resonance Corruption ConditionInstance.
        """
        ...

    @cached_property
    def is_protagonism_locked(self) -> bool:
        """True if the character is mechanically locked from protagonism.

        Today: corruption terminal stage is the only source.
        Future: berserker terminal state, possession, etc. expand the OR.
        """
        return self._has_corruption_terminal_stage()

    def _has_corruption_terminal_stage(self) -> bool:
        # ConditionInstance.target FKs to ObjectDB (the character typeclass);
        # CharacterSheet links to its character via the existing sheet→character
        # path (the resolver is the standard sheet→character helper used by
        # other magic services — see Spec A's CharacterCorruptionHandler usage
        # patterns for the canonical resolution).
        character = self.character  # implementation detail: actual attribute
                                    # / helper resolved per existing sheet
                                    # patterns
        if character is None:
            return False
        return ConditionInstance.objects.filter(
            target=character,
            condition__corruption_resonance__isnull=False,
            current_stage__stage_order=5,
        ).exists()
```

`ConditionInstance.target` FKs to `objects.ObjectDB` (the character typeclass)
per the existing conditions model. The query walks
`CharacterSheet → character (ObjectDB) → condition_instances`; the helper that
resolves `sheet → character` exists on the existing CharacterSheet (used by
other magic services). The query filter uses
`current_stage__stage_order=5` (the actual `ConditionStage.stage_order` field;
not "stage_number") and `condition__corruption_resonance` (the marker FK on
`ConditionTemplate` formalized in §3.4).

`corruption_current` and `corruption_lifetime` are real fields on
`CharacterResonance` per §2.1 — no method needed for them.

`is_protagonism_locked` is invalidated on stage transitions via the standard
cached_property invalidation pattern (service layer clears the cache after
mutations).

Future autonomy-loss systems (berserker, possession) extend
`is_protagonism_locked` by adding their own `_has_X` predicate and OR-ing it in.
No handler infrastructure to refactor.

### 2.6 Wiring `ConditionStage` resist checks into stage advancement

Scope 3's `advance_condition_severity` currently advances stages deterministically
on threshold crossing. This scope wires the existing — but unused —
`ConditionStage.resist_check_type` and `ConditionStage.resist_difficulty` fields
into the advancement path so the character can roll to avoid escalation. The
check-failure path is severity-aware to support the "pushing yourself fails fast"
design intent.

**Existing fields on `ConditionStage` (already in the codebase, currently
unused by `advance_condition_severity`):**

```
resist_check_type      FK CheckType  null=True   "Check type to resist progression"
resist_difficulty      PositiveIntegerField  default=10  "Difficulty to resist progression"
```

These were authored at Scope 3 landing as a hook for resist-on-advance behavior
but never wired into `advance_condition_severity`. This scope wires them.

**Field addition on `ConditionStage` (only one new field):**

```
advancement_resist_failure_kind  TextChoices  default=ADVANCE_AT_THRESHOLD
   ADVANCE_AT_THRESHOLD = existing behavior; advance on threshold crossing
                          (the resist check, if any, is ignored — preserves
                          back-compat for any existing content that authored
                          resist_check_type for non-advancement reasons).
   HOLD_OVERFLOW         = severity accumulates over threshold; each accrual
                          that crosses or holds-above the next stage's threshold
                          rolls a resist check via resist_check_type +
                          resist_difficulty. Pass holds, fail advances.
```

Existing conditions outside Soulfray and Corruption keep working unchanged —
`advancement_resist_failure_kind` defaults to ADVANCE_AT_THRESHOLD, which is
the current behavior even if `resist_check_type` is non-null. Per-content
authoring opts into the resist-check gate by setting failure_kind=HOLD_OVERFLOW.

**Service extension to `advance_condition_severity`:**

The function gains an `outcome: AdvancementOutcome` field on its
`SeverityAdvanceResult` return type:

```python
class AdvancementOutcome(TextChoices):
    NO_CHANGE = "NO_CHANGE", "No stage change"
    HELD = "HELD", "Threshold crossed but resist check passed"
    ADVANCED = "ADVANCED", "Stage advanced"


@dataclass
class SeverityAdvanceResult:
    previous_stage: "ConditionStage | None"
    new_stage: "ConditionStage | None"
    stage_changed: bool
    total_severity: int
    outcome: AdvancementOutcome  # NEW field, this scope
```

The function logic is extended (sketch — exact integration with the existing
function body):

```python
def advance_condition_severity(
    instance: ConditionInstance,
    amount: int,
) -> SeverityAdvanceResult:
    instance.severity += amount

    next_stage = (
        instance.condition.stages.filter(
            severity_threshold__isnull=False,
            severity_threshold__lte=instance.severity,
        )
        .order_by("-severity_threshold")
        .first()
    )

    if next_stage and next_stage != instance.current_stage:
        if (next_stage.advancement_resist_failure_kind == HOLD_OVERFLOW
                and next_stage.resist_check_type is not None):
            # Fire reactive event so triggers can intervene
            check_result = perform_advancement_resist_check(
                instance, next_stage,
            )
            if check_result.passed:
                # Hold at current stage; severity persists over threshold
                instance.save(update_fields=["severity"])
                return SeverityAdvanceResult(
                    previous_stage=instance.current_stage,
                    new_stage=instance.current_stage,
                    stage_changed=False,
                    total_severity=instance.severity,
                    outcome=AdvancementOutcome.HELD,
                )
        # Advance + fire on_entry aftermath (existing path)
        instance.current_stage = next_stage
        instance.save(...)
        # ... existing stage-change emission + apply_stage_entry_aftermath ...
        return SeverityAdvanceResult(
            ...,
            outcome=AdvancementOutcome.ADVANCED,
        )

    instance.save(update_fields=["severity"])
    return SeverityAdvanceResult(..., outcome=AdvancementOutcome.NO_CHANGE)
```

`perform_advancement_resist_check` emits the new
`EventName.CONDITION_STAGE_ADVANCE_CHECK_ABOUT_TO_FIRE` reactive event
(introduced in this scope, §3.5) before resolving. Triggers (Soul Tether
mediation, Kudos rerolls, ally interventions, future content) listen on this
event and can modify the roll's bonus, force a reroll, or prompt the player.
Standard Scope 5.5 pattern.

**Backward compatibility for existing callers:** `SeverityAdvanceResult` gains
the `outcome` field but retains all existing fields. Existing destructuring
callers (e.g., `SoulfrayProgressionTests`) continue to read `previous_stage`,
`new_stage`, `stage_changed`, `total_severity`. The new field is additive; tests
that need to verify HELD vs ADVANCED behavior add `result.outcome` assertions.

**HOLD_OVERFLOW semantics:** When severity exceeds threshold but the resist
check passed, severity persists on the condition row at the over-threshold
value (the sync to `corruption_current` per §2.1 also keeps that field above
threshold). The next accrual triggers another check (pressure mounts; cumulative
resists become harder via authored modifiers — e.g., a stage-keyed
ConditionCheckModifier per Scope 3's pattern, or per-prior-pass scaling).
The character "holds the line" but the line keeps creeping; eventually they fail.

**Severity is not clamped at the threshold under HOLD_OVERFLOW.** A character
who passed the stage 1→2 check at 200 severity (threshold 200) can hold at
stage 1 with severity=200, and the next accrual lands them at severity=210
still rolling for stage 2 advancement. `corruption_current` mirrors this
unbounded value. If they later fail, the new stage's `severity` starts at the
overflowed value — they jump straight into deep-stage-2 territory rather than
flooring back to the threshold.

### 2.7 Constraints & integrity summary

- `CharacterResonance.corruption_current` decreases only via service layer
  (`reduce_corruption`); no model-level monotonicity check (would forbid the
  legitimate decrease path).
- `CharacterResonance.corruption_lifetime` monotonic via service layer
  (`accrue_corruption` only); no model-level check.
- `MagicalAlterationTemplate` per-kind CheckConstraints enforce field shape per
  §2.2.
- `CorruptionConfig` singleton-by-convention; no DB constraint.
- Per-resonance `ConditionTemplate` rows are content; standard ConditionTemplate
  validation applies.
- `ConditionStage.advancement_resist_failure_kind` defaults to
  `ADVANCE_AT_THRESHOLD`, preserving existing behavior for every unmodified
  condition. The existing `resist_check_type` (nullable) and `resist_difficulty`
  (default 10) fields keep their existing schema; this scope only wires them
  into `advance_condition_severity` when the failure_kind opts in. Existing
  content authored against `resist_check_type` for non-advancement reasons
  (if any) continues to work unchanged.
- The new `ConditionTemplate.corruption_resonance` FK (§3.4) is nullable and
  defaults to NULL, so every existing ConditionTemplate row remains valid
  post-migration.

---

## 3. Services & Accrual Formula

All new services in `world/magic/services/corruption.py`. Mirrors Scope 6's split
(`anima.py`, `soulfray.py`, etc.).

### 3.1 Per-cast accrual formula (`accrue_corruption_for_cast`)

The canonical accrual call inside the technique pipeline. Called once per cast
at a hook point in `services/techniques.py`, after Soulfray accumulation and
before consequence-pool dispatch.

```python
def accrue_corruption_for_cast(
    *,
    caster_sheet: CharacterSheet,
    technique_use_result: TechniqueUseResult,
    config: CorruptionConfig | None = None,
) -> CorruptionAccrualSummary:
    """Apply per-resonance corruption ticks for one technique cast.

    Reads runtime stats from technique_use_result to identify which
    resonances contributed and by how much. For each non-Celestial
    resonance involved with non-zero tick, calls accrue_corruption.

    Returns a frozen summary (per-resonance ticks, stage transitions,
    advancement-check outcomes) for downstream UI / event consumers.
    """
```

Internal computation per involved resonance R:

```
involvement(R) = stat_bonus_R_contributed_to_this_cast
              + sum(resonance_cost of pulls anchored to threads with resonance=R)

base_tick(R)   = involvement(R)
               × affinity_coefficient[R.affinity]   / 10
               × tier_coefficient[technique.tier]   / 10

multipliers    = ((deficit ? deficit_multiplier : 10)
                × (mishap   ? mishap_multiplier   : 10)
                × (audere   ? audere_multiplier   : 10)) / 1000

tick(R)        = ceil(base_tick(R) × multipliers)
```

**Amended by #5231 (ADR-5231).** A cast is worked in one resonance, so only that resonance gets the cast's
`stat_bonus_contribution` (the whole runtime intensity); a pull's spend still attaches to the resonance that paid for
it. The tick is no longer rounded on its own. With `ordinary` the exact `base_tick × multipliers` (`_raw_tick`),
`hasty_fall` the exact hasty-fall part, and `part` the caster's share of the full corruption
(`cast_corruption_part`: 100 when the Abyssal share of her own true aura reaches
`CorruptionConfig.full_corruption_from_share`, else `CorruptionConfig.light_corruption_percent`; no aura counts as 100),
`tick(R) = ceil((ordinary × part / 100 + hasty_fall) × leak_percent / 100)`: one rounding up, the light part reduces the
ordinary tick (a pull paid in an Abyssal resonance included) and never the hasty-fall part, and the part is read only
when some ordinary tick is above zero. See `docs/systems/magic.md` "A cast is worked in one resonance".

If `tick(R) == 0` after rounding (Celestial resonances always; very low Primal
cantrip casts often), no service call is made for R — no accrual, no event, no
audit trail noise.

For each R with `tick(R) > 0`:

```python
accrue_corruption(
    character_sheet=caster_sheet,
    resonance=R,
    amount=tick(R),
    source=CorruptionSource.TECHNIQUE_USE,
    technique_use=technique_use_result,
)
```

**Note on stat-bonus measurement:** `stat_bonus_R_contributed_to_this_cast`
reads from Scope 2's `get_runtime_technique_stats` output, which already returns
per-resonance contributions to the runtime intensity/control bonuses. The
formula consumes that breakdown directly; no new instrumentation is required in
the runtime stats pipeline.

### 3.2 `accrue_corruption` — canonical accrual entry point

The single call site for all corruption accrual. Spec B's Soul Tether redirect
intercepts here; future autonomy-loss systems plug into the same shape.

```python
def accrue_corruption(
    *,
    character_sheet: CharacterSheet,
    resonance: Resonance,
    amount: int,
    source: CorruptionSource,
    technique_use: TechniqueUseResult | None = None,
    redirect_origin: CharacterSheet | None = None,
) -> CorruptionAccrualResult:
    """Apply `amount` corruption to (sheet, resonance) and resolve stage.

    Steps (atomic in one transaction):
      1. Increment CharacterResonance.corruption_current and
         corruption_lifetime by amount.
      2. If no per-resonance Corruption ConditionTemplate authored for
         resonance, log audit event and return (no-op).
      3. Get-or-create the ConditionInstance for (character, template) only
         if corruption_current crosses stage 1 threshold this call. Otherwise
         no condition row written.
      4. Sync ConditionInstance.severity to corruption_current. Call
         advance_condition_severity (which handles resist checks per
         §2.6 and stage-entry on_entry_conditions firing). Under
         HOLD_OVERFLOW failure_kind, severity is NOT clamped at threshold
         on a passing resist check — both severity and corruption_current
         persist at the over-threshold value, so the next accrual rolls
         from the elevated baseline (pressure mounts).
      5. Emit corruption_accrued event with a frozen payload.
      6. If stage transition resolves to a warning stage (3 or 4), emit
         corruption_warning event with appropriate severity.
      7. If stage transition resolves to stage 5, emit protagonism_locked
         event (§3.5).

    redirect_origin is non-null when this call is an overflow re-call from the Soul
    Tether redirect handler; it is a recursion guard, skipping the redirect and the
    Sineater resistance. Nothing in the code sets it today (§11.1).

    Before step 1 a Sineater's resistance softens the amount (§13.1), except for
    source INDULGED, which adds exactly what staff configured.
    """
```

Returns a frozen `CorruptionAccrualResult` dataclass (per project's
no-dict-returns rule):

```python
@dataclass(frozen=True)
class CorruptionAccrualResult:
    resonance: Resonance
    amount_applied: int
    current_before: int
    current_after: int
    lifetime_before: int
    lifetime_after: int
    stage_before: int
    stage_after: int
    advancement_outcome: AdvancementOutcome  # NO_CHANGE / HELD / ADVANCED
    condition_instance: ConditionInstance | None  # None if accrual stayed sub-threshold
```

**Pre-mutation event for Spec B interception:** Before step 1, foundation emits
a `corruption_accruing` reactive event with the proposed accrual payload
(character_sheet, resonance, amount, source, redirect_origin; the amount is mutable).
Spec B's Soul Tether redirect handler listens on this event and, when the Sinner has
Hollow capacity in the resonance, lowers `payload.amount` by what the Hollow absorbs. A
payload amount of 0 ends the accrual. The unabsorbed remainder accrues to the Sinner as
this same accrual; nothing is passed to the Sineater. The handler skips sources
`SINEATING_CARRIED` and `INDULGED`. Foundation does nothing tether-specific.

### 3.3 `reduce_corruption` — canonical recovery entry point

Called by recovery rituals (Spec B's tether-mediated rescue
rituals, future Mission rituals). Decrement the field, sync the condition,
fire stage-decrement events.

```python
def reduce_corruption(
    *,
    character_sheet: CharacterSheet,
    resonance: Resonance,
    amount: int,
    source: CorruptionRecoverySource,
    ritual: Ritual | None = None,
    grant_resonance_back: bool = True,
    shrink_holdings: bool = True,
) -> CorruptionRecoveryResult:
    """Reduce corruption_current on (sheet, resonance), sync the condition.

    Steps (atomic):
      1. Decrement CharacterResonance.corruption_current (clamp at 0).
      1b. Keep a Sineater's Mire holdings within the corruption that is left (§13.1):
          corruption that is not held for any Sinner comes off first, then the
          holdings shrink in proportion. Skipped when shrink_holdings is False,
          which only release_mire passes because it lowers one holding itself.
      2. corruption_lifetime UNCHANGED.
      3. If a ConditionInstance exists, call decay_condition_severity
         (Scope 6) which retreats stages and resolves the condition
         when severity drops below stage 1 threshold.
      3b. Grant the resonance cleansing payout back, unless grant_resonance_back is
          False (Sineating and settling the Mire pay by their own rules).
      4. Emit corruption_reduced event.
      5. If stage retreat crosses out of stage 5, emit protagonism_restored
         event (§3.5).
    """
```

### 3.4 Passive decay integration & `ConditionTemplate.corruption_resonance` FK

**`ConditionTemplate.corruption_resonance` field addition (required, this scope):**

```
corruption_resonance   FK Resonance  null=True, blank=True, on_delete=PROTECT
                       help_text="Non-null marks this template as a per-resonance
                                  Corruption ConditionTemplate. Drives is_protagonism_locked
                                  detection (§2.5) and decay-time field sync (§3.4)."
```

Authored non-null on per-resonance Corruption ConditionTemplates (one per
resonance with Corruption authored). Null on every other ConditionTemplate
(Soulfray, aftermath, magical alterations, etc.). Single FK addition; serves
as the marker for both the protagonism-lock detection query (§2.5) and the
decay-time field sync below.

**Decay integration:**

Decay rides Scope 6's `decay_all_conditions_tick` unchanged. Per-resonance
Corruption ConditionTemplates author `passive_decay_per_day` (default 1),
`passive_decay_max_severity` set to stage 2's threshold, and
`passive_decay_blocked_in_engagement=True`.

Scope 6's `decay_condition_severity` is extended (small additive change) to
also decrement `CharacterResonance.corruption_current` when the condition's
template has `corruption_resonance` non-null. Implementation:
`decay_condition_severity` calls `reduce_corruption` internally for
Corruption-kind conditions, so the field-syncing path is the same one rituals
use. Single canonical mutation path. Non-Corruption templates' decay paths
are unchanged.

### 3.5 Risk-transparency events

`accrue_corruption` and the advancement-check path emit the following reactive
events. **All seven names are added to `EventName` TextChoices in
`flows/constants.py` as part of this scope** — the reactive layer (Scope 5.5)
binds `TriggerDefinition.event_name` to this enum, so events authored only as
bare strings cannot be used in trigger filters. The data migration adds these
seven variants in the same migration that introduces the corruption models.

| `EventName` variant | When | Payload |
|---|---|---|
| `CORRUPTION_ACCRUING` | Pre-mutation (interception) | character_sheet, resonance, amount, source |
| `CORRUPTION_ACCRUED` | Post-mutation | `CorruptionAccrualResult` fields |
| `CORRUPTION_WARNING` | On entry to stage 3 or 4 | character_sheet, resonance, stage, severity (ADVISORY \| URGENT) — character-loss-possible at stage 3, character-loss-likely at stage 4 |
| `PROTAGONISM_LOCKED` | On entry to stage 5 | character_sheet, resonance, cause (TextChoices) — character-loss explicit |
| `PROTAGONISM_RESTORED` | On exit from stage 5 | character_sheet, cause |
| `CORRUPTION_REDUCED` | Post-mutation in `reduce_corruption` | `CorruptionRecoveryResult` fields |
| `CONDITION_STAGE_ADVANCE_CHECK_ABOUT_TO_FIRE` | Inside `perform_advancement_resist_check`, pre-roll | condition, target_stage, base_difficulty (modifiable by triggers) |

The existing `EventName.CONDITION_STAGE_CHANGED` event continues to fire from
Scope 3's stage-change emission inside `advance_condition_severity` (already
implemented at lines ~1481–1493 of `world/conditions/services.py`). This scope
does not retitle that event; it adds the new ones above for the corruption-
specific and resist-check-specific moments.

UI surfaces (warning prompts, character-loss notices) are authored content
listening on these events. The user-facing copy on `CORRUPTION_WARNING`
(stages 3 and 4) and `PROTAGONISM_LOCKED` (stage 5) MUST use the exact phrase
"character loss" rather than euphemisms — surfaced to player at the moment of
risk, not buried in tooltips. The Audere offer flow (Scope 2) gains a
pre-Audere advisory if the character has any resonance at corruption stage 3+.

### 3.6 Service summary table

```
accrue_corruption_for_cast(...)    Per-cast orchestrator. Hook from techniques.py.
accrue_corruption(...)             Atomic single-resonance accrual + stage resolution.
                                   Spec B intercepts here.
reduce_corruption(...)             Atomic single-resonance decrement + stage retreat.
                                   Rescue, Sineating, settling the Mire, decay and staff
                                   call it; future Missions will.
get_corruption_config()            Lazy-create singleton (pk=1).
```

No public ritual-specific service in §3: recovery rituals are content that uses these
primitives via a FlowDefinition's effect step.

---

## 4. Atonement Rite (removed in #4751)

This section once described a self-targeted cleansing rite for stages 1 and 2 of the performer's own
corruption. It was built as a SERVICE ritual (`perform_atonement_rite`) rather than the FLOW shape
sketched here, and it never ran: ritual dispatch called it with arguments it did not accept. #4751
removed it with its Ritual row, its conversion rate and `CorruptionRecoverySource.ATONEMENT_RITE`
(ADR-4751). Corruption a character carries falls by daily decay (Scope 6), by a Sineater's rescue
(Spec B), and, since #5177, by Sineating: a Sineater takes it on (§13.1). Stage 1 and 2 characters
had only decay until then. The settling rite (`docs/systems/magic.md`, "Drift correction") is the
one rite for a changing aura. It writes no corruption for a character's own resonances, and it
settles the Mire a Sineater carries by lowering their corruption (`CorruptionRecoverySource.MIRE_SETTLED`,
§13.1). "Atonement" survives only as the plain word for a settling-rite reflection that turns away
from something.

The foundation primitives (`reduce_corruption`, `get_corruption_stage`) are unchanged and are what
Spec B's rescue rituals call.

---

## 5. Protagonism Lock & Consumer Hooks

### 5.1 `is_protagonism_locked` derivation

Per §2.5, a `cached_property` on `CharacterSheet`:

```python
@cached_property
def is_protagonism_locked(self) -> bool:
    return self._has_corruption_terminal_stage()
```

Today: corruption terminal stage is the only source. Future autonomy-loss
systems (berserker, possession, mind control) extend the OR by adding their own
predicates and updating the cached_property.

Consumer-system gates (§5.3) read this aggregate, not the corruption-specific
query. They don't care WHY the lock is in place; they care that protagonism
is locked.

### 5.2 `ProtagonismLockedError`

Sibling to existing `EventError` / `JournalError` / `ProgressionError` /
`AlterationGateError` typed-exception pattern:

```python
class CorruptionError(Exception):
    user_message: str
    SAFE_MESSAGES: ClassVar[set[str]] = {...}

class ProtagonismLockedError(CorruptionError):
    SAFE_MESSAGES = {
        "Character is currently locked from protagonism and cannot perform this action.",
    }
```

Used by API layer (per project pattern) — view layers translate to 403/422
responses with `exc.user_message`, never `str(exc)`. Service functions raise it;
view permission classes or serializer validation surfaces it cleanly.

### 5.3 Consumer-system hooks

Each consumer system adds a one-line check on `is_protagonism_locked` and
either raises `ProtagonismLockedError` (error context) or skips the operation
(tick/silent context). Foundation enumerates the gates; consumer-system PRs
implement them in the same scope merge as the foundation.

| System | Location | Behavior on lock |
|---|---|---|
| Resonance gain (Spec C) | `create_pose_endorsement`, `create_scene_entry_endorsement`, `residence_trickle_tick`, `settle_weekly_pot` | Skip silently (sheet's own gain paused; others endorsing them is also blocked at the validation layer) |
| Progression (XP) | `world.progression.services.spends.spend_xp_on_unlock` | Raise `ProtagonismLockedError` |
| AP regen | `ap_regen_tick` | Skip silently — AP regen for the locked sheet pauses |
| Stories (protagonism) | story participation creation / advancement service functions | Locked sheet cannot be added as protagonist participant; existing protagonist participation transitions to NPC participation status (or is preserved-but-silenced — Stories app authoring decision) |
| Scene initiation | scene creation service functions invoked by player commands | Locked sheet cannot initiate own scenes; can still be invoked by other PCs' scenes |
| Resonance currency spend | `spend_resonance_for_imbuing`, `spend_resonance_for_pull` | Raise `ProtagonismLockedError` |

These changes ship in the same PR as the corruption foundation. Each is small
(one-line `if sheet.is_protagonism_locked:` block); the spec lists them so the
implementation plan can sequence them.

### 5.4 Mechanical interpretation of "Subsumed"

When a Corruption ConditionInstance reaches stage 5, the player's character
becomes mechanically NPC-like:

- Cannot drive their own story (stories gates)
- Cannot earn for their own progression (resonance gain, XP, AP gates)
- Cannot initiate scenes for own goals (scene gate)
- Cannot spend their resonance currency on imbuing or pulls (currency gates)

The character is NOT removed from the world. They remain in scenes other PCs
invoke them in (existing stories app machinery handles this), the original
player can puppet them mechanically when they appear, and the existing combat
death pipeline applies if other PCs choose to "put them down."

Foundation does not add an "NPC mode" account/character flag. The combination
of consumer-system gates above IS the mechanical expression of "no longer a
protagonist." Player-side UI reads `is_protagonism_locked` to display state and
surface the constraint visibly.

### 5.5 Lock exit

`reduce_corruption` calls dropping severity below stage 5 threshold
automatically resolve the lock — Scope 6's `decay_condition_severity` retreats
stage, the cached_property invalidates, the gates lift. Foundation emits
`protagonism_restored` event for UI / RP messaging.

Spec B's tether-mediated rescue ritual is the canonical authored path
triggering this. Future Mission rituals provide alternative paths. Death exit
uses the existing combat death pipeline (no foundation changes).

---

## 6. Config & Tuning

### 6.1 `CorruptionConfig` defaults

Per §2.3. Lazy-created singleton. Default values (placeholders, tuned in
playtest):

| Knob | Default | Reasoning |
|---|---|---|
| `Affinity.corruption_coefficient` (Celestial) | 0 | Celestial never corrupts |
| `Affinity.corruption_coefficient` (Primal) | 0 | Primal casts stopped corrupting in #4751 |
| `Affinity.corruption_coefficient` (Abyssal) | 10 (× 0.1 → 1.0) | Abyssal at full rate |
| `tier_1_coefficient` | 10 | Cantrip baseline |
| `tier_2_coefficient` | 20 | Doubles per tier |
| `tier_3_coefficient` | 40 | |
| `tier_4_coefficient` | 80 | |
| `tier_5_coefficient` | 160 | Heaviest techniques pour |
| `deficit_multiplier` | 20 (× 0.1 → 2.0) | Deficit casts 2× |
| `mishap_multiplier` | 15 (× 0.1 → 1.5) | Mishap casts 1.5× |
| `audere_multiplier` | 15 (× 0.1 → 1.5) | Audere 1.5× |
| `intrusive_thoughts_stage` / `compulsion_stage` | 1 / 2 | The stages at which the impulse is shown and then becomes a Compulsion (§13) |
| `sineater_max_stage` | 2 | The stage a Sineater's carried corruption stops at (§13.1) |
| `compulsion_condition` | unset | The condition a Compulsion lays; the Required content page lists it while unset |
| `compulsion_indulge_corruption` | 5 | Corruption added when a character gives in to a Compulsion (§13.2) |

Target curve: a Prospect (level 1, tier 1 cantrips) casting Abyssal magic accrues
~1 corruption per cast. Stage 1 threshold of 50 = 50 cantrip casts to enter
stage 1. A level-3 caster running tier-3 techniques accrues
~10–20 per cast — stage 1 in a few sessions, stage 2 within the level.

These curves are illustrative. Playtest will retune; the spec's intent is the
*shape* (Abyssal pours, Primal drips, Celestial nothing; tier escalates
disproportionately), not the magnitudes.

### 6.2 Per-resonance ConditionTemplate authoring conventions

Reference templates ship at scope landing for at least one resonance per
non-Celestial affinity (e.g., one Primal + one Abyssal). Each authored template
provides:

- 5 ConditionStage rows with severity_threshold, resist_check_type,
  resist_difficulty, advancement_resist_failure_kind=HOLD_OVERFLOW
- optionally `on_entry_conditions` on any stage; nothing is required there, stage 5 needs none
  because `is_protagonism_locked` is derived, and no code reads Corruption Twist alterations
  when a stage is entered (§2.4)
- `passive_decay_per_day=1`, `passive_decay_max_severity` set to stage 2's
  threshold, `passive_decay_blocked_in_engagement=True`

Other resonances are `accrue_corruption` no-ops until staff author content.

### 6.3 Subsumption check tuning

Stage 4 → 5 advancement check is *the* anti-character-loss inflection. Authored
at high difficulty (default DC 35 for Abyssal corruption; lower for Primal).
This is where Spec B's Soul Tether intervention triggers fire, where Kudos
rerolls plug in, where ally interventions and future Mission ritual triggers
listen on the reactive event to modify the roll.

Stage 1→2, 2→3 authored at moderate difficulty (DC 12 / DC 18 for Abyssal;
lower for Primal — corruption is meant to be slow at early stages).

Stage 3→4 authored at higher difficulty (DC 25 for Abyssal). Crossing into
stage 4 should be a real character-defining event the player can fight against.

All values are placeholders; staff tunes via per-stage ConditionStage rows.
Soulfray's stage DCs (§7.1) and Corruption's stage DCs are independently
authored — the difficulties differ in the retrofit table because the two
conditions have different intended progression curves. Implementers should
not assume the values match.

---

## 7. Soulfray Retrofit

The generalized `ConditionStage` advancement-check extension (§2.6) requires
Soulfray's existing stages to be retrofitted with check parameters, otherwise
Soulfray progression remains deterministic-on-threshold while Corruption gains
the resist-check mechanic. Consistency requires both to use the same
infrastructure.

### 7.1 Data migration

A single data migration sets resist-check parameters on existing Soulfray
ConditionStage rows. The `resist_check_type` and `resist_difficulty` fields
already exist on ConditionStage (Scope 3 authored them as a hook); the
migration populates them and sets the new `advancement_resist_failure_kind`
field to opt the stages into resist-gated advancement:

| Stage | resist_check_type | resist_difficulty | advancement_resist_failure_kind |
|---|---|---|---|
| 1→2 (Tearing) | magical endurance | 8 | HOLD_OVERFLOW |
| 2→3 (Ripping) | magical endurance | 10 | HOLD_OVERFLOW |
| 3→4 (Sundering) | magical endurance | 18 | HOLD_OVERFLOW |
| 4→5 (Unravelling) | magical endurance | 25 | HOLD_OVERFLOW |

### 7.2 Audere accessibility tuning

Stage 1→2 and 2→3 difficulties are deliberately low so Audere-eligible
characters reliably reach Soulfray stage 3 under sustained pushing. The resist
check is NOT meant to gate Audere accessibility — it gates the late-stage
Sundering / Unravelling cascade.

### 7.3 Existing test updates

`SoulfrayProgressionTests` (Scope 3 / Scope 6) updated for the new behavior:
passing a resist check now holds at the lower stage with severity over
threshold; existing assertions about "advances on threshold crossing" become
"advances on threshold crossing + resist check failure."

The retrofit may shift some test expectations; the migration is part of this
scope's PR.

### 7.4 No new Soulfray content

This scope does not add new Soulfray stages, consequence pools, or aftermath
conditions. The retrofit is purely infrastructural — Soulfray's existing
content keeps working.

---

## 8. Testing Strategy

### 8.1 Unit tests (`world/magic/tests/`)

- **CorruptionConfig:** singleton creation, default values, lazy-create on
  first read.
- **`accrue_corruption_for_cast` formula:** per-affinity coefficients (Celestial
  zero, Primal 0.2, Abyssal 1.0); per-tier escalation; multipliers (deficit /
  mishap / Audere); rounding (ceil); zero-tick suppression.
- **`accrue_corruption`:** field updates atomic; lazy condition creation on
  first stage-1 crossing; sub-threshold accrual leaves no condition; multiple
  callers don't deadlock; redirect_origin pass-through.
- **`reduce_corruption`:** field updates atomic; condition severity sync; stage
  retreat; lifetime field unchanged; clamp at zero.
- **Stage advancement check:** authored DC, resist check fires on threshold
  crossing, HOLD_OVERFLOW pass-path leaves severity over threshold without
  stage advance, ADVANCE_AT_THRESHOLD path preserved for unmodified conditions.
- **`is_protagonism_locked`:** derives from stage 5 ConditionInstance
  presence, cached_property invalidation on stage transition.
- **`MagicalAlterationTemplate.kind` discriminator:** CheckConstraints fire on
  invalid shapes; existing MAGE_SCAR rows untouched; CORRUPTION_TWIST rows
  require resonance + stage_threshold.

### 8.2 Integration tests

In `src/world/magic/tests/integration/test_corruption_flow.py`, mirroring
Scope 6's `test_soulfray_recovery_flow.py` pattern:

1. **Full per-cast accrual.** Caster casts an Abyssal tier-3 technique with
   thread pulls. `corruption_current` and `corruption_lifetime` increment by
   the formula's expected value on the involved resonance. Audit event emitted.
2. **Lazy condition creation.** Repeated cantrip casts accrue counter; no
   ConditionInstance until threshold crossed; on crossing, condition created at
   stage 1; stage 1's `on_entry_conditions` (cosmetic affliction) applied.
3. **Resist check holds.** At stage 1 → 2 boundary, character passes the
   resist check; severity holds over threshold; stage stays at 1; next cast
   triggers another resist check.
4. **Resist check fails.** Same boundary; check fails; stage advances to 2;
   stage 2 `on_entry_conditions` queue a Corruption Twist alteration; player
   resolves via existing PendingAlteration flow.
5. **Stage 5 subsumption.** Stages cascade to 5; `protagonism_locked` event
   emitted; `is_protagonism_locked` returns True.
6. **Consumer-system gates.** Subsumed character: blocked from XP spend,
   resonance currency spend, scene initiation; resonance gain hooks skip them;
   AP regen pauses.
7. **(Removed, #4751.)** The Atonement Rite full path no longer exists; stage 1
   corruption falls only by decay or a Sineater's rescue.
8. **(Removed, #4751.)** The Atonement refusal scenarios went with the rite.
9. **Decay over time.** Corruption ConditionInstance at stage 1 decays per
   Scope 6 daily tick; severity drops; condition auto-resolves when below
   stage 1 threshold; counter on CharacterResonance decrements per the §3.4
   sync; lifetime field unchanged.
10. **No coverage no-op.** `accrue_corruption` on a resonance without a
    Corruption ConditionTemplate authored: counter increments, audit event
    fires, no condition created, no error.
11. **Lock exit.** Subsumed character has corruption reduced via `reduce_corruption`
    (simulating a future Spec B rescue or staff intervention); lock lifts;
    `protagonism_restored` event emitted; consumer gates clear.
12. **Soulfray retrofit regression.** Existing Soulfray progression tests pass
    against the new advancement-check shape with retrofit defaults. No Audere
    accessibility regression: a deficit-pushing caster reliably reaches
    Soulfray stage 3.

### 8.3 Factories (`world/magic/factories.py`)

- `CorruptionConfigFactory` (singleton helper).
- `CorruptionConditionTemplateFactory` (per-resonance, with five staged
  ConditionStage rows authored at default thresholds).
- `CorruptionTwistTemplateFactory` (MagicalAlterationTemplate with
  kind=CORRUPTION_TWIST, parameterized resonance + stage_threshold).
- `with_corruption_at_stage(character_sheet, resonance, stage)` helper — sets
  the field, creates the condition, advances to the target stage. Used by
  tests and integration scenarios.

### 8.4 Regression coverage

Changes to `MagicalAlterationTemplate` (new `kind` field), `ConditionStage`
(new advancement check fields), and `CharacterResonance` (new corruption
fields) require full-regression runs against magic, conditions, and progression
test suites. Run with and without `--keepdb` before PR (per project CLAUDE.md).

---

## 9. Out of Scope

Explicitly NOT in this scope:

- Soul Tether mechanics (Spec B)
- Tether-mediated rescue rituals for stages 3+ (Spec B)
- Sineater minor temporary affliction authoring (Spec B authors `ConditionTemplate`s)
- Mission-driven cleansing quests (future)
- Berserker / possession / mind-control as parallel autonomy-loss systems
  (future scopes; protagonism aggregator is shaped for them)
- Specific identity-twist alteration content beyond the 1–2 reference
  templates per non-Celestial affinity (staff content authoring)
- Player-vs-player "put them down" mechanics (existing combat death pipeline)
- Abyssal-affinity character creation gating (existing CG flows)
- Public corruption leaderboards (CharacterResonance.corruption_lifetime
  enables this in the future, but no public surface ships now)
- Generic protagonism-lock UI surface (per-system UI authoring)

---

## 10. Risks & Unknowns

### 10.1 Stat-bonus measurement reliability

The accrual formula's `stat_bonus_R_contributed_to_this_cast` reads from
Scope 2's `get_runtime_technique_stats`. If that pipeline's per-resonance
attribution is incomplete or fuzzy, corruption ticks may misattribute.
Implementation phase verifies the runtime stats output exposes per-resonance
contributions cleanly; if it doesn't, additional instrumentation is needed.
Flagged for impl-phase resolution.

### 10.2 ConditionTemplate FK addition

The `corruption_resonance` FK addition on `ConditionTemplate` (§3.4) is a
schema change to a Scope 3 model. Migration is straightforward (nullable FK,
defaults null), but the change touches a foundational table — regression
coverage is critical.

### 10.3 Soulfray retrofit behavior shift

Adding HOLD_OVERFLOW resist checks to Soulfray's existing stages changes
behavior at thresholds (passes now hold rather than advance). Existing
Soulfray content is tuned around immediate advancement; retrofit defaults
(low difficulty at early stages) keep Audere accessible, but deeper Soulfray
playtests may need additional tuning.

### 10.4 Per-resonance authoring overhead

Each resonance requires an authored Corruption ConditionTemplate + 5
ConditionStages to be "live."
Pre-alpha that's tractable for a curated set; scaling to all canonical
resonances is content authoring, not architectural.

### 10.5 Internal denormalization (corruption_current ↔ ConditionInstance.severity)

Service-layer-managed sync. Potential drift if a non-canonical mutation path
emerges. Mitigation: only `accrue_corruption`, `reduce_corruption`, and Scope
6 decay (which delegates to `reduce_corruption`) write to either field.
Documented as a known compromise; staff reconciliation query handles drift if
it ever appears.

### 10.6 Cache invalidation for `is_protagonism_locked`

The cached_property must be invalidated on stage 5 transitions. Service-layer
mutations must clear the cache (the same pattern existing handler caches
follow). Implementation phase verifies all stage-5-touching code paths invalidate.

### 10.7 ProtagonismLockedError consumer coverage

Each consumer system listed in §5.3 must add its gate in the same PR. Missing
a consumer leaves a hole — a Subsumed character could (e.g.) still spend XP if
the progression gate is forgotten. Implementation plan must enumerate all
consumers; regression tests catch missed gates.

---

## 11. Handoff to Spec B (Soul Tether)

The foundation's interface to Spec B in five surfaces. Spec B does not modify
foundation code; it consumes the surfaces.

### 11.1 `accrue_corruption` interception

Spec B's tether redirect listens on the `corruption_accruing` reactive event
emitted by `accrue_corruption` before the field mutation. When the targeted
character is a Sinner with Hollow capacity on an active tether in this resonance,
the handler (`soul_tether_redirect_handler`) drains the Hollow and lowers
`payload.amount` by what it absorbed. It does not cancel the event and it issues no
replacement call: the remainder accrues to the Sinner as the same accrual, and a
fully absorbed accrual ends at amount 0. **Nothing passes to the Sineater.** An earlier
design sent a "trace amount" to the Sineater; Spec B diverged from it
(`docs/architecture/soul-tether.md` §5.3), and corruption reaches a Sineater only when they
take it on by Sineating (§13.1).

Foundation does nothing tether-specific. `accrue_corruption(redirect_origin=...)` and
`CorruptionSource.SPEC_B_REDIRECT` remain in the code for the overflow-to-Sineater idea that
Sineating superseded; the handler reads `redirect_origin` only as a recursion guard.

### 11.2 `reduce_corruption` primitive

Spec B's tether-mediated rescue rituals (FLOW-dispatched `Ritual` rows
authored in Spec B, with Soul Tether
eligibility gates and stage 3+ effect ranges) call `reduce_corruption` as
their effect step. Sineating and settling the Mire call it too (§13.1). Foundation primitive, Spec B content.

### 11.3 Stage advancement check intervention

Spec B's Soul Tether registers triggers that listen on
`EventName.CONDITION_STAGE_ADVANCE_CHECK_ABOUT_TO_FIRE` for the Abyssal partner. A Sineater in the
same room is prompted to commit Hollow capacity and take Tether Strain for a bonus to the
Sinner's resist roll. Standard reactive-layer authoring.

### 11.4 Sineater minor temporary afflictions

The design planned authored `ConditionTemplate` rows for Sineater-flavored afflictions ("Heavy
Soul," "Whispers Heard," etc.). They were not built. What a Sineater feels from carried
corruption is the Intrusive Thoughts and Compulsion display of §13 and the Mire's own stage
conditions, from the Sineater's own corruption.

### 11.5 Carried corruption on the Sineater

A Sineater's `corruption_current` and `corruption_lifetime` rise when they take on a Sinner's
corruption by Sineating, as if they had cast on that resonance themselves, except that their
resistance (§13.1) softens it. The corruption falls when they settle the Mire (§13.1), by daily
decay, and by another Sineater's Sineating or rescue; the Rite of Atonement that once offered
self-cleansing was removed in #4751.

---

## 12. Naming Conventions Used in This Spec

For implementation reference, the names introduced or finalized:

**Models / fields:**

*New:*
- `CharacterResonance.corruption_current` (PositiveIntegerField)
- `CharacterResonance.corruption_lifetime` (PositiveIntegerField)
- `MagicalAlterationTemplate.kind` (extended TextChoices: MAGE_SCAR / CORRUPTION_TWIST)
- `MagicalAlterationTemplate.resonance` (FK Resonance, nullable)
- `MagicalAlterationTemplate.stage_threshold` (PositiveSmallIntegerField, nullable)
- `ConditionTemplate.corruption_resonance` (FK Resonance, nullable, on_delete=PROTECT;
  marker for Corruption-kind templates per §3.4)
- `ConditionStage.advancement_resist_failure_kind` (TextChoices, default ADVANCE_AT_THRESHOLD)
- `SeverityAdvanceResult.outcome` (new field on existing dataclass; AdvancementOutcome enum)
- `CorruptionConfig` (singleton model, pk=1), with the impulse and Sineater-cap fields of #5177
- `MireHolding` (#5177; `world/magic/models/soul_tether.py`) and `ImpulseShown` (#5177;
  `world/magic/models/impulse.py`)

*Existing — referenced but not added:*
- `ConditionStage.resist_check_type` (FK CheckType, nullable; existed at Scope 3
  landing, wired into advancement by this scope)
- `ConditionStage.resist_difficulty` (PositiveIntegerField, default 10; existed,
  wired into advancement by this scope)
- `ConditionStage.stage_order` (existing field; the spec's queries filter on
  `current_stage__stage_order=5` — the field is `stage_order`, not `stage_number`)
- `ConditionInstance.target` (existing FK to ObjectDB; the protagonism-lock
  query filters via this field)

**Enums / TextChoices:**
- `AlterationKind.MAGE_SCAR`, `AlterationKind.CORRUPTION_TWIST`
- `CorruptionSource.TECHNIQUE_USE`, `CorruptionSource.SPEC_B_REDIRECT`,
  `CorruptionSource.STAFF_GRANT`, `CorruptionSource.DEFILEMENT`, and, from #5177,
  `CorruptionSource.SINEATING_CARRIED` and `CorruptionSource.INDULGED`
- `CorruptionRecoverySource.SPEC_B_RESCUE`,
  `CorruptionRecoverySource.PASSIVE_DECAY`,
  `CorruptionRecoverySource.STAFF_GRANT`, and, from #5177,
  `CorruptionRecoverySource.SINEATING` and `CorruptionRecoverySource.MIRE_SETTLED`
- `CorruptionCause.STAGE_5_SUBSUMPTION`, `CorruptionCause.STAGE_5_RECOVERED`
- `AdvancementResistFailureKind.ADVANCE_AT_THRESHOLD`,
  `AdvancementResistFailureKind.HOLD_OVERFLOW` (TextChoices on
  ConditionStage.advancement_resist_failure_kind)
- `AdvancementOutcome.NO_CHANGE`, `AdvancementOutcome.HELD`,
  `AdvancementOutcome.ADVANCED` (TextChoices used as the
  `SeverityAdvanceResult.outcome` field type)

**Services:**
- `accrue_corruption_for_cast(...)`
- `accrue_corruption(...)`
- `reduce_corruption(...)`
- `get_corruption_config()`

**Methods on `CharacterSheet`:**
- `get_corruption_stage(resonance) -> int`
- `is_protagonism_locked` (cached_property)
- `_has_corruption_terminal_stage()` (private)

**Reactive events (added to `flows.constants.EventName` TextChoices in this scope):**
- `EventName.CORRUPTION_ACCRUING`
- `EventName.CORRUPTION_ACCRUED`
- `EventName.CORRUPTION_WARNING`
- `EventName.CORRUPTION_REDUCED`
- `EventName.PROTAGONISM_LOCKED`
- `EventName.PROTAGONISM_RESTORED`
- `EventName.CONDITION_STAGE_ADVANCE_CHECK_ABOUT_TO_FIRE`

**Existing events referenced (not added by this scope):**
- `EventName.CONDITION_STAGE_CHANGED` (existing Scope 3 emission; continues
  firing from `advance_condition_severity`)

**Errors:**
- `CorruptionError` (base)
- `ProtagonismLockedError`

**Authored content:**
- Per-resonance Corruption ConditionTemplates with 5 ConditionStages each are content-repo rows; the
  production seeder authors none. The test-fixture builder `author_reference_corruption_content()`
  makes a reference set, with CORRUPTION_TWIST templates nothing reads at runtime (§2.4).
- Soulfray ConditionStage retrofit (data migration only)
- The Compulsion condition (named on `CorruptionConfig.compulsion_condition`), staff-authored with a
  scene duration and a check modifier that scales with severity (§13.2)

---

## 13. Carried Corruption and Impulses (#5177)

### 13.1 Corruption a Sineater carries: the Mire

Corruption a character carries comes down only through a Sineater, apart from daily decay. A
Sineater takes it on by Sineating (`docs/architecture/soul-tether.md` §7): `take_on_corruption` lowers
the Sinner's corruption through `reduce_corruption` (source `SINEATING`, no resonance cleansing
payout) and raises the Sineater's through `accrue_corruption` (source `SINEATING_CARRIED`). The
corruption is the Sineater's own: it sits on their `CharacterResonance.corruption_current` for the
Sinner's resonance, with that resonance's `ConditionInstance` and stages, so it climbs the same
stages as a Sinner's own. **The Mire** is the name for exactly this corruption, and for nothing else.

- **Whose it is.** `MireHolding` (per Sineater-side `CharacterRelationship` and resonance: `amount`)
  partitions `corruption_current` by Sinner.
  **Invariant: the holdings in a resonance never sum to more than the Sineater's corruption in it.**
  Only `take_on_corruption` and `release_mire` (`world/magic/services/mire.py`) write `amount`. When
  corruption falls for any other reason (daily decay, a rescue, staff), `reduce_corruption` takes
  unheld corruption first and then shrinks the holdings in proportion (largest remainder, each at
  most its own). Corruption a Sineater adds by giving in to a Compulsion (§13.2) is more of the
  Mire: `add_to_largest_holding` assigns it to the Sinner with the most held.
- **Resistance.** `_apply_sineater_corruption_resistance` shrinks what arrives, by `lifetime_helped`
  in the resonance against `SoulTetherConfig.resistance_full_at`, capped at 90%, for a Sineater with
  any live thread on a tether. It does not apply to `INDULGED`.
- **The stage cap.** The Mire stops at the Compulsion stage: the ritual takes on only what fits below
  the threshold of the stage after `CorruptionConfig.sineater_max_stage`, working backward through the
  resistance (`corruption_that_can_move`), and refuses when nothing fits until the Sineater settles
  some. A Sineater's own casting is not capped by it.
- **Coming down.** The Sineater settles the Mire through the settling rite by Absolve, Condemn or
  Succumb (`services/mire_settling.py`). Absolve and Condemn lower the corruption and the holding with
  `release_mire`, which calls `reduce_corruption` with source `MIRE_SETTLED`, no cleansing payout and
  no holding shrink (the holding is lowered itself). Succumb turns the Mire into resonance in the
  Sineater's own aura. Details are in `docs/architecture/soul-tether.md` §7.5.
- **A fallen Sineater** (aura predominantly Abyssal) serves no one: Sineating and the rescue refuse
  (`SineaterFallenError`).

### 13.2 Impulses: Intrusive Thoughts and Compulsion

A character carrying corruption in a resonance, whether their own or a Sineater's Mire, feels that
resonance pull. The same code serves a Sinner and a Sineater because it reads corruption, not the
tether (`world/magic/services/impulses.py`).

- **Display.** From the stage `CorruptionConfig.intrusive_thoughts_stage` (default 1) the corruption
  condition is shown as "Intrusive Thoughts: <resonance>"; from `compulsion_stage` (default 2) as
  "Compulsion: <resonance>". This is `corruption_display_name`, used by the condition serializers (the
  owner's and the observers'), `mire_carried_by`, telnet `resonances` and the Soul Tether panel.
  It is display only: no template is renamed, nothing in the database changes, and it is never a lookup
  key.
- **Intrusive Thoughts.** When something the resonance cares about is present in a scene (an authored
  situation of that resonance holds: `kindled_for(...).fed_tier`), the character is sent
  `Resonance.impulse_text` (or a plain line when staff wrote none), once per resonance per scene
  (`ImpulseShown`). Nothing else happens, and the player always chooses what the character does.
- **Compulsion.** At the Compulsion stage, when that is present and the character has not earned
  the resonance by a deed of their own since the scene began (`earned_in_scene`: a grant from
  `COMPULSION_INDULGING_SOURCES`, today only a kindled deed),
  `CorruptionConfig.compulsion_condition` is laid on them at severity `stage - compulsion_stage + 1`.
  Staff author that condition with a scene duration and a check modifier that scales with severity, so
  the penalty rides their rolls for the rest of the scene. Unset, nothing is laid and the Required
  content page lists it. The condition is named by `compulsion_condition`; it is a `ConditionTemplate`,
  not the control-loss `Compulsion` model in `world/conditions/models.py`.
- **Giving in.** When a kindled deed (a `COMPULSION_INDULGING_SOURCES` grant) grows the resonance in a
  live scene (`grant_resonance` calls `give_in_to_compulsion`), the first such deed lifts the Compulsion
  for the scene, tells the character (after the transaction commits), and adds `compulsion_indulge_corruption` of corruption in the resonance (source
  `INDULGED`: exactly the configured amount, no resistance, and the Hollow absorbs none of it). A
  Sineater's addition is carried for the Sinner with the largest holding. A grant from another player, a
  GM or a cron (a settled pose endorsement, a scene entry, a mission reward) is not the character giving
  in and never counts, and neither is succumbing to the Mire, which is a settling. A failure in the give-in
  is logged and never rolls back the grant.
- **Lifting.** Settling below the Compulsion stage, the situation passing, or giving in lifts the
  condition the next time impulses are refreshed. `refresh_impulses` runs when a pose is posted (web and
  telnet), before a cast's modifiers are gathered, and when the kindled resonances panel and telnet
  `resonances` are shown; `impulses_now` only reads. Every call goes through `safe_refresh_impulses`, which
  logs and swallows a failure so the pose, cast or panel proceeds, and a line is not spent while the
  character has no live session.
- **Scars.** The conditions are built so that magical scars can reuse them later; nothing here
  prevents it.
