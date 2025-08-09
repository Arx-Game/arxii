# Scenes

Arx I used a system called "RPEvents" for player run story scenes. To avoid clashing with the engine's own event hooks we refer to them as **scenes** in Arx II. No scene logs or data need to be imported from the original game. We only care about matching the flexibility that players enjoyed.

For detailed technical implementation including the database design and guise system for message attribution, see [Scenes Technical Implementation](../scenes-technical.md).

Scenes serve as the moment-to-moment building blocks of **Stories** (see [Episodes to Stories Migration](../migrations/episodes-to-stories.md)). While Arx I focused on Episodes as administrative containers, Arx II emphasizes Stories as long-running narratives that provide meaningful context for scenes.

## Scene-Story Integration

Scenes in Arx II are designed to advance and develop ongoing Stories:

- **Story Context**: Scenes should ideally connect to active Stories, providing narrative progression
- **Development Rewards**: Scenes within Stories can award development points for character growth
- **Relationship Building**: Story-contextualized scenes build meaningful relationships between characters
- **Narrative Continuity**: Scenes create the detailed, roleplay-driven moments within larger Story arcs

## GM Authority and Trust

Scenes are mostly driven by commands, with the Story framework providing guardrails and guidance for GMs. Player GMs gain autonomy over time through a trust system that governs both scene management and Story authority. At higher trust levels they can run stories with the same authority that staff wielded in Arx I, but without needing access to administrative commands.

Key goals:

- Scenes are launched and managed via commands.
- Trust levels gate the scope of actions a player GM may take during a scene and within Stories.
- GM commands cover administrative needs so storytelling flows smoothly.
- Scenes serve as crucial bookkeeping elements for Story progression and character development.
