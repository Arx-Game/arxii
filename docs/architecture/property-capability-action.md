# Properties, Capabilities, Applications, and Actions

> The foundational interaction model for Arx II. This document describes how
> characters interact with the game world through four layers: what things
> ARE (Properties), what characters CAN DO (Capabilities), WHERE those
> Capabilities are relevant (Applications), and what becomes AVAILABLE in
> context (Actions). Every system that involves characters interacting with
> objects, creatures, or each other should follow this pattern.

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
Conditions, rooms, weather, and GM-created Situations. They are the shared
vocabulary that connects all game systems.

**Properties are not Capabilities.** A wooden door IS wooden — that's a
Property. A character who CAN command wood — that's a Capability. The door
doesn't "do" anything by being wooden. The character does something because
they have a Capability that's relevant to the door's Property.

**Environment Properties** matter too. A room might have the `water` Property
because it contains a lake, or `shadows_present` because it's dimly lit. These
are preconditions — a shadow teleporter can only teleport when shadows are
present, and a fire controller needs existing fire to direct.

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

**Related Capabilities are distinct.** `fire_generation` (creating fire from
nothing), `fire_control` (directing existing fire), and using a mundane fire
tool (torch, tinderbox) are different Capabilities with different constraints.
A fire controller needs the `fire_present` Environment Property; a fire
generator does not. Both can achieve the same Applications (burning, igniting),
but through different mechanisms with different checks. Keep Capabilities
distinct when they have meaningfully different constraints or checks.

#### Where Capabilities Come From

Most Capabilities are **derived**, not stored:

- **Traits** — strength derives into physical force, agility derives into
  precision and evasion. These are calculated from trait values, not stored
  as separate records.
- **Baseline human abilities** — walking, climbing, swimming at basic levels.
  These don't need records. A Condition can remove them (paralysis removes
  movement), but the default is assumed.

Some Capabilities are **explicitly granted** by sources:

- **Techniques** — activated magical abilities that grant Capabilities, often
  with constraints (e.g., "grants teleportation when `shadows_present`").
  Currently the only implemented source is Conditions via
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

**Avoid Capability proliferation.** Keep Capabilities generic enough to cover
a concept broadly, but distinct enough that different mechanisms with different
constraints or checks remain separate. Total vocabulary should be ~20-30
Capabilities.

### Applications: Where Capabilities Are Relevant

An **Application** is a designed pairing of a Capability with a Property,
declaring that this Capability can interact with things that have this
Property. Applications are pure eligibility — they say "you CAN attempt
something here" without defining how it resolves.

Applications for `fire_generation`:
- **Burn** — fire + `flammable` targets
- **Ignite** — fire + `ignitable` targets
- **Illuminate** — fire + `dark` environments
- **Warm** — fire + `cold` environments
- **Cook** — fire + `raw_food` targets
- **Explode** — fire + `volatile` targets

Note that `fire_control` could share many of the same Applications (Burn,
Ignite, etc.) but with the additional constraint that `fire_present` must
be an Environment Property. Multiple Capabilities can have Applications with
the same name targeting the same Property — the mechanism differs, not the
interaction.

Applications for `physical_force`:
- **Break** — force + `solid` targets
- **Lift** — force + `heavy` targets
- **Push** — force + `movable` targets

Applications for `flight`:
- **Fly Over** — flight + `tall` obstacles
- **Aerial Evasion** — flight + open space

**An Application record is minimal:**
- Name (the interaction: "Burn", "Break", "Fly Over")
- Capability (what mechanism is required)
- Property (what quality makes it relevant)

Applications carry NO check type, NO narrative template, and NO difficulty.
Those come from other layers:
- **Check type** comes from the mechanism delivering the Capability (the
  Technique, tool, or innate ability — see "The Delivery Mechanism" below)
- **Difficulty and outcomes** come from the Situation
- **Narrative** comes from the combination of mechanism + Situation

Applications are defined globally — a designed vocabulary of ~40-60 total
across all Capabilities. They are authored once and apply everywhere.

**Applications are designed, not auto-generated.** We don't compute every
possible Capability x Property intersection. A designer asks "what are the
interesting things you can do with fire?" and creates the Applications. Most
Capabilities have 3-8 interesting Applications.

### Actions: What Becomes Available in Context

When a character has Capabilities relevant to the current Situation's
Properties, **Actions become visible**. An Action is what the player actually
sees and chooses — the composition of an Application, a delivery mechanism,
and a Situation.

The same Application produces different Actions depending on Situation and
mechanism:

| Application | Mechanism | Situation | Action Presented |
|-------------|-----------|-----------|-----------------|
| Burn | Fire Blast (Technique) | Flammable door | "Fire Blast: Burn Through" |
| Burn | Torch (Equipment) | Flammable door | "Torch: Burn Through" |
| Burn | Fire Blast (Technique) | Enemy camp (Mission) | "Fire Blast: Start a Fire" |
| Illuminate | Fire Blast (Technique) | Dark room | "Fire Blast: Light the Way" |
| Fly Over | Wings (Species) | Tall wall | "Fly Over the Wall" |
| Fly Over | Wind Magic (Technique) | Tall wall | "Wind Magic: Fly Over the Wall" |

