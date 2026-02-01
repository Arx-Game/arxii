# Magic App

The magic system for Arx II. Power flows from identity and connection.

## Core Concepts

- **Affinity**: Three magical sources (Celestial, Primal, Abyssal) - now ModifierType entries
- **Aura**: A character's soul-state as percentages across affinities
- **Resonance**: Style tags that define magical identity - now ModifierType entries
- **Motif**: Character-level magical aesthetic containing resonances and associations
- **Threads**: Magical manifestation of relationships

## Models

### Character State
- `CharacterAura` - Tracks a character's affinity percentages (celestial/primal/abyssal)
- `CharacterResonance` - Personal resonances attached to characters (FK to ModifierType)
- `CharacterAnima` - Magical resource (anima) tracking

### Gifts & Techniques
- `Gift` - Thematic collections of magical techniques (affinity FK to ModifierType)
- `TechniqueStyle` - How magic manifests (Manifestation, Subtle, Prayer, etc.)
- `EffectType` - Types of magical effects (Attack, Defense, Movement, etc.)
- `Restriction` - Limitations that grant power bonuses (Touch Range, etc.)
- `Technique` - Player-created magical abilities with level, style, effect type
- `CharacterGift` - Links characters to known Gifts
- `CharacterTechnique` - Links characters to known Techniques

### Anima Recovery
- `CharacterAnimaRitual` - Personalized recovery ritual (stat + skill + resonance)
- `DraftAnimaRitual` - Draft version during character creation
- `AnimaRitualPerformance` - Historical record of ritual performances

### Motif System
- `Motif` - Character-level magical aesthetic
- `MotifResonance` - Resonances in a motif (from gifts or optional)
- `ResonanceAssociation` - Normalized tags (Spiders, Fire, Shadows)
- `MotifResonanceAssociation` - Links resonances to associations

### Thread System
- `ThreadType` - Types of relationships (Lover, Ally, Rival, etc.)
- `Thread` - Magical connection between two characters
- `ThreadJournal` - IC records of thread evolution
- `ThreadResonance` - Resonances attached to threads

**Note:** Affinity and Resonance types are managed via ModifierType entries in
the mechanics app with category='affinity' or 'resonance'.

## Removed Models (deprecated)

The following models have been removed and replaced:
- `Power` - Replaced by `Technique` (player-created abilities)
- `CharacterPower` - Replaced by `CharacterTechnique`
- `IntensityTier` - Replaced by level-based tier calculation in Technique
- `AnimaRitualType` - Replaced by freeform stat+skill+resonance system

## Design Doc

See `docs/plans/2026-01-20-magic-system-design.md` for full system design.

## Key Rules

- Player-facing data is narrative, not numerical (aura shows prose, not percentages)
- Affinities and Resonances are ModifierType entries (category='affinity' or 'resonance')
- FKs to affinities/resonances should include validation that category matches
- Use SharedMemoryModel for lookup tables (via mechanics.ModifierType)
- Technique tier is derived from level (1-5=T1, 6-10=T2, etc.)
