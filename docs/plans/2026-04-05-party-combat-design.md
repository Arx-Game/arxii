# Party Combat System Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the core Party Combat system — asymmetrical PvE encounters where a covenant (adventuring party) fights authored NPC opposition, with combo discovery, boss phases, and escalating narrative tension.

**Architecture:** Combat builds on top of existing check, fatigue, condition, capability, and consequence systems. New models handle encounter state, NPC behavior, round management, and combo learning. The system is PC-centric — NPCs have authored threat pools, not mirrored character sheets.

**Tech Stack:** Django models (SharedMemoryModel), existing check pipeline (`perform_check`), existing fatigue/condition/consequence systems, DRF API endpoints, React frontend.

---

## Core Design Principles

### Asymmetrical by Design
Party Combat is NOT symmetrical. PCs and NPCs are fundamentally different:
- PCs have character sheets, capabilities, techniques, fatigue pools, health pools
- NPCs have authored stat blocks, threat pools, soak values, and phase definitions
- PCs are always the active agents — even when "defending," PCs make checks
- NPC actions are relatively static; what matters is PC rolls and abilities

### Risks and Stakes
Every encounter defines two axes:
- **Risks** — personal to characters: death, harm to loved ones, identity-threatening losses, injury
- **Stakes** — world-level: organization reputation (low), regional consequences (mid), fate of the world (high)
- Encounters range from "easy victory lap" to "unwinnable last stand where a PC sacrifices to save everyone"

### Teamwork is Mandatory
Encounters are intentionally impossible to solo and much harder for small groups:
- Boss soak mechanics make individual attacks ineffective without combo follow-ups
- Covenant roles provide speed, armor, and combo eligibility bonuses
- Combo learning rewards relationship investment between characters

---

## Data Models

### CombatEncounter
Top-level container for a fight.

| Field | Type | Notes |
|-------|------|-------|
| covenant | FK to Covenant, nullable | Party Combat normally has one; Open Encounters (future) may not |
| scene | FK to Scene | Combat happens within a scene for RP integration |
| encounter_type | enum | PARTY_COMBAT, OPEN_ENCOUNTER (future) |
| round_number | PositiveIntegerField | Current round, starts at 1 |
| status | enum | DECLARING, RESOLVING, BETWEEN_ROUNDS, COMPLETED |
| risk_level | enum | Authored metadata — LOW through EXTREME |
| stakes_level | enum | Authored metadata — LOCAL through WORLD |
| story | FK to Story, nullable | Optional narrative tracking |
| episode | FK to Episode, nullable | Optional narrative tracking |

### CombatOpponent
Each NPC entity in the encounter.

| Field | Type | Notes |
|-------|------|-------|
| encounter | FK to CombatEncounter | |
| tier | enum | SWARM, MOOK, ELITE, BOSS, HERO_KILLER |
| name | CharField | Authored by GM |
| description | TextField | Authored by GM |
| health | IntegerField | Current health (can go negative) |
| max_health | PositiveIntegerField | Starting health |
| soak_value | PositiveIntegerField | Damage below this is absorbed (still probes) |
| probing_current | PositiveIntegerField | Current probing counter, default 0 |
| probing_threshold | PositiveIntegerField, nullable | Points needed to unlock combos (null = no probing mechanic) |
| current_phase | PositiveIntegerField | Current boss phase, default 1 |
| threat_pool | FK to ThreatPool | What this opponent does each round |
| status | enum | ACTIVE, DEFEATED, FLED |

### CombatParticipant
Each PC in the encounter.

| Field | Type | Notes |
|-------|------|-------|
| encounter | FK to CombatEncounter | |
| character_sheet | FK to CharacterSheet | |
| covenant_role | enum, nullable | Determines resolution rank; null = rank 20 |
| health | IntegerField | Current health (can go negative — tracks depth below zero) |
| max_health | PositiveIntegerField | Derived from stamina + path level + covenant armor + threads |
| status | enum | ACTIVE, UNCONSCIOUS, DYING, DEAD |
| dying_final_round | BooleanField | True = this PC gets one last round before death |

### CombatRoundAction
One per PC per round — their declared actions.

