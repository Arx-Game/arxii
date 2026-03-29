# Magic System

**Status:** in-progress
**Depends on:** Traits, Progression, Relationships, Combat, Crafting (for fashion/resonance)

## Overview
Magic in Arx II is deeply personal and relationship-driven. A character's magical power grows from who they are, who they connect with, and how the world perceives them. The system ties together affinities, resonances, gifts, techniques, and threads into a cohesive magical identity that evolves throughout play.

## Core Mechanics

### Intensity and Control
Every technique has two core stats: **intensity** (raw power) and **control** (safety/precision). These are base values on the technique, modified at runtime by resonance, affinity bonuses, combat escalation, and audere states.

- When intensity exceeds control, effects become unpredictable and anima cost can spike
- If actual anima cost exceeds the character's pool, the excess deals damage to the caster
- This creates the heroic sacrifice mechanic — push for maximum power at the risk of self-destruction
- Higher-tier techniques have disproportionately more intensity relative to control, making them inherently more volatile

### Affinity Bonuses (via Resonance)
Resonance points feed into technique stats through affinity alignment:
- **Celestial:** every 10 resonance → +2 control (precise magic)
- **Primal:** every 10 resonance → +1 intensity, +1 control (balanced magic)
- **Abyssal:** every 10 resonance → +2 intensity (powerful magic)
- Rounded up

### Combat Escalation
In serious boss fights, intensity auto-escalates each round. Characters make control checks to keep control in pace. Relationship events (true love threatened, ally falls) can spike intensity dramatically. Emotional state (anger, desperation) also feeds intensity. This mirrors superhero/fantasy boss fight pacing — things only escalate, never reset.

### No Healing, Shielding Instead
Restoration mechanics are counter to the tension-building combat design. Shielding prevents damage without undoing escalation. Healing is absent by design.

### Anima
Magical resource. Each technique has a base anima cost. In combat, active techniques drain anima per round. Out of combat, techniques drain once and fade on room leave or hourly cron. Anima recovery is handled through personalized rituals.

## Key Design Points
- **Affinities:** Three magical alignments (Celestial, Primal, Abyssal) expressed as percentages of a character's aura
- **Resonances:** Personal magical themes mapped to ModifierTargets — a character's magical "vibe" that strengthens specific abilities
- **Gifts:** Thematic power collections that capture a character's magical identity. Named symbolically (e.g., "Flames of the Defiant"). Serve as containers for techniques
- **Cantrips:** Simplified, staff-curated techniques for CG. A cantrip IS a baby technique — same mechanical system (intensity, control, anima cost, effect type, style), just preset at low values. At CG finalization, a cantrip creates a real Technique in the character's Gift
- **Techniques:** Magical abilities with intensity, control, level, style, effect type, and anima cost. The primary way magic manifests in gameplay. Cantrips are the starting point; full technique creation unlocks post-CG
- **Threads:** Magical relationships between characters. Bond strength feeds magical power — characters who are deeply connected are magically stronger together. Tying a thread to a technique gives better resonance-to-stat conversion for that technique
- **Motifs:** A character's magical aesthetic — the imagery and symbolism that defines their magic
- **Facets:** Hierarchical imagery/symbolism nodes. Items and fashion can have facets that map to character resonances, creating the fashion-to-power feedback loop
- **Traditions:** Magical schools/lineages that provide templates and community
- **Reincarnation/Atavism:** Past life tracking that can influence current magical development
- **Magic feeds off perception:** How others see a character influences their magical strength. "Aura farming" — making a dramatic entrance at a ball — is literally a viable strategy
- **Audere Majora:** Temporarily grants access to intensity far beyond control. Maximum drama, maximum risk. Feeds the "battered down, break through" heroic arc

## Effect Types
Known effect categories (will expand as combat develops):
- **Weapon enhancement** — adds damage to weapon attacks (flame blade)
- **Ranged attack** — standalone damage, scales with intensity (fire bolt)
- **Buff** — applies beneficial conditions
- **Debuff** — applies/removes/counters detrimental conditions
- **Defense** — self-warding and warding others
- **Utility** — non-combat effects (illusions, environmental manipulation, grid effects)

Some abilities cross categories (poison touch = attack + subtle assassination tool) and will need the restriction/tag system to express.

## What Exists
- **Models:** CharacterAura, CharacterResonance, Gift, CharacterGift, Technique, CharacterTechnique, TechniqueStyle, EffectType, Restriction, IntensityTier, CharacterAnima, CharacterAnimaRitual, AnimaRitualPerformance, Motif, MotifResonance, MotifResonanceAssociation, Facet, CharacterFacet, Thread, ThreadType, ThreadJournal, ThreadResonance, Tradition, CharacterTradition, CharacterAffinityTotal, CharacterResonanceTotal, Reincarnation, Cantrip, **TechniqueCapabilityGrant**
- **Capability integration:** TechniqueCapabilityGrant links Techniques to CapabilityTypes (from conditions app) with `base_value + (intensity_multiplier * intensity)` formula. This feeds into the mechanics app's action generation pipeline — when a character has a Technique that grants a Capability, the system can match it against Properties on Challenges to surface available approaches
- **Cantrip-technique alignment** — cantrip templates produce real Techniques with intensity/control at CG finalization
- **APIs:** Full viewsets and serializers
- **Frontend:** CantripSelector for CG magic stage
- **Tests:** Extensive coverage of affinity totals, anima rituals, techniques, styles, restrictions, motifs, effect types, character magic, services, resonance integration

## CG Magic Flow
See `docs/plans/2026-03-01-magic-revamp-design.md` for the original revamp design and
`docs/plans/2026-03-02-cantrip-technique-alignment.md` for the cantrip-technique alignment.

