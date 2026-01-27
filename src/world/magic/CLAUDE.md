# Magic App

The magic system for Arx II. Power flows from identity and connection.

## Core Concepts

- **Affinity**: Three magical sources (Celestial, Primal, Abyssal) - now ModifierType entries
- **Aura**: A character's soul-state as percentages across affinities
- **Resonance**: Style tags that define magical identity - now ModifierType entries
- **Threads**: Magical manifestation of relationships (see relationships app)

## Models

- `CharacterAura` - Tracks a character's affinity percentages (hardcoded celestial/primal/abyssal fields)
- `CharacterResonance` - Personal resonances attached to characters (FK to ModifierType)
- `Gift` - Thematic collections of magical powers (affinity FK to ModifierType)
- `Power` - Individual magical abilities within a Gift (affinity FK to ModifierType)
- `IntensityTier` - Configurable thresholds for power effects
- `CharacterAnima` - Magical resource tracking
- `AnimaRitualType` - Types of personalized recovery rituals
- `ThreadType`, `Thread`, `ThreadJournal`, `ThreadResonance` - Relationship threads

**Note:** Affinity and Resonance models have been deleted. They are now managed via
ModifierType entries in the mechanics app with category='affinity' or 'resonance'.

## Design Doc

See `docs/plans/2026-01-20-magic-system-design.md` for full system design.

## Key Rules

- Player-facing data is narrative, not numerical (aura shows prose, not percentages)
- Affinities and Resonances are ModifierType entries (category='affinity' or 'resonance')
- FKs to affinities/resonances should include validation that category matches
- Use SharedMemoryModel for lookup tables (via mechanics.ModifierType)