**Outcomes are goals, not mechanics.** "Get past this door," "lure the target
to you," "survive this hazard," "damage this enemy" — these are what the
character is trying to achieve. The Situation provides the goal and determines
what success means mechanically. The Application and Capability stay the
same; what changes is the Situation.

**Visibility filtering:** If the check difficulty vs. character Capability is
at impossible-tier (rank gap where every result on the chart is failure), the
option doesn't appear. This keeps the UI honest — characters see meaningful
choices, not noise.

---

## The Delivery Mechanism

When a character employs a Capability, they do so through a **mechanism** —
the Technique, tool, innate ability, or trait that provides the Capability.
The mechanism determines HOW the character does it, which drives the check
type and narrative.

- Fire Blast (Technique) -> Arcane Attack check, "channels a blast of fire"
- Torch (Equipment) -> Dexterity check, "holds the torch to"
- Wings (Species innate) -> Agility check, "leaps into the air"
- Wind Magic (Technique) -> Arcane Control check, "summons a gust"
- Raw Strength (Trait-derived) -> Might check, "braces and pushes"

The mechanism is not a separate model — it's the source that grants the
Capability. The Technique, tool, or trait already exists; it just also carries
information about what check it uses when its Capabilities are employed.

### Availability vs. Application: The Two-Check Pattern

Employing a Capability can involve up to two checks:

**Availability** — Is the Capability actually usable right now?
- The character has the Capability (from a source)
- Environmental/constraint Properties are satisfied (`shadows_present`, etc.)
- If the mechanism requires activation, an activation check may be needed
  (e.g., successfully invoking a complex Technique)

**Application** — Can you use that Capability effectively in this Situation?
- The Attempt resolves whether the character succeeds at the task
- Difficulty comes from the Situation
- Check type comes from the mechanism or the task itself

In many cases, one or both checks are trivial and get skipped:

| Scenario | Availability | Application Attempt |
|----------|-------------|-------------------|
| Winged species dodging boulder | Trivial (has wings) | Agility check |
| Wind mage dodging boulder | Wind Magic check | Agility check |
| Fire Blast burning door | Arcane check | Trivial (door can't dodge) |
| Torch burning door | Trivial (has torch) | Trivial (hold it there) |
| Shadow Step past a wall | Requires `shadows_present` | Arcane check |

The Availability step overlaps with Capability constraints — if the
environmental Properties aren't met, the Capability isn't available and
the Application doesn't even appear. When the mechanism is innate or
trivial to activate, Availability is automatic. When activation requires
skill (casting a spell, invoking a complex ability), it's a check.

The Application Attempt is the main resolution — it uses the existing
Attempt system (`resolve_attempt()`) with difficulty from the Situation
and check type from the mechanism or task.

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
   (derived from intensity/control), with what environmental constraints
2. **Properties on effects** — when this Technique's Capabilities are used
   in Actions, what Properties do the effects carry (e.g., a shadow bolt
   carries `shadow` and `piercing` Properties for combo/interaction purposes)
3. **Check type** — how the Technique resolves when used as a mechanism
   (this may come from the Technique's existing fields like style or
   effect_type rather than a new field)

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

Species, equipment, and Conditions can further modify these derived values
through the standard additive aggregation.

---

## Situations

A **Situation** is a challenge or opportunity that characters encounter. It
has Properties, a goal, and a difficulty. Situations are the Context in which
Capabilities become relevant and Actions are generated.

### Types of Situation

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

**GM-Created Situations** — a GM sets the stage for a story scene. "A boulder
is rolling at your party" — the GM picks a preset (or builds from Properties:
`solid`, `heavy`, `massive`, `rolling`), sets severity. The system generates
options from each character's Capabilities.

A Situation can represent concrete objects (a boulder, a door), environmental
states (poison gas filling a room, walls closing in), or abstract challenges
(a tense negotiation, a collapsing escape route). Not everything needs to be
a physical game object.

### What a Situation Provides

