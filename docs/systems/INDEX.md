# Arx II Systems Index

> Quick reference for AI agents and developers. For each system: what it does,
> key models, key functions/methods, and what it connects to.
>
> **For detailed documentation**, follow the links to individual system docs.

---

## Game Systems

### Magic
Powers, affinities, auras, resonances, and magical relationships (threads).

- **Models:** `Gift`, `CharacterGift`, `CharacterAura`, `Technique`, `CharacterTechnique`, `Thread`
- **Key Methods:** `CharacterAura.dominant_affinity`, `Thread.get_matching_types()`
- **Enums:** `AffinityType`, `ResonanceScope`, `ResonanceStrength`, `AnimaRitualCategory`
- **Integrates with:** traits (for magical rolls), progression (for gift unlocks)
- **Source:** `src/world/magic/`
- **Details:** [magic.md](magic.md)

### Traits
Character statistics and dice rolling mechanics.

- **Models:** `Trait`, `CharacterTraitValue`, `PointConversionRange`, `CheckRank`, `ResultChart`
- **Key Functions:** `get_trait_value()`, dice rolling via `ResultChart`
- **Integrates with:** magic (intensity calculations), skills (bonuses), combat (rolls)
- **Source:** `src/world/traits/`
- **Details:** [traits.md](traits.md)
### Skills
Character abilities with parent skills and specializations.

- **Models:** `Skill`, `Specialization`, `CharacterSkillValue`, `CharacterSpecializationValue`
- **Integrates with:** traits (skill checks), character_creation (skill selection)
- **Source:** `src/world/skills/`
- **Details:** [skills.md](skills.md)
### Distinctions
Character advantages and disadvantages (CG Stage 6: Traits).

- **Models:** `DistinctionCategory`, `Distinction`, `DistinctionEffect`, `CharacterDistinction`
- **Key Methods:** `Distinction.calculate_total_cost()`, `Distinction.get_mutually_exclusive()`
- **Enums:** `DistinctionOrigin`, `OtherStatus`
- **Integrates with:** character_creation (draft storage), traits (stat modifiers)
- **Source:** `src/world/distinctions/`
- **Details:** [distinctions.md](distinctions.md)

### Checks
Check resolution engine — converts trait values to ranks and rolls against result charts.

- **Models:** Uses lookup tables from traits (PointConversionRange, CheckRank, ResultChart)
- **Key Functions:** `perform_check()`, `CheckRank.get_rank_for_points()`
- **Integrates with:** traits (lookup tables), skills (check bonuses)
- **Source:** `src/world/checks/`
- **Details:** [checks.md](checks.md)

### Conditions
Persistent states that modify capabilities, checks, and resistances with stage progression and interactions.

- **Models:** `ConditionCategory`, `ConditionTemplate`, `ConditionStage`, `ConditionInstance`, `ConditionCapabilityEffect`, `ConditionCheckModifier`, `ConditionResistanceModifier`, `ConditionDamageOverTime`, `ConditionDamageInteraction`, `ConditionConditionInteraction`
- **Lookup Tables:** `CapabilityType`, `CheckType`, `DamageType`
- **Key Functions:** `apply_condition()`, `remove_condition()`, `get_capability_status()`, `get_check_modifier()`, `get_resistance_modifier()`, `process_round_start()`, `process_round_end()`, `process_damage_interactions()`
- **Integrates with:** combat (DoT, capability blocking), magic (power sources), progression (interactions)
- **Source:** `src/world/conditions/`
- **Details:** [conditions.md](conditions.md)
### Species
Species/race definitions with stat bonuses and language assignments.

- **Models:** `Species`, `SpeciesStatBonus`, `Language`
- **Key Methods:** `Species.get_stat_bonuses_dict()`, `Species.is_subspecies`
- **Integrates with:** character_creation (Beginnings.allowed_species), forms (physical traits)
- **Source:** `src/world/species/`
- **Details:** [species.md](species.md)
### Forms
Physical appearance options (height, build, hair/eye colors).

- **Models:** `HeightBand`, `Build`, `FormTrait`, `FormTraitOption`, `CharacterForm`
- **Enums:** `TraitType` (color/style)
- **Integrates with:** character_sheets (appearance), species (height bands per species)
- **Source:** `src/world/forms/`
- **Details:** [forms.md](forms.md)
### Classes (Paths)
Character paths with evolution hierarchy through stages of power.

