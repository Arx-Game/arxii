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

- **Models:** `Trait`, `CharacterTraitValue`, `PointConversionRange`, `CheckRank`, `ResultChart`, `ResultChartOutcome`
- **Handlers:** `TraitHandler` (via `character.traits`), `StatHandler` (via `character.stats`)
- **Key Functions:**
  - `character.traits.get_trait_value(name)` — with modifiers applied
  - `character.traits.get_base_trait_value(name)` — raw, no modifiers
  - `character.traits.get_trait_display_value(name)` — 1.0-10.0 scale
  - `character.traits.get_traits_by_type(type)` — dict[name → value]
  - `character.traits.calculate_check_points(trait_names)` — weighted points
  - `character.stats.get_stat(name)` — internal value
  - `character.stats.get_stat_display(name)` — display value (1-5)
- **9 Primary Stats:** strength, agility, stamina, charm, presence, perception, intellect, wits, willpower
- **Trait Types:** stat, skill, modifier, other
- **Trait Categories:** physical, social, mental, magic, combat, general, crafting, war, other
- **Integrates with:** magic (intensity calculations), skills (bonuses), mechanics (modifier stacking), checks (point calculation)
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

- **Models:** `CheckCategory`, `CheckType`, `CheckTypeTrait`, `CheckTypeAspect`
- **Key Functions:** `perform_check(character, check_type, target_difficulty, extra_modifiers) -> CheckResult`, `get_rollmod(character) -> int`
- **Key Types:** `CheckResult` (outcome, chart, roller_rank, target_rank, trait_points, aspect_bonus)
- **Pipeline:** trait points (weighted via CheckTypeTrait) + aspect bonus (path level) + modifiers → CheckRank → ResultChart → roll+rollmod → outcome
- **Integrates with:** traits (lookup tables), skills (check bonuses), conditions (check modifiers), goals (bonuses)
- **Source:** `src/world/checks/`
- **Details:** [checks.md](checks.md)

### Attempts
Narrative consequence layer on top of checks — pairs check outcomes with weighted roulette-style consequences.

- **Models:** `AttemptCategory`, `AttemptTemplate`, `AttemptConsequence`
- **Key Functions:** `resolve_attempt(character, attempt_template, target_difficulty, extra_modifiers) -> AttemptResult`
- **Key Types:** `AttemptResult` (attempt_template, check_result, consequence, all_consequences), `ConsequenceDisplay` (label, tier_name, weight, is_selected)
- **Pattern:** Results are transient — nothing persisted. Caller decides what to do with the consequence. `character_loss` flag + rollmod protection prevents permanent loss for protected characters.
- **Integrates with:** checks (perform_check), traits (CheckOutcome tiers)
- **Source:** `src/world/attempts/`

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
Time/effort resource economy with regeneration via cron. The most complete gate pattern in the codebase.

- **Models:** `ActionPointConfig`, `ActionPointPool`
- **Key Methods:**
  - `ActionPointPool.get_or_create_for_character(character)` — safe accessor
  - `pool.can_afford(amount) -> bool` — check before spending
  - `pool.spend(amount) -> bool` — atomic via `select_for_update`
  - `pool.bank(amount) -> bool`, `pool.unbank(amount) -> int`
  - `pool.get_effective_maximum() -> int` — base + distinction modifiers
  - `pool.apply_daily_regen()`, `pool.apply_weekly_regen()`
- **Pattern:** Fully integrated with mechanics modifier system via `get_modifier_for_character(char, "action_points", ...)` for regen rates and pool max. Uses `select_for_update` for race-condition safety.
- **Integrates with:** codex (teaching costs AP), mechanics (AP modifiers from distinctions), cron (daily/weekly regeneration)
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
XP, kudos, development points, and unlock system. Contains the most explicit prerequisite framework.

