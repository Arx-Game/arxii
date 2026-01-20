# Magic App

The magic system for Arx II. Power flows from identity and connection.

## Core Concepts

- **Affinity**: Three magical sources (Celestial, Primal, Abyssal)
- **Aura**: A character's soul-state as percentages across affinities
- **Resonance**: Style tags that define magical identity, attachable to many objects
- **Threads**: Magical manifestation of relationships (see relationships app)

## Models

- `Affinity` - The three affinity definitions (SharedMemoryModel lookup)
- `Resonance` - Fixed list of resonance types (SharedMemoryModel lookup)
- `CharacterAura` - Tracks a character's affinity percentages
- `CharacterResonance` - Personal resonances attached to characters

## Design Doc

See `docs/plans/2026-01-20-magic-system-design.md` for full system design.

## Key Rules

- Player-facing data is narrative, not numerical (aura shows prose, not percentages)
- Resonances attach via explicit ForeignKey models, not ContentType
- Use SharedMemoryModel for lookup tables (Affinity, Resonance definitions)
