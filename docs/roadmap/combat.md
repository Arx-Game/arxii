# Combat

**Status:** not-started
**Depends on:** Traits, Skills, Magic, Conditions, Mechanics, Relationships (for combo attacks)

## Overview
Combat is always Players vs. the Bad Guys — no PVP killing. Three distinct combat modes serve different scales and narrative purposes, all designed to create heroic moments and reward teamwork over solo power.

## Key Design Points

### Asymmetrical by Design
Party Combat is NOT symmetrical like tabletop RPGs. PCs do not fight mirrored opponents.
The opposition does not have character sheets with capabilities. Instead:
- **Offensive round:** PCs pick actions and resolve attacks against the opposition
- **Defensive round:** The opposition acts via threat patterns; PCs make defensive checks
- NPCs have behaviors, threat patterns, and soak values — not mirrored PC sheets
- The only symmetrical PC-vs-NPC combat is a special Duel variant (high-drama 1v1 to the death)

### Three Combat Modes (each with variations)
- **Party Combat:** The main form. Asymmetrical — PCs vs opposition (boss, minions, swarm).
  Intentionally impossible to solo; combos and covenant roles (party roles) are fundamental.
  Designed for heroic team-up arcs: characters get battered, pushed to the edge, and break
  through with Audere Majora. Variations range from "victory lap against fodder" to
  "unwinnable last stand where a PC sacrifices to save the party."
- **Battle Scenes:** Large-scale abstracted conflicts with variations: army vs army (PCs on
  one side), all PCs vs kaiju-scale opponent. Fixed rounds, victory points, mass participants.
  Similar feel (mass combat) but stylistic differences within.
- **Duels:** Normally non-lethal PC vs PC sparring, slow-paced with pose integration. But also
  supports high-drama lethal 1v1 (PC vs significant NPC) — the only symmetrical combat mode.

### Risks and Stakes
Every encounter defines Risks (personal to character) and Stakes (world-level):
- **Risks:** Character death, harm to loved ones, identity-threatening losses, minor injury
- **Stakes:** Organization reputation (low), regional consequences (mid), fate of the world (high)
- Encounter design ranges from "easy victory lap" to "the fight you can't win but must fight"

### Round Structure
One unified round — no artificial offensive/defensive split.

1. **Declaration** — All PCs declare their focused action + passives simultaneously. NPC
   actions are determined automatically. PCs may or may not see NPC intentions (who they
   target, what they're doing) based on IC mechanical abilities (spells, techniques, etc.).
2. **Resolution** — Actions resolve in covenant rank order:
   - Ranks 1-2: Fastest covenant roles (e.g., scout/striker archetypes)
   - Ranks 3-12: Other covenant roles in speed order
   - ~Rank 15: NPCs (safely after most PCs)
   - ~Rank 20: No covenant role (unbuffed normal humans)
   - Slow debuffs/effects add ranks (e.g., +10) to resolution order
   - Fast PCs can kill minions before they act, or buff allies before the boss resolves

### Three-Category Actions
Each round, a PC has three action categories: **Physical, Social, Mental**.
- PC picks ONE **focused action** in one category (their main action for the round)
- The other two categories get **passive defaults** — small buffs/support chosen per round
- Example: "Massive Shadow Sword" (physical focus) + "Tactical Orders" (social passive, group
  combat buff) + "Keep It Together" (mental passive, defensive buff vs mental attacks)
- Focused actions cost fatigue in their category + anima for magical techniques
- Passives let characters express personality in combat (what they say/think while fighting)

### Covenant Roles
Combat archetypes assigned when a covenant (adventuring party) is formed via IC ritual.
- Static for the duration of combat — not altered on the fly
- Can be changed between combats via a new ritual
- Each role has a fixed speed rank determining resolution order
- Roles also determine combo eligibility and party synergy mechanics
- Specific roles and speed rankings are future content — enum stubs for now

### NPC Tiers
Five distinct NPC types with different mechanical treatment:
- **Swarm** — mass of fodder, swarm-count based (no individual HP), no soak. PCs mow through
  them. Danger is attritional volume. Simple stat block.
- **Mook** — individual minions with modest stats. Between swarms and elites. Individually
  manageable but can overwhelm in numbers.
- **Elite** — individual HP, some soak, may require one combo to take down. Roughly paired
  1:1 against PCs as independent challenges. Extraordinary attacks or abilities.
- **Boss** — massive HP, high soak, probing/combo/phase system. The centerpiece encounter.
  Essentially immune until probed enough for combos to land. Multiple phases.
- **Hero Killer** — staff-only tier. Kaiju, gods, endgame threats that PCs cannot defeat.
  Triggers narrative "you must run" state rather than combat engagement. Uses specific
  narrative rules, not just massive stats. Not available to normal GMs.

### Boss Soak and Combo Mechanics
Bosses (and to a lesser degree Elites) use the soak/probing/combo system:
- Soak threshold ignores attacks below a damage floor
- Every attack that hits (even soaked) builds a **probing defenses** counter
- When probing reaches a threshold, combo attacks that bypass soak become available
- Combos require multiple PCs coordinating — valueless for solo players
- Landing a combo can advance the boss to the next **phase** (different stage of the fight)
- This creates the escalating tension loop: probe → combo → phase shift → harder patterns

### Encounter Scaling (future — GM tooling, not core combat)
Difficulty is hybrid: base from story context, adjusted by party composition. GMs mostly
pick a tier (Swarm/Mook/Elite/Boss), name it, describe it, and the system fills in
appropriate defaults based on party strength and story risk level. GMs have limited control
over exact difficulty — the system handles most of it to ensure consistency across GMs.
C-style consequence pools are better suited for abstract mission challenges (e.g., assassinate
an NPC at a bar) where concrete NPC objects aren't needed.

### Health Pool and Damage
Health is separate from fatigue — fatigue degrades effectiveness, health degrades survival.

**Health pool sources:** Stamina (slight contribution) + Path level (large) + covenant role
armor bonuses + woven magical thread protection. Magical power is the dominant factor.

**Wound ladder** (descriptive, added to character description):
- 90%+ health: "Perfectly healthy"
- Escalating descriptions down to 0%: bruised → battered → ... → "death's door"

**Threshold effects:**
- Hit > 50% of total health: chance of permanent wounds/scars
- Below 20% health: chance of knockout per hit, increased by high fatigue/collapse risk
- 0% health: chance of death per hit, high chance of permanent wounds/scars
- Magical damage at 0%: chance of magical scars (Soulfray-related)
- All threshold checks modified by roll modifiers as usual

**Audere triggers:** Health is the primary Audere domain — risk of character loss is the
core trigger. Fatigue compounds danger (collapse risk when health is low) but Audere
moments come from being on the edge of death, not from being tired.

**Damage resolution:** When an NPC action targets a PC, the PC makes a defensive check
(physical/social/mental matching the attack type). NPC attack power sets base damage;
the PC's check result modifies it (great success = no damage, partial = reduced, failure =
full, critical failure = extra). NPC attacks are relatively static — what matters is
PC rolls and abilities. Effort level on defense adds fatigue pressure (spend high effort
to defend better but drain your pools faster). Focus stays on PCs as active agents.