- **Properties** — what qualities are present (tagged from presets or manually)
- **Goal** — what characters are trying to achieve ("get past this," "survive
  this," "resolve this")
- **Difficulty/severity** — how hard the challenge is
- **Outcome mapping** — what success and failure mean mechanically, composed
  from Outcome Primitives
- Optional **custom narrative** — designer-authored text for important moments

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

When Capabilities meet Properties in a Situation, the system resolves what
Actions are available through a consistent pipeline:

```
1. IDENTIFY Properties in the Situation
   - Target Properties (obstacle, creature, object, mission challenge)
   - Environment Properties (room, weather, terrain, elements present)
   - Condition Properties (status effects on the target)

2. CHECK AVAILABILITY of Capabilities
   - Does the character have relevant Capabilities? (from any source)
   - Are environmental constraints met? (shadows_present, fire_present, etc.)
   - If activation check required, can the mechanism be invoked?

3. MATCH Capabilities to Applications
   - For each Property, find Applications where the character has an
     available Capability
   - Filter by difficulty: if rank gap is impossible-tier, hide the option

4. PRESENT Actions
   - Compose Application + mechanism + Situation into a named Action
   - Show difficulty indicator relative to character's Capability value
   - Use custom narrative if the designer authored one for this Situation

5. RESOLVE via the Attempt system
   - Player chooses an Action
   - resolve_attempt() handles the check roll with tiered consequences
   - Check type comes from the delivery mechanism (Technique, tool, trait)
   - Difficulty comes from the Situation
   - Capability value may vary at resolution time based on intensity,
     modifiers, escalation, and other runtime factors

6. APPLY outcomes (Situation-dependent)
   - Obstacle: bypass resolution (destroy, personal pass, temporary clear)
   - Mission: stage progression or failure consequences
   - Combat: damage + condition interactions + Property combos
   - Scene: narrative outcome, environment change, state change
   - Outcomes are composed from Outcome Primitives, not hardcoded
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

Each Situation composes 1-2 primitives for its outcomes. Designers write
templated narrative around them. Important moments get custom text.

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

Mapping to architecture concepts:
- ObstacleProperty = Property (isolated to obstacles; needs generalization)
- BypassCapabilityRequirement = Capability gate on an Application
- BypassOption = an Application composed with obstacle-specific resolution
- ObstacleTemplate = a reusable Situation definition
- ObstacleInstance = a Situation placed in the world

Note: The obstacle system bundles Application + resolution together in
BypassOption. The generalized architecture separates these — Applications
are independent, and resolution comes from the Situation + mechanism.

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
  Capabilities they provide, with what constraints
- **Shared Property model** — ObstacleProperty exists but is isolated to
  obstacles; needs generalization
- **Application model** — no model for globally-defined Applications
  connecting Capabilities to Properties
- **Situation model** — no generalized model for presenting challenges with
  Properties and generating Actions from Capabilities
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

6. **Applications are pure eligibility.** They carry no check type, no
   narrative, no difficulty. Those come from the delivery mechanism (check
   type), the Situation (difficulty, outcomes), and their combination
   (narrative).

7. **Combo rules live on Properties, not Techniques.** "Shattering + frozen =
   amplified" applies to ANY source with those Properties. Never hardcode
   Technique-to-Technique combos.

8. **The obstacle pattern is the template.** New interaction systems should
   follow the same structure: target has Properties, Applications connect
   Capabilities to Properties, Situation determines outcomes.

9. **Outcomes are goals, not mechanics.** The Application declares eligibility.
   The Situation determines what success means (bypass, progression, damage,
   narrative). Mechanical effects are composed from primitives.

10. **Most Capabilities are derived.** Trait values derive into Capabilities.
    Only unusual or granted Capabilities need explicit storage.

11. **Party coordination is mandatory for bosses.** Boss encounters require
    combo attacks from multiple characters. Solo damage should be ineffective
    against boss defenses.

12. **Data entry must scale.** Properties (~30-50), Capabilities (~20-30), and
    Applications (~40-60) are small vocabularies authored once. Contextual
    Situations are composed from these building blocks, not authored from
    scratch. Hundreds to low thousands of authored Situations is acceptable
    if each is a few fields of data, not custom code.

13. **No hardcoded results.** Outcomes are composed from mechanical primitives
    with templated narrative. Important moments get custom text. No Situation
    should require custom code to resolve.

---

## Open Questions

These need implementation exploration to resolve:

1. **Situation model:** How does the generalized Situation relate to the
   existing obstacle model? Is it a new model that subsumes obstacles, or
   a parallel concept? How does it represent abstract challenges ("walls
   closing in") vs. concrete objects ("boulder")?

2. **Application model:** What's the concrete data model? Minimally it's
   Capability FK + Property FK + name. But how does it relate to the existing
   BypassOption? Is BypassOption refactored to reference Applications, or
   does it remain obstacle-specific with Applications as a parallel system?

3. **Technique Capability grants:** What model connects Techniques to the
   Capabilities they grant? How are environmental constraints represented?
   How do Capability values derive from Technique stats (intensity/control)?

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

9. **Resolution mapping:** How does a Situation determine the Attempt
   resolution for each applicable Application? The check type comes from
   the delivery mechanism; the Situation provides difficulty and outcomes.
   The existing obstacle system bundles these in BypassOption/
   BypassCheckRequirement. The generalized version needs to separate
   Application (eligibility) from resolution (mechanism + Situation).

10. **Availability checks:** When a mechanism requires an activation check
    (invoking a complex Technique), how is that modeled? Is it a separate
    Attempt before the Application Attempt, or a modifier on the main
    Attempt? How do we avoid making trivial activations feel like
    unnecessary friction?
