# Scope #3: Anima Warp Progression & Consequence Streams

## Purpose

Complete the technique use consequence model. Scopes #1 and #2 built the
`use_technique()` pipeline with anima cost, safety checkpoints, runtime
modifiers, and Audere. Scope #3 makes consequences real: Anima Warp becomes
a progressive condition with severity stages driven by anima depletion,
control mishaps become authored pools that fire on imprecision, and high
Warp stages unlock dangerous consequence pools — including magical
alterations — that fire on every subsequent cast.

## Key Design Principles

- **Warp is the danger axis, not anima.** Low anima is a precursor to
  danger, not danger itself. Anima depletion drives Warp accumulation;
  Warp stage drives consequences and warnings. Players are warned because
  their soul is damaged, not because of resource math.
- **Three distinct consequence streams.** Control mishaps (imprecision),
  Warp stage consequences (soul damage), and the intended effect are
  independent streams with independent authored pools. They don't
  contaminate each other.
- **Everything is authored data.** Stage count, thresholds, consequence
  pools, warning text, severity formulas — all live in the database.
  Factories create test instances; production will have different values.
  The code provides the mechanics; content provides the feel.
- **Severity accumulates continuously.** Small overburns add up over time.
  Big overburns are immediately dangerous. Warp is a runway, not a cliff.
- **Control mishaps are never lethal.** Sloppy casting causes collateral
  damage, not character death. Lethality lives exclusively on late Warp
  stages.

## What This Builds

### 1. Severity as Accumulator for Progressive Conditions

No new fields on `ConditionInstance`. The existing `severity` field
(`PositiveIntegerField`, default 1) serves double duty:

- **For non-accumulating conditions** (poisons, buffs): severity is
  potency, set once at creation, scaled by `stage.severity_multiplier`
  via `effective_severity`. Unchanged behavior.
- **For accumulating conditions** (Anima Warp): severity is incremented
  by `advance_condition_severity()` and drives stage advancement via
  `severity_threshold` on stages.

Accumulating conditions should set `severity_multiplier = 1.00` on all
their stages, since severity is a running total rather than a potency
value — scaling it would produce meaningless numbers.

The key behavioral difference: accumulating conditions bypass
`apply_condition()`'s refresh logic (which does `max(existing, new)`)
by calling `advance_condition_severity()` directly on the existing
instance. `apply_condition()` is only used for first-time creation.

### 2. Severity Threshold on ConditionStage

New field on `ConditionStage`:

- `severity_threshold` — `PositiveIntegerField`, nullable. When a
  condition instance's `severity` reaches or exceeds this value, the
  condition advances to this stage. Null means the stage uses time-based
  progression only (existing `rounds_to_next` behavior).

This enables two coexisting progression modes on ConditionStage:
- **Time-based** — existing `rounds_to_next` countdown (poisons, buffs)
- **Severity-based** — new `severity_threshold` (Anima Warp, future
  similar conditions)

A stage can use either or both. Anima Warp stages would have
`severity_threshold` set and `rounds_to_next` null.

### 3. Consequence Pool on ConditionStage

New field on `ConditionStage`:

- `consequence_pool` — nullable FK to `actions.ConsequencePool`. When a
  character uses a technique while at this stage, the pool fires and a
  consequence is selected. Null means no per-cast consequences at this
  stage.

**Warp consequences are dramatic from stage 1.** Even the earliest
stages produce visible, frightening effects appropriate to the
character's magical identity: glowing aura, encroaching darkness,
crackling energy, resonance-flavored manifestations. Mechanical effects
include light damage, fatigue, disorientation, and other conditions.
Psychological effects are also in scope: hearing voices urging
surrender, flashbacks to traumatic magical experiences, compulsions.
The tone from the very first stage should emphasize intensity and
strain. "Benign" in this context means no permanent alteration or
death risk *yet* — not that nothing happens.