| Field | Type | Notes |
|-------|------|-------|
| participant | FK to CombatParticipant | |
| round_number | PositiveIntegerField | |
| focused_action | FK to technique/ability | Main action for the round |
| focused_category | enum | PHYSICAL, SOCIAL, MENTAL |
| focused_target | FK (GenericFK or to CombatOpponent) | Who they're targeting |
| effort_level | EffortLevel enum | From fatigue system |
| physical_passive | FK to passive ability, nullable | Null if physical is the focused category |
| social_passive | FK to passive ability, nullable | Null if social is the focused category |
| mental_passive | FK to passive ability, nullable | Null if mental is the focused category |
| combo_upgrade | FK to ComboDefinition, nullable | If upgraded to a combo, which one |

### CombatOpponentAction
NPC actions for a round, auto-selected from threat pool.

| Field | Type | Notes |
|-------|------|-------|
| opponent | FK to CombatOpponent | |
| round_number | PositiveIntegerField | |
| threat_entry | FK to ThreatPoolEntry | Which action was selected |
| targets | M2M to CombatParticipant | Who is being targeted |

---

## NPC Tier System

Five tiers with distinct mechanical treatment:

### Swarm
Mass of fodder. No individual HP — uses a swarm count that decrements as PCs mow through them. No soak. Danger is attritional volume.

### Mook
Individual minions with modest stats. Between swarms and elites. Individually manageable but can overwhelm in numbers. Low or no soak.

### Elite
Individual HP, some soak, may require one combo to take down. Roughly paired 1:1 against PCs as independent challenges. May have special abilities or extraordinary attacks.

### Boss
Massive HP, high soak, probing/combo/phase system. The centerpiece encounter. Essentially immune to non-combo damage until probed enough. Multiple authored phases with different threat pools and behaviors.

### Hero Killer
Staff-only tier. Kaiju, gods, endgame threats. Triggers narrative "you must run" state. Uses specific narrative rules, not just massive stats. Not available to normal GMs.

---

## Round Structure

### 1. Declaration
All PCs submit actions simultaneously:
- Choose focused action (technique/ability) in one category (physical/social/mental)
- Choose target
- Choose effort level
- Choose passives for the other two categories
- NPC actions auto-selected from threat pool
- PCs may or may not see NPC intentions based on IC abilities (techniques, spells, etc.)

### 2. Combo Detection
After all declarations are submitted:
- System scans declared actions against combo library
- Matches against ComboDefinitions where all slots are satisfied
- A combo must be known by at least one participating PC, OR a combat discovery roll succeeds
- Eligible PCs see their action glowing + text notification
- Any PC can independently upgrade to the combo — no mutual confirmation needed
- If a trigger PC changes their base action, dependent combos break and upgraders revert

### 3. Resolution
Actions resolve in covenant rank order:
- Ranks 1-2: Fastest covenant roles
- Ranks 3-12: Other covenant roles in speed order
- ~Rank 15: NPCs
- ~Rank 20: No covenant role (unbuffed normal humans)
- Speed modifiers (buffs/debuffs) shift rank up or down
- Ties within rank resolve simultaneously

**PC action resolution:**
- PC makes check via `perform_check()` with effort, fatigue, and modifier penalties
- Fatigue cost applied in the focused category + anima for magical techniques
- Against Swarm: reduces swarm count
- Against Mook: damage to health
- Against Elite/Boss: damage below soak absorbed but increments probing counter; damage above soak (or from combos bypassing soak) applies to health
- Passive abilities fire their effects (buffs, defensive bonuses, group support)

**NPC action resolution (~rank 15):**
- Target PC(s) make defensive checks (physical/social/mental matching attack type)
- NPC base damage modified by PC check result (great success = no damage, partial = reduced, failure = full, critical failure = extra)
- Damage applies to PC health pool
- Threshold checks:
  - Hit > 50% of max health: chance of permanent wound/scar
  - Below 20% health: knockout chance per hit, increased by fatigue
  - At 0% or below: death chance per hit (escalating with negative health), high chance of permanent wounds/scars (magical scars from magical damage)

**Combo resolution:**
- Each PC who upgraded resolves their combo portion at their own covenant rank
- The combo replaces their focused action entirely (new authored effect)
- Effects pile on as each participant resolves
- Non-upgrading PCs keep their normal actions

