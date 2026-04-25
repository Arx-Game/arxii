# Magic Scope #7 — Corruption — Design

**Status:** Design
**Date:** 2026-04-25
**Depends on:** Spec A (Resonance currency + Threads + Rituals — DONE), Scope 3 (Soulfray
Progression — DONE), Scope 5 (Magical Alterations — DONE), Scope 5.5 (Reactive
Foundations — DONE), Scope 6 (Soulfray Recovery & Decay — DONE)
**Blocks:** Resonance Pivot Spec B (Soul Tether + Relational Resilience + Ritual
Capstones)
**Related:** `docs/roadmap/magic.md`, `src/world/magic/CLAUDE.md`,
`docs/superpowers/specs/2026-04-21-magic-scope-6-soulfray-recovery-design.md`

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
| Resonance ↔ Corruption | Magical identity-twist drift | Casting non-Celestial techniques over time | Atonement Rite (this scope), Soul Tether mediation (Spec B), decay |

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
  Atonement Rite is a FLOW-dispatched Ritual.
- `Resonance` / `Affinity` / `CharacterResonance` (Spec A) — counter fields live
  on `CharacterResonance`; affinity coefficient reads through `Resonance.affinity`.
- `get_runtime_technique_stats` (Scope 2) — used to measure resonance stat
  contribution per cast.
- Reactive layer (Scope 5.5) — `condition_stage_advance_check_about_to_fire`
  event surface for resist-check intervention; `corruption_accruing` event for
  Spec B's redirect interception.
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
to accrue 1000 Abyssal corruption" etc.). Recovery, decay, and Spec B's tether
redirect do NOT touch this field.

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
precision — project pattern.

```
celestial_coefficient    PositiveSmallIntegerField  default=0    (× 0.1 → 0.0)
primal_coefficient       PositiveSmallIntegerField  default=2    (× 0.1 → 0.2)
abyssal_coefficient      PositiveSmallIntegerField  default=10   (× 0.1 → 1.0)

tier_1_coefficient       PositiveSmallIntegerField  default=10   (× 0.1 → 1.0)
tier_2_coefficient       PositiveSmallIntegerField  default=20
tier_3_coefficient       PositiveSmallIntegerField  default=40
tier_4_coefficient       PositiveSmallIntegerField  default=80
tier_5_coefficient       PositiveSmallIntegerField  default=160

deficit_multiplier       PositiveSmallIntegerField  default=20   (× 0.1 → 2.0)
mishap_multiplier        PositiveSmallIntegerField  default=15
audere_multiplier        PositiveSmallIntegerField  default=15

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

**Five `ConditionStage` rows** per template, with severity_threshold values per
the design intent (placeholder defaults; staff tune):

| Stage | Name | severity_threshold | Effects |
|---|---|---|---|
| 1 | Whispers | 50 | `on_entry_conditions`: minor cosmetic affliction (e.g., "Whispers Heard," fast-decaying, RP-flag only). No alteration queued. |
| 2 | Manifestation | 200 | `on_entry_conditions`: queue first Corruption Twist alteration via the existing `MAGICAL_SCARS`-style effect handler with `kind=CORRUPTION_TWIST`. |
| 3 | Erosion | 500 | Second Corruption Twist queued + `corruption_warning` reactive event with severity ADVISORY. |
| 4 | Subsumption-Adjacent | 1000 | Third Corruption Twist queued + `corruption_warning` reactive event with severity URGENT ("character loss likely without intervention"). |
| 5 | Subsumption | 1500 | No further Corruption Twist queued. The subsumption itself is the terminal effect — `protagonism_locked` event fires (§3.5). |

Stage advancement-check parameters (per §2.6) are also authored per-stage.

**`MagicalAlterationTemplate` rows with `kind=CORRUPTION_TWIST`** authored per
(resonance, stage_threshold) pair. Library of personality/RP-flagged alterations.
Player resolves via the existing `PendingAlteration` library-pick / scratch-author
flow (Scope 5). Resonance-flavored — Web of Spiders templates are
predatory-caretaker themes, Flames of the Defiant templates are burn-it-all-down
rage themes.

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
        return ConditionInstance.objects.filter(
            character_sheet=self,
            template__corruption_resonance__isnull=False,
            stage_number=5,
        ).exists()
```

