# Technique Use Flow Design

## Purpose

Define how a character uses a magical technique — from choosing to cast through
resolution, anima cost, and side effects. This is the core "I use Flame Lance"
pipeline that connects the magic system to the existing resolution infrastructure.

## Key Design Principles

- **Anima is not a gate.** A character can always attempt to use magic. Anima
  determines safety, not access. When anima runs out, the deficit is drawn from
  the caster's life force.
- **Risk is always explicit.** Any outcome that could harm the character requires
  an opt-in safety checkpoint. The player must see the cost, understand the danger,
  and deliberately confirm. Character death risk is stated in those exact terms.
- **The technique always works.** The intended effect resolves through the normal
  check/consequence pipeline. Mishaps from loss of control are *additional*
  consequences, not replacements for the intended effect.
- **Higher intensity is genuinely better.** Pushing intensity increases capability
  values and effect power. The cost and mishap risk are the trade-off, not a
  penalty on effectiveness.
- **Control is efficiency.** High control reduces anima costs and eliminates mishap
  risk. Mastery means casting for free with no side effects.

## Technique Use Flow

When a player uses a technique (against a challenge, in a scene, or in combat):

### Step 1: Calculate Runtime Stats

Compute `runtime_intensity` and `runtime_control` from the technique's base values
plus any active modifiers.