- **Models:** `ExperiencePointsData`, `XPTransaction`, `CharacterXP`, `DevelopmentPoints`, `DevelopmentTransaction`, `KudosPointsData`, `KudosTransaction`, `CharacterUnlock`, `XPCostChart`, `XPCostEntry`, `CharacterPathHistory`
- **Unlock Requirements** (all have `is_met_by_character(character) -> tuple[bool, str]`):
  - `TraitRequirement` — checks CharacterTraitValue
  - `LevelRequirement` — checks character_class_levels
  - `ClassLevelRequirement` — checks specific class level
  - `MultiClassRequirement` — multiple class levels
  - `TierRequirement` — tier 1 vs tier 2
  - `AchievementRequirement` — **stub**, checks `character.db` attribute
  - `RelationshipRequirement` — **stub**, always returns False
- **Key Functions:**
  - `check_requirements_for_unlock(character, unlock) -> tuple[bool, list[str]]`
  - `get_available_unlocks_for_character(character) -> AvailableUnlocks`
  - `ExperiencePointsData.can_spend(amount) -> bool`
  - `CharacterXP.can_spend(amount) -> bool`
- **Pattern:** `AbstractClassLevelRequirement` base class with polymorphic `is_met_by_character()` — extend this for new prerequisite types (society, relationship, etc.)
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

- **Models:** `Scene`, `SceneParticipation`, `Persona`, `SceneMessage`, `SceneMessageSupplementalData`, `SceneMessageReaction`
- **Key Fields:** `SceneMessage.mode` (pose/emit/say/whisper/ooc), `SceneMessage.context` (public/tabletalk/private), `SceneMessage.sequence_number` (ordered), `SceneMessage.receivers` (M2M, empty=everyone)
- **Key Functions:** `broadcast_scene_message(scene, action)` — pushes scene state to participants via websocket
- **Pattern:** Messages are flat (ordered by sequence_number), no threading. `SceneMessageSupplementalData.data` (JSONField) exists as escape hatch for rich metadata without bloating main table.
- **Note:** No `parent` FK for threading, no `message_type` beyond mode/context, no action-block concept yet. Auto-logging from in-game commands happens via `message_location()` flow service function.
- **Integrates with:** roster (characters), stories (EpisodeScene join), instances (preservation check), flows (auto-logging via message_location)
- **Source:** `src/world/scenes/`
- **Details:** [scenes.md](scenes.md)
### Stories
Player-driven narrative campaign system with hierarchical structure.

- **Models:** `Story`, `Chapter`, `Episode`, `StoryParticipation`, `PlayerTrust`, `TrustCategory`
- **Integrates with:** scenes (episode content), roster (participants)
- **Source:** `src/world/stories/`
- **Details:** [stories.md](stories.md)
### Mechanics
Unified modifier system — categories, types, sources, and per-character modifier values.

- **Models:** `ModifierCategory`, `ModifierType`, `ModifierSource`, `CharacterModifier`
- **Key Functions:**
  - `get_modifier_for_character(character, category_name, type_name) -> int` — main lookup (used by TraitHandler internally)
  - `get_modifier_total(sheet, modifier_type) -> int`
  - `get_modifier_breakdown(sheet, modifier_type) -> ModifierBreakdown` — with sources, immunity, amplification
  - `create_distinction_modifiers(char_distinction) -> list[CharacterModifier]`
  - `delete_distinction_modifiers(char_distinction) -> int`
- **Categories:** stat, magic, affinity, resonance, action_points, development, height_band, condition_control_percent, condition_intensity_percent, condition_penalty_percent, goal
- **Pattern:** `DistinctionEffect` → `ModifierSource` → `CharacterModifier`. Future: equipment, spells follow same pattern.
- **Integrates with:** distinctions (modifier sources), conditions (modifier sources), traits (stat modifiers), action_points (AP modifiers), goals (goal domains)
- **Source:** `src/world/mechanics/`
- **Details:** [mechanics.md](mechanics.md)

### Relationships
Character-to-character opinions, conditions, and situational modifier gating.

