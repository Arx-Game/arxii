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
engagement IS the social state. The bonus value is authored data —
`SoulfrayConfig.social_safety_bonus` (default 10, staff-tunable in admin,
#4098 owner ruling) — not hardcoded; see `docs/systems/magic.md`'s
"Social safety bonus" note for the formula it feeds.

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

### Ultimate Reveal During Audere (#4098) [BUILT & WIRED]

This section previously said the hook was a no-op and that Audere reveals techniques
from the character's *next* tier (a preview of their future self). Neither is true as
built: a plain Audere reveals the character's **current** Path's ultimates for their
major Gift; Audere Majora is itself an Audere for the new Path, revealing *that* Path's
ultimates once the Crossing resolves (spec decision 12 corrected the original framing
above before #4098 shipped).

An ultimate is a flagged `Technique` (`is_ultimate=True`), never a separate catalog or
a `CharacterTechnique`. `ultimate_reveal_for(sheet)`
(`world/magic/services/ultimates.py`) derives the reveal on every read - no offer
table - from the character's owned (current/new Path x major Gift), owned-known (any
Path, still held as MAJOR), and bond (active patron/companion) pools, filtered by
#4097's prerequisite gate, grouped by category (Sword/Shield/Crown, shown under
authored display labels). A technique the character already knows (`KnownUltimate`)
lists by name; an undiscovered one lists only its category card - its identity never
reaches the wire. The player's choice (`choose_ultimate`) stores the `KnownUltimate`
row and marks it the character's single `readied` pick; it does not cast anything -
the pick still goes through the ordinary combat declaration, castable only while an
active DECLARING round holds. Full detail: `docs/systems/magic.md`'s "Ultimates"
section; `docs/adr/adr-4098-ultimates-are-flagged-techniques-revealed-at-audere.md`.

### Audere Majora

The threshold-crossing moment where a character *becomes* their future self —
literally leveling up to the next advanced class with temporarily boosted
powers. If they survive, the ascended techniques become available to learn
through normal progression. If they don't survive, it's sacrifice.

**Depends on:** Tier advancement system, technique revelation.

### GM narration of surges and Crossings (#4101) [BUILT & WIRED]

An Audere surge (`_announce_surge`) and an Audere Majora Crossing (`_route_crossing`)
each resolve their own text (the character's prepared `CharacterSurgeText`/
`CharacterCrossingText` first, then, Crossing only, the patron `AudereMajoraFaithVariant`,
then the authored tier default), then call `world.gm.prompt_services
.route_narratable_event` with `GMPromptKind.AUDERE_SURGE`/`CROSSING`. With a GM opted in
(`GMPromptGroup.AUDERE`), that text becomes a `GMPrompt` the GM narrates instead of an
automatic broadcast; with none, the resolved text broadcasts/logs exactly as before
#4101. A Crossing's private vision still logs via `narrate_privately` even with no
active scene. `Technique.is_ultimate`'s reveal pick (`_route_ultimate_chosen`,
`GMPromptKind.AUDERE_ULTIMATE`) is GM-signal-only: no authored default line exists for a
pick, so with no GM opted in nothing is delivered. Full model/queue reference:
`docs/systems/magic.md`'s "GM Prompt Queue" section; `docs/systems/scenes.md`'s "GM
narration of mechanical events" section; ADR-4101.

### Relationship Event Intensity Spikes (#2013) [BUILT & WIRED]

This section used to list relationship-driven intensity spikes as a future hook
waiting on a combat event system and Thread integration. Both exist now, as
dramatic surges: `SurgeTriggerKind` (`world/combat/constants.py`) names nine
triggers, and `apply_dramatic_surge` (`world/combat/escalation.py`) is the shared
seam every one of them writes through, adding its amount straight onto
`engagement.intensity_modifier`. Two of the nine are the relationship-event
spikes this section asked for: `ALLY_FALLEN` (`apply_relationship_escalation_spike`,
fired off the `CHARACTER_INCAPACITATED`/`CHARACTER_KILLED` events via
`relationship_spike_handler`) and `ALLY_PERIL` (`apply_peril_escalation_spike`,
fired off `CONDITION_APPLIED` entering an acute-peril condition via
`peril_spike_handler`). Each reads the surging participant's own bonded ties
(`CharacterRelationship` rows whose label type has `fuels_escalation_spikes=True`
and whose combined scene/invested depth clears the escalation curve's
`spike_minimum_track_points`) before surging, so only characters with an actual
stake in the one who fell or is in peril get the spike. The other seven
(`HIGH_STAKES`, `HATED_FOE`, `INTERFERENCE`, the two boss triggers, `GM_MANUAL`)
cover combat drama outside the relationship axis and are not part of this hook.

