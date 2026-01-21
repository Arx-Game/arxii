# Arx II Systems Index

> Quick reference for AI agents and developers. For each system: what it does,
> key models, key functions/methods, and what it connects to.
>
> **For detailed documentation**, follow the links to individual system docs.

---

## Game Systems

### Magic
Powers, affinities, auras, resonances, and magical relationships (threads).

- **Models:** `Affinity`, `Resonance`, `CharacterAura`, `CharacterGift`, `Power`, `Thread`
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
- **Details:** [traits.md](traits.md) *(coming soon)*

### Skills
Character abilities with parent skills and specializations.

- **Models:** `Skill`, `Specialization`, `CharacterSkill`, `CharacterSpecialization`
- **Integrates with:** traits (skill checks), character_creation (skill selection)
- **Source:** `src/world/skills/`
- **Details:** [skills.md](skills.md) *(coming soon)*

### Character Sheets
Character identity, appearance, demographics, and guise system.

- **Models:** `CharacterSheet`, `Race`, `Subrace`, `Characteristic`, `CharacteristicValue`, `Guise`
- **Integrates with:** roster (character management), character_creation (sheet setup)
- **Source:** `src/world/character_sheets/`
- **Details:** [character_sheets.md](character_sheets.md) *(coming soon)*

### Character Creation
Multi-stage character creation flow with draft system.

- **Models:** `CharacterDraft`, `StartingArea`, `Beginning`, `Family`
- **Key Functions:** Stage validation, draft progression
- **Integrates with:** All character-related systems (traits, skills, magic, sheets)
- **Source:** `src/world/character_creation/`
- **Details:** [character_creation.md](character_creation.md) *(coming soon)*

### Roster
Character lifecycle management with web-first applications and player anonymity.

- **Models:** `Roster`, `RosterEntry`, `RosterTenure`, `RosterApplication`, `PlayerMail`
- **Integrates with:** accounts, character_sheets, scenes
- **Source:** `src/world/roster/`
- **Details:** [roster.md](roster.md) *(coming soon)*

### Scenes
Roleplay session recording with participant tracking and message logging.

- **Models:** `Scene`, `SceneParticipation`, `Persona`, `SceneMessage`, `SceneMessageReaction`
- **Integrates with:** roster (characters), stories (narrative context)
- **Source:** `src/world/scenes/`
- **Details:** [scenes.md](scenes.md) *(coming soon)*

### Stories
Player-driven narrative campaign system with hierarchical structure.

- **Models:** `Story`, `Chapter`, `Episode`, `StoryParticipation`, `PlayerTrust`, `TrustCategory`
- **Integrates with:** scenes (episode content), roster (participants)
- **Source:** `src/world/stories/`
- **Details:** [stories.md](stories.md) *(coming soon)*

---

## Core Infrastructure

### Flows
Database-driven game logic engine. All game mechanics execute through flows.

- **Models:** `FlowDefinition`, `FlowStep`, `TriggerDefinition`
- **Key Functions:** `execute_flow()`, `register_trigger()`, `emit_event()`
- **Pattern:** Events trigger flows, flows execute steps, steps call service functions
- **Integrates with:** All game systems (flows orchestrate everything)
- **Source:** `src/flows/`
- **Details:** [flows.md](flows.md) *(coming soon)*

### Commands
User input processing layer. Thin commands delegate to handlers.

- **Key Classes:** `BaseCommand`, `BaseDispatcher`, `BaseHandler`
- **Pattern:** Command → Dispatcher (regex parsing) → Handler (permissions) → Flow
- **Integrates with:** flows (handlers trigger flows), typeclasses (command sets)
- **Source:** `src/commands/`
- **Details:** [commands.md](commands.md) *(coming soon)*

### Behaviors
Database-driven behavior attachment for dynamic object customization.

- **Key Classes:** `BehaviorDefinition`, `BehaviorInstance`
- **Pattern:** Attach behaviors to objects without code changes
- **Integrates with:** typeclasses (objects), flows (behavior triggers)
- **Source:** `src/behaviors/`
- **Details:** [behaviors.md](behaviors.md) *(coming soon)*

### Typeclasses
Core Evennia object definitions (Character, Room, Exit, Account).

- **Key Classes:** `Character`, `Room`, `Exit`, `Account`, `Object`
- **Pattern:** Inherit from Evennia base classes, add Arx-specific behavior
- **Integrates with:** All systems (typeclasses are the foundation)
- **Source:** `src/typeclasses/`
- **Details:** [typeclasses.md](typeclasses.md) *(coming soon)*

### Evennia Extensions
Extensions to Evennia models for additional data storage.

- **Key Classes:** `PlayerData`, data handlers, integration adapters
- **Pattern:** Extend Evennia models without modifying library code
- **Integrates with:** accounts, characters, Evennia core
- **Source:** `src/evennia_extensions/`
- **Details:** [evennia_extensions.md](evennia_extensions.md) *(coming soon)*

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
| Check character's trait value | traits | `get_trait_value(character, trait_slug)` |
| Get character's dominant affinity | magic | `character.aura.dominant_affinity` |
| Check if character has a gift | magic | `CharacterGift.objects.filter(character=char, gift__slug=slug).exists()` |
| Execute game logic | flows | `execute_flow(flow_name, context={...})` |
| Process user command | commands | Command → Dispatcher → Handler → Flow |
| Get character's skills | skills | `CharacterSkill.objects.filter(character=char)` |

---

## Adding New Systems

When adding a new system, create a doc at `docs/systems/<system>.md` following the template in [magic.md](magic.md), then add an entry to this index.