### 4. Round End
- Check encounter completion (all opponents defeated, all PCs down, etc.)
- Advance round counter
- Return to Declaration

---

## Health and Damage

### Health Pool
Separate from fatigue. Fatigue degrades effectiveness; health degrades survival.

**Sources:** Stamina (slight contribution) + Path level (large) + covenant role armor + woven magical thread protection. Magical power is the dominant factor.

**Wound ladder** (descriptive text added to character):
- 90%+ : healthy appearance
- Escalating descriptions as health drops
- Near 0%: death's door

### Damage Thresholds
- **Hit > 50% max health:** chance of permanent wound/scar
- **Below 20% health:** knockout chance per hit, increased by high fatigue / collapse risk
- **At 0% health or below:** death chance per hit (escalating as negative health deepens), high chance of permanent wounds/scars, magical scars from magical damage
- Negative health is tracked precisely — deeper negative = worse odds
- All threshold checks modified by existing roll modifier system

### Knockout and Death
- **Unconscious:** Round skipped (no focused action, no category passives). Covenant passives, thread bonuses, and ambient effects still fire. Can be revived by allies (limited, not easy healing).
- **Lethal hit:** PC enters DYING status. `dying_final_round` set. They get one more round to act — non omnis moriar moment, no resource constraints, go out swinging.
- **Dead:** Permanent. No resurrection. Character is gone.

### Audere Integration
Health is the primary Audere domain. Risk of character loss is the core trigger for Audere and Audere Majora. Fatigue compounds danger (collapse risk when health is low) but the breakthrough moment comes from being on the edge of death.

---

## Boss Phase System

Optional per boss — a one-phase boss just has a single threat pool and soak value.

### BossPhase Model

| Field | Type | Notes |
|-------|------|-------|
| opponent | FK to CombatOpponent | The boss |
| phase_number | PositiveIntegerField | 1, 2, 3... |
| threat_pool | FK to ThreatPool | Different attack patterns per phase |
| soak_value | PositiveIntegerField | Can change per phase |
| probing_threshold | PositiveIntegerField | Points needed to unlock combos this phase |
| transition_trigger | authored | Combo damage threshold, specific combo, or health percentage |
| description | TextField | Narrative description of what changes when phase begins |

### Phase Flow
1. Boss starts Phase 1 with high soak
2. PCs attack — damage below soak absorbed but increments probing counter
3. Probing hits threshold — combo opportunities light up for PCs with matching actions
4. PCs land combos — real damage and/or phase transition trigger hit
5. Next phase begins: new threat pool, possibly new soak/probing values, narrative fires
6. Probing counter resets or carries over partially (authored per boss)
7. Repeat until final phase defeated

---

## Combo System

### ComboDefinition
Staff-authored combinations. Hidden by default, learned through play.

| Field | Type | Notes |
|-------|------|-------|
| name | CharField | e.g., "Shadow Vortex Bind" |
| description | TextField | Narrative flavor |
| hidden | BooleanField, default True | Shown only after learned |
| discoverable_via_training | BooleanField | Can be learned through training |
| discoverable_via_combat | BooleanField | Can emerge during combat |
| discoverable_via_research | BooleanField | Can be found through clues/lore |
| minimum_probing | PositiveIntegerField, nullable | Probing threshold required (null = no requirement) |
| authored effects | (via consequence/effect system) | Damage, conditions, soak bypass, phase advance, etc. |

### ComboSlot
One per required participant. Each slot evaluated independently.

| Field | Type | Notes |
|-------|------|-------|
| combo | FK to ComboDefinition | |
| slot_number | PositiveIntegerField | Ordering |
| required_action_type | enum/FK | Action type this slot needs (Restraint, Strike, Ward, etc.) |
| resonance_requirement | CharField or FK | Specific resonance, "any of [list]", or "any" |

### ComboLearning
Which PCs know which combos.

| Field | Type | Notes |
|-------|------|-------|
| combo | FK to ComboDefinition | |
| character_sheet | FK to CharacterSheet | |
| learned_via | enum | TRAINING, COMBAT, RESEARCH |
| learned_at | DateTimeField | |

A combo only needs to be known by ONE participating PC to appear as an option for all participants in that combo.