One naming note: the depth signal these two triggers read is a bonded
`CharacterRelationship` (via its labels), not a woven `magic.Thread`, so
"Thread bonds" in the original wording overstated the mechanism. The intensity
these surges add feeds the Audere gates exactly as described above: Audere's
first gate reads the runtime intensity tier, which sums
`engagement.intensity_modifier`.

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

### Certain Death Deferral (#4098) [BUILT & WIRED]

This section used to describe Scope #3's Soulfray-sacrifice deferral as future design.
It is now built, for the narrower case the spec actually asked for: Soulfray's
`character_loss` consequence, under a `death_deferred` condition (Audere or Audere
Majora), defers rather than killing synchronously, so the character stays ALIVE and
keeps acting through the decisive moment instead of dying mid-action.

`defer_or_apply_certain_death(character_sheet) -> bool` (`world/vitals/services.py`)
is what Soulfray's stage-consequence resolution calls in place of an unconditional
kill: under an active `death_deferred` condition it sets
`CharacterVitals.death_certain_pending` and the character keeps acting; otherwise it
kills now. The pending death resolves through `apply_pending_certain_death`, called
from the existing condition-expiry seam
(`_resolve_deferred_death_on_expiry`, `world/conditions/services.py`) when the LAST
deferring condition on the character ends - ordinarily Audere's own end at the
encounter's close - and backstopped by `cleanup_completed_encounter`
(`world/combat/services.py`) for every participant at encounter completion, in case
the condition never expired cleanly through the normal path. Both the defer and the
resolution check `is_death_prevented_by_story` first, so an active story-protected
dependency still blocks the death and clears the pending flag with no death.

**Accepted consequence:** a dispel that removes the deferring condition mid-fight (not
at the encounter's natural end) resolves the pending death right there, through the
same expiry seam - deferral is tied to the condition's own lifetime, not to the
encounter's, so an early dispel is an early death rather than a held one.

**An ABANDONED encounter cancels the pending death instead of resolving it**
(#4098 owner ruling, 2026-10-01): a GM closing a broken fight shouldn't kill anyone.
`cleanup_completed_encounter` (`world/combat/services.py`) checks
`encounter.outcome == EncounterOutcome.ABANDONED` and, when true, calls the new
`clear_pending_certain_death(character_sheet) -> bool` (`world/vitals/services.py` -
clears `death_certain_pending` without ever applying the death, unlike
`apply_pending_certain_death`) for every participant, via the
`_cancel_pending_certain_death_if_abandoned` helper - and does this **before** the
Audere/Audere Majora teardown loop just below it. Ordering matters: ending Audere there
calls `remove_condition`, which reaches the same `_resolve_deferred_death_on_expiry`
expiry seam described above, and that seam applies a pending certain death the instant
the last deferring condition is gone - if the flag were still armed when that loop ran,
an abandoned encounter would kill through the ordinary expiry seam before the function's
own backstop loop (further down, unconditional for every outcome) ever got a chance to
matter. Every other outcome (VICTORY/DEFEAT/FLED) is unaffected - the death still applies
through the expiry seam or the backstop exactly as before.

**Soulfray can kill only inside a combat encounter** (#4098 owner ruling, 2026-10-01):
a scene cast, a technique-enhanced social action, a battle, and a reactive protection
fired with no active COMBAT engagement all pass `lethal=False` into `accumulate_soulfray`,
which bounds accumulated severity below the first death-risk stage instead of ever
rolling a `character_loss` consequence outside combat. Full detail:
`docs/systems/magic.md`'s "Ultimates" section (the "Soulfray" note),
`docs/systems/INDEX.md`'s Vitals section, and
`docs/adr/adr-4098-ultimates-are-flagged-techniques-revealed-at-audere.md`.

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