For MVP, this is just the base values (IntensityTier.control_modifier is
deferred to scope #2 alongside other runtime modifiers):
```
runtime_intensity = technique.intensity
runtime_control = technique.control
```

**Future modifier hooks (scope #2):**
- Affinity bonuses: Celestial +2 control per 10 resonance, Primal +1/+1,
  Abyssal +2 intensity per 10 resonance
- Social scene safety: large passive control bonus outside combat/challenges,
  making magic trivially safe during RP
- Combat escalation: intensity increases per round in boss fights
- Relationship spikes: emotional events (ally falls, loved one threatened)
  spike intensity
- Audere: massive intensity increase with tier-locked technique access

### Step 2: Calculate Effective Anima Cost

```
control_delta = runtime_control - runtime_intensity
effective_cost = max(technique.anima_cost - control_delta, 0)
```

- **Control > intensity**: delta is positive, cost decreases (efficiency)
- **Intensity > control**: delta is negative, cost increases (strain)
- **Very high control**: cost floors at 0 (mastery, free casting)

Examples with base_anima_cost=10:
- intensity=10, control=10 → delta=0 → cost=10 (baseline)
- intensity=10, control=15 → delta=5 → cost=5 (efficient)
- intensity=10, control=25 → delta=15 → cost=0 (mastery)
- intensity=15, control=10 → delta=-5 → cost=15 (strained)
- intensity=25, control=10 → delta=-15 → cost=25 (dangerous)

### Step 3: Safety Checkpoint (Only When Overburning)

Calculate the deficit:
```
deficit = effective_cost - character_anima.current
```

**If deficit <= 0:** No checkpoint. Anima is deducted silently. The player sees
the updated value in their UI but is not prompted.

**If deficit > 0:** The pipeline pauses and presents:

- Exact cost breakdown: "Flame Lance costs 15 anima. You have 8."
- What happens: "7 anima will be drawn from your life force."
- Severity label based on the deficit relative to character state:
  - Minor overburn: "Painful — you will sustain magical injuries."
  - Significant overburn: "Dangerous — you will sustain serious magical injuries."
  - Severe overburn: **"This can result in character death."**
- Explicit opt-in: Confirm or Cancel.

The severity thresholds are configurable (authored data, not hardcoded), but the
"can result in character death" label is **mandatory** above a defined threshold.
It is never hidden, softened, or omitted.

This uses the same `awaiting_confirmation` pause pattern as the existing action
resolution pipeline, triggered by resource math rather than consequence pool
`character_loss` flags.

### Step 4: Deduct Anima

On confirmation (or immediately if no checkpoint):
```
character_anima.current = max(character_anima.current - effective_cost, 0)
```

The deficit value is **passed through from Step 3's calculation** — it is not
re-derived by attempting to make the model go negative. `CharacterAnima.current`
is a `PositiveIntegerField` and never goes below 0. The deficit is a computed
value (`effective_cost - current_anima`) that determines overburn severity in Step 7.

Uses `select_for_update` for race-condition safety, following the
`ActionPointPool.spend()` pattern. Two simultaneous technique uses must not both
pass the safety checkpoint and then overdraw.

### Step 5: Calculate Capability Value

The technique's capability grants are evaluated with the runtime intensity:
```
effective_value = grant.base_value + (grant.intensity_multiplier * runtime_intensity)
```

Higher intensity = higher capability value = better chance against tough challenges
and access to harder approaches. This is why pushing intensity is desirable despite
the cost.

Note: `TechniqueCapabilityGrant.calculate_value()` already accepts an optional
`intensity` override parameter. The runtime intensity feeds in here.

### Step 6: Resolve Intended Effect

The normal resolution pipeline runs:
- **Challenge path**: `get_available_actions()` → player picks approach →
  `resolve_challenge()` with the enhanced capability source
- **Scene action path**: `resolve_scene_action()` via `Technique.action_template` FK
  (already exists on the model for using techniques outside challenge contexts)
- **Gated pipeline**: `start_action_resolution()` if the approach/template uses gates

The check runs, consequences are selected and applied. This is unchanged from the
existing pipeline — the technique use flow feeds *into* it with enhanced values.

### Step 7: Apply Overburn Condition

If there was an anima deficit (from Step 3/4), apply a condition:
- Condition template: "Anima Warp" (working name, to be workshopped)
- Severity: scaled to the deficit amount
- Applied deterministically — not a random consequence, but a guaranteed result
  of the resource math
- The condition carries mechanical effects (stat penalties, ongoing damage, etc.)
  and can evolve into permanent magical scars at high severity

This uses the existing `ConsequenceEffect` APPLY_CONDITION handler.

### Step 8: Resolve Mishap Rider (If Intensity > Control)

If `runtime_intensity > runtime_control`, a mishap consequence pool fires
**after** the intended effect has resolved. This happens regardless of anima
state — even with plenty of anima, loss of control produces side effects.
The difference is that with sufficient anima, these side effects are always
non-lethal (environmental collateral, minor injuries, unintended area effects).
Lethal mishap consequences only enter the pool when combined with anima overburn.

- The mishap pool is selected based on the control deficit magnitude:
  `control_deficit = runtime_intensity - runtime_control`
- Small deficit → minor side effects pool (environmental collateral, brief
  discomfort)
- Large deficit → severe side effects pool (magical burns, property damage,
  area effects hitting allies)
- The main resolution's check result is reused for consequence selection from
  the mishap pool (same outcome tier determines which mishap is selected)
- These consequences are *additional* to the intended effect. The technique
  worked; these are the collateral.

The mishap rider calls `select_consequence_from_result()` directly with the
mishap pool and the main check result, then `apply_resolution()` for the
selected consequence. This is a direct call from the technique use wrapper
(post-resolution), not routed through the context pool infrastructure (which
exists but is not yet wired into `start_action_resolution()`).

**Audere hook (scope #2):** During Audere, the control deficit is enormous, so the
mishap pool is severe — these are the most dramatic moments in the game.

## What Needs Building

### New Service Functions (world/magic/services.py)

- **`calculate_effective_anima_cost(technique, runtime_intensity, runtime_control)`**
  → returns `int` (effective cost after control delta)
- **`calculate_anima_deficit(character, effective_cost)`**
  → returns `int` (deficit, 0 if no overburn)
- **`deduct_anima(character, effective_cost)`**
  → deducts from CharacterAnima, returns deficit amount
- **`get_overburn_severity(deficit)`**
  → returns severity label and whether character death is possible
- **`get_runtime_technique_stats(technique, character)`**
  → returns `(runtime_intensity, runtime_control)` — MVP returns base values,
  future work adds modifier hooks

### Orchestrator (world/magic/services.py)

- **`use_technique(character, technique, resolution_context)`**
  → orchestrates Steps 1-8: calculates runtime stats, effective cost,
  checks for overburn, deducts anima, delegates to the appropriate
  resolution path (Step 6), then applies overburn condition and mishap
  rider. Returns a result combining the resolution outcome with any
  overburn/mishap effects.

### Mishap Pool Selection (world/magic/services.py)

- **`select_mishap_pool(control_deficit)`**
  → returns the appropriate ConsequencePool based on deficit magnitude,
  or None if no deficit

Mishap pools are a small number of global ConsequencePool records tiered by
deficit range (e.g., deficit 1-5 = minor mishaps, 6-15 = moderate, 16+ = severe),
authored by staff. No new model needed — just ConsequencePool records with
consequences at various outcome tiers. Lookup is by deficit range, not by
technique or EffectType.

### Pipeline Integration

- New pause trigger in the resolution pipeline for anima overburn
  (alongside existing `character_loss` pause)
- Mishap rider pool wired as a context consequence pool after main resolution
- `TechniqueCapabilityGrant.calculate_value(intensity=runtime_intensity)` called
  with runtime intensity instead of base intensity

### Authored Content (Not Code)

- Overburn condition template(s) with severity-scaled effects
- Mishap consequence pools at different severity tiers
- Severity threshold configuration for safety checkpoint labels

## What This Does NOT Build (Future Scope)

### Scope #2: Runtime Intensity/Control Modifiers
- Affinity bonuses to intensity/control from resonance
- Social scene passive control bonus
- Combat escalation (per-round intensity increase)
- Relationship event intensity spikes
- Audere trigger (intensity threshold detection)
- Audere stat modifications (massive intensity boost, temporary technique access)
- Audere Majora (tier-crossing with extreme risk)

### Scope #3: Negative Consequence Types
- Magical scar condition templates and their mechanical effects
- Abyssal corruption as a long-term consequence of overuse
- New ConsequenceEffect types if needed (or use APPLY_CONDITION with
  specific templates)
- Scar/corruption progression systems (accumulation over time)

### Audere / Audere Majora (Scope #2, Detailed Notes)

Audere ("To Dare") is not a separate mechanic — it's what happens when intensity
crosses a threshold during escalation. The system detects the threshold and offers
the player the choice to embrace it.

- **Audere**: Triggered when runtime intensity exceeds a threshold (pushed by
  combat escalation and narrative events). Greatly increases intensity, makes
  higher-tier techniques available, temporarily expands anima pool — but not
  nearly enough to cover the new costs safely. Carries extreme mishap risk.
- **Audere Majora** ("To Dare Greatly"): The threshold-crossing moment — ascending
  from one level tier to the next (5→6, 10→11, 15→16, 20→21). Requires being
  ready for the next tier. Even more intensity, even more risk. Success means
  leveling up. Failure could mean death. The defining character moment.
- **Extreme risk**: Audere and Audere Majora carry real danger of character death,
  making them the highest-stakes moments in the game.

## Integration Test Expansion Points

The pipeline integration tests (`test_pipeline_integration.py`) should grow to cover:

- **Anima cost calculation**: technique with various intensity/control ratios
  produces correct effective costs
- **Safety checkpoint trigger**: overburn deficit triggers confirmation pause,
  no-deficit does not
- **Anima deduction**: current anima reduced correctly, deficit tracked
- **Overburn condition application**: deficit > 0 applies condition with
  correct severity
- **Capability value with runtime intensity**: enhanced intensity produces
  higher capability values that match harder challenges
- **Mishap rider firing**: intensity > control triggers mishap pool after
  main resolution succeeds
- **Mishap not firing when controlled**: intensity <= control produces no
  mishap consequences
- **Safety checkpoint cancel**: overburn triggers confirmation, player cancels,
  no anima deducted, no resolution occurs
- **Full flow**: technique use → anima cost → safety check → resolution →
  overburn condition → mishap rider, all in one test proving the complete chain

## Relationship to Existing Pipeline

```
Current pipeline (unchanged):
  get_available_actions() → player picks → resolve_challenge() / resolve_scene_action()

New technique use wrapper:
  Player chooses technique
  → calculate_runtime_stats()          [Step 1 - base values, future: modifiers]
  → calculate_effective_anima_cost()   [Step 2 - delta formula]
  → safety_checkpoint()                [Step 3 - pause if overburn]
  → deduct_anima()                     [Step 4 - resource update]
  → calculate_value(runtime_intensity) [Step 5 - enhanced capability]
  → [existing resolution pipeline]     [Step 6 - unchanged]
  → apply_overburn_condition()         [Step 7 - if deficit]
  → resolve_mishap_rider()             [Step 8 - if intensity > control]
```

The technique use flow wraps the existing pipeline — it doesn't replace it.
Steps 1-5 happen before resolution, steps 7-8 happen after.
