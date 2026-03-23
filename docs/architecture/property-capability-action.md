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

Properties are **innate and structural** — they describe enduring qualities,
not transitory states. A door is flammable because of what it's made of. A
creature is abyssal because of what it is. Properties don't change moment to
moment (that's what Conditions are for — see "Properties vs. Dynamic State"
below).

Properties attach to anything: obstacles, creatures (via species), equipment,
rooms, and GM-created Situations. They are the shared vocabulary that connects
all game systems.

**Properties are not Capabilities.** A wooden door IS wooden — that's a
Property. A character who CAN command wood — that's a Capability. The door
doesn't "do" anything by being wooden. The character does something because
they have a Capability that's relevant to the door's Property.

**Properties are not damage math.** DamageType (fire, cold, shadow) describes
what an attack DOES — that's output, not a description of the target.
Resistance and vulnerability are handled by the existing Condition/DamageType
system (`ConditionResistanceModifier`, `ConditionDamageInteraction`). Properties
are about surfacing emergent gameplay options ("oh, I can do THAT here?"), not
about modifying damage numbers.

#### Properties vs. Dynamic State

Not everything that might seem like a Property should be one. The rule:

- **Properties** = innate, structural, authored. "This door is flammable."
  Doesn't change unless the thing fundamentally changes.
- **Conditions** = transitory states with lifecycle. "This character is
  burning." Has duration, stacking, stages. Already built.
- **World state** = environmental facts derived from game systems. Time of
  day, weather, "blood is present in this room because someone took damage."
  These are queried at runtime by service functions, not stored as Properties.

When the action pipeline asks "what's true about this situation?", it checks
all three sources: static Properties on targets/locations, active Conditions,
and relevant world state. A shadow teleport Technique's prerequisite ("shadows
available") might be satisfied by a Property on a dark room, OR by a
nighttime check from the gametime module, OR by an active shadow Condition.
The prerequisite check queries whatever sources are relevant — Properties are
just one input.

#### Conditions Can Carry Properties

When a character transforms (werewolf battleform, elemental form, etc.), they
temporarily gain structural qualities they don't normally have — "clawed",
"bestial", "large". These are modeled by Conditions that carry Properties:

- Technique activates → applies "Werewolf Battleform" Condition
- That Condition grants Capabilities (via `ConditionCapabilityEffect`)
- That Condition also carries Properties (via M2M to Property)
- The action pipeline sees those Properties when checking the character