`corruption_current` and `corruption_lifetime` are real fields on
`CharacterResonance` per §2.1 — no method needed for them.

`is_protagonism_locked` is invalidated on stage transitions via the standard
cached_property invalidation pattern (service layer clears the cache after
mutations).

Future autonomy-loss systems (berserker, possession) extend
`is_protagonism_locked` by adding their own `_has_X` predicate and OR-ing it in.
No handler infrastructure to refactor.

### 2.6 Generalized `ConditionStage` advancement-check extension

Scope 3's `advance_condition_severity` currently advances stages deterministically
on threshold crossing. This scope adds a resist-check gate at advancement so the
character can roll to avoid escalation. The check-failure path is severity-aware
to support the "pushing yourself fails fast" design intent.

**Field additions on `ConditionStage`** (Scope 3 model; affects all stage-driven
conditions, not just Corruption):

```
advancement_check_type           FK CheckType   null=True
                                    null = no resist check (default; existing behavior)
advancement_check_difficulty     PositiveSmallIntegerField  default=0
advancement_resist_failure_kind  TextChoices  default=ADVANCE_AT_THRESHOLD
                                    ADVANCE_AT_THRESHOLD: existing behavior, advance immediately
                                    HOLD_OVERFLOW: severity accumulates over threshold;
                                                   each accrual rolls; pass holds, fail advances
```

Existing conditions (everything outside Soulfray and Corruption) keep working
unchanged because `advancement_check_type` defaults to NULL. Per-content
authoring opts into the resist check.

**Service extension to `advance_condition_severity`:**

```python
def advance_condition_severity(condition, amount, *, source_event=None):
    new_severity = condition.severity + amount
    new_stage = compute_stage_from_severity(condition.template, new_severity)

    if new_stage > condition.stage:
        next_stage = condition.template.stages.get(stage_number=condition.stage + 1)
        if next_stage.advancement_check_type is not None:
            check_result = perform_advancement_check(
                condition, next_stage, source_event=source_event,
            )
            if check_result.passed:
                condition.severity = new_severity
                condition.save(update_fields=["severity"])
                return AdvancementResult.HELD
        advance_to_stage(condition, next_stage, new_severity)
        return AdvancementResult.ADVANCED

    condition.severity = new_severity
    condition.save(update_fields=["severity"])
    return AdvancementResult.NO_CHANGE
```

`perform_advancement_check` emits a `condition_stage_advance_check_about_to_fire`
reactive event before resolving. Triggers (Soul Tether mediation, Kudos rerolls,
ally interventions, future content) listen on this event and can modify the
roll's bonus, force a reroll, or prompt the player. Standard Scope 5.5 pattern.

**HOLD_OVERFLOW semantics:** When severity exceeds threshold but the resist
check passed, severity persists on the condition row at the over-threshold
value. The next accrual triggers another check (pressure mounts; cumulative
resists become harder via authored modifiers, e.g., per-prior-pass penalty). The
character "holds the line" but the line keeps creeping; eventually they fail.

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
- `ConditionStage.advancement_*` fields are nullable/defaulted to preserve
  existing behavior for unmodified conditions.

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
         §2.6 and stage-entry on_entry_conditions firing).
      5. Emit corruption_accrued event with a frozen payload.
      6. If stage transition resolves to a warning stage (3 or 4), emit
         corruption_warning event with appropriate severity.
      7. If stage transition resolves to stage 5, emit protagonism_locked
         event (§3.5).

    redirect_origin is non-null when this call is the Sineater leg of
    a Soul Tether redirect (Spec B sets this). Foundation passes it
    through to the audit event payload; no foundation-side behavior.
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
(character_sheet, resonance, amount). Spec B's Soul Tether redirect listens on
this event and (when conditions match) calls `cancel_event` (Scope 5.5
CANCEL_EVENT) and issues replacement `accrue_corruption` calls — a reduced
amount to the original Abyssal target plus a small trace amount to the Sineater.
Foundation does nothing tether-specific; the redirect is fully Spec B's
authoring.