As stages advance, the pools shift: minor strain gives way to serious
mechanical penalties, then magical alterations, then at the final
stages `character_loss` entries. The consequence pools AND the
resilience check penalty both ramp — a double squeeze where it becomes
harder to resist AND the consequences of failure grow more severe.

The pool fires on **every technique use while at that stage**, not on
stage entry. This means the danger is ongoing — every cast at a
dangerous Warp stage is a roll of the dice, and the player's skill
determines how well they weather it.

**Consequence selection uses a secondary resilience check.** The
technique's own check result does not drive Warp consequence selection
— that would be semantically wrong (a successful fire spell shouldn't
determine how badly your soul is damaged). Instead:

1. `WarpConfig.resilience_check_type` and `WarpConfig.base_check_difficulty`
   define a resilience check (e.g., a "magical endurance" CheckType
   using relevant magical skills/stats). The check type and base
   difficulty are constant across all stages.
2. Each Warp stage has authored `ConditionCheckModifier` records
   (existing model, attached via stage FK) that apply escalating
   penalties to the resilience CheckType. Stage 1 might have a small
   penalty; late stages have severe penalties. This uses the existing
   condition effect infrastructure — no new fields on ConditionStage.
3. The technique's check outcome applies an additional modifier to the
   resilience check: botching the technique penalizes the Warp check,
   critting gives a bonus. Mapped from technique outcome tier to a
   signed modifier value via `TechniqueOutcomeModifier` (authored data).
4. The resilience check is performed with both modifiers applied.
5. The consequence is selected from the stage's pool based on the
   resilience check's outcome tier, using the existing
   `select_consequence_from_result()`.

This gives players agency — a character with strong magical discipline
can resist worse Warp outcomes even at high stages. But the stage
penalties mean even skilled casters eventually struggle, and botching a
technique while in Warp makes everything worse. Like saving throws
with escalating DC.

### 4. Warp Severity Accumulation

#### Anima Ratio Threshold

Single-row global configuration table (SharedMemoryModel), same pattern
as `AudereThreshold` — queried with `.first()`:

- `warp_threshold_ratio` — `DecimalField`. The anima ratio (current/max)
  below which technique use starts accumulating Warp severity. Example:
  0.30 means Warp starts accumulating when anima drops below 30%.
- `severity_scale` — `PositiveIntegerField`. Base scaling factor for
  converting depletion into severity.
- `deficit_scale` — `PositiveIntegerField`. Additional scaling factor
  for the deficit portion (anima spent beyond zero).
- `resilience_check_type` — FK to `checks.CheckType`. The check used
  for Warp resilience (e.g., "magical endurance"). Constant across all
  stages.
- `base_check_difficulty` — `PositiveIntegerField`. Base difficulty for
  the resilience check before stage-specific modifiers.

#### Severity Calculation

After anima is deducted (Step 4), the post-deduction anima ratio
determines Warp severity contribution:

```
ratio = current_anima / max_anima  (0.0 when empty, negative not possible)
```

- **ratio >= threshold** — no Warp severity. Magic is safe with reserves.
- **ratio < threshold** — severity increases as ratio decreases. The
  further below the threshold, the more severity per cast.
- **Deficit casting** (anima was insufficient, current is now 0) — the
  deficit amount adds additional severity on top of the zero-ratio
  contribution. Spending anima you don't have translates directly into
  severity at some scale.

The exact formula shape is determined by authored data. For the initial
implementation, a linear interpolation from threshold to zero plus deficit
scaling:

```
if ratio >= threshold:
    severity = 0
else:
    # How far below the threshold (0.0 = empty, 1.0 = at threshold)
    depletion = (threshold - ratio) / threshold
    severity = ceil(severity_scale * depletion)
    if deficit > 0:
        severity += ceil(deficit_scale * deficit)
```

Production can tune via the config values. The function signature:

```python
def calculate_warp_severity(
    current_anima: int,
    max_anima: int,
    deficit: int,
    config: WarpConfig,
) -> int:
```

#### Condition Application and Advancement

New service function `advance_condition_severity(instance, amount)`:

- Adds `amount` to `instance.severity`
- Queries the condition's stages ordered by `severity_threshold`
- Advances `current_stage` to the highest stage whose
  `severity_threshold <= instance.severity`
- Can skip multiple stages if the severity jump is large enough
- Returns a `SeverityAdvanceResult` dataclass:

```python
@dataclass
class SeverityAdvanceResult:
    previous_stage: ConditionStage | None
    new_stage: ConditionStage | None
    stage_changed: bool
    total_severity: int
```

If no Warp condition exists on the character yet, `apply_condition()` is
called first to create one, then `severity` is set to the
calculated amount and stage is resolved.

**Note:** The Anima Warp `ConditionTemplate` must have
`is_stackable=False`. The `unique_together` constraint on
`ConditionInstance` (`target`, `condition`) ensures one Warp instance per
character. `apply_condition()` will refresh rather than stack on
subsequent applications.

### 5. Revised Safety Checkpoint (Step 3)

The safety checkpoint is **driven by Warp stage, not anima deficit.**

When a character has an active Anima Warp condition, Step 3 checks their
current stage and presents the stage's authored warning text and severity
label. The player confirms or cancels.

- Each ConditionStage can carry warning/description text (existing
  `description` field, or a new `warning_text` field if the description
  serves a different purpose).
- Early stages: informational ("You are experiencing magical strain.")
- Late stages: explicit death risk ("This can result in character death.")
- No Warp condition: no warning. Even if anima is low, there's no danger
  *yet* — the danger comes after this cast accumulates Warp.

This means the **first time** a character enters Warp is unwarned. They
cast, Warp accumulates past stage 1's threshold, and the *next* time they
cast they see the warning. A deliberate "oh no" moment.

The existing `confirm_overburn` parameter on `use_technique()` is renamed
to `confirm_warp_risk` (or similar) to reflect the new semantics.

### 6. MishapPoolTier Config Model

Small authored table (SharedMemoryModel) for mapping control deficit
ranges to consequence pools:

- `min_deficit` — `PositiveIntegerField`
- `max_deficit` — `PositiveIntegerField` (nullable for "N and above")
- `consequence_pool` — FK to `ConsequencePool`

Ranges must not overlap. Validated via `clean()` method that checks for
existing tiers whose range intersects the new one. The query in
`select_mishap_pool(control_deficit)` uses `min_deficit__lte=deficit`
and either `max_deficit__gte=deficit` or `max_deficit__isnull=True`,
ordered by `min_deficit` descending, returning `.first()`.

Control mishap pools contain **no `character_loss` consequences.** These
are imprecision effects: environmental collateral, unintended area damage,
minor injuries to the caster. Dramatic but never lethal on their own.

### 7. Magical Alteration Hook

At high Warp stages, one of the possible consequences in the stage's
consequence pool is a "magical alteration occurs" entry. This is a new
`ConsequenceEffect` type — `MAGICAL_ALTERATION` — that, when selected,
calls a dedicated function to determine the specific alteration.

The alteration resolution function takes the character's magical identity
(resonances, affinity, Warp state, etc.) as inputs and determines what
happens. **This function is a stub in Scope #3** — it's called, but the
actual alteration logic (selecting from the vast space of possible
alterations based on character identity) is a future system. For now, the
stub applies a generic "Magical Alteration" condition template created by
factories.

The `MAGICAL_ALTERATION` effect handler reuses the existing
`condition_template` FK on `ConsequenceEffect` — the authored entry
points at a placeholder "Magical Alteration" `ConditionTemplate`. The
handler queries the character's magical identity from `ResolutionContext`
(which carries the character via `context.character`). In the stub
implementation, it just applies the pointed-to condition template. When
the real alteration system is built, the handler is replaced to call the
full resolution function.

This keeps the consequence pool clean — it doesn't need hundreds of
alteration entries. It has one entry that says "an alteration happens" and
delegates the specifics.

## Changes to `use_technique()`

The 8-step pipeline is revised:

**Step 1: Calculate runtime stats** — unchanged from Scope #2.

**Step 2: Calculate effective anima cost** — unchanged.

**Step 3: Safety checkpoint** — **rewritten.** Checks character's current
Warp stage. If they have active Anima Warp, presents the stage's warning.
Player confirms or cancels. No Warp = no warning.

**Step 4: Deduct anima** — unchanged mechanically.

**Step 5: Calculate capability value** — unchanged.

**Step 6: Resolve intended effect** — unchanged.

**Step 7: Warp accumulation and stage consequences** — **rewritten.**
Three sub-steps:
- **7a:** Calculate Warp severity from post-deduction anima state
  (ratio relative to threshold, plus deficit contribution). Zero if above
  threshold.
- **7b:** If severity > 0, look up the character's existing Warp
  condition. If none exists, call `apply_condition()` to create one,
  then call `advance_condition_severity()` with the calculated amount.
  If one already exists, call `advance_condition_severity()` directly
  on the existing instance. Stage may advance.
- **7c:** Check current Warp stage's consequence pool. If the stage has
  a pool, perform the resilience check: take the stage's check_type and
  check_difficulty, apply a modifier derived from the technique's check
  outcome (Step 6), perform the check, and select a consequence from
  the pool based on the resilience check's outcome tier. This is where
  dramatic strain effects, magical alterations, and (at late stages)
  `character_loss` consequences can occur.

**Step 8: Control mishap rider** — **implemented.** `select_mishap_pool()`
now queries `MishapPoolTier` instead of returning None. Pools contain only
non-lethal imprecision consequences.

## What Gets Removed/Changed

- **`OverburnSeverity` dataclass** — removed. Safety checkpoint is now
  Warp-stage-driven, not deficit-severity-driven.
- **`get_overburn_severity()` function** — removed. Replaced by Warp
  stage lookup.
- **`_DEATH_RISK_THRESHOLD` / `_DANGEROUS_THRESHOLD` constants** — removed
  (if they exist as constants). Danger is authored on Warp stages.
- **`warp_multiplier` on AudereThreshold** — field can remain but is no
  longer used in Warp severity calculation. Audere naturally drives high
  costs because of the massive intensity boost, which increases anima cost,
  which depletes anima faster, which increases Warp severity through the
  normal formula. No artificial multiplier needed.
- **`_get_warp_multiplier()` function** — removed.
- **`TechniqueUseResult.warp_multiplier_applied` field** — removed.
- **`TechniqueUseResult.overburn_severity` field** — replaced with Warp
  stage information:
  - `warp_result: WarpResult | None` — dataclass with
    `severity_added: int`, `stage_name: str | None`,
    `stage_advanced: bool`, `resilience_check: CheckResult | None`,
    `stage_consequence: AppliedEffect | None`
- **`TechniqueUseResult.confirmed` field** — semantics change from
  "confirmed overburn" to "confirmed despite Warp warning."
- **`confirm_overburn` parameter** — renamed to `confirm_warp_risk` to
  reflect Warp-stage semantics.

## What This Does NOT Build

- **Magical alteration resolution** — the function that determines *what*
  alteration occurs based on character identity. Scope #3 builds the hook
  (MAGICAL_ALTERATION effect type, stub function); the content system is
  future work.
- **Abyssal corruption** — long-term consequence of abyssal magic overuse.
  Separate system, separate scope.
- **Character loss deferral** — death during Audere deferred to narrative
  moment. Needs combat/mission lifecycle.
- **Resonance/affinity filtering of consequence pools** — future
  refinement where a character's magical identity influences which
  consequences are more likely.
- **Warp recovery/decay** — how Warp severity decreases over time or
  through specific actions (rest, anima rituals, healing). Without
  recovery, Warp is a one-way ratchet. Recovery mechanics likely tie
  into the anima ritual system or rest/downtime mechanics. For now,
  Warp persists until explicitly removed (e.g., via admin or future
  recovery system).