This keeps Properties as the shared vocabulary while Conditions handle the
temporal lifecycle. The eventual EffectBundle pattern (TECH_DEBT #3) will
let any source (Technique, Distinction, equipment) directly declare a bundle
of effects including Properties, but Conditions-as-bundles work as the bridge.

Property sources on a character at query time:
- **Innate**: species, equipment (when built)
- **Temporary**: active Conditions with Property M2M
- Properties from these sources are unioned — no conflicts, just aggregation

### Capabilities: What Characters Can Do

A **Capability** is an atomic primitive describing a fundamental way a
character can affect the world, with a graduated value representing how
effectively they can do it.

- "Can generate (value: 15)" — create something from nothing
- "Can project (value: 20)" — push force/energy outward at range
- "Can traverse (value: 8)" — move through/past/over things
- "Can perceive (value: 12)" — sense, detect, analyze

Capabilities are NOT binary. A value of 0 means effectively unable. Higher
values beat higher thresholds. "Impossible" just means a very high requirement.
Floor is always 0 — negative modifiers reduce but never go below zero.

**Capabilities are atomic primitives, not compound concepts.** A Capability
name should be a single verb or simple noun — `generation`, `force`,
`traversal`, `perception`, `barrier`, `manipulation`. Compound names like
`fire_generation` or `shadow_traversal` indicate a missing abstraction: the
noun part (fire, shadow) belongs on the **source** as effect Properties, not
on the Capability itself. Any underscore in a Capability name is a potential
sign of wrong abstraction level.

This keeps the vocabulary to ~10-15 primitives while supporting infinite
variety through Techniques that combine multiple Capabilities with different
Properties and prerequisites. A fire mage's "Flame Lance" grants `generation`,
`force`, AND `projection` — all with `fire` effect Properties. A single
Technique bundling multiple Capabilities is the norm, not the exception.

**Reference Capability vocabulary:**

| Capability | What it enables |
|---|---|
| `generation` | Creating something from nothing |
| `force` | Raw power — breaking, lifting, pushing, striking |
| `projection` | Directing energy/force at range |
| `manipulation` | Controlling/directing something that already exists |
| `barrier` | Blocking, containing, shielding |
| `traversal` | Moving through/past/over things |
| `movement` | Basic locomotion (baseline human) |
| `perception` | Sensing, detecting, analyzing |
| `communication` | Conveying information across barriers |
| `precision` | Fine control, accuracy |
| `endurance` | Withstanding hostile conditions |
| `suppression` | Negating, dampening a quality |
| `transmutation` | Changing one thing into another |

This is a starting vocabulary, not exhaustive. New primitives can be added
when a genuinely distinct way of affecting the world emerges that can't be
expressed by existing primitives.

**Capabilities are substrate-agnostic.** `barrier` is `barrier` whether it's
made of fire, ice, shadow, or steel. The Properties on the effect (from the
Technique or equipment) determine what the barrier is made of, which matters
for combo interactions and narrative — but the Capability itself is generic.
This means a fire mage and a martial fighter with a shield both see "Shield"
Actions against incoming threats. They feel strong across contexts, not
siloed into their specialty.

**Passive effects are not Capabilities.** Regeneration, disease immunity,
damage resistance — these modify what happens TO a character, not what a
character can DO. They belong in the conditions/modifier system.

**Capabilities are evaluated per-source, not aggregated.** When a character
has `force` from both a Technique (Flame Lance, value 15) and traits (high
Strength, value 25), these are two separate paths to the same Application.
The player sees two distinct Actions: "Break Through (Flame Lance)" and
"Break Through (Raw Strength)" — each with its own check type, cost, risk,
and narrative. They don't stack into a combined value of 40 unless the
sources are explicitly designed to combine (e.g., a buff Technique that
enhances a trait, or a stat modifier).

#### Where Capabilities Come From

**Techniques** are the primary source — and they bundle multiple Capabilities.
A single Technique like "Flame Lance" grants `generation` + `force` +
`projection`, all with `fire` effect Properties. "Shadow Step" grants
`traversal` with prerequisite `shadows_present` and `shadow` effect
Properties. Techniques also carry effect Properties from their Gift's
resonance — a shadow mage's Techniques all carry `shadow`.

**Traits** derive into Capabilities via calculation:

- High Strength → `force` at a value derived from the trait score
- High Agility → `precision` at a derived value
- High Perception → `perception` at a derived value

These are calculated at query time, not stored as separate records.

**Conditions** grant or modify Capabilities via `ConditionCapabilityEffect`
(already built). Paralysis removes `movement`; empowerment boosts `force`.

**Equipment** grants Capabilities when worn/wielded. A blessed shield
grants `barrier` with `holy` effect Properties.

**Species** and **Distinctions** grant innate Capabilities (not yet built).

**Capability grants can have constraints.** A Technique might grant
`traversal`, but only when `shadows_present` is satisfied. Another source
might grant `traversal` unconditionally. Same Capability, different source
constraints. See "Capability Constraints" in Implementation Decisions.

**Each source is a separate Action path.** When multiple sources grant the
same Capability, each produces its own Action with its own check type,
cost, and narrative. Sources only stack when explicitly designed to combine
(buff Techniques modifying trait values, stat modifiers from Distinctions).

**Keep the vocabulary small.** ~10-15 atomic primitives. Richness comes
from Techniques bundling multiple Capabilities with different Properties,
not from proliferating the Capability list.

### Applications: Where Capabilities Are Relevant

An **Application** is a designed pairing of a Capability with a Property,
declaring that this Capability can interact with things that have this
Property. Applications are pure eligibility — they say "you CAN attempt
something here" without defining how it resolves.

Applications for `generation`:
- **Evaporate** — generation + `flooding`
- **Illuminate** — generation + `dark`
- **Ignite** — generation + `flammable`

Applications for `force`:
- **Break** — force + `solid`
- **Drain** — force + `flooding`
- **Lift** — force + `heavy`

Applications for `manipulation`:
- **Channel** — manipulation + `flooding`
- **Direct** — manipulation + `gaseous`

Applications for `barrier`:
- **Shield** — barrier + `cursed`
- **Contain** — barrier + `flooding`
- **Block** — barrier + `projectile`

Applications for `traversal`:
- **Escape** — traversal + `enclosed`
- **Navigate** — traversal + `dark`
- **Cross** — traversal + `hazardous`

Applications for `perception`:
- **Analyze** — perception + `cursed`
- **Scout** — perception + `dark`
- **Detect** — perception + `hidden`

Applications for `suppression`:
- **Cleanse** — suppression + `cursed`
- **Disperse** — suppression + `gaseous`

Note that the same Application name can appear for multiple Capabilities.
"Drain" might be achievable via `force` (smash the floor open) or
`manipulation` (direct the water away). These are different Capability +
Property pairings that happen to achieve a similar goal. Each produces
distinct Actions because the delivery mechanism differs.

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
|---|---|---|---|
| Evaporate | Flame Lance (Technique) | Flooded crypt | "Flame Lance: Boil Away" |
| Drain | Flame Lance (Technique) | Flooded crypt | "Flame Lance: Blast the Floor" |
| Drain | Raw Strength (Trait) | Flooded crypt | "Force Open the Drain" |
| Drain | Sanctified Strike (Technique) | Flooded crypt | "Sanctified Strike: Smash Through" |
| Illuminate | Flame Lance (Technique) | Dark room | "Flame Lance: Light the Way" |
| Shield | Blessed Shield (Equipment) | Cursed area | "Blessed Shield: Ward Against Curse" |
| Escape | Shadow Step (Technique) | Enclosed room | "Shadow Step: Phase Through" |

Note that Kael has three Actions for dealing with the flood — all via the
same Application (`force` + `flooding` = "Drain") but through different
mechanisms. Each is presented separately because they have different check
types, costs, risks, and narrative.

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

The Application Attempt is the main resolution — it uses the challenge
resolution system (`resolve_challenge()`) with difficulty from the Situation
and check type from the mechanism or task.

---

## Techniques as Capability Sources

A **Technique** is a specific way to USE a Gift. It grants the character
Capabilities and potentially enables new Actions through those Capabilities.

A Gift like "Shadow Magic" is broad and abstract. Techniques make it concrete:
- "Shadow Barrier" grants `barrier` (effect Properties: `shadow`)
- "Shadow Grasp" grants `manipulation` + `projection` (effect: `shadow`)
- "Shadow Step" grants `traversal` (prereq: `shadows_present`, effect: `shadow`)
- "Veil Sight" grants `perception` (prereq: `shadows_present`, effect:
  `shadow`, `arcane`)

**Gift resonances are metaphysical, not mechanical.** A "Shadow Magic" Gift
doesn't mean all its Techniques deal shadow damage. A shadow Technique might
create physical barriers, enhance stealth, enable teleportation, or form
weapons. The resonance describes the magical source, not the mechanical
outcome.

**What a Technique declares:**
1. **Capability grants** — what Capabilities it provides, at what values
   (derived from intensity), with what environmental prerequisites. A
   single Technique typically grants 2-4 Capabilities.
2. **Properties on effects** — when this Technique's Capabilities are used
   in Actions, what Properties do the effects carry (e.g., Flame Lance
   carries `fire`, `concussive`, `light`). These come from the Technique
   itself and from the Gift's resonance.
3. **Check type** — how the Technique resolves when used as a mechanism
   (this may come from the Technique's existing fields like style or
   effect_type rather than a new field)

The effect Properties drive combo interactions and also create emergent
consequences. If Flame Lance carries `light`, using it to "Drain" the
flood also illuminates the room — which might remove `dark` as a
Property, affecting other characters' shadow-dependent Actions.

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

- High Strength → `force` at a value derived from the trait score
- High Agility → `precision` at a derived value
- High Perception → `perception` at a derived value
- High Stamina → `endurance` at a derived value

These are NOT stored as records. They're calculated when Capability values
are aggregated. The derivation formula is defined per trait-Capability pair
via `TraitCapabilityDerivation` (see Implementation Decisions).

Trait-derived Capabilities produce their own Actions separately from
Technique-granted Capabilities. "Break Through (Raw Strength)" is a
different Action from "Break Through (Flame Lance)" — different check
type, different costs, different narrative.

---

## Situations and Challenges

A **Situation** is a scene-level event composed of one or more
**Challenges**. Challenges are the atomic unit — each one is a discrete
problem with its own Properties, severity, and resolution. A Situation
groups them, adds narrative framing, and can define dependencies between
them.

### Challenges: The Atomic Problem

A **Challenge** is something characters need to deal with — either an
**inhibitor** (blocks actions, prevents progress) or a **threat** (actively
causes harm). The existing obstacle system is a specialized implementation
of the inhibitor type. Challenges generalize this to cover both.

Examples of inhibitors: a locked door, a sealed chamber, darkness blocking
vision, a magical ward preventing passage.

Examples of threats: cursed water dealing damage over time, poison gas
filling a room, a collapsing ceiling, rising floodwater.

Each Challenge has:
- **Properties** — what qualities it has (`flooding`, `cursed`, `solid`, etc.)
- **Severity** — how hard it is to resolve (scales check difficulty)
- **Resolution type** — DESTROY (gone for everyone), PERSONAL (resolved for
  this character only), TEMPORARY (suppressed for N rounds)
- **Approaches** — specific Applications paired with check types and
  consequence text
- Optional **dependencies** — "this Challenge is hidden/inactive until
  another Challenge is resolved"

### Situations: Composed of Challenges

A Situation groups multiple Challenges into a coherent scene. A GM picks
a Situation preset and the system creates all its Challenges at once.

**Example — "Rising Cursed Flood" Situation:**

| Challenge | Properties | Type | Resolution |
|---|---|---|---|
| The Flood | `flooding`, `liquid` | Threat | DESTROY |
| The Curse | `cursed`, `arcane` | Threat | DESTROY |
| The Sealed Chamber | `enclosed`, `solid` | Inhibitor | DESTROY |
| The Darkness | `dark` | Inhibitor | TEMPORARY |

Each Challenge can be resolved independently — illuminating the room
doesn't drain the water. But dependencies can enforce pacing: the curse
anchor is `submerged`, so it only becomes targetable after the flood is
resolved.

### Actions Are Per-Challenge

Characters see Actions for each active Challenge based on their
Capabilities. The pipeline matches each character's Capability sources
against each Challenge's Properties via the Application table.

For the Flooded Crypt with three characters:

**Kael** (fire mage):
- Flame Lance grants: `generation`, `force`, `projection` (effect: `fire`,
  `concussive`, `light`)
- Inner Furnace grants: `barrier`, `endurance` (effect: `fire`, `heat`)
- Trait-derived: `force` (from Strength)

**Lyra** (shadow mage):
- Shadow Step grants: `traversal` (prereq: `shadows_present`, effect: `shadow`)
- Veil Sight grants: `perception` (prereq: `shadows_present`, effect:
  `shadow`, `arcane`)
- Shadow Grasp grants: `manipulation`, `projection` (effect: `shadow`)
- Trait-derived: `perception` (from Perception), `precision` (from Agility)

**Dren** (martial / protector):
- Sanctified Strike grants: `force`, `suppression` (effect: `holy`)
- Blessed Shield (equipment) grants: `barrier` (effect: `holy`)
- Trait-derived: `force` (from very high Strength), `endurance` (from Stamina)

**What Kael sees for "The Flood" Challenge:**
- "Evaporate (Flame Lance)" — `generation` + `flooding`. Side effect:
  `light` effect Property may resolve "The Darkness" too.
- "Drain (Flame Lance)" — `force` + `flooding`. Blast the floor open.
- "Drain (Raw Strength)" — `force` + `flooding`. Physically force a drain.
- "Contain (Inner Furnace)" — `barrier` + `flooding`. Hold back the water.

**What Lyra sees for "The Darkness" Challenge:**
- "Navigate (Shadow Step)" — `traversal` + `dark`. Prereq `shadows_present`
  is satisfied because the room IS dark.

**What Dren sees for "The Curse" Challenge:**
- "Cleanse (Sanctified Strike)" — `suppression` + `cursed`. Holy effect.
- "Shield (Blessed Shield)" — `barrier` + `cursed`. Protect the party.

**Emergent interaction:** If Kael uses Flame Lance (which carries `light`)
to evaporate the flood, the room is no longer `dark` — removing
`shadows_present`, which disables Lyra's Shadow Step and Veil Sight.
Nobody designed this tension. It emerged from Properties and prerequisites.

### Cooperative Actions

When multiple characters can address the same Challenge through the same
Application, the system surfaces a **cooperative Action**. Characters see
both their solo option and the cooperative version:

- "Drain (Flame Lance)" — solo, Kael's `force`: 15 vs difficulty 30 *(hard)*
- "Drain — cooperate with Dren" — combined. Each participant rolls
  independently. All succeed = great outcome; mixed = partial; all fail =
  disaster.

**Cooperative Actions are a core design goal.** The game emphasizes party
coordination. Boss encounters require combined efforts. Diverse Capability
compositions make teams strategically stronger than individuals.

How cooperative resolution works:
1. One character initiates an Action on a Challenge
2. Other characters with the same Application available can join
3. Each participant rolls their own check (their own check type from their
   own delivery mechanism)
4. Results are combined — more successes = better combined outcome
5. Custom narrative describes each participant's contribution

This means Kael blasting the floor with fire, Dren smashing it with holy
force, and Lyra pulling at fractures with shadow all contribute to
"Drain" — each rolling independently, each with their own dramatic moment.

### GM Workflow

GMs are responsible for **setting the stage**, never for game-designing on
the fly. The workflow is:

1. GM picks a Situation preset or creates one from Challenge building blocks
2. GM optionally adjusts severity on individual Challenges
3. The system evaluates character Capabilities against Challenge Properties
   via the global Application table
4. Each character sees personalized Actions per Challenge, including
   cooperative opportunities
5. Players choose and the system resolves

**GMs should not need to think about "what can players do."** The system
handles that. If a player has a Capability that should logically apply but
no option appears, that's feedback for the system designers to add an
Application or Property — not something the GM patches at the table.

**Property presets** reduce GM burden. Common Challenges ("locked door",
"magical barrier", "poison gas", "collapsing ceiling") come as templates
with pre-tagged Properties. Situations compose multiple Challenge templates
into coherent scenes.

---

## The Interaction Pipeline

When Capabilities meet Properties in Challenges, the system resolves what
Actions are available through a consistent pipeline:

```
1. IDENTIFY active Challenges in the room
   - Each Challenge has its own Properties
   - Check dependency gates (is this Challenge revealed yet?)

2. FOR EACH Challenge, FOR EACH character:
   a. CHECK AVAILABILITY of Capabilities
      - For each Capability source (Technique, trait, equipment):
        - Does this source grant a relevant Capability?
        - Are source-level prerequisites met?
        - Are Capability-level prerequisites met?
        - Can the character afford activation cost (anima)?

   b. MATCH available Capabilities to Applications
      - For each Challenge Property, find Applications where the
        character has an available Capability from this source
      - Evaluate the source's Capability value against the Challenge's
        severity-scaled difficulty
      - Filter: if impossible-tier, hide the option

   c. GENERATE Actions
      - Each source × Application = one Action
      - Same Application from different sources = different Actions
      - Include delivery mechanism info (check type, cost, narrative)

3. IDENTIFY cooperative opportunities
   - Where multiple characters have Actions for the same Application
     on the same Challenge, surface a cooperative Action option
   - Players see both solo and cooperative versions

4. PRESENT Actions to each character
   - Grouped by Challenge
   - Show difficulty indicator per source
   - Show cooperative options with participating characters
   - Use custom narrative from ChallengeApproach if authored

5. RESOLVE
   - Solo: single check (source's check type, severity-scaled difficulty)
   - Cooperative: each participant rolls independently with their own
     check type; results combine for better/worse outcomes
   - Weighted consequence selection from the Challenge's consequence table
   - ApproachConsequence overrides for custom narrative per approach

6. APPLY outcomes
   - Resolution type: DESTROY, PERSONAL, or TEMPORARY
   - Side effects: Technique effect Properties may resolve other
     Challenges (light from fire resolves darkness)
   - Dependency unlocks: resolved Challenges may reveal new ones
   - Outcomes composed from Outcome Primitives, not hardcoded
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
magic in combat.

### What Uses This System

- Environmental Challenges: flooding room + `generation`, darkness +
  `traversal`, oil slick + `generation`
- Situational advantages: high ground + `traversal`, cover + `projection`
- Novel Applications: using ice magic to freeze a flooded floor, using
  `force` to collapse terrain on enemies
- Boss Properties: `armored`, `warded`, `regenerating` — these function like
  Challenge Properties that must be addressed through Capabilities

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

**The Attempt system** (`src/world/attempts/`) was speculative infrastructure
for check resolution with weighted narrative consequences. It had no callers
outside its own app and has been removed. Its useful patterns (weighted
consequence selection per tier, character loss protection) were absorbed into
the Challenge consequence system.

### What's Not Built

- **Technique Capability grants** — no model for Techniques declaring what
  Capabilities they provide, with what constraints (see "Technique
  Capability Grants" in Implementation Decisions below)
- **Shared Property model** — ObstacleProperty exists but is isolated to
  obstacles; needs generalization into `mechanics.Property` (see
  "Property Model" in Implementation Decisions below)
- **Application model** — no model for globally-defined Applications
  connecting Capabilities to Properties (see "Application Model" in
  Implementation Decisions below)
- **Situation model** — no generalized model for presenting challenges with
  Properties and generating Actions from Capabilities (see "Situation
  Model" in Implementation Decisions below)
- **Trait-derived Capabilities** — no calculation pipeline from trait values
  to Capability values
- **Damage-dealing pipeline** — no service to deal typed damage and call
  the existing interaction/resistance systems

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

- **DamageType** is independent from Properties. DamageType describes what
  an attack DOES (output); Properties describe what a target IS (input).
  They share thematic vocabulary (fire/cold/shadow) but are different
  concepts operating at different pipeline stages. Damage math stays in the
  Condition/DamageType system; Properties drive emergent Action options.
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

3. **Capabilities are atomic primitives.** Single verbs — `generation`,
   `force`, `traversal`, `perception`. No compound names. The noun part
   (fire, shadow) belongs on the source as effect Properties. ~10-15 total.

4. **Capabilities are per-source.** Each source of a Capability produces
   a separate Action. Sources only stack when explicitly designed to
   combine (buff Techniques, stat modifiers). Floor at 0 per source.

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

8. **Challenges are the atomic unit.** Each discrete problem has its own
   Properties, severity, and resolution. Situations compose Challenges.
   Obstacles are a type of Challenge.

9. **Outcomes are goals, not mechanics.** The Application declares eligibility.
   The Situation determines what success means (bypass, progression, damage,
   narrative). Mechanical effects are composed from primitives.

10. **Most Capabilities are derived.** Trait values derive into Capabilities.
    Only unusual or granted Capabilities need explicit storage.

11. **Party coordination is mandatory for bosses.** Boss encounters require
    combo attacks from multiple characters. Solo damage should be ineffective
    against boss defenses.

12. **Data entry must scale.** Properties (~30-50), Capabilities (~10-15), and
    Applications (~40-60) are small vocabularies authored once. Challenges
    are composed from these building blocks; Situations compose Challenges.
    Hundreds to low thousands of authored Challenges is acceptable if each
    is a few fields of data, not custom code.

14. **Cooperative play is a core goal.** The system should surface cooperative
    Actions when multiple characters can address the same Challenge. Party
    coordination should feel rewarding and strategically important.

15. **"Yes, but..." over "No."** Control failure, resource depletion, and
    difficult odds should produce dramatic consequences, not prevent action.
    Fizzled effects are anticlimactic. Consequences escalate drama.

13. **No hardcoded results.** Outcomes are composed from mechanical primitives
    with templated narrative. Important moments get custom text. No Situation
    should require custom code to resolve.

---

## Implementation Decisions

Decisions made during brainstorming, recorded for implementors.

### Property Model — DECIDED

**Location:** `world/mechanics` (alongside other cross-cutting game mechanics).

**`Property`** (SharedMemoryModel):
- `name` (CharField, unique) — e.g., "flammable", "solid", "dark", "clawed",
  "bestial", "tall", "metallic"
- `description` (TextField)
- `category` FK to `PropertyCategory`
- ~30-50 total, authored once

**`PropertyCategory`** (SharedMemoryModel):
- `name` (CharField, unique) — e.g., "material", "environmental",
  "elemental", "structural", "biological"
- `description` (TextField)
- `display_order` (PositiveIntegerField)

**ObstacleProperty replacement:** `ObstacleTemplate.properties` M2M and
`BypassOption.obstacle_property` FK both point to `mechanics.Property`
instead. Regenerate obstacle migrations cleanly (use fake-migrate to zero,
then regenerate).

**ConditionTemplate gets M2M to Property:** Enables Conditions to carry
Properties (werewolf battleform grants "clawed", "bestial", "large").

**DamageType stays independent.** No FK between DamageType and Property.
They share thematic vocabulary but operate at different pipeline stages
(damage math vs. emergent Action options).

### Application Model — DECIDED

**Location:** `world/mechanics`.

**`Application`** (SharedMemoryModel):
- `name` (CharField) — "Burn", "Illuminate", "Fly Over", "Douse", "Drain"
- `capability` FK to `CapabilityType`
- `target_property` FK to `Property` — what the Challenge must have
- `required_effect_property` FK to `Property` (nullable) — what the
  source's effect must carry. Null means any source of this Capability
  qualifies. Used for medium-specific Applications like "Fly Over"
  requiring `aerial` effect Property.
- `description` (TextField) — default narrative for the interaction
- Unique constraint on (`capability`, `target_property`, `name`)
- ~40-60 total, authored once

**The effect Property filter solves the "flight problem."** Atomic
Capabilities like `traversal` cover many mechanisms (flying, phasing,
swimming, shadow-stepping). The `required_effect_property` on the
Application distinguishes them:

| Application | Capability | Target Property | Required Effect |
|---|---|---|---|
| Fly Over | `traversal` | `tall` | `aerial` |
| Phase Through | `traversal` | `solid` | `incorporeal` |
| Navigate Dark | `traversal` | `dark` | `shadow` |
| Swim Through | `traversal` | `flooding` | `aquatic` |
| Drain | `force` | `flooding` | *(none)* |
| Illuminate | `generation` | `dark` | *(none)* |

Applications with no required effect are broadly accessible — anyone with
`force` can attempt "Drain." Applications with a required effect need a
specific kind of source.

**Applications are pure eligibility.** No difficulty, no check type, no
minimum Capability value. Difficulty comes from the Challenge; check type
comes from the delivery mechanism.

**Relationship to BypassOption:** BypassOption is replaced by
ChallengeApproach when the Challenge system is built. See "Situation
and Challenge Models" below.

### Capability Constraints — DECIDED

Constraints on Capability grants (e.g., "shadow teleportation requires
shadows") are **prerequisite checks**, not Property FKs. A prerequisite
check is a registered callable that can query any combination of:

- Static Properties on the target/location
- Active Conditions on characters/objects
- World state (gametime, weather, recent events)

This avoids forcing dynamic state into the Property model. The constraint
on a Technique grant says "check: shadows_available" and the registered
function checks room Properties, active Conditions, AND time of day.

Implementation details (model shape for prerequisite registrations, where
the registry lives) are deferred to implementation time.

Prerequisites exist at two levels:

- **Capability-level** — inherent to the Capability itself. Shadow control
  always requires shadows, regardless of source. Stored on `CapabilityType`
  as `prerequisite` (FK to `PrerequisiteType`).
- **Grant-level** — specific to the mechanism providing it. Giant wings need
  open space; wind magic flight does not. Stored on the grant model (e.g.,
  `TechniqueCapabilityGrant.prerequisite` FK to `PrerequisiteType`).

Both must pass for the Capability to be available.

### Technique Capability Grants — DECIDED

**Location:** `world/magic`.

**`TechniqueCapabilityGrant`**:
- `technique` FK to `Technique`
- `capability` FK to `CapabilityType`
- `base_value` (integer, default 0) — flat Capability contribution
- `intensity_multiplier` (DecimalField, default 0) — multiplied by
  Technique's current intensity
- `prerequisite` (FK to `PrerequisiteType`, nullable) — source-specific constraint

**Effective value** = `base_value + (intensity_multiplier * technique.intensity)`

This two-component formula supports:
- Purely flat grants: `base_value=10, intensity_multiplier=0` → always 10
- Purely scaling grants: `base_value=0, intensity_multiplier=1.5` → scales
  with intensity
- Mixed: `base_value=5, intensity_multiplier=1.0` → baseline 5, grows with
  intensity

**Control is not part of the value calculation.** Control governs execution
risk — when a Technique is used and intensity exceeds control, effects
become unpredictable with harmful side effects. This is a check at the
point of Technique activation, not at the Capability calculation layer.
Not all Capabilities come from Techniques, so control is irrelevant to
the Capability system.

**EffectType is unchanged.** EffectType is a categorization label for
Techniques (Attack, Defense, Movement). Capability grants are a separate
concern that EffectType was never designed to carry. EffectType may prove
useful for UI grouping or filtering; if it turns out to be dead weight, it
can be removed later.

**Other Capability sources** use the same additive pattern but their own
grant models:
- **Conditions** — `ConditionCapabilityEffect` (already built, flat value)
- **Traits** — calculated at query time, not stored (see open question)
- **Species, Equipment, Distinctions** — future, same pattern

`get_capability_sources()` returns per-source Capability values (not
aggregated) so the pipeline can generate separate Actions per source.
Stacking only happens when sources are explicitly designed to combine
(buff Techniques modifying trait values, stat modifiers from Distinctions).
Each source value floors at 0.

### Situation and Challenge Models — DECIDED

**Location:** `world/mechanics` (cross-cutting game mechanic).

The Situation/Challenge system is the generalized interaction model. It
absorbed the obstacle system and the former `world/attempts` app into a
unified design with two layers: Situations (narrative framing, grouping)
and Challenges (atomic problems with Properties and resolution).

**Key principle:** All game activities take place on the grid, in rooms.
Challenges always attach to a room (ObjectDB). Multi-room events create
separate instances in each room.

#### Absorbing Existing Systems

**The `world/attempts` app** (`AttemptTemplate`, `AttemptConsequence`,
`resolve_attempt()`) was speculative infrastructure with no callers
outside its own app. Its patterns (weighted consequence selection,
character loss protection) have been absorbed into Challenge resolution.
The app has been removed.

**The `world/obstacles` app** is a working but specialized implementation
of the Challenge concept. Obstacles are Challenges that inhibit actions.
The obstacle models should be refactored into the Challenge system:

- `ObstacleTemplate` → `ChallengeTemplate`
- `ObstacleProperty` → replaced by shared `Property` (already decided)
- `BypassOption` → `ChallengeApproach` (Application + check + consequences)
- `ObstacleInstance` → `ChallengeInstance`

The underlying check infrastructure (`perform_check()` in `world/checks`,
`CheckOutcome` tiers in `world/traits`) stays unchanged.

#### Models

**`ChallengeCategory`** (SharedMemoryModel):
- `name` (CharField, unique) — "environmental", "combat", "narrative",
  "mission", "structural"
- `description` (TextField)
- `display_order` (PositiveIntegerField)

**`ChallengeTemplate`** (SharedMemoryModel):
- `name` (CharField, unique) — "Cursed Flood", "Sealed Chamber", "Darkness"
- `description_template` (TextField) — narrative with `{variables}`
- `properties` M2M to `Property`
- `severity` (PositiveIntegerField, default=1) — scales all check
  difficulties
- `goal` (TextField) — what characters are trying to achieve
- `category` FK to `ChallengeCategory`
- `challenge_type` (CharField) — INHIBITOR (blocks actions) or THREAT
  (actively causes harm)
- `blocked_capability` FK to `CapabilityType` (nullable) — for inhibitors:
  what Capability is blocked while this Challenge is active (from obstacles)
- `discovery_type` (CharField) — OBVIOUS or DISCOVERABLE (from obstacles)

**`ChallengeConsequence`** — default outcomes per tier:
- `challenge_template` FK to `ChallengeTemplate`
- `outcome_tier` FK to `CheckOutcome`
- `label` (CharField) — default narrative ("The water drains away")
- `mechanical_description` (TextField) — what happens mechanically
- `weight` (PositiveIntegerField) — probability weight within tier
- `resolution_type` (CharField) — DESTROY / PERSONAL / TEMPORARY
- `resolution_duration_rounds` (PositiveIntegerField, nullable)
- `character_loss` (BooleanField, default=False)

**`ChallengeApproach`** — an Application paired with this Challenge:
- `challenge_template` FK to `ChallengeTemplate`
- `application` FK to `Application`
- `check_type` FK to `CheckType` — what check this approach uses
- `required_effect_property` FK to `Property` (nullable) — Challenge-specific
  constraint on top of whatever the Application requires. E.g., a spectral
  flood's Drain approach requires `holy` or `arcane` effect Properties even
  though the generic "Drain" Application has no effect requirement.
- `display_name` (CharField, nullable) — override Action name
- `custom_description` (TextField, nullable) — pre-choice description

**`ApproachConsequence`** — optional per-approach overrides:
- `approach` FK to `ChallengeApproach`
- `outcome_tier` FK to `CheckOutcome`
- `label` (CharField) — custom narrative for this approach + tier
- `mechanical_description` (TextField, nullable) — null = use default
- `weight` (PositiveIntegerField, nullable) — null = use default
- `resolution_type` (CharField, nullable) — null = use default. Allows
  per-approach differences (burning an ice wall = DESTROY; flying over
  = PERSONAL bypass)

**`SituationTemplate`** (SharedMemoryModel):
- `name` (CharField, unique) — "Rising Cursed Flood", "Collapsing Mine"
- `description_template` (TextField) — narrative framing
- `challenges` M2M to `ChallengeTemplate` (with through model for
  ordering and dependencies)
- `category` FK to `ChallengeCategory`

**`SituationChallengeLink`** — through model for Situation → Challenge M2M:
- `situation_template` FK
- `challenge_template` FK
- `display_order` (PositiveIntegerField)
- `depends_on` FK to self (nullable) — this Challenge is hidden until
  the linked Challenge is resolved (e.g., curse anchor hidden until
  flood is drained)

**`SituationInstance`** — a Situation placed in the world:
- `template` FK to `SituationTemplate`
- `location` FK to `ObjectDB` — the room
- `template_variables` (JSONField, default=dict)
- `is_active` (BooleanField, default=True)
- `created_by` FK to Account (nullable) — which GM created this
- `scene` FK to `Scene` (nullable) — ties to a specific scene

**`ChallengeInstance`** — tracks per-Challenge state within a Situation:
- `situation_instance` FK to `SituationInstance` (nullable — standalone
  Challenges don't need a parent Situation)
- `template` FK to `ChallengeTemplate`
- `location` FK to `ObjectDB` — the room
- `is_active` (BooleanField, default=True)
- `is_revealed` (BooleanField, default=True) — false if dependency unmet

**`CharacterChallengeRecord`** — tracks per-character resolution:
- `character` FK to `ObjectDB`
- `challenge_instance` FK to `ChallengeInstance`
- `approach` FK to `ChallengeApproach`
- `resolved_at` (DateTimeField)

#### Resolution Flow

1. Query active ChallengeInstances in the room (standalone + from
   active SituationInstances)
2. For each revealed Challenge, for each character:
   a. For each Capability source, check prerequisites and match against
      the Challenge's Properties via Application table
   b. Each source × Application = one potential Action
   c. Filter by source's Capability value vs severity-scaled difficulty
3. Identify cooperative opportunities (same Application on same Challenge
   available to multiple characters)
4. Present Actions grouped by Challenge, including cooperative options
5. Resolve: solo = single check; cooperative = each participant rolls
   independently, results combine
6. Weighted consequence selection with approach-level overrides
7. Apply resolution: DESTROY/PERSONAL/TEMPORARY
8. Check for side effects (Technique effect Properties may resolve
   other Challenges), update dependency reveals

#### Cooperative Resolution

When multiple characters can address the same Challenge through the same
Application, the system surfaces cooperative Actions. Each participant
rolls their own check using their own delivery mechanism's check type.
Results combine:

- All succeed → best outcome tier
- Mixed → intermediate outcome
- All fail → worst outcome

This is automated — once participants agree to cooperate, all rolls
happen simultaneously. Each character gets their dramatic moment in the
resolution narrative.

**Cooperative Actions are a core design goal.** The game emphasizes party
coordination. Diverse Capability compositions make teams stronger.

#### Authoring Experience

**Challenges** are the building blocks. Authors create ChallengeTemplates,
tag Properties, set severity, write default consequences, then add
approaches with custom narrative per approach. The fun part: "What happens
when someone uses holy suppression to cleanse this curse? What about when
someone tries to barrier against it?"

**Situations** compose Challenges. Authors create SituationTemplates that
group multiple ChallengeTemplates with dependencies. "Rising Cursed Flood"
= The Flood + The Curse + The Sealed Chamber + The Darkness, with the
curse anchor depending on the flood being resolved.

**Always customizable, never required.** Custom narrative per approach is
the thing authors WANT to write. Sensible defaults always work as fallback.

**Standalone Challenges work too.** A locked door doesn't need a Situation
wrapper — it's just a ChallengeInstance placed on an exit.

### Trait-Derived Capabilities — PROPOSED

**Location:** `world/mechanics` (alongside other Capability infrastructure).

Traits derive into Capabilities using the same two-component formula as
Technique grants. A lookup model maps traits to the Capabilities they
contribute to:

**`TraitCapabilityDerivation`** (SharedMemoryModel):
- `trait` FK to `Trait`
- `capability` FK to `CapabilityType`
- `base_value` (integer, default 0) — flat contribution
- `trait_multiplier` (DecimalField, default 0) — multiplied by the
  character's trait value (internal scale, 1-100)

**Effective value** = `base_value + (trait_multiplier * trait_value)`

Examples:
- Strength → `force`: `base_value=0, trait_multiplier=0.5`
  (strength 50 → force 25)
- Agility → `precision`: `base_value=0, trait_multiplier=0.3`
  (agility 70 → precision 21)
- Perception → `perception`: `base_value=5, trait_multiplier=0.2`
  (perception 40 → perception 13)

A single trait can derive into multiple Capabilities (agility → `precision`
AND `traversal`). A single Capability can have contributions from multiple
traits (`force` from strength AND stamina with different multipliers).

**Calculation happens at query time, not stored.** Trait-derived Capability
values are calculated when queried. Each trait derivation produces a
separate Capability source — "force from Strength" is a distinct Action
path from "force from Flame Lance." They don't aggregate unless explicitly
designed to stack (e.g., a buff Technique modifies the trait value itself).

**Why not PointConversionRange?** The existing `PointConversionRange`
provides non-linear curves for check point calculation. That complexity
may not be needed for Capability derivation — a simple linear multiplier
keeps the system predictable and the values easy to reason about. If
non-linear derivation proves necessary later, the model can be extended
with min/max ranges, but start simple.

**Status:** Proposed, not yet confirmed with project lead. The formula
shape matches TechniqueCapabilityGrant (consistent pattern), but the
specific multiplier values and trait-to-Capability mappings need design
input.

### Availability and Control — PROPOSED

The two-check pattern (Availability → Application Attempt) resolves as:

**Availability** is mostly gatekeeping, not a check:
1. Does the character have the Capability? (aggregation > 0)
2. Are prerequisites met? (Capability-level + source-level)
3. Can the character afford the cost? (anima for Techniques)
4. Is the mechanism accessible? (equipment wielded, etc.)

If all gates pass, the Capability is available. No dice roll for
availability in most cases.

**Control risk** is separate from availability. When a Technique is
activated and intensity > control, a control check determines side
effects. The Technique still fires — control governs safety, not whether
you can act. This creates the dramatic tension: you CAN push beyond your
control, but bad things might happen.

Control checks only apply to Techniques (the mechanism with
intensity/control stats). Trait-derived Capabilities, species innates,
and equipment have no control risk — they're always safe to use.

**The Application Attempt** is the main resolution — `perform_check()`
with check type from the delivery mechanism and difficulty from the
Challenge's severity. This is where the ChallengeConsequence /
ApproachConsequence system kicks in.

**Control never prevents activation.** A fizzled Technique is anticlimactic
— unsatisfying when real stakes are on the line. The Technique always fires;
control failure means dangerous, dramatic side effects. This is a core
design principle: the game favors "yes, but..." over "no." Consequences
should escalate drama, not deflate it.

---

## Open Questions

These need implementation exploration or project lead input to resolve:

1. **GM override mechanism:** How do GM-created bespoke options get flagged
   and reviewed? What's the UI for this? (Low priority — can be designed
   when the GM tooling is built.)

2. **Baseline human Capabilities:** Walking, climbing, swimming at basic
   levels are assumed without requiring explicit records. How are these
   represented? Options: a) hardcoded defaults in the aggregation service,
   b) a "baseline" pseudo-source that contributes values, c) just create
   TraitCapabilityDerivation rows for common traits. Option (c) is simplest
   and most consistent.

3. **Cooperative resolution details:** How exactly do multiple independent
   rolls combine into a cooperative outcome? Simple options: count
   successes, average tiers, or use best/worst with modifiers from
   additional participants. Needs playtesting to feel right.

4. **Side effect resolution:** When a Technique's effect Properties
   interact with other Challenges (fire + light resolves darkness), is
   this automatic or does it require a separate Action? If automatic,
   how does the system detect and apply it?

5. **Challenge threat mechanics:** For THREAT-type Challenges (cursed
   water dealing damage), how does ongoing harm work? Tick damage per
   round? Escalating severity? This likely ties into the combat/round
   system which isn't designed yet.

---

## Future Integration Notes

### Missions

Situations are the natural building block for Mission stages. A Mission
stage can require resolving a Situation — the party arrives at a location,
faces the Situation's Challenges, and completing them advances the Mission.

This means the same authoring tools, resolution flows, and cooperative
mechanics apply to both ad-hoc GM encounters and structured Mission
content. No separate "mission encounter" system needed.

### SituationBuilder Tooling

The Challenge/Situation system has enough moving parts (Properties,
ChallengeApproaches, consequences, dependencies, required effect
Properties) that a guided authoring UI will eventually be needed.
A SituationBuilder should:

- Walk authors through creating ChallengeTemplates step by step
- Show which Applications will match based on tagged Properties
- Preview the Action menu players would see
- Let authors compose Challenges into Situations with dependency graphs
- Provide templates for common patterns (locked door, environmental
  hazard, magical barrier, social obstacle)

This is a tooling concern, not an architecture concern — the data model
supports it already. Build it when GM tooling is prioritized.
