# Properties, Capabilities, Applications, and Actions

> The foundational interaction model for Arx II. This document describes how
> characters interact with the game world through four layers: what things
> ARE (Properties), what characters CAN DO (Capabilities), HOW they do it
> (Applications), and what becomes AVAILABLE in context (Actions). Every
> system that involves characters interacting with objects, creatures, or
> each other should follow this pattern.

---

## The Four Layers

### Properties: What Things Are

A **Property** is a neutral, descriptive fact about something in the game
world. Properties don't imply good or bad — they describe qualities.

- "This door is wooden."
- "This creature is abyssal."
- "This barrier is made of shadow."
- "This armor is metallic."
- "This room contains water."
- "The room is dark."

Properties attach to anything: obstacles, creatures (via species), equipment,
conditions, rooms, weather, and GM-created Situations. They are the shared
vocabulary that connects all game systems.

**Properties are not Capabilities.** A wooden door IS wooden — that's a
Property. A character who CAN command wood — that's a Capability. The door
doesn't "do" anything by being wooden. The character does something because
they have a Capability that's relevant to the door's Property.

**Environment Properties** matter too. A room might have the `water` Property
because it contains a lake, or `shadows_present` because it's dimly lit. These
are preconditions that make certain Capabilities useful — a shadow teleporter
can only teleport when shadows are present.

### Capabilities: What Characters Can Do

A **Capability** is a mechanism a character has for actively affecting the
world, with a graduated value representing how effectively they can do it.

- "Can generate fire (value: 15)"
- "Can fly (value: 5)"
- "Can project force (value: 20)"
- "Can teleport (value: 8)"
- "Can perceive the supernatural (value: 3)"

Capabilities are NOT binary. A value of 0 means effectively unable. Higher
values beat higher thresholds. "Impossible" just means a very high requirement.
Floor is always 0 — negative modifiers reduce but never go below zero.

**Capabilities are mechanisms, not states.** A Capability should always map to
"a way to affect the world that enables Actions." Flight enables going over
things, dodging differently, reaching high places. Fire generation enables
burning, igniting, illuminating, warming. Physical force enables breaking,
lifting, pushing. Each Capability opens up Action possibilities that characters
without it don't have.

**Passive effects are not Capabilities.** Regeneration, disease immunity,
damage resistance — these modify what happens TO a character, not what a
character can DO. They belong in the conditions/modifier system. The rare
exception (pain immunity letting you attempt something unbearable) would be
modeled as a Capability like "endure extreme conditions" rather than
retroactively treating the passive effect as a Capability.

#### Where Capabilities Come From

Most Capabilities are **derived**, not stored:

- **Traits** — strength derives into physical force, agility derives into
  precision and evasion. These are calculated from trait values, not stored
  as separate records.
- **Baseline human abilities** — walking, climbing, swimming at basic levels.
  These don't need records. A condition can remove them (paralysis removes
  movement), but the default is assumed.

Some Capabilities are **explicitly granted** by sources:

- **Techniques** — activated magical abilities that grant Capabilities, often
  with constraints (e.g., "grants teleportation when `shadows_present`").
  Currently the only implemented source is conditions via
  `ConditionCapabilityEffect`.
- **Conditions** — active status effects that grant or modify Capabilities.
- **Distinctions** — character traits that grant innate Capabilities
  (not yet built; blocked by EffectBundle pattern).
- **Species** — inherent racial Capabilities (not yet built).
- **Equipment** — items that grant Capabilities when worn/wielded
  (not yet built).

**Capability grants can have constraints.** A Technique might grant
teleportation, but only when `shadows_present` is a Property of the current
environment. Another Technique might grant the same Capability unconditionally.
Same Capability, different source constraints.

**Capability aggregation:** All sources contribute positive or negative values
additively. Total floors at 0. No percentage modifiers, no multiplication,
no caps.

**Avoid Capability proliferation.** Keep Capabilities generic. One Capability
should cover a concept broadly — `physical_force` covers punching, lifting,
and breaking. `fire_generation` covers burning, igniting, illuminating, and
warming. Don't create a dozen Capabilities for variations of the same
mechanism. Total vocabulary should be ~20-30 Capabilities.

### Applications: How Capabilities Apply

