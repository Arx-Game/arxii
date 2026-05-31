# Scope #2: Runtime Modifiers & Audere

## Purpose

Make technique use dynamic. Scope #1 built the `use_technique()` pipeline with
static base values for intensity and control. Scope #2 makes those values
responsive to the character's current state: what they're doing, how much
pressure they're under, and whether they've crossed into Audere.

This scope also introduces CharacterEngagement — a first-class concept for
"what is this character actively doing that has stakes" — and connects both
the existing CharacterModifier system and new engagement process state to
technique runtime stats.

## Key Design Principles

- **Two modifier streams.** Identity bonuses (from who you are — Distinctions,
  Conditions, resonance, equipment) flow through CharacterModifier. Process
  bonuses (from what's happening right now — escalation, Audere, combat
  pressure) live on CharacterEngagement. Both feed into runtime stats but
  have different lifecycles and semantics.
- **Engagement is observable.** What a character is doing is social information,
  not just mechanical state. Other characters can see that someone is engaged
  in combat, a mission, or a challenge.
- **Audere is rare and earned.** It requires high intensity, existing Soulfray,
  AND active engagement. It's a climactic moment in a dangerous situation, not
  a power-up the player activates at will.
- **Audere is triggered by events, not technique use.** When conditions are met
  (intensity spike from escalation, ally falling, etc.), the system offers
  Audere. The player then chooses what to do with that power.
- **Lifecycle modifiers are process state.** Engagement-scoped modifiers
  (escalation, Audere boost) have no permanence outside the engagement. They
  live on CharacterEngagement fields and vanish when the engagement ends.
  CharacterModifier is reserved for identity-derived bonuses that persist
  with their source (Distinctions, Conditions, equipment).

## What This Builds

### 1. CharacterEngagement Model

A first-class representation of what a character is actively doing that has
stakes. Lives in `world/mechanics` (cross-cutting concern).

**Fields:**
- `character` — OneToOneField to ObjectDB (SharedMemoryModel for cache)
- `engagement_type` — TextChoices: CHALLENGE, COMBAT, MISSION
- `source_content_type` — FK to ContentType (generic relation to source)
- `source_id` — PositiveIntegerField (ID of the source object)
- `escalation_level` — PositiveIntegerField, default 0
- `intensity_modifier` — IntegerField, default 0 (process-derived intensity bonus)
- `control_modifier` — IntegerField, default 0 (process-derived control bonus)
- `started_at` — DateTimeField, auto_now_add

**Behavior:**
- Created by the engaging system (challenge resolution, future combat, future
  missions) when a character enters a stakes-bearing context.
- Updated when the engagement type changes (mission escalates to combat),
  escalation increments, or process modifiers change.
- Deleted when the engagement ends (challenge resolved, combat over, mission
  complete). All process state vanishes with it.
- Absence of engagement = character is in social/freeform mode.

**Observable by other characters.** The engagement type and escalation level
are visible to other players entering a scene — "those three are clearly in
the middle of something." This informs social interaction decisions.

**No nesting for now.** OneToOne means one active engagement per character.
If nesting is needed (mission containing combat), the engagement is updated
to reflect the innermost context. If a more complex model is needed in the
future, a separate M2M table for suspended/latent engagements can be added
without changing the primary OneToOne.

**Escalation and process modifiers are externally managed.** CharacterEngagement
does not increment its own escalation or update its own modifiers. The
engaging system (combat, missions, challenges) decides when and how to update
these fields based on its own rules. Different contexts create different
pressure: a boss fight escalates every round, a tense negotiation escalates
on failed checks, a casual challenge might not escalate at all.

**Process modifiers vs identity modifiers.** The `intensity_modifier` and
`control_modifier` fields on CharacterEngagement are for transient process
state — escalation ticking up intensity, Audere's boost, taking a hit that
spikes intensity. These are anonymous (no source tracking needed), temporary
(gone when engagement ends), and don't participate in CharacterModifier's
amplification/immunity rules.

Identity-derived bonuses that happen to apply during engagement (e.g., a
Distinction like "Veteran Duelist" giving +2 intensity during combat) remain
CharacterModifiers. The *condition for when they're active* may reference
engagement state, but the bonus comes from who the character is, not from
the process. Contextual activation of identity modifiers is a future design
need (see "Contextual Modifier Evaluation" in hook points).