- **Audere pool expansion interaction** — Audere expands the anima pool
  via `anima_pool_bonus`, which temporarily raises the ratio and may
  delay Warp accumulation for a few casts. This is intentional — the
  expanded pool is temporary fuel that depletes on the same curve.
  No special handling needed.

## New Models Summary

| Model | App | Purpose |
|-------|-----|---------|
| `MishapPoolTier` | `world/magic` | Maps control deficit ranges to consequence pools |
| `WarpConfig` | `world/magic` | Anima ratio threshold and severity scaling for Warp accumulation |
| `TechniqueOutcomeModifier` | `world/magic` | Maps technique check outcome tiers to signed modifier values for the Warp resilience check |

## Modified Models Summary

| Model | Change |
|-------|--------|
| `ConditionStage` | Add `severity_threshold` (nullable PositiveIntegerField) |
| `ConditionStage` | Add `consequence_pool` (nullable FK to ConsequencePool) |
| `AudereThreshold` | `warp_multiplier` field unused (can remove or leave) |

## New Service Functions

| Function | Location | Purpose |
|----------|----------|---------|
| `advance_condition_severity(instance, amount)` | `conditions/services.py` | Increment severity, advance stage if threshold crossed |
| `calculate_warp_severity(current, maximum, deficit, config)` | `magic/services.py` | Compute Warp severity from anima state |
| `get_warp_warning(character)` | `magic/services.py` | Return current Warp stage warning for safety checkpoint |

## New ConsequenceEffect Type

`MAGICAL_ALTERATION` — added to the EffectType choices. Handler calls a
stub function that applies a generic alteration condition. Future work
fills in the real resolution logic.

## Integration Test Expansion

The pipeline integration tests grow to cover:

- **Warp accumulation from low anima** — technique use below threshold
  ratio creates/advances Warp condition with correct severity
- **No Warp above threshold** — technique use with plenty of anima
  produces no Warp
- **Severity-driven stage advancement** — accumulated severity crossing
  threshold advances stage; large severity can skip stages
- **Warp resilience check drives consequence selection** — technique use
  at a Warp stage performs a secondary resilience check, outcome tier
  determines which consequence is selected from the stage's pool
- **Technique outcome modifies resilience check** — botching the
  technique applies a penalty to the Warp resilience check; strong
  technique outcome applies a bonus
- **Warp stage consequence pool — early stage** — consequence pool at
  stage 1 produces dramatic but non-permanent effects (strain, fatigue,
  visual manifestations)
- **Safety checkpoint from Warp stage** — character with Warp gets
  warning on next cast; character without Warp gets no warning
- **First Warp is unwarned** — character with no Warp casts, accumulates
  Warp, was not warned before this cast
- **Control mishap pool selection** — deficit queries MishapPoolTier,
  returns correct pool
- **Control mishaps are non-lethal** — mishap pool consequences have no
  `character_loss` entries
- **Control mishap fires independently of Warp** — character with full
  anima and no Warp but intensity > control gets mishap consequences
- **Full flow** — technique use with low anima and high intensity:
  Warp warning → confirm → resolve → Warp accumulates → stage consequence
  fires → control mishap fires. All three streams produce independent
  results.

## Relationship to Existing Pipeline

```
Existing (unchanged):
  get_available_actions() → player picks → resolve_challenge() / resolve_scene_action()

Scope #1 (partially revised):
  use_technique() wrapping resolution with anima cost + safety + consequences

Scope #2 (unchanged):
  Runtime modifiers, CharacterEngagement, Audere lifecycle

Scope #3 revisions to use_technique():
  Step 3: Safety checkpoint
    Was: check anima deficit, warn on overburn
    Now: check Warp stage, warn based on stage severity

  Step 7: Warp accumulation + resilience check
    Was: commented-out stub
    Now: calculate severity from anima ratio → advance Warp →
         resilience check (modified by technique outcome) → fire stage pool

  Step 8: Control mishap
    Was: stub returning None
    Now: query MishapPoolTier → select from pool → apply non-lethal consequences
```