An **Application** is a specific, designed way to use a Capability against or
in the presence of a Property. Applications describe what you DO with a
mechanism when a particular quality is relevant. They are the bridge between
what a character can do and what the world presents.

Applications for `fire_generation`:
- **Burn** — apply fire to destroy something `flammable`
- **Ignite** — apply fire to light something `ignitable`
- **Illuminate** — apply fire to brighten a `dark` space
- **Warm** — apply fire to heat a `cold` environment
- **Cook** — apply fire to prepare `raw_food`
- **Explode** — apply fire to detonate something `volatile`

These sound like synonyms but are mechanically distinct — different
situations, different targets, different checks, different outcomes.

Applications for `physical_force`:
- **Break** — apply force to shatter something `solid`
- **Lift** — apply force to move something `heavy`
- **Push** — apply force to displace something `movable`

Applications for `flight`:
- **Fly Over** — use flight to bypass something `tall`
- **Aerial Evasion** — use flight for dodging in open space

Each Application carries: a name, a default narrative template, and a check
type for resolution. Applications are defined globally — a small, designed
vocabulary of ~40-60 total across all Capabilities, authored once and reusable
everywhere.

**Applications are designed, not auto-generated.** We don't compute every
possible Capability x Property intersection. A designer asks "what are the
interesting things you can do with fire?" and creates the Applications. Most
Capabilities have 3-8 interesting Applications.

### Actions: What Becomes Available in Context

When a character has Capabilities relevant to the current Situation's
Properties, **Actions become visible**. An Action is an Application presented
in context with a goal and outcomes — what the player actually sees and
chooses.

The same Application produces different Actions in different contexts:

| Application | Context | Action Presented | Outcome |
|-------------|---------|-----------------|---------|
| Burn | Obstacle (flammable door) | "Burn Through" | Bypass obstacle |
| Burn | Utility (unlit torch) | "Light the Torch" | Ignite object |
| Burn | Mission (enemy camp) | "Start a Fire" | Create distraction |
| Burn | Environment (cold room) | "Build a Fire" | Warm the area |
| Fly Over | Obstacle (tall wall) | "Fly Over the Wall" | Bypass obstacle |
| Aerial Evasion | Combat (melee attacker) | "Take to the Air" | Evasion option |

The **Context** provides:
- The **goal**: what the character is trying to achieve
- The **presentation**: how the Application is named and described here
- The **outcome**: what success and failure mean, composed from mechanical
  primitives (destroy obstacle, apply condition, progress mission, change
  Property, deal damage, create narrative record)
- Optional **custom narrative**: designer-authored text for important moments
- **Visibility filtering**: if the check difficulty vs. character Capability
  is at impossible-tier (rank gap where every result is failure), the option
  doesn't appear

**Outcomes are goals, not mechanics.** "Get past this door," "lure the target
to you," "survive this hazard," "damage this enemy" — these are what the
character is trying to achieve. The mechanical effects are a layer the Context
provides. In a mission, success means stage progression. At an obstacle,
success means bypass. In combat, success means damage with type interactions.
In a scene, success means narrative outcome. The Application and Capability
stay the same; what changes is the Situation.

**Resolution uses the Attempt system.** `resolve_attempt(character,
attempt_template, target_difficulty)` handles the check roll with weighted
consequences per outcome tier. The Attempt system is already built — it
provides tiered success/failure with the roulette display.

### The Resolution Chain

```
Situation (Properties + goal + difficulty)
  -> Applications match (character Capabilities meet Situation Properties)
    -> Contextual Actions presented to player
      -> Player chooses one
        -> AttemptTemplate resolves (check + tiered consequences)
          -> Context interprets outcome into mechanical primitives
```

The Situation maps applicable Applications to AttemptTemplates. The
Application provides the check type; the Situation provides the difficulty
and consequences. This is the same pattern the obstacle system uses —
`BypassOption` is an Application in obstacle Context, `BypassCheckRequirement`
is the check, and bypass resolution is the outcome.

---

## Techniques as Capability Sources

A **Technique** is a specific way to USE a Gift. It grants the character
Capabilities and potentially enables new Actions through those Capabilities.