### 2. ModifierTargets for Technique Stats

Two new ModifierTarget records in a new "technique_stat" ModifierCategory:
- `intensity` — identity-derived bonuses to runtime intensity
- `control` — identity-derived bonuses to runtime control

These are authored data (created via factories in tests, admin for production).
Any system that wants to modify a character's technique stats based on their
identity writes a CharacterModifier pointing at these targets through the
existing modifier infrastructure.

### 3. Upgraded `get_runtime_technique_stats()`

Currently returns base values. Becomes:

```
runtime_intensity = technique.intensity
                  + get_modifier_total(character_sheet, intensity_target)  # identity
                  + engagement.intensity_modifier                          # process

runtime_control = technique.control
                + get_modifier_total(character_sheet, control_target)      # identity
                + engagement.control_modifier                              # process
                + social_safety_bonus (if no CharacterEngagement)
                + intensity_tier.control_modifier (based on resulting intensity)
```

Note: `get_modifier_total()` takes a `CharacterSheet` instance (not ObjectDB).
The caller resolves the character's sheet before calling.

**Two modifier streams, one sum.** Identity bonuses from CharacterModifier
(Distinctions, future resonance, future equipment) and process bonuses from
CharacterEngagement fields (escalation, Audere) are summed into final runtime
values. The technique use flow doesn't care where a bonus originated.

**Social safety bonus** is applied directly when the character has no
CharacterEngagement, rather than as a modifier record. The absence of
engagement IS the social state. The bonus value is authored data (a game
setting, not hardcoded).