### 3.3 `reduce_corruption` — canonical recovery entry point

Called by recovery rituals (Atonement Rite §4, Spec B's tether-mediated rescue
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
) -> CorruptionRecoveryResult:
    """Reduce corruption_current on (sheet, resonance), sync the condition.

    Steps (atomic):
      1. Decrement CharacterResonance.corruption_current (clamp at 0).
      2. corruption_lifetime UNCHANGED.
      3. If a ConditionInstance exists, call decay_condition_severity
         (Scope 6) which retreats stages and resolves the condition
         when severity drops below stage 1 threshold.
      4. Emit corruption_reduced event.
      5. If stage retreat crosses out of stage 5, emit protagonism_restored
         event (§3.5).
    """
```

### 3.4 Passive decay integration

Decay rides Scope 6's `decay_all_conditions_tick` unchanged. Per-resonance
Corruption ConditionTemplates author `passive_decay_per_day` (default 1),
`passive_decay_max_severity` set to stage 2's threshold, and
`passive_decay_blocked_in_engagement=True`.

Scope 6's `decay_condition_severity` is extended (small additive change) to
also decrement `CharacterResonance.corruption_current` for Corruption-kind
conditions. Implementation: `decay_condition_severity` calls `reduce_corruption`
internally when the condition's template is identified as Corruption-kind, so
the field-syncing path is the same one rituals use. Single canonical mutation
path.

Identification of Corruption-kind ConditionTemplates: by the presence of an
authored corruption-specific marker. Recommended implementation: a
`corruption_resonance` FK on `ConditionTemplate` (non-null for Corruption
templates, null otherwise) — the same marker referenced by `_has_corruption_terminal_stage`
in §2.5. Adding a single FK to `ConditionTemplate` is preferable to scanning
template names or maintaining a separate registry.

### 3.5 Risk-transparency events

`accrue_corruption` emits the following reactive events (Scope 5.5 surface):

| Event | When | Payload |
|---|---|---|
| `corruption_accruing` | Pre-mutation (interception) | character_sheet, resonance, amount, source |
| `corruption_accrued` | Post-mutation | CorruptionAccrualResult fields |
| `corruption_warning` | On entry to stage 3 or 4 | character_sheet, resonance, stage, severity (ADVISORY \| URGENT) |
| `protagonism_locked` | On entry to stage 5 | character_sheet, resonance, cause=CorruptionCause.STAGE_5_SUBSUMPTION |
| `protagonism_restored` | On exit from stage 5 | character_sheet, cause=CorruptionCause.STAGE_5_RECOVERED |
| `corruption_reduced` | Post-mutation in `reduce_corruption` | CorruptionRecoveryResult fields |
| `condition_stage_advance_check_about_to_fire` | Inside `perform_advancement_check`, pre-roll | condition, target_stage, base_difficulty (modifiable by triggers) |

UI surfaces (warning prompts, character-loss notices) are authored content
listening on these events. The Audere offer flow (Scope 2) gains a pre-Audere
advisory if the character has any resonance at corruption stage 3+.

### 3.6 Service summary table

```
accrue_corruption_for_cast(...)    Per-cast orchestrator. Hook from techniques.py.
accrue_corruption(...)             Atomic single-resonance accrual + stage resolution.
                                   Spec B intercepts here.
reduce_corruption(...)             Atomic single-resonance decrement + stage retreat.
                                   Atonement Rite + Spec B + future Missions all call.