- **Models:** `RelationshipCondition` (SharedMemoryModel), `CharacterRelationship`
- **Key Fields:** `CharacterRelationship.reputation` (-1000 to 1000), `conditions` (M2M to RelationshipCondition)
- **Pattern:** `RelationshipCondition.gates_modifiers` (M2M to ModifierType) — conditions activate/deactivate situational modifiers
- **Examples:** "Attracted To" gates Allure modifier, "Fears" gates Intimidation bonus
- **Integrates with:** mechanics (modifier gating), character_sheets (CharacterSheet FK)
- **Source:** `src/world/relationships/`

---

## Core Infrastructure

### Actions
Self-contained game actions that own prerequisites, execution, and events.

- **Key Classes:** `Action` (base dataclass), `Prerequisite`, `ActionResult`, `ActionAvailability`
- **Registry:** `get_action(key)`, `get_actions_for_target_type(target_type)`, `ACTIONS_BY_KEY`
- **Target Types:** `SELF`, `SINGLE`, `AREA`, `FILTERED_GROUP`
- **Concrete Actions:** `LookAction`, `InventoryAction`, `SayAction`, `PoseAction`, `WhisperAction`, `GetAction`, `DropAction`, `GiveAction`, `TraverseExitAction`, `HomeAction`
- **Pattern:** `action.run(actor, **kwargs)` → checks prerequisites → executes → returns `ActionResult`
- **Integrates with:** service functions (direct calls), commands (telnet compatibility), flows (future: complex triggers)
- **Not Yet Built:** `ActionEnhancement` model, `SyntheticAction` model, event emission, `CharacterCapabilities` facade, on-demand availability endpoint
- **Source:** `src/actions/`

### Flows
Database-driven game logic engine for complex branching sequences.

- **Models:** `FlowDefinition`, `FlowStepDefinition`, `TriggerDefinition`, `Trigger`, `TriggerData`, `Event`
- **Key Classes:** `FlowStack`, `FlowExecution`, `FlowEvent`, `SceneDataManager`, `TriggerRegistry`
- **Object States:** `BaseState`, `CharacterState`, `RoomState`, `ExitState` — ephemeral wrappers with permission methods (`can_move`, `can_traverse`) and appearance rendering
- **Service Functions:** `send_message`, `message_location`, `send_room_state`, `move_object`, `check_exit_traversal`, `traverse_exit`, `get_formatted_description`, `show_inventory` — accept `BaseState` directly (no `FlowExecution` dependency)
- **Critical Note:** No `FlowDefinition` records exist in the database. The flow system is infrastructure scoped to complex branching sequences triggered by events.
- **Source:** `src/flows/`
- **Details:** [flows.md](flows.md)

### Commands
Thin telnet compatibility layer that delegates to Actions.

- **Key Classes:** `ArxCommand` (base with `action` + `resolve_action_args()`), `FrontendMetadataMixin` (for non-action commands)
- **Pattern:** Telnet text → `command.func()` → `resolve_action_args()` → `action.run()`. Web bypasses commands entirely.
- **Frontend Integration:** `ArxCommand.to_payload()` builds descriptors from action metadata. `serialize_cmdset()` aggregates for room state.
- **Non-action commands:** CmdIC, CmdCharacters, CmdAccount, CmdSheet, CmdPage, builder commands
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

## Quick Reference: "Can This Character Do X?"

These are the existing patterns for querying character capabilities across all systems.