A Gift like "Shadow Magic" is broad and abstract. Techniques make it concrete:
- "Shadow Barrier" grants `force_projection` when used defensively
- "Shadow Bolt" grants `shadow_projection` for attacks
- "Shadow Step" grants `teleportation` constrained by `shadows_present`
- "Shadow Blade" grants `weapon_enhancement` with shadow Properties

**Gift resonances are metaphysical, not mechanical.** A "Shadow Magic" Gift
doesn't mean all its Techniques deal shadow damage. A shadow Technique might
create physical barriers, enhance stealth, enable teleportation, or form
weapons. The resonance describes the magical source, not the mechanical
outcome.

**What a Technique declares:**
1. **Capability grants** — what Capabilities it provides, at what values
   (derived from intensity/control), with what constraints
2. **Properties on effects** — when this Technique's Capabilities are used
   in Actions, what Properties do the effects carry (e.g., a shadow bolt
   carries `shadow` and `piercing` Properties for combo/interaction purposes)

The Capability grants are a small list per Technique (typically 1-3). The
Properties on effects are what drive combo interactions in combat and
determine how the Technique's Actions interact with target Properties.

### Current State of Techniques

`src/world/magic/models.py` — Technique currently has:
- `gift` FK, `style` FK (TechniqueStyle), `effect_type` FK (EffectType)
- `intensity` (power), `control` (precision), `anima_cost` (resource cost)
- `level` (gates progression, derives tier)
- `restrictions` M2M (limitations that grant power bonuses)

What Technique currently lacks is any connection to the Capability system — no
way to declare what Capabilities it grants, what constraints apply, or what
Properties its effects carry. Building this connection is the path forward.

### Trait-Derived Capabilities

Not all Capabilities come from Techniques. Traits derive into Capabilities
via calculation:

- High Strength -> `physical_force` Capability at a value derived from the
  trait score
- High Agility -> `precision` and `evasion` Capabilities
- High Perception -> `awareness` Capability

These are NOT stored as records. They're calculated when Capability values
are aggregated. The derivation formula is defined once (e.g., "physical_force
= strength_value * 2") and applies to all characters.

Species, equipment, and conditions can further modify these derived values
through the standard additive aggregation.

---

## Contexts and Situations

Actions are generated when Capabilities meet Properties **in a Context**. The
Context is the Situation presenting a challenge or opportunity.

### Types of Context

**Obstacles** — already built. An obstacle on an exit with Properties,
bypass options gated by Capability requirements, and check-based resolution.
This is the first implementation of the full pattern.

**Mission Stages** — a narrative challenge like "lure the target to you" or
"get past the guards." The stage has Properties on the challenge/target, and
characters see options based on their Capabilities. Success progresses the
mission; failure has narrative consequences.

**Combat Situations** — environmental effects, terrain features, or
situational elements during a fight. A room flooding during combat adds
`submerged` Properties; characters with `aquatic_breathing` gain options
others don't have. (Note: structured combo attacks between party members
are a separate, designed system — not derived from this pipeline.)

**Scene Interactions** — narrative moments where Capabilities create
interesting options. A dark room where a character with `fire_generation`
can illuminate, or a locked chest where `lockpicking` is relevant.

**GM-Created Situations** — a GM sets the stage for a story scene, tagging
a Situation with Properties. "A boulder is rolling at your party" — the GM
picks a preset (or builds from Properties: `solid`, `heavy`, `massive`,
`rolling`), sets severity. The system generates options from each character's
Capabilities.

### GM Workflow

GMs are responsible for **setting the stage**, never for game-designing on
the fly. The workflow is:

1. GM creates a Situation, either from a preset template or by tagging
   Properties manually
2. GM sets difficulty/severity
3. The system evaluates character Capabilities against the Situation's
   Properties via the global Application table
4. Each character sees personalized Actions based on what they can do
5. Players choose and the system resolves via the Attempt pipeline

**GMs should not need to think about "what can players do."** The system
handles that. If a player has a Capability that should logically apply but
no option appears, that's feedback for the system designers to add an
Application or Property — not something the GM patches at the table.

GMs may have a mechanism to add a bespoke option at their table, but this
should be flagged as a GM ruling for later review. Consistency matters — two
GMs should not make different rulings on identical Situations.

