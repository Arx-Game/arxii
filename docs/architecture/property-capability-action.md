# Properties, Capabilities, and Actions

> The foundational interaction model for Arx II. This document describes how
> characters interact with the game world through three layers: what things
> ARE (properties), what characters CAN DO (capabilities), and what becomes
> AVAILABLE (actions). Every system that involves characters interacting with
> objects, creatures, or each other should follow this pattern.

---

## The Three Layers

### Properties: What Things Are

A **property** is a neutral, descriptive fact about something in the game
world. Properties don't imply good or bad — they describe qualities.

- "This door is wooden."
- "This creature is abyssal."
- "This barrier is made of shadow."
- "This attack carries fire."
- "This armor is metallic."
- "This room contains water."

Properties attach to anything: obstacles, creatures (via species), attacks
(via techniques), equipment, conditions, rooms, weather. They are the shared
vocabulary that connects all game systems.

**Properties are not capabilities.** A wooden door IS wooden — that's a
property. A character who CAN command wood — that's a capability. The door
doesn't "do" anything by being wooden. The character does something because
they have a capability that's relevant to the door's property.

**Environment properties** matter too. A room might have the `water` property
because it contains a lake. A character with water-control techniques gains
additional action options when water is present — the environment is a
precondition for certain capabilities to be useful.

### Capabilities: What Characters Can Do

A **capability** is something a character can do, with a graduated value
representing how well they can do it.

- "Can generate fire (value: 15)"
- "Can fly (value: 5)"
- "Can command wood (value: 8)"
- "Can perceive the supernatural (value: 3)"

Capabilities are NOT binary. A value of 0 means effectively unable. Higher
values beat higher thresholds. "Impossible" just means a very high requirement.
Floor is always 0 — negative modifiers reduce but never go below zero.

#### Where Capabilities Come From

Most capabilities are **derived**, not stored:

- **Traits** — strength derives into physical force, lifting capability,
  melee impact. Dexterity derives into precision, evasion, acrobatics. These
  are NOT stored as separate `CapabilityType` records — they're calculated
  from the trait values a character already has.
- **Baseline human abilities** — walking, climbing, swimming at basic levels.
  These don't need records. A condition can remove them (paralysis removes
  movement), but the default is assumed.

Some capabilities are **explicitly granted** by sources:

- **Conditions** — active status effects that grant or modify capabilities
  (currently the only implemented source via `ConditionCapabilityEffect`)
- **Techniques** — activated magical abilities that grant capabilities when
  used (not yet built; see "Techniques as Actions" below)
- **Distinctions** — character traits that grant innate capabilities
  (not yet built; blocked by EffectBundle pattern)
- **Species** — inherent racial capabilities (not yet built)
- **Equipment** — items that grant capabilities when worn/wielded
  (not yet built)

**Capability aggregation:** All sources contribute positive or negative
values additively. Total floors at 0. No percentage modifiers, no
multiplication, no caps.

**Avoid capability proliferation.** Keep capabilities generic enough that
one capability covers a concept. Don't have a dozen ways to say "move fast"
that all need to match the same properties. If `physical_force` covers
punching, lifting, and breaking, that's better than three separate
capabilities.

### Actions: What Becomes Available

When a character has capabilities relevant to a target's or environment's
properties, **actions become visible**. This is the interaction engine — the
game doesn't hardcode "Fireball can destroy Wooden Door." Instead:

1. The door has the `flammable` property
2. A bypass option exists: things with `flammable` can be burned through,
   requiring `fire_generation` capability and an Arcane Control check
3. The character has a fire technique active, contributing `fire_generation`
   capability — the option appears with its difficulty rank vs. the
   character's capability value
4. The player chooses "Burn Through" and the check resolves success or
   failure, with consequences for either outcome

**Capability is not a hard gate.** If a character has any relevant capability,
the action appears as an option. The system shows how the difficulty compares
to their capability value — a tough action is visible but marked as unlikely
to succeed. The actual capability value may vary at resolution time based on
check results, intensity, and other factors. Players make informed choices
about risk, and both success and failure produce meaningful outcomes.

The same principle applies everywhere:
- **Obstacle bypasses:** obstacle properties + character capabilities →
  bypass options with difficulty indicators (already built)