get_corruption_config()            Lazy-create singleton (pk=1).
```

No public ritual-specific service in §3 — the Atonement Rite is content (§4)
that uses these primitives via its FlowDefinition's effect step.

---

## 4. Atonement Rite (Authored Content)

The foundation's only authored cleansing ritual. Self-targeting; effective for
stages 1–2 of the performer's own corruption. Spec B and future Mission specs
author the heavier paths.

### 4.1 Ritual row

One `Ritual` row authored at scope landing using the Spec A `Ritual` model — no
new model.

```
name                    "Rite of Atonement"
slug                    "rite_of_atonement"
execution_kind          FLOW
flow                    FK FlowDefinition (authored alongside)
service_function_path   "" (FLOW dispatch)
site_property           FK Property "consecrated_ground"
hedge_accessible        False
glimpse_eligible        False
narrative_prose         (authored)
```

`RitualComponentRequirement` rows author component costs. The "asks a lot of
participants" weight is expressed via multi-component requirements + multi-step
flow content (§4.2), not via a single resource cost. Specific components are
content authoring; spec ships placeholder requirements that staff retune.

### 4.2 FlowDefinition shape

The flow's eligibility gates are standard flow check steps reading from existing
surfaces. Sketch (actual flow content is authored, not code):

1. **Verify performer affinity** — check step against
   `performer.character.aura.primary_affinity`. Allowed: Celestial or Primal.
   Failure → flow aborts via the existing ritual-abort path.
2. **Verify self-targeting** — check step that target == performer.
3. **Verify corruption stage in range** — check step that
   `target.get_corruption_stage(resonance) in (1, 2)`.
4. **Consume ritual components** — standard Spec A `RitualComponentRequirement`
   consumption.
5. **Narrative steps** — multi-step flow content (witness presence, recitations,
   prompts) authored per design intent.
6. **Effect step** — call
   `reduce_corruption(character_sheet=performer_sheet, resonance=target_resonance, amount=<authored>, source=CorruptionRecoverySource.ATONEMENT_RITE)`.
   Amount is a flow step parameter, authored on the FlowDefinition.

The flow-check abort path uses whatever signaling the flow system already emits
— same shape as any other ritual that fails preconditions. No new error
vocabulary.

### 4.3 Foundation primitives the flow uses

Already shipped in §3 — no atonement-specific code:

- `reduce_corruption` (§3.3) — the only mechanical effect call
- `CharacterSheet.get_corruption_stage(resonance)` (§2.5) — eligibility query
- `CharacterAura.primary_affinity` and `Resonance.affinity` — existing surfaces

If the flow system cannot natively express "check target's corruption stage on
a resonance," the fix is a generic flow check step type (a flow primitive), not
an atonement-specific helper. The foundation does NOT ship per-ritual
validators.

### 4.4 What the foundation does NOT ship

- **Other-targeting variants** (Celestial cleansing of a Primal/Abyssal ally) —
  Spec B / future Mission specs.
- **Stage 3+ recovery rituals** — Spec B authors via additional `Ritual` rows +
  FlowDefinitions reusing the same primitives.
- **Subsumption rescue ritual** — Spec B's Soul Tether rescue path is the
  canonical authored answer.
- **Bulk atonement** — one rite per resonance is the design intent; matches the
  "narrative weight per resonance" framing.
- **Cooldowns / per-scene limits** — content tuning, not foundation
  infrastructure.

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
| `celestial_coefficient` | 0 | Celestial never corrupts |
| `primal_coefficient` | 2 (× 0.1 → 0.2) | Primal accrues 1/5 the rate of Abyssal |
| `abyssal_coefficient` | 10 (× 0.1 → 1.0) | Abyssal at full rate |
| `tier_1_coefficient` | 10 | Cantrip baseline |
| `tier_2_coefficient` | 20 | Doubles per tier |
| `tier_3_coefficient` | 40 | |
| `tier_4_coefficient` | 80 | |
| `tier_5_coefficient` | 160 | Heaviest techniques pour |
| `deficit_multiplier` | 20 (× 0.1 → 2.0) | Deficit casts 2× |
| `mishap_multiplier` | 15 (× 0.1 → 1.5) | Mishap casts 1.5× |
| `audere_multiplier` | 15 (× 0.1 → 1.5) | Audere 1.5× |

Target curve: a Prospect (level 1, tier 1 cantrips) casting Abyssal magic accrues
~1 corruption per cast. Stage 1 threshold of 50 = 50 cantrip casts to trigger
"Whispers." A level-3 caster running tier-3 techniques accrues
~10–20 per cast — stage 1 in a few sessions, stage 2 within the level.

These curves are illustrative. Playtest will retune; the spec's intent is the
*shape* (Abyssal pours, Primal drips, Celestial nothing; tier escalates
disproportionately), not the magnitudes.

### 6.2 Per-resonance ConditionTemplate authoring conventions

Reference templates ship at scope landing for at least one resonance per
non-Celestial affinity (e.g., one Primal + one Abyssal). Each authored template
provides:

- 5 ConditionStage rows with severity_threshold, advancement_check_type,
  advancement_check_difficulty, advancement_resist_failure_kind=HOLD_OVERFLOW
- on_entry_conditions for stage 1 (cosmetic/RP flag), stages 2–4 (queue
  Corruption Twist alterations), stage 5 (subsumption marker — typically empty
  since `is_protagonism_locked` is derived)
- 2–4 `MagicalAlterationTemplate` rows with `kind=CORRUPTION_TWIST`, per
  (resonance, stage_threshold), populated as the library pool for stage 2/3/4
  alteration application
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

---

## 7. Soulfray Retrofit

The generalized `ConditionStage` advancement-check extension (§2.6) requires
Soulfray's existing stages to be retrofitted with check parameters, otherwise
Soulfray progression remains deterministic-on-threshold while Corruption gains
the resist-check mechanic. Consistency requires both to use the same
infrastructure.

### 7.1 Data migration

A single data migration adds advancement-check parameters to existing Soulfray
ConditionStage rows:

| Stage | advancement_check_type | advancement_check_difficulty | advancement_resist_failure_kind |
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
7. **Atonement Rite full path.** Celestial performer with stage 1 corruption
   on a Primal resonance; performs Rite of Atonement; FlowDefinition consumes
   components; effect step calls `reduce_corruption`; severity drops below
   stage 1 threshold; condition resolved.
8. **Atonement refused.** Abyssal performer attempts Atonement → flow check
   step fails on affinity gate. Performer with stage 3 corruption attempts
   Atonement → flow check step fails on stage gate.
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
- Atonement other-targeting (Celestial cleansing of an ally) — Spec B / future
- Atonement cooldowns / per-scene limits — content tuning, not infrastructure
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

Each resonance requires authored Corruption ConditionTemplate + 5
ConditionStages + 2–4 Corruption Twist alteration templates to be "live."
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
character has an active Soul Tether and is in the Abyssal role for this
resonance, Spec B cancels the original event (Scope 5.5 CANCEL_EVENT) and
issues two replacement `accrue_corruption` calls:
- A reduced amount to the original Abyssal target (the unredirected portion)
- A small trace amount to the Sineater (one of their claimed Primal resonances —
  selection logic is Spec B's authoring)

Foundation does nothing tether-specific. The redirect is fully Spec B's
authoring. The trace-to-Sineater portion uses the same `accrue_corruption`
primitive, with stage-1 thresholds tuned high enough that trace ticks don't
advance the Sineater under normal tether activity; passive decay keeps the
Sineater's counter low.

### 11.2 `reduce_corruption` primitive

Spec B's tether-mediated rescue rituals (FLOW-dispatched `Ritual` rows
authored in Spec B, mirroring §4's Atonement shape but with Soul Tether
eligibility gates and stage 3+ effect ranges) call `reduce_corruption` as
their effect step. Foundation primitive, Spec B content.

### 11.3 Stage advancement check intervention

Spec B's Soul Tether registers triggers that listen on
`condition_stage_advance_check_about_to_fire` for the Abyssal partner. Triggers
apply the Sineater's contribution to the resist roll — bonus, co-roll, or
forced-pass depending on tether tier and Sineater affinity. Standard
reactive-layer authoring.

### 11.4 Sineater minor temporary afflictions

Spec B authors `ConditionTemplate` rows for Sineater-flavored afflictions
("Heavy Soul," "Whispers Heard," etc.) — fast-decaying, non-staging, applied
via the existing condition machinery. No foundation infrastructure beyond
what Scope 6 already ships.

### 11.5 Trace resonance corruption to Sineater

Per §11.1, Spec B's redirect calls `accrue_corruption` on the Sineater with a
small trace amount. The Sineater's `corruption_current` and
`corruption_lifetime` rise as if the Sineater had cast on that resonance
themselves. Self-recovery via Atonement Rite (§4) is available to the Sineater
for any Primal-resonance corruption they accumulate, since Atonement supports
self-targeted cleansing of stages 1-2 — closing the recovery loop without
requiring a Celestial third party.

---

## 12. Naming Conventions Used in This Spec

For implementation reference, the names introduced or finalized:

**Models / fields:**
- `CharacterResonance.corruption_current`
- `CharacterResonance.corruption_lifetime`
- `MagicalAlterationTemplate.kind` (extended TextChoices)
- `MagicalAlterationTemplate.resonance` (FK, nullable)
- `MagicalAlterationTemplate.stage_threshold` (nullable)
- `ConditionTemplate.corruption_resonance` (FK to Resonance, nullable; marker
  for Corruption-kind templates)
- `ConditionStage.advancement_check_type` (FK CheckType, nullable)
- `ConditionStage.advancement_check_difficulty`
- `ConditionStage.advancement_resist_failure_kind` (TextChoices)
- `CorruptionConfig` (singleton model)

**Enums / TextChoices:**
- `AlterationKind.MAGE_SCAR`, `AlterationKind.CORRUPTION_TWIST`
- `CorruptionSource.TECHNIQUE_USE`, `CorruptionSource.SPEC_B_REDIRECT`,
  `CorruptionSource.STAFF_GRANT`
- `CorruptionRecoverySource.ATONEMENT_RITE`,
  `CorruptionRecoverySource.SPEC_B_RESCUE`,
  `CorruptionRecoverySource.PASSIVE_DECAY`,
  `CorruptionRecoverySource.STAFF_GRANT`
- `CorruptionCause.STAGE_5_SUBSUMPTION`, `CorruptionCause.STAGE_5_RECOVERED`
- `AdvancementResistFailureKind.ADVANCE_AT_THRESHOLD`,
  `AdvancementResistFailureKind.HOLD_OVERFLOW`
- `AdvancementOutcome.NO_CHANGE`, `AdvancementOutcome.HELD`,
  `AdvancementOutcome.ADVANCED`

**Services:**
- `accrue_corruption_for_cast(...)`
- `accrue_corruption(...)`
- `reduce_corruption(...)`
- `get_corruption_config()`

**Methods on `CharacterSheet`:**
- `get_corruption_stage(resonance) -> int`
- `is_protagonism_locked` (cached_property)
- `_has_corruption_terminal_stage()` (private)

**Reactive events (Scope 5.5 surface):**
- `corruption_accruing`
- `corruption_accrued`
- `corruption_warning`
- `corruption_reduced`
- `protagonism_locked`
- `protagonism_restored`
- `condition_stage_advance_check_about_to_fire`

**Errors:**
- `CorruptionError` (base)
- `ProtagonismLockedError`

**Authored content shipped:**
- `Ritual` row: "Rite of Atonement" + its FlowDefinition
- 1–2 per-resonance Corruption ConditionTemplates per non-Celestial affinity
  (with 5 ConditionStages + 2–4 CORRUPTION_TWIST MagicalAlterationTemplates each)
- Soulfray ConditionStage retrofit (data migration only)