**Summary:** Player picks a staff-curated cantrip (grouped by archetype, filtered by Path). Behind the scenes, a real Technique with intensity/control/anima cost is created in the character's Gift. Player sees name + description + optional flavor (element/damage type). Mechanical stats are hidden.

**Post-CG progression unlock order:** cantrip (L1) → resonance discovery (L2) → thread weaving + motif (L3) → technique development + anima ritual (L4) → second gift (L5) → deeper magic (L6+)

## What's Needed for MVP

### Technique Use Flow (Design Spec Complete)
**Spec:** `docs/superpowers/specs/2026-03-29-technique-use-flow-design.md`

The core "I use Flame Lance" pipeline, connecting magic to the existing resolution
infrastructure. Three scopes identified:

**Scope #1 — Technique Use Flow (ready for implementation):**
- Anima cost calculation: `effective_cost = max(base_cost - (control - intensity), 0)`
- Safety checkpoint when anima would go negative (explicit opt-in to life force drain)
- Anima deduction with select_for_update
- Capability value enhancement from runtime intensity
- Anima Warp condition applied on overburn (severity scaled to deficit)
- Mishap rider consequences when intensity > control (non-lethal with sufficient anima)
- `use_technique()` orchestrator wrapping the existing resolution pipeline

**Scope #2 — Runtime Modifiers and Audere (design notes captured, needs own spec):**
- Affinity bonuses: Celestial +2 control, Primal +1/+1, Abyssal +2 intensity per 10 resonance
- Social scene passive control bonus (magic is much safer outside combat)
- Combat escalation (per-round intensity increase)
- Relationship event intensity spikes
- **Audere** — a Condition (not just high intensity) deliberately entered when offered.
  Grants massive intensity boost, higher-tier technique access, expanded anima pool.
  Dramatically accelerates Anima Warp accumulation.
- **Audere Majora** — tier-crossing (5→6, 10→11, 15→16, 20→21). Death during Audere
  Majora is **sacrifice, not failure** — characters who die are choosing to give
  everything so others can win. The system should make space for deliberate, meaningful
  sacrifice.
- IntensityTier.control_modifier integration

**Scope #3 — Negative Consequence Types (design notes captured, needs own spec):**
- Anima Warp as a **progressive Condition with severity stages** — builds over rounds
  of deficit casting, not instant death. Early stages are penalties/pain, middle stages
  risk scarring, late stages approach lethal territory. A runway, not a cliff.
- Magical scar condition templates
- Abyssal corruption as long-term consequence of overuse
- Mishap pool selection considers both control deficit AND current Warp stage
- Non-lethal mishaps when anima is sufficient; lethal consequences only enter pools
  when combined with anima overburn

**Key design principles (apply across all scopes):**
- Anima is a safety margin, not a gate. Magic always works. Deficit costs life force.
- Risk is always explicit. Character death warnings use those exact words.
- The technique always works. Mishaps are additional, not replacements.
- Higher intensity is genuinely better. Cost/risk is the trade-off.
- Control is efficiency. High control = cheap/free casting with no side effects.

### Other MVP Needs
- **Post-CG magic progression UI** — level-gated unlocks for resonances, threads, techniques, motifs, gifts
- **Budget-based technique builder** — replaces restriction-based power for post-CG technique creation
- Thread system UI integration (models exist, needs frontend)
- Aura farming mechanics — how perception at scenes feeds into resonance strength
- Fashion-to-resonance integration (requires Items & Crafting systems)
- Magical discovery through gameplay — unpredictable moments during RP where magic manifests
- Thread strengthening through relationship development
- Tradition gameplay (beyond CG templates — what traditions do during play)
- **Covenants** — magically-empowered adventuring parties (see below)

## Covenants (Post-MVP)

Covenants are magically-empowered oaths — blood rituals that enshrine each participant's role and bind them to a shared goal. Every covenant has a sworn objective that all members commit to achieving together. The magic is real: the oath grants power, and the roles shape how that power manifests.

**Covenant types — not one-size-fits-all:**
- **Covenant of the Durance** — The foundational type. An adventuring party swears to support each other as they pursue the Durance (their overarching story of magical discovery). Long-lived, deeply personal, built around relationship bonds
- **Covenant of Battle** — Formed for a specific war or battle scene. Assigns war roles that empower participants for large-scale conflict. Shorter-lived, can stack with a character's existing Durance covenant. Dissolved when the battle ends or objective is achieved
- **Other types TBD** — The covenant framework should support different oath types with different durations, goals, and role sets. A covenant of investigation, a covenant of vengeance, a trade pact — anywhere a sworn magical oath with defined roles makes narrative sense

**Three foundational archetypes (for Durance covenants):** Sword (offense) / Shield (defense) / Crown (support). At early levels, players pick from these three basic roles. As the covenant or members level up, specialized sub-roles unlock within each archetype. Battle covenants and other types may have their own role sets. Specific role names TBD.

**Key constraints:**
- Roles are unique within a covenant — no two members hold the same role
- Covenant bonds function like enhanced Threads with shared resonance
- Covenant role influences which techniques are empowered during group content
- Covenant-level progression unlocks group abilities
- Battle covenants stack with Durance covenants — a character can be in both simultaneously

**Dependencies:** Thread system UI, group content (missions/combat), post-CG technique system, role definitions.

## Notes

### Cross-reference: Aspect Focus & Path Evolution
See `character-progression.md` → "Aspect Focus as Path Evolution Guide" for a future design idea where players choose an aspect to lean into, guiding both check bonuses and path evolution. This touches magic because aspect weights feed into the check resolution pipeline alongside affinity/resonance mechanics.