### Other Design Points
- **No symmetrical PVP:** Frees balance to focus on "feels cool" rather than "perfectly fair"
- **Magic is predominant:** Gifts should greatly move the needle. Higher Path steps and threshold crossings should feel transformative in combat
- **Relationship bonuses in combat:** Romance gives collaborative bonuses; if one partner is near death, the other gets an overwhelming bonus nudging them toward an Audere Majora. Rivalries give intensity bonuses. Party bonds improve coordination
- **Level considerations:** Need caps to prevent low-level characters from feeling worthless, while still allowing them to participate meaningfully
- **Fatigue integration:** Combat actions drain fatigue pools by category, creating attrition pressure that builds toward collapse/Audere moments

## What Exists
- **Models:** Conditions app has combat-relevant fields (affects_turn_order, draws_aggro, turn_order_modifier, aggro_priority). Mechanics app has modifier collection/stacking, plus the new Challenge/Situation system (ChallengeTemplate, ChallengeInstance, ChallengeApproach) and action generation pipeline. Checks app has the roll resolution engine
- **Capability/Application system:** Properties on enemies/environments, Applications matching character Capabilities to available combat actions, ChallengeApproach with required_effect_property for fine-grained constraints (e.g., fire resistance requires fire-generating capability). Action generation auto-surfaces what each character can do in a given combat situation
- **Supporting systems:** Check pipeline (trait-to-rank conversion, result charts). Conditions with stage progression, DoT, and Properties M2M. TechniqueCapabilityGrant connects magic techniques to capabilities. TraitCapabilityDerivation connects stats to capabilities
- **No dedicated combat models** — no encounters, initiative tracking, targeting, damage resolution, or party management

## What's Needed for MVP

### Party Combat (first priority) — designed, not yet built
Full design: `docs/plans/2026-04-05-party-combat-design.md`

- CombatEncounter, CombatOpponent, CombatParticipant models
- Round lifecycle (declaration → combo detection → resolution by covenant rank)
- Three-category action system (focused + passives)
- Health pool system (separate from fatigue, with wound ladder and threshold effects)
- NPC tier system (Swarm, Mook, Elite, Boss, Hero Killer)
- Threat pool NPC behavior (weighted selection, targeting modes)
- Boss phase system (soak → probing → combo → phase transition)
- Combo system (staff-authored, action type + resonance slots, ComboLearning)
- Knockout/death mechanics (unconscious round skip, dying final round, permanent death)
- DEAL_DAMAGE effect handler implementation (currently stubbed)
- Covenant role enum stubs with speed rankings

### Open Encounters (future — builds on Party Combat)
- Spontaneous combat for any number of participants, drop-in/drop-out
- Nullable covenant, participants can join/leave mid-fight
- Same combat primitives, different encounter structure

### Battle Scenes (future — separate system)
- Mass combat VP system with variations (army vs army, all PCs vs kaiju)
- Fixed rounds, victory point tracking, mass participant handling
- Risk/reward action choices per round

### Duels (future — separate system)
- Normally non-lethal PC vs PC sparring with pose integration
- Special variant: lethal 1v1 PC vs significant NPC (only symmetrical combat mode)

### Shared Future Work
- Encounter scaling / GM tooling — difficulty from story context + party composition
- Relationship modifier integration in combat (romance bonuses, rivalry intensity)
- Audere Majora trigger conditions from health thresholds
- Combat UI — web-first interface for all combat modes
- Specific covenant role definitions (enum stubs now, content later)
- Combo content authoring

## Design Document

See `docs/plans/2026-04-05-party-combat-design.md` for the full Party Combat design.

## Notes