- **Models:** `Path`, `CharacterClass`
- **Enums:** `PathStage` (Prospect, Potential, Puissant, True, Grand, Transcendent)
- **Key Methods:** `Path.parent_paths`, `Path.child_paths` (evolution hierarchy)
- **Integrates with:** progression (level requirements), character_creation (Prospect selection)
- **Source:** `src/world/classes/`
- **Details:** [classes.md](classes.md)
### Areas
Spatial hierarchy for organizing rooms into regions, districts, and neighborhoods.

- **Models:** `Area`, `AreaClosure` (unmanaged, materialized view)
- **Enums:** `AreaLevel` (Region, District, Neighborhood)
- **Key Functions:** `get_ancestry()`, `get_descendant_areas()`, `get_rooms_in_area()`, `reparent_area()`
- **Pattern:** Postgres materialized view with recursive CTE for hierarchy queries
- **Integrates with:** realms (Area.realm FK), evennia_extensions (RoomProfile.area FK)
- **Source:** `src/world/areas/`
- **Details:** [areas.md](areas.md)
### Instances
Temporary instanced rooms spawned on demand for missions, GM events, and tutorials.

- **Models:** `InstancedRoom`
- **Enums:** `InstanceStatus` (Active, Completed)
- **Key Functions:** `spawn_instanced_room()`, `complete_instanced_room()`
- **Pattern:** Lifecycle record attached to regular Room via OneToOneField; rooms with scene history are preserved
- **Integrates with:** character_sheets (owner FK), scenes (preservation check), evennia_extensions (ObjectDisplayData for description)
- **Source:** `src/world/instances/`
- **Details:** [instances.md](instances.md)
### Realms
Game world realms (Arx, Luxan, etc.) for geographical/political organization.

- **Models:** `Realm`
- **Integrates with:** societies (Society.realm FK), character_creation (StartingArea)
- **Source:** `src/world/realms/`
- **Details:** [realms.md](realms.md)
### Societies
Social structures, organizations, reputation, and legend tracking.

- **Models:** `Society`, `OrganizationType`, `Organization`, `OrganizationMembership`, `SocietyReputation`, `OrganizationReputation`, `LegendEntry`, `LegendSpread`
- **Enums:** `ReputationTier`
- **Principle Axes:** mercy, method, status, change, allegiance, power (-5 to +5)
- **Integrates with:** realms (Society.realm FK), character_sheets (Guise for identity)
- **Source:** `src/world/societies/`
- **Details:** [societies.md](societies.md)
### Goals
Goal domain allocation and journal-based XP progression.

- **Models:** `CharacterGoal`, `GoalJournal`, `GoalRevision`
- **Goal Domains:** Stored as `ModifierType(category='goal')` in mechanics system
- **Six Domains:** Standing, Wealth, Knowledge, Mastery, Bonds, Needs
- **Integrates with:** progression (XP rewards), mechanics (goal domains use ModifierType)
- **Source:** `src/world/goals/`
- **Details:** [goals.md](goals.md)
### Action Points
Time/effort resource economy with regeneration via cron.

- **Models:** `ActionPointConfig`, `ActionPointPool`
- **Key Methods:** `ActionPointConfig.get_active()`, `ActionPointPool.spend()`, `ActionPointPool.regenerate()`
- **Integrates with:** codex (teaching costs AP), cron (daily/weekly regeneration)
- **Source:** `src/world/action_points/`
- **Details:** [action_points.md](action_points.md)

### Codex
Lore storage and character knowledge tracking.

- **Models:** `CodexCategory`, `CodexSubject`, `CodexEntry`, `CharacterCodexKnowledge`
- **Key Methods:** Character learning from starting choices or teaching
- **Integrates with:** action_points (teaching costs), consent (visibility), character_creation (starting knowledge)
- **Source:** `src/world/codex/`
- **Details:** [codex.md](codex.md)
### Consent
OOC visibility groups for player-controlled content sharing.