**Property presets** reduce GM burden. Common Situations ("boulder," "fire
wall," "collapsing bridge," "magical barrier," "locked door") come as
templates with pre-tagged Properties. A GM picks a preset, optionally
tweaks it, sets severity, done.

---

## The Interaction Pipeline

When Capabilities meet Properties in a Context, the system resolves what
Actions are available through a consistent pipeline:

```
1. IDENTIFY Properties in the Situation
   - Target Properties (obstacle, creature, object, mission challenge)
   - Environment Properties (room, weather, terrain, elements present)
   - Condition Properties (status effects on the target)

2. MATCH Capabilities to Applications
   - For each Property, find Applications where the character has the
     required Capability at a non-trivial value
   - Check Capability source constraints (shadows required, etc.)
   - Filter by difficulty: if rank gap is impossible-tier, hide the option

3. PRESENT Actions in Context
   - Compose Application + Context into a named Action with narrative
   - Show difficulty indicator relative to character's Capability value
   - Use custom narrative if the designer authored one for this Situation

4. RESOLVE via the Attempt system
   - Player chooses an Action
   - resolve_attempt() handles the check roll with tiered consequences
   - Capability value may vary at resolution time based on intensity,
     modifiers, escalation, and other runtime factors

5. APPLY outcomes (Context-dependent)
   - Obstacle: bypass resolution (destroy, personal pass, temporary clear)
   - Mission: stage progression or failure consequences
   - Combat: damage + condition interactions + Property combos
   - Scene: narrative outcome, environment change, state change
   - Outcomes are composed from a small set of mechanical primitives,
     not hardcoded per Situation
```

### Outcome Primitives

Outcomes are composed from a small, defined set of mechanical effects:

- **Bypass/remove obstacle** — clear a blocking element
- **Apply Condition** — inflict a status effect on a target
- **Remove Condition** — clear a status effect
- **Change Property** — add or remove a Property on a target or environment
- **Deal typed damage** — inflict damage with a type for interaction rules
- **Progress stage** — advance a mission or encounter phase
- **Create narrative record** — log what happened for scene history
- **Transform/change state** — alter an object (raw food -> cooked, etc.)

Each Context composes 1-2 primitives. Designers write templated narrative
around them. Important moments get custom text.

---

## Combat Considerations

Combat uses the Property/Capability/Application model for **situational
interactions** — environmental effects, terrain exploitation, novel uses of
magic in combat Contexts.

### What Uses This System

- Environmental interactions: flooding room + `aquatic_breathing`, darkness +
  `shadow_traversal`, oil slick + `fire_generation`
- Situational advantages: high ground + `flight`, cover + `teleportation`
- Novel Applications: using ice magic to freeze a flooded floor, using
  force to collapse terrain on enemies
- Boss Properties: `armored`, `warded`, `regenerating` — these function like
  obstacle Properties that must be addressed through Capabilities

### What Does NOT Use This System

**Structured combo attacks** between party members are designed, named,
coordinated strategies — not derived from the Capability/Property pipeline.
Combos are planned and executed by players as explicit tactics. They will
be a separate, structured system where:

- Combo rules are defined between Properties, not between Techniques
  ("shattering + frozen = amplified" applies to ANY source)
- Party coordination makes diverse Capability composition strategically
  important
- Combo discovery and execution should feel rewarding as deliberate strategy

The Property/Capability system feeds INTO combos (attack Properties and
target Properties are what combo rules match on) but combo resolution is
its own designed subsystem.

### Intensity and Control in Combat

During combat, the intensity stat escalates, increasing effective Capability
values for Techniques. Control counterbalances — precision vs. raw power.
Narrative events (ally injured, dramatic revelation) can spike intensity.
Some Actions may require minimum intensity thresholds, meaning they're only
available as the fight escalates — creating the dramatic arc of fights
building toward breakthrough moments.

---

## How This Maps to Current Code

### What's Built

**The obstacle/bypass system** is the first implementation of this pattern:

```
ObstacleTemplate (has Properties via M2M)
  -> ObstacleProperty (e.g., "tall", "solid", "ice")
       -> BypassOption (e.g., "Fly Over", "Climb", "Melt")
             +-- BypassCapabilityRequirement (Capability + minimum_value)
             +-- BypassCheckRequirement (check type + base difficulty)
```

This maps directly to the model: ObstacleProperty = Property,
BypassCapabilityRequirement = Capability gate, BypassOption = an Application
in obstacle Context. The generalization is lifting this pattern to work
beyond obstacles.

**Capability resolution** (`src/world/conditions/services.py`):
- `get_capability_value(target, capability_type)` — single lookup
- `get_all_capability_values(target)` — bulk lookup, dict[str, int]
- Currently aggregates ONLY from Conditions. Future sources are additive.

**The Action Enhancement system** provides the mechanism for sources to
modify Actions:
- `ActionEnhancement` links sources (Technique, Distinction, Condition) to
  base Actions
- Effect configs define what enhancements do mechanically
- The handler dispatch system is extensible

**The Condition interaction system** has combo rules between Conditions and
damage types, fully implemented but with no callers:
- `ConditionDamageInteraction` — combo rules (Condition + damage -> effect)
- `process_damage_interactions()` — resolution function, tested, never called
- Needs a damage-dealing pipeline to call it

**The Attempt system** handles check resolution with narrative consequences:
- `resolve_attempt()` — check roll with weighted consequence tiers
- Transient results — caller decides what to do with the outcome
- Already suitable for resolving Capability-based Actions

### What's Not Built

- **Technique Capability grants** — no model for Techniques declaring what
  Capabilities they provide
- **Shared Property model** — ObstacleProperty exists but is isolated to
  obstacles; needs generalization
- **Application model** — no model for globally-defined Applications
  connecting Capabilities to Properties
- **Context/Situation model** — no generalized model for presenting
  challenges with Properties
- **Trait-derived Capabilities** — no calculation pipeline from trait values
  to Capability values
- **Damage-dealing pipeline** — no service to deal typed damage and call
  the existing interaction/resistance systems
- **Property presets** — no template system for common Situations

---

## Condition Scope

Conditions currently serve as both narrow status effects ("paralyzed",
"frozen") and broad effect bundles (anything applied to a character that
modifies Capabilities, checks, resistances, and more). This dual role is
functional but creates conceptual blur.

The distinction matters because:
- A **status effect** like "Frozen" is a discrete state with clear
  Properties, clear duration, and clear interactions (shattering combos,
  fire removes it).
- An **effect bundle** like "Werewolf Battleform Active" is a complex
  package of Capability grants, check modifiers, and Property changes that
  happens to be modeled as a Condition.

The EffectBundle pattern (TECH_DEBT item #3) is intended to address this —
once any source can grant a bundle of effects, Techniques and Distinctions
won't need to route everything through Conditions. This should naturally
narrow Conditions back toward their intended role as status effects.

For now, Conditions work as the catch-all. But new systems should be designed
with the eventual separation in mind.

---

## The Type Registry Problem

The codebase has several models answering "what kind of thing is this?" in
overlapping ways. Deep analysis lives in
`docs/plans/2026-03-05-properties-and-combat-mechanics-design.md`.

Key points relevant to this architecture:

- **DamageType** describes a subset of Properties (types of harm). Not all
  Properties are damage types. The relationship between DamageType and a
  future shared Property model needs careful thought.
- **ObstacleProperty** IS a Property model, but isolated to obstacles. A
  shared Property model should replace or generalize it.
- **CapabilityType** is the Capability definition model. It lives in
  conditions but is used cross-system (conditions + obstacles).
- **Resonances** (now proper models after the ModifierTarget refactor) are
  thematically related to Properties but distinct — resonance measures how
  much fire magic a character has (quantitative), while a Property describes
  that something IS fire-typed (qualitative). A resonance may imply certain
  Properties on Techniques that draw from it, but they are not the same
  concept.

---

## Integration Points

| System | How It Connects |
|--------|----------------|
| Combat | Properties on attacks and targets drive situational interactions; boss defenses are obstacle-like; structured combos are a separate system informed by Properties |
| Magic | Techniques grant Capabilities with optional constraints; Gift resonances suggest (not dictate) Technique effect Properties |
| Items & Equipment | Items have Properties (metallic, enchanted); equipped items contribute Capabilities |
| Character Progression | Higher path levels unlock Techniques with higher Capability values |
| Relationships | Relationship states can modify Capability values; narrative events spike intensity |
| Missions | Mission Stages present challenges with Properties; Capabilities determine available approaches |
| Stories/GM | GMs create Situations from Property presets; system generates options from character Capabilities |
| Achievements | Novel interactions are database records the achievement system can reference |

### With the EffectBundle Refactor

The EffectBundle pattern (TECH_DEBT item #3) is the key enabler for multiple
Capability sources. Once any source (Distinction, Technique, equipment,
species) can grant a bundle of effects including Capability contributions,
the Capability aggregation service automatically picks them up.

---

## Design Constraints

These are hard requirements that any implementation must respect:

1. **Nothing is binary.** Capabilities are integer values with thresholds.
   Even "impossible" things just require very high values. No boolean gates.

2. **Properties are neutral.** They describe what something IS, not whether
   that's good or bad. "Abyssal" is a Property. Whether it creates
   vulnerability to celestial attacks is determined by interaction rules.

3. **Capabilities are mechanisms.** Every Capability should map to "a way to
   affect the world that enables Actions." If it doesn't enable any Action
   a character could take, it's a passive effect, not a Capability.

4. **Capabilities aggregate additively.** All sources contribute positive or
   negative values. Total floors at 0. No percentage modifiers.

5. **Applications are globally defined.** Interaction rules between
   Capabilities and Properties are authored once by system designers and
   apply everywhere. GMs set the stage; they don't define what players can do.

6. **Combo rules live on Properties, not Techniques.** "Shattering + frozen =
   amplified" applies to ANY source with those Properties. Never hardcode
   Technique-to-Technique combos.

7. **The obstacle pattern is the template.** New interaction systems should
   follow the same structure: target has Properties, Applications connect
   Capabilities to Properties, Context determines outcomes.

8. **Outcomes are goals, not mechanics.** The Application describes the
   approach. The Context determines what success means (bypass, progression,
   damage, narrative). Mechanical effects are composed from primitives.

9. **Most Capabilities are derived.** Trait values derive into Capabilities.
   Only unusual or granted Capabilities need explicit storage.

10. **Party coordination is mandatory for bosses.** Boss encounters require
    combo attacks from multiple characters. Solo damage should be ineffective
    against boss defenses.

11. **Data entry must scale.** Properties (~30-50), Capabilities (~20-30), and
    Applications (~40-60) are small vocabularies authored once. Contextual
    Situations are composed from these building blocks, not authored from
    scratch. Hundreds to low thousands of authored Situations is acceptable
    if each is a few fields of data, not custom code.

12. **No hardcoded results.** Outcomes are composed from mechanical primitives
    with templated narrative. Important moments get custom text. No Situation
    should require custom code to resolve.

---

## Open Questions

These need implementation exploration to resolve:

1. **Context model:** How does the generalized Context/Situation relate to
   the existing obstacle model? Is it a new model that subsumes obstacles,
   or a parallel concept? How does it represent abstract challenges like
   "walls closing in" vs. concrete objects like "boulder"?

2. **Application model:** What's the concrete data model for Applications?
   How does it relate to the existing BypassOption? Is a BypassOption just
   an Application in obstacle Context, or are they different models?

3. **Technique Capability grants:** What model connects Techniques to the
   Capabilities they grant? How are constraints (shadows required)
   represented? How do Capability values derive from Technique stats
   (intensity/control)?

4. **Property unification:** Does ObstacleProperty generalize into a shared
   Property model, or is a new model created? How does it relate to
   DamageType (which is a subset of Properties)?

5. **Trait derivation formulas:** How exactly do trait values convert to
   Capability values? Is this a simple multiplier, a lookup table, or
   something more nuanced?

6. **GM override mechanism:** How do GM-created bespoke options get flagged
   and reviewed? What's the UI for this?

7. **Capability constraint model:** How do source constraints (shadows
   required, underwater only) get stored and evaluated? Is this a simple
   Property-presence check, or can constraints be more complex?

8. **EffectType evolution:** Does the existing EffectType model on Technique
   evolve to carry Capability-grant information, or is that a separate model?
   EffectType currently has: name, base_power, has_power_scaling,
   base_anima_cost — minimal but potentially extensible.

9. **Situation-to-AttemptTemplate mapping:** How does a Situation map its
   applicable Applications to AttemptTemplates for resolution? The
   Application provides the check type; the Situation provides difficulty
   and consequences. The existing obstacle system does this via
   BypassCheckRequirement — the generalized version needs definition.