### Matching Logic
When all ComboSlots are satisfied by different PCs' declared actions (one PC per slot, action type matches, resonance matches), the combo is available. Each slot is independent — no cross-slot references.

---

## Threat Pools (NPC Behavior)

### ThreatPool
Named collection of NPC actions.

| Field | Type | Notes |
|-------|------|-------|
| name | CharField | e.g., "Dragon Phase 1" |
| description | TextField | |

### ThreatPoolEntry
One possible action the NPC can take.

| Field | Type | Notes |
|-------|------|-------|
| pool | FK to ThreatPool | |
| name | CharField | e.g., "Claw Swipe" |
| description | TextField | |
| attack_category | enum | PHYSICAL, SOCIAL, MENTAL |
| base_damage | PositiveIntegerField | |
| weight | PositiveIntegerField | Selection probability |
| targeting_mode | enum | SINGLE, MULTI, ALL |
| target_count | PositiveIntegerField, nullable | For MULTI mode |
| target_selection | enum | RANDOM, HIGHEST_THREAT, LOWEST_HEALTH, SPECIFIC_ROLE |
| conditions_applied | M2M to ConditionTemplate, nullable | Applied on hit |
| minimum_phase | PositiveIntegerField, nullable | Only available in this phase or later |
| cooldown_rounds | PositiveIntegerField, nullable | Can't repeat for N rounds |

### Selection Logic
Each round: filter by phase/cooldown/conditions, then select by weight. Targeting defaults heavily toward tank covenant role for single-target attacks. Staff/senior GMs can override selection.

---

## Covenant Roles

Combat archetypes assigned when a covenant is formed via IC ritual. Static for combat duration, changeable between combats via new ritual.

- Each role has a fixed **speed rank** (enum) determining resolution order
- Roles affect **armor bonuses** and what armor types benefit them
- Roles affect **combo eligibility** (some combos may require specific role combinations)
- Roles provide **passive covenant bonuses** that persist even when unconscious
- Specific roles and speed rankings are future content — enum stubs for now
- PCs without a covenant role default to rank 20

---

## Integration with Existing Systems

| System | Integration |
|--------|-------------|
| **Check pipeline** | All combat rolls use `perform_check()`. Fatigue penalties, effort modifiers, roll modifiers all apply automatically. |
| **Fatigue** | Focused actions cost fatigue in their category. Magical techniques cost anima. Attrition builds naturally across rounds. |
| **Conditions** | NPC attacks apply conditions on hit. Phase transitions apply/remove conditions. Soulfray from magical damage. Permanent wounds/scars are conditions with permanent duration. |
| **Consequence/Effect pipeline** | Combo effects and NPC effects use existing ConsequenceEffect system. DEAL_DAMAGE handler (currently stubbed) gets implemented. |
| **Capability system** | PC available actions in combat derive from capabilities via `get_capability_sources_for_character()`. |
| **Achievements** | Stat hooks: `combat.enemies_defeated`, `combat.combos_learned`, `combat.phases_broken`, `combat.non_omnis_moriar`, `combat.bosses_killed`, etc. First combo learning game-wide triggers Discovery. |
| **Health pool** | New system introduced by combat. Derived from stamina + path level + covenant armor + threads. |

---

## Scope Boundaries

### In scope (this design)
- Party Combat encounter model and round lifecycle
- NPC tiers (Swarm, Mook, Elite, Boss, Hero Killer)
- Three-category action system (focused + passives)
- Health pool and damage/wound threshold system
- Boss phase system
- Combo definition, learning, detection, and resolution
- Threat pool NPC behavior
- Covenant role speed ranking and resolution order

### Out of scope (future work)
- **Open Encounters** — alternate combat type for spontaneous/drop-in fights, built on same primitives
- **Battle Scenes** — mass combat VP system, different encounter structure entirely
- **Duels** — symmetrical 1v1, potentially lethal variant for high-drama NPC fights
- **Encounter scaling/GM tooling** — hybrid difficulty from story context + party composition
- **Specific covenant role definitions** — enum stubs now, content authored later
- **Specific combo content** — system built now, combos authored as content
- **NPC AI sophistication** — threat pools handle MVP, smarter behavior later
- **Combat UI** — frontend design is a separate effort after backend is built
