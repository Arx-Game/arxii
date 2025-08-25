# World - Game Content and Mechanics

Game-specific Django apps containing all Arx II gameplay systems. Replaces Evennia attributes with proper Django models.

## Subdirectories

### `roster/` - Character Management System
Character lifecycle management with web-first applications and player anonymity.

**Key Models**: `Roster`, `RosterEntry`, `RosterTenure`, `RosterApplication`, `TenureDisplaySettings`, `PlayerMail`

### `scenes/` - Roleplay Session Recording  
Captures roleplay sessions with participant tracking and message logging.

**Key Models**: `Scene`, `SceneParticipation`, `Persona`, `SceneMessage`, `SceneMessageReaction`

### `stories/` - Narrative Campaign System
Player-driven storytelling with hierarchical structure and trust-based participation.

**Key Models**: `Story`, `Chapter`, `Episode`, `StoryParticipation`, `PlayerTrust`, `TrustCategory`

### `traits/` - Character Statistics System
Character stats and dice rolling mechanics based on Arx I's successful system.

**Key Models**: `Trait`, `CharacterTraitValue`, `PointConversionRange`, `CheckRank`, `ResultChart`

### `character_sheets/` - Character Demographics
Character identity, appearance, and biographical data with guise system.

**Key Models**: `CharacterSheet`, `Race`, `Subrace`, `Characteristic`, `CharacteristicValue`, `Guise`

### `classes/` - Character Classes System
Class-based character progression and abilities.

**Key Models**: `CharacterClass`, `ClassLevel`, `ClassAbility`

### `progression/` - Character Advancement
Experience, rewards, and character development systems.

**Key Models**: `ExperienceGain`, `Reward`, `Unlock`, `Achievement`

## Integration Points

- **Trust System**: Cross-app trust relationships for player agency
- **Character Data**: Unified character information across multiple apps
- **Flow Integration**: Models used by flows system for game logic
- **API Integration**: REST endpoints for web interface