**IntensityTier.control_modifier** is looked up based on the final runtime
intensity (after all modifiers). The IntensityTier model already exists with
a `control_modifier` field and `threshold` values. This is per-technique (based
on the technique's resulting intensity), not per-character.

### 4. AudereThreshold Config Model

Small configuration table (SharedMemoryModel) for Audere trigger thresholds
and effect values. Expected to have a single row (global config), but modeled
as a table for factory/test flexibility.

**Fields:**
- `minimum_intensity_tier` — FK to IntensityTier (intensity must reach this tier)
- `minimum_warp_stage` — FK to ConditionStage (Soulfray must be at this stage+)
- `intensity_bonus` — IntegerField (added to engagement.intensity_modifier on activation)
- `anima_pool_bonus` — PositiveIntegerField (temporary max anima increase)
- `warp_multiplier` — PositiveIntegerField (Soulfray severity increment multiplier)

All values are authored and tunable without code changes.

### 5. Audere Condition & Lifecycle

**Audere as a ConditionTemplate** with `has_progression=True`.

#### Trigger (hard triple gate)

All three must be met simultaneously:
1. Character's runtime intensity resolves to an IntensityTier at or above
   `AudereThreshold.minimum_intensity_tier` (lookup: find the highest
   IntensityTier whose `threshold` value is <= the character's runtime
   intensity, then compare tier ordering)
2. Character has an active Soulfray condition at or above `AudereThreshold.minimum_warp_stage`
3. Character has an active CharacterEngagement

The engagement gate is a narrative guardrail. While it should be nearly
impossible to accumulate the required intensity and Soulfray outside of dangerous
situations, Audere is explicitly a combat/high-stakes moment. A character
doesn't go super saiyan during a pub darts tournament.

#### Trigger timing

Audere is NOT checked during `use_technique()`. It is checked when intensity
changes — specifically, when the engaging system updates the engagement's
process modifiers or escalation level. The flow:

1. Something spikes intensity (escalation tick, future: ally hurt, damage taken)
2. The system that caused the spike calls `check_audere_eligibility(character)`
3. If eligible, `offer_audere(character)` pauses and presents the offer
4. Player accepts or declines

This means Audere is active BEFORE the player chooses a technique. They see
their new power level and the revealed techniques, then decide what to do.
This avoids the anticlimactic experience of discovering godlike power while
already committed to casting a weak spell.

For Scope #2, the only system that triggers the eligibility check is
CharacterEngagement escalation. Future systems (combat events, relationship
spikes) call the same function.

#### On acceptance

- Apply Audere ConditionTemplate to character
- Add `AudereThreshold.intensity_bonus` to `engagement.intensity_modifier`
  (process state — lives on the engagement, dies with it)
- Store the pre-Audere `CharacterAnima.maximum` value (on a dedicated field
  on CharacterAnima like `pre_audere_maximum`, nullable) so it can be
  restored on Audere end
- Increase `CharacterAnima.maximum` by `AudereThreshold.anima_pool_bonus`
  (and optionally grant some current anima — enough to feel powerful but
  not enough to be safe)
- Future (not Scope #2): reveal next-tier techniques from the character's
  ascending Path

#### On decline

Nothing happens. The offer is not repeated until the next intensity change
that re-triggers eligibility.

#### Lifecycle end

Audere ends when:
- Engagement ends (CharacterEngagement deleted → scene/combat over)
- Soulfray reaches a critical stage (authored on the condition's final stage)
- Character voluntarily releases it (future, low priority)

On end:
- If engagement still exists: subtract `AudereThreshold.intensity_bonus`
  from `engagement.intensity_modifier`
- If engagement is being deleted: process modifiers vanish automatically
- `CharacterAnima.maximum` reverted to `pre_audere_maximum` value, field
  set back to null
- The Soulfray condition remains — Audere ending doesn't reset Soulfray

### 6. Soulfray Acceleration During Audere

Step 7 of `use_technique()` (apply overburn condition) checks for active
Audere. If present, the Soulfray severity increment is multiplied by
`AudereThreshold.warp_multiplier`. This is a simple multiplication on the
severity value before passing to `apply_condition()`.

This means a character in Audere accumulates Soulfray dramatically faster than
normal. Each technique use during Audere pushes them further up the Soulfray
progression — through penalties, into scarring risk, toward lethal territory.
The runway is still there (Soulfray is progressive, not sudden), but Audere
compresses it.

### 7. Changes to `use_technique()`

The existing 8-step pipeline from Scope #1 changes minimally:

- **Step 1** — `get_runtime_technique_stats()` now queries both modifier streams
  (CharacterModifier totals + CharacterEngagement fields) instead of returning
  base values. Audere's intensity bonus is already reflected in the engagement
  fields if active.
- **Step 7** — Soulfray severity increment scaled by `warp_multiplier` if Audere
  is active.

All other steps are unchanged. Audere logic lives outside `use_technique()`.

## What This Documents (Future Hook Points)

### Resonance/Affinity Bonuses

Resonance is deeply contextual. A character's effective resonance when using
a technique depends on:
- **Which Gift** the technique belongs to (Gift resonances define which of the
  character's resonance sources are relevant — they're a filter, not a source)
- **Environment** (lair decorations, room properties that match resonances)
- **Fashion/presentation** (outfit, affectations, motifs that boost resonances)
- **Perception** (how others see the character — aura farming)

The affinity bonus formula (Celestial +2 control per 10, Primal +1/+1,
Abyssal +2 intensity per 10) applies to the *contextually relevant* resonance
total, not a static aggregate. Most of the input systems (fashion, environment,
perception) don't exist yet.

**Hook point:** `get_runtime_technique_stats()` queries ModifierTargets. When
resonance bonuses are implemented, they write CharacterModifier records
(identity-derived, persists with source) through whatever system evaluates
contextual resonance. The technique use flow doesn't need to change.

### Technique Revelation During Audere

When a character enters Audere, they should see techniques from their next
tier — specifically from the advanced Path they're ascending toward. These
are techniques they don't know and have never seen. The revelation is a
preview of their future self and serves as a progression carrot.

**Depends on:** Path progression infrastructure (querying "what is this
character's next-tier Path and its Gifts/Techniques").

**Hook point:** `offer_audere()` has a post-acceptance step where technique
revelation would fire. Currently a no-op.

### Audere Majora

The threshold-crossing moment where a character *becomes* their future self —
literally leveling up to the next advanced class with temporarily boosted
powers. If they survive, the ascended techniques become available to learn
through normal progression. If they don't survive, it's sacrifice.

**Depends on:** Tier advancement system, technique revelation.

### Relationship Event Intensity Spikes

Thread bonds between characters should feed intensity spikes during dramatic
moments — an ally falling, a loved one being threatened. These spikes update
`engagement.intensity_modifier` (process state) and can trigger Audere
eligibility checks.

**Depends on:** Combat event system, Thread integration, narrative event
detection.

**Hook point:** Any system that updates engagement process modifiers calls
`check_audere_eligibility()` after the update.

### Escalation Tick Triggers

CharacterEngagement has an `escalation_level` field, but Scope #2 doesn't
build the systems that increment it. Each engaging system owns its own
escalation rules:
- Combat: per-round intensity increase, possibly accelerating
- Missions: depends on risk level (not all missions escalate)
- Challenges: depends on the challenge (life-or-death vs casual)

**Hook point:** When escalation increments, the engaging system updates
`engagement.intensity_modifier` (translating escalation level into an
intensity bonus) and calls `check_audere_eligibility()`.

### Contextual Modifier Evaluation

Beyond lifecycle modifiers, there's a need for identity-derived bonuses that
are conditionally active based on situation. A Distinction like "Veteran
Duelist" might grant +2 intensity, but only during combat engagement. These
are CharacterModifiers (identity-derived, persists with the Distinction), but
their activation depends on context.

This is where the Trigger system may evolve — a generalized "given the current
situation, which of this character's identity modifiers are active?" evaluation.
The pattern would be: "get all modifiers for this part of the lifecycle for
this character and apply them."

This is a broader architectural question that affects more than technique
stats. Document as a cross-cutting design need. The modifier system already
supports this data (CharacterModifier records exist, ModifierTargets exist) —
what's missing is the conditional activation layer.

### Character Loss Deferral (Scope #3)

Character death from Audere sacrifice should be deferred to a narratively
appropriate moment — not mid-action. A character in Audere Majora who pushes
past lethal Soulfray stages is choosing sacrifice so others can win. The death
plays out after the decisive moment (winning the boss fight, holding the line,
etc.), not as an interruption to the action.

Character loss from sacrifice is always the result of a deliberate choice
chain (entered Audere → kept pushing → kept confirming overburn). The system
makes space for players to choose sacrifice deliberately, with full
understanding of what they're giving up and what they're achieving for others.

This is part of Scope #3's Soulfray progression design, not Scope #2.

## Integration Test Expansion

The pipeline integration tests grow to cover:

- **Social safety bonus**: no engagement → control bonus applied to runtime stats
- **Engagement present**: engaged character → no social safety bonus
- **Escalation modifier**: engagement.intensity_modifier updated →
  reflected in runtime stats
- **IntensityTier.control_modifier**: applied based on resulting intensity tier
- **Two-stream stacking**: CharacterModifier identity bonus + engagement process
  bonus both contribute to runtime stats
- **Audere eligibility — all gates met**: intensity tier + Soulfray stage +
  engagement → eligible
- **Audere eligibility — missing one gate**: each gate individually insufficient
- **Audere eligibility — no engagement**: high intensity + high Soulfray but not
  engaged → not eligible
- **Audere acceptance**: condition applied → engagement.intensity_modifier
  updated → anima pool expanded → runtime stats reflect boost
- **Audere decline**: no state change, normal technique use continues
- **Soulfray acceleration**: overburn during Audere → Soulfray severity multiplied
- **Audere cleanup on condition end**: intensity_modifier reduced, anima pool
  reverted, Soulfray remains
- **Audere cleanup on engagement end**: engagement deleted → all process state
  gone → Audere condition removed
- **Full flow**: engagement → escalation → Audere trigger → accept → technique
  use with boosted stats → Soulfray with multiplier → engagement ends → cleanup

## Relationship to Existing Pipeline

```
Existing (unchanged):
  get_available_actions() → player picks → resolve_challenge() / resolve_scene_action()

Scope #1 (unchanged):
  use_technique() wrapping resolution with anima cost + safety + mishap

Scope #2 additions:
  Intensity-changing event (escalation tick, future: ally hurt, etc.)
  → update engagement.intensity_modifier
  → check_audere_eligibility()
  → offer_audere() if eligible
  → player accepts → Audere condition + engagement modifier updated + anima expanded

  use_technique() Step 1:
    technique.intensity
      + get_modifier_total(char_sheet, intensity_target)   # identity stream
      + engagement.intensity_modifier                       # process stream

    technique.control
      + get_modifier_total(char_sheet, control_target)     # identity stream
      + engagement.control_modifier                         # process stream
      + social_safety_bonus (if no engagement)
      + IntensityTier.control_modifier

  use_technique() Step 7:
    Soulfray severity × AudereThreshold.warp_multiplier (if Audere active)
```

The technique use flow remains a wrapper around the existing resolution
pipeline. Scope #2 adds inputs to Step 1 and a multiplier to Step 7.
Audere logic is entirely separate from technique use.