- **Models:** `ConsentGroup`, `ConsentGroupMember`, `VisibilityMixin`
- **Key Methods:** `VisibilityMixin.is_visible_to()`
- **Pattern:** RosterTenure-based (player's tenure, not character)
- **Integrates with:** roster (RosterTenure), codex (visibility), any model using VisibilityMixin
- **Source:** `src/world/consent/`
- **Details:** [consent.md](consent.md)
### Progression
XP, kudos, development points, and unlock system.

- **Models:** `ExperiencePointsData`, `XPTransaction`, `DevelopmentPoints`, `DevelopmentTransaction`, `KudosPointsData`, `KudosTransaction`, `CharacterUnlock`, `XPCostChart`, `XPCostEntry`, `CharacterPathHistory`
- **Unlock Requirements:** `TierRequirement`, `LevelRequirement`, `TraitRequirement`, `ClassLevelRequirement`, `AchievementRequirement`, `RelationshipRequirement`
- **Key Functions:** XP spending, unlock validation, kudos claims
- **Integrates with:** traits (unlock requirements), classes (path unlocks), goals (XP rewards)
- **Source:** `src/world/progression/`
- **Details:** [progression.md](progression.md)

### Character Sheets
Character identity, appearance, demographics, and guise system.

- **Models:** `CharacterSheet`, `Heritage`, `Characteristic`, `CharacteristicValue`, `Guise`
- **Integrates with:** roster (character management), character_creation (sheet setup)
- **Source:** `src/world/character_sheets/`
- **Details:** [character_sheets.md](character_sheets.md)
### Character Creation
Multi-stage character creation flow with draft system.

- **Models:** `CharacterDraft`, `StartingArea`, `Beginnings`
- **Key Functions:** Stage validation, draft progression
- **Integrates with:** All character-related systems (traits, skills, magic, sheets)
- **Source:** `src/world/character_creation/`
- **Details:** [character_creation.md](character_creation.md)
### Roster
Character lifecycle management with web-first applications and player anonymity.

- **Models:** `Roster`, `RosterEntry`, `RosterTenure`, `RosterApplication`, `PlayerMail`
- **Integrates with:** accounts, character_sheets, scenes
- **Source:** `src/world/roster/`
- **Details:** [roster.md](roster.md)
### Scenes
Roleplay session recording with participant tracking and message logging.

- **Models:** `Scene`, `SceneParticipation`, `Persona`, `SceneMessage`, `SceneMessageReaction`
- **Integrates with:** roster (characters), stories (narrative context)
- **Source:** `src/world/scenes/`
- **Details:** [scenes.md](scenes.md)
### Stories
Player-driven narrative campaign system with hierarchical structure.

- **Models:** `Story`, `Chapter`, `Episode`, `StoryParticipation`, `PlayerTrust`, `TrustCategory`
- **Integrates with:** scenes (episode content), roster (participants)
- **Source:** `src/world/stories/`
- **Details:** [stories.md](stories.md)
### Mechanics
Game engine for modifier collection, stacking, and roll resolution.

- **Models:** `ModifierCategory`, `ModifierType`, `CharacterModifier`
- **Key Functions:** Modifier collection, stacking rules, roll calculations
- **Integrates with:** distinctions (modifier sources), conditions (modifier sources), equipment (future)
- **Source:** `src/world/mechanics/`
- **Details:** [mechanics.md](mechanics.md)

---

## Core Infrastructure

### Flows
Database-driven game logic engine. All game mechanics execute through flows.

- **Models:** `FlowDefinition`, `FlowStepDefinition`, `TriggerDefinition`
- **Key Functions:** `FlowStack.execute_flow()`, `TriggerRegistry.register_trigger()`, `FlowDefinition.emit_event_definition()`
- **Pattern:** Events trigger flows, flows execute steps, steps call service functions
- **Integrates with:** All game systems (flows orchestrate everything)
- **Source:** `src/flows/`
- **Details:** [flows.md](flows.md)
### Commands
User input processing layer. Thin commands delegate to handlers.

- **Key Classes:** `ArxCommand`, `BaseDispatcher`, `BaseHandler`
- **Pattern:** Command → Dispatcher (regex parsing) → Handler (permissions) → Flow
- **Integrates with:** flows (handlers trigger flows), typeclasses (command sets)
- **Source:** `src/commands/`
- **Details:** [commands.md](commands.md)
### Behaviors
Database-driven behavior attachment for dynamic object customization.

- **Key Classes:** `BehaviorPackageDefinition`, `BehaviorPackageInstance`
- **Pattern:** Attach behaviors to objects without code changes
- **Integrates with:** typeclasses (objects), flows (behavior triggers)
- **Source:** `src/behaviors/`
- **Details:** [behaviors.md](behaviors.md)
### Typeclasses
Core Evennia object definitions (Character, Room, Exit, Account).

- **Key Classes:** `Character`, `Room`, `Exit`, `Account`, `Object`
- **Pattern:** Inherit from Evennia base classes, add Arx-specific behavior
- **Integrates with:** All systems (typeclasses are the foundation)
- **Source:** `src/typeclasses/`
- **Details:** [typeclasses.md](typeclasses.md)
### Evennia Extensions
Extensions to Evennia models for additional data storage.

- **Key Classes:** `PlayerData`, data handlers, integration adapters
- **Pattern:** Extend Evennia models without modifying library code
- **Integrates with:** accounts, characters, Evennia core
- **Source:** `src/evennia_extensions/`
- **Details:** [evennia_extensions.md](evennia_extensions.md)
---

## Frontend

### Character Creation UI
React components for the multi-stage character creation flow.

- **Key Components:** `CharacterCreationPage`, stage components (`OriginStage`, `MagicStage`, etc.)
- **Hooks:** `useDraft()`, `useAffinities()`, `useResonances()`, `useGifts()`
- **Source:** `frontend/src/character-creation/`

### Game Client
WebSocket-based game interface for MUD interaction.

- **Key Components:** `GamePage`, `CommandInput`, `OutputDisplay`
- **Hooks:** `useWebSocket()`, `useGameState()`
- **Source:** `frontend/src/game/`

### Roster UI
Character browsing and management interface.

- **Key Components:** `RosterListPage`, `CharacterSheetPage`
- **Source:** `frontend/src/roster/`

---

## Quick Reference: Common Tasks

| Task | System | Entry Point |
|------|--------|-------------|
| Check character's trait value | traits | `TraitHandler(character).get_trait_value(trait_name)` |
| Get character's dominant affinity | magic | `character.aura.dominant_affinity` |
| Check if character has a gift | magic | `CharacterGift.objects.filter(character=char, gift__name=name).exists()` |
| Execute game logic | flows | `FlowStack.execute_flow(flow_execution)` |
| Process user command | commands | Command → Dispatcher → Handler → Flow |
| Get character's skills | skills | `CharacterSkillValue.objects.filter(character=char)` |
| Get character's distinctions | distinctions | `CharacterDistinction.objects.filter(character=char)` |
| Check mutual exclusion | distinctions | `distinction.get_mutually_exclusive()` |
| Apply a condition | conditions | `apply_condition(target, condition_template, severity=2)` |
| Check if capability blocked | conditions | `get_capability_status(target, capability_type).is_blocked` |
| Get check modifier from conditions | conditions | `get_check_modifier(target, check_type).total_modifier` |
| Process round damage | conditions | `process_round_start(target)`, `process_round_end(target)` |
| Get character's goal points | goals | `CharacterGoal.objects.filter(character=char)` |
| Spend action points | action_points | `ActionPointPool.objects.get(character=char).spend(cost)` |
| Check character knowledge | codex | `CharacterCodexKnowledge.objects.filter(character=char, entry__name=name).exists()` |
| Get organization membership | societies | `OrganizationMembership.objects.filter(guise=guise)` |
| Get species stat bonuses | species | `species.get_stat_bonuses_dict()` |
| Get character's unlocks | progression | `CharacterUnlock.objects.filter(character=char)` |
| Get character's modifiers | mechanics | `CharacterModifier.objects.filter(character=char)` |
| Sum modifiers for type | mechanics | `get_modifier_total(character, modifier_type)` |
| Get area ancestry | areas | `get_ancestry(area)` |
| Get rooms in area | areas | `get_rooms_in_area(area)` |
| Spawn instanced room | instances | `spawn_instanced_room(name, desc, owner, return_loc)` |
| Complete instanced room | instances | `complete_instanced_room(room)` |

---

## Adding New Systems

When adding a new system, create a doc at `docs/systems/<system>.md` following the template in [magic.md](magic.md), then add an entry to this index.