- **Combat interactions:** attack properties + target properties → combo
  effects (not yet built)
- **Utility actions:** environment properties + character capabilities →
  novel interactions (not yet built)

---

## Techniques as Actions

A **technique** is always an action, or a set of actions, that a character
can take using their magical Gift. This is a fundamental distinction from
other capability sources:

- A **distinction** is a passive effect bundle on a character — it modifies
  what they are and what they can do, but it doesn't DO anything itself.
- A **technique** is active — it's a specific way to USE a Gift. It grants
  the character new actions or modifies existing ones.

A Gift like "Shadow Magic" is broad and abstract. Techniques make it real:
- Forming a barrier of shadows (defensive action)
- Launching a blast of shadows (offensive action)
- Stepping through shadows to teleport (movement action)
- Forming a sword of shadows to wield (equipment-enhancing action)

**Gift resonances are metaphysical associations, not mechanical identity.**
A "Shadow Magic" gift doesn't mean all its techniques deal shadow damage.
A shadow technique might create physical barriers, enhance stealth, enable
teleportation, or form weapons. The resonance describes the magical source,
not the mechanical outcome.

**Techniques grant capabilities when activated.** A werewolf's "Assume
Battleform" technique might grant increased physical force, regeneration,
and a supernatural fear howl — multiple capabilities from a single technique.
These capabilities then interact with properties on targets and in the
environment to generate available actions through the normal pipeline.

**Techniques carry properties on their effects.** When a shadow spear hits
something, the attack carries properties — maybe `shadow` and `piercing`.
These aren't stored as a single `damage_type` FK on the technique, because
a technique can produce varied effects with multiple properties. The
properties live on the actions the technique enables.

### Current State of Techniques

`src/world/magic/models.py` — Technique has:
- `gift` FK, `style` FK (TechniqueStyle), `effect_type` FK (EffectType)
- `intensity` (power), `control` (precision), `anima_cost` (resource cost)
- `level` (gates progression, derives tier)
- `restrictions` M2M (limitations that grant power bonuses)

What Technique currently lacks is any connection to the action system — no
way to declare what actions it enables, what capabilities it grants when
activated, or what properties its effects carry. Building this connection
is the path forward, not decorating Technique with type fields.

Cantrip (`src/world/magic/models.py:1451`) is a staff-curated technique
template for character creation. It will be collapsed into Technique.

---

## How This Maps to Current Code

### What's Built

**The obstacle/bypass system** is the first and only implementation of this
pattern. It demonstrates the full flow:

```
ObstacleTemplate (has properties via M2M)
  └── ObstacleProperty (e.g., "tall", "solid", "ice")
        └── BypassOption (e.g., "Fly Over", "Climb", "Melt")
              ├── BypassCapabilityRequirement (capability + minimum_value)
              └── BypassCheckRequirement (check type + base difficulty)
```

**Key files:**
- `src/world/obstacles/models.py` — property/bypass/requirement models
- `src/world/obstacles/services.py` — resolution flow
- `src/world/conditions/models.py:60-77` — CapabilityType definition
- `src/world/conditions/services.py:577-689` — capability value aggregation
- `src/actions/definitions/movement.py:147-217` — TraverseExitAction calling
  into obstacle services

**How bypass resolution works:**
1. `get_obstacles_for_object(exit, character)` finds active obstacles
2. `get_all_capability_values(character)` aggregates capabilities from
   conditions (currently the only source)
3. `get_bypass_options_for_character(obstacle, character, capabilities)`
   matches obstacle properties → bypass options → capability requirements
4. Options shown to player with difficulty context vs. capability values
5. `attempt_bypass()` runs the check and resolves the outcome

**Capability resolution** (`src/world/conditions/services.py`):
- `get_capability_value(target, capability_type)` — single capability lookup
- `get_all_capability_values(target)` — bulk lookup returning dict[str, int]
- `get_capability_status(target, capability_type)` — value with source breakdown
- Currently aggregates ONLY from `ConditionCapabilityEffect` rows on active
  conditions. Future sources (distinctions, species, equipment, techniques)
  will be added as the EffectBundle pattern enables them.

### What's Partially Built

**The action enhancement system** provides the mechanism for techniques to
modify actions, but techniques cannot yet contribute capabilities:

- `ActionEnhancement` model links sources (technique, distinction, condition)
  to base actions via explicit FKs
- Effect configs (`ModifyKwargsConfig`, `AddModifierConfig`,
  `ConditionOnCheckConfig`) define what enhancements DO
- Voluntary technique enhancements work (tested in
  `src/actions/tests/test_enhancements.py`)
- Involuntary technique enhancements silently fail because `Technique` does
  not implement `should_apply_enhancement()`

**Key files:**
- `src/actions/models/enhancement.py` — ActionEnhancement with source FKs
- `src/actions/models/effect_configs.py` — typed effect config models
- `src/actions/effects/` — handler dispatch system
- `src/actions/base.py` — Action.run() lifecycle

**The condition interaction system** provides combo rules between conditions
and damage types, but has no callers:

- `ConditionDamageInteraction` defines: "Frozen + Force damage = +50% damage,
  removes Frozen" — this IS a combo rule
- `process_damage_interactions()` is fully implemented and tested
- No action or service function calls it because no damage-dealing pipeline
  exists yet

**Key files:**
- `src/world/conditions/models.py:625-690` — ConditionDamageInteraction
- `src/world/conditions/services.py:509-569` — process_damage_interactions()

### What's Not Built

**Technique-to-action connection:** Techniques have stats (intensity, control,
anima_cost) but no way to define what actions they enable or what capabilities
they grant when activated. The action infrastructure exists (`Action` base
class, enhancement system, prerequisite system) but techniques don't plug
into it yet.

**Shared property model:** No shared property model exists. `ObstacleProperty`
is the right pattern but is isolated — only obstacles use it. Properties need
to be a cross-cutting concept that attaches to obstacles, techniques (via
their actions), creatures, items, conditions, rooms, and more.

**Multiple capability sources:** Only conditions feed capability values.
Techniques, distinctions, species, and equipment should all contribute but
don't yet. This is blocked by the EffectBundle pattern (see
`src/world/mechanics/TECH_DEBT.md`, item #3).

**Trait-derived capabilities:** No mechanism exists to derive capabilities
from trait values (e.g., high Strength → high `physical_force` capability).
This should be a calculation, not stored records.

**Damage-dealing pipeline:** No "deal X damage of type Y to target Z" service
exists. This would call the existing (but unused)
`process_damage_interactions()` and `get_resistance_modifier()`.

**Combat actions:** No Attack, Defend, or UseAbility action definitions exist.
The action infrastructure is ready but no combat-specific actions have been
defined.

---

## Properties vs. Capabilities: The Distinction

These are separate concepts that work together. Confusing them leads to
architectural sprawl.

**Properties** describe qualities of things. They're neutral descriptive
tags. A wooden door IS wooden. A fire spell IS fire-typed. An abyssal
creature IS abyssal. Properties don't do anything on their own.

**Capabilities** describe what characters can actively DO, with graduated
values. A character CAN generate fire at level 12. A character CAN fly at
level 5. A character CAN command wood at level 8. Capabilities come from
sources and are aggregated.

**The connection:** Properties on targets and environments determine what
capabilities are RELEVANT. The `flammable` property on a door makes
`fire_generation` capability relevant. The `armored` property on a boss
makes `armor_piercing` capability relevant. The `water` property on a room
makes `water_control` capability relevant. Without the matching property,
the capability exists but has no target to act on.

This mirrors the obstacle system exactly:
- `ObstacleProperty` = the property on the obstacle
- `BypassCapabilityRequirement` = which capability is relevant + threshold
- The bypass option bridges them: "for things with property X, capability Y
  is relevant — show the option with its difficulty vs. the character's value"

---

## The Interaction Pipeline

When properties meet capabilities, the system resolves what actions are
available through a consistent pipeline:

```
1. IDENTIFY target and environment properties
   - Obstacle: template.properties (M2M)
   - Combat target: species properties + active condition properties
   - Environment: room properties (weather, terrain, elements present)
   - Item: item type properties + enchantment properties

2. MATCH properties to interaction rules
   - Obstacle: BypassOption attached to matching ObstacleProperty
   - Combat: combo rules matching attack properties to target properties
   - Utility: interaction options matching character capabilities to
     environment properties

3. PRESENT options with difficulty context
   - Any option where the character has relevant capability is shown
   - Display difficulty rank vs. character's capability value
   - Player makes an informed choice about which action to attempt

4. RESOLVE with a check
   - Uses the check system (checks.CheckType + perform_check)
   - Actual capability value may vary based on intensity, modifiers, etc.
   - Difficulty scales by severity/intensity
   - Outcome feeds into attempt/consequence system if narrative weight needed
   - Both success and failure produce meaningful results

5. APPLY effects
   - Obstacle: bypass resolution (destroy, personal, temporary)
   - Combat: damage + condition interactions
   - Utility: state changes, narrative outcomes
```

---

## Combat as an Instance of This Pattern

Boss combat follows the same property/capability/action pattern. Defeating
a boss is effectively impossible without combo attacks — party coordination
is a hard requirement, not an optional bonus.

### Boss Defenses as Properties

A boss has defensive properties (armored, warded, regenerating) that function
like obstacle properties. Normal attacks are "soaked" by these defenses —
the boss is effectively an obstacle that must be bypassed through combos.

### Combo Attacks as Coordinated Actions

Combos are planned and coordinated by players — they should feel rewarding
as explicit strategies, not accidental discoveries. Combo rules are defined
between properties, not between specific techniques: "shattering + frozen =
amplified" applies to ANY attack with the shattering property against ANY
target with the frozen property.

Example combo flow:
1. Boss has `armored` defense property
2. Character A uses "Frost Bind" (technique whose action carries `ice`
   property) → applies "Frozen" condition to boss
3. Character B uses "Shatter" (technique whose action carries `shattering`
   property) → combo rule: `shattering` + `frozen` → amplified damage
4. Armor is temporarily weakened, damage gets through
5. Boss adapts (phase change, new properties) → party re-strategizes

Not all combos consume the enabling condition. Some may be repeatable for
the duration of the condition — the combo rule defines whether it consumes
its trigger or not.

### Party Coordination

Different paths grant techniques with different properties. A diverse party
has access to more property combinations, enabling more combo paths. This
makes party composition strategically important: not just "we need a healer"
but "we need someone who can create frozen states so our force striker can
exploit them."

### Intensity and Control

During combat, the intensity stat escalates, unlocking more powerful
techniques (higher capability thresholds). Control counterbalances —
precision vs. raw power. Narrative events (ally injured, dramatic
revelation) can spike intensity, driving fights toward climactic
breakthrough moments. Some techniques may require minimum intensity
thresholds, meaning they're only available as the fight escalates.

---

## The Type Registry Problem

The codebase has six separate models that each answer "what kind of thing is
this?" in slightly different ways. Understanding the sprawl is necessary to
avoid making it worse.

### Current Registries

| Model | App | Purpose | Connected To |
|-------|-----|---------|-------------|
| DamageType | conditions | Categories of harm | ModifierType (resonance FK) |
| CapabilityType | conditions | Things characters can do | ConditionCapabilityEffect, obstacles |
| conditions.CheckType | conditions | Check types for condition modifiers | ConditionCheckModifier |
| checks.CheckType | checks | Weighted check resolution | perform_check(), obstacles, actions, attempts |
| ObstacleProperty | obstacles | Descriptive tags on obstacles | BypassOption |
| ModifierType | mechanics | Numerical modifier targets | Many systems (being refactored) |

### CheckType (Resolved)

Previously two separate `CheckType` models existed (`conditions.CheckType`
and `checks.CheckType`). This has been unified — `checks.CheckType` is the
single source of truth. All conditions FKs now reference it directly.

### Where Properties Would Fit

Properties are a new concept that partially overlaps with existing registries:

- **DamageType** describes a SUBSET of properties (types of harm). Not all
  properties are damage types. "Wooden" is a property but not a damage type.
  The relationship between DamageType and a future Property model needs
  careful thought — they may share values but serve different roles.
- **ObstacleProperty** IS a property system, but isolated to obstacles. A
  shared Property model should replace it.