| Question | System | How to Check |
|----------|--------|-------------|
| Is a capability blocked by conditions? | conditions | `get_capability_status(target, capability_type).is_blocked` |
| What check modifier from conditions? | conditions | `get_check_modifier(target, check_type).total_modifier` |
| What resistance to damage type? | conditions | `get_resistance_modifier(target, damage_type)` |
| Does character have a condition? | conditions | `has_condition(target, condition_template)` |
| Can character afford AP cost? | action_points | `pool.can_afford(amount)` (atomic: `pool.spend(amount)`) |
| Can character afford XP cost? | progression | `xp_data.can_spend(amount)` |
| Does character meet unlock reqs? | progression | `check_requirements_for_unlock(character, unlock)` → `tuple[bool, list[str]]` |
| What trait/stat value? | traits | `character.traits.get_trait_value(name)` (with modifiers) |
| What is character's check rank? | checks | `perform_check(character, check_type, difficulty)` → `CheckResult` |
| What distinctions does char have? | distinctions | `CharacterDistinction.objects.filter(character=char)` |
| What techniques does char know? | magic | `char.sheet_data.character_techniques.select_related("technique")` |
| What gifts does char have? | magic | `char.sheet_data.character_gifts.select_related("gift")` |
| What's char's anima pool? | magic | `character.anima.current`, `.maximum` |
| Is char in an organization? | societies | `OrganizationMembership.objects.filter(guise=guise, organization=org)` |
| What's char's reputation tier? | societies | `SocietyReputation.objects.get(guise=guise, society=society).get_tier()` |
| What relationship to target? | relationships | `CharacterRelationship.objects.filter(source=sheet_a, target=sheet_b)` |
| Does relationship have condition? | relationships | `.filter(conditions__name="Trusts").exists()` |
| What modifier from distinctions? | mechanics | `get_modifier_for_character(char, category, type_name)` |
| Full modifier breakdown? | mechanics | `get_modifier_breakdown(sheet, modifier_type)` |
| Is content visible to player? | consent | `content.is_visible_to(tenure)` |
| Resolve attempt with consequences? | attempts | `resolve_attempt(character, template, difficulty)` → `AttemptResult` |

**Established prerequisite pattern:** `AbstractClassLevelRequirement.is_met_by_character(character) -> tuple[bool, str]` in progression — extend this for new prerequisite types.

**Complete gate example:** `CodexTeachingOffer.can_accept()` in `src/world/codex/models.py` — checks identity, knowledge state, prerequisites, and AP cost in sequence.

## Quick Reference: Common Tasks

| Task | System | Entry Point |
|------|--------|-------------|
| Check character's trait value | traits | `character.traits.get_trait_value(trait_name)` |
| Get character's dominant affinity | magic | `character.aura.dominant_affinity` |
| Check if character has a gift | magic | `CharacterGift.objects.filter(character=char, gift__name=name).exists()` |
| Get character's skills | skills | `CharacterSkillValue.objects.filter(character=char)` |
| Get character's distinctions | distinctions | `CharacterDistinction.objects.filter(character=char)` |
| Check mutual exclusion | distinctions | `distinction.get_mutually_exclusive()` |
| Apply a condition | conditions | `apply_condition(target, condition_template, severity=2)` |
| Process round damage | conditions | `process_round_start(target)`, `process_round_end(target)` |
| Get character's goal points | goals | `CharacterGoal.objects.filter(character=char)` |
| Get goal bonus for domain | goals | `get_goal_bonus(character_sheet, "Standing")` |
| Spend action points | action_points | `ActionPointPool.get_or_create_for_character(char).spend(cost)` |
| Check character knowledge | codex | `CharacterCodexKnowledge.objects.filter(character=char, entry__name=name).exists()` |
| Get organization membership | societies | `OrganizationMembership.objects.filter(guise=guise)` |
| Get reputation tier | societies | `SocietyReputation.objects.get(guise=guise, society=society).get_tier()` |
| Get species stat bonuses | species | `species.get_stat_bonuses_dict()` |
| Get character's unlocks | progression | `CharacterUnlock.objects.filter(character=char)` |
| Get available unlocks | progression | `get_available_unlocks_for_character(character)` |
| Sum modifiers for type | mechanics | `get_modifier_for_character(character, category, type_name)` |
| Full modifier breakdown | mechanics | `get_modifier_breakdown(sheet, modifier_type)` |
| Get area ancestry | areas | `get_ancestry(area)` |
| Get rooms in area | areas | `get_rooms_in_area(area)` |
| Spawn instanced room | instances | `spawn_instanced_room(name, desc, owner, return_loc)` |
| Complete instanced room | instances | `complete_instanced_room(room)` |
| Resolve narrative attempt | attempts | `resolve_attempt(character, template, difficulty)` |

---

## Adding New Systems

When adding a new system, create a doc at `docs/systems/<system>.md` following the template in [magic.md](magic.md), then add an entry to this index.