- **ModifierType** (category='resonance') overlaps thematically — "fire
  resonance" and "fire property" are related but distinct. The resonance
  measures how much fire magic a character has (quantitative, being refactored
  into its own model). The property describes that something IS fire-typed
  (qualitative). A resonance might IMPLY certain properties on techniques
  that draw from it, but they are not the same thing.

---

## Condition Scope

Conditions currently serve as both narrow status effects ("paralyzed",
"frozen") and broad effect bundles (anything applied to a character that
modifies capabilities, checks, resistances, and more). This dual role is
functional but creates conceptual blur.

The distinction matters because:
- A **status effect** like "Frozen" is a discrete state with clear
  properties (the `frozen` property), clear duration, and clear interactions
  (shattering combos, fire removes it).
- An **effect bundle** like "Werewolf Battleform Active" is a complex
  package of capability grants, check modifiers, and property changes that
  happens to be modeled as a condition.

The EffectBundle pattern (TECH_DEBT item #3) is intended to address this —
once any source can grant a bundle of effects, techniques and distinctions
won't need to route everything through conditions. This should naturally
narrow conditions back toward their intended role as status effects.

For now, conditions work as the catch-all. But new systems should be designed
with the eventual separation in mind: if something is fundamentally a status
effect, model it as a condition. If it's a complex capability package, plan
for it to be an EffectBundle once that pattern exists.

---

## Integration Points

### With Roadmap Systems

| System | How It Connects |
|--------|----------------|
| Combat | Properties on attacks and targets drive combo resolution; boss defenses are obstacle-like |
| Magic | Techniques are actions that grant capabilities; Gift resonances suggest (not dictate) technique properties |
| Items & Equipment | Items have properties (metallic, enchanted); equipped items contribute capabilities |
| Character Progression | Higher path levels unlock techniques with higher capability values |
| Relationships | Relationship states can modify capability values (combat bonuses from bonds); narrative events spike intensity |
| Missions | Mission obstacles use the property/bypass pattern for branching challenges |
| Achievements | Novel property+capability interactions are database records the achievement system can point to |

### With the EffectBundle Refactor

The EffectBundle pattern (TECH_DEBT item #3) is the key enabler for multiple
capability sources. Once any source (distinction, technique, equipment,
species) can grant a bundle of effects including capability contributions,
the capability aggregation service automatically picks them up.

The refactor order:
1. EffectBundle pattern replaces DistinctionEffect (brother's work in progress)
2. Capability resolution service gains new sources (additive — no existing
   code changes, just new queries)
3. Properties model created (generalizes ObstacleProperty to a shared model)
4. Techniques connect to the action system (define what actions they enable)
5. Combat interaction rules defined between properties

---

## Design Constraints

These are hard requirements that any implementation must respect:

1. **Nothing is binary.** Capabilities are integer values with thresholds.
   Even "impossible" things just require very high values. No boolean gates.

2. **Properties are neutral.** They describe what something IS, not whether
   that's good or bad. "Abyssal" is a property. Whether it makes you
   vulnerable to celestial attacks is determined by combo rules, not by the
   property itself.

3. **Capabilities aggregate additively.** All sources contribute positive or
   negative values. Total floors at 0. No percentage modifiers, no
   multiplication, no caps (yet).

4. **Combo rules live on properties, not techniques.** "Shattering + frozen =
   amplified" applies to ANY technique with the shattering property against
   ANY target with the frozen property. Never hardcode technique-to-technique
   combos.

5. **The obstacle pattern is the template.** New interaction systems should
   follow the same structure: target has properties → interaction options
   attach to properties → capability requirements gate access → check
   resolves outcome.

6. **Techniques are actions, not stat blocks.** A technique defines what a
   character can DO with their Gift. It's not a passive bundle of type fields.
   Properties and capabilities flow from the actions a technique enables, not
   from decorating the Technique model with type FKs.

7. **Most capabilities are derived.** Trait values derive into capabilities
   (strength → physical force). Only unusual or granted capabilities need
   explicit storage. Avoid proliferating stored capability records for things
   that can be calculated.

8. **Achievement-trackable.** Any novel interaction (first combo discovered,
   first property exploited) should be a database record that the achievement
   system can point to.

9. **Party coordination is mandatory for bosses.** Boss encounters must be
   designed so that combo attacks from multiple characters are required.
   Solo damage should be ineffective against boss defenses.
