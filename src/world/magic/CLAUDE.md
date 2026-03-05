# Magic App

The magic system for Arx II. Power flows from identity and connection.

## Core Concepts

- **Affinity**: Three magical sources (Celestial, Primal, Abyssal) - now ModifierTarget entries
- **Aura**: A character's soul-state as percentages across affinities
- **Resonance**: Style tags that define magical identity - now ModifierTarget entries
- **Motif**: Character-level magical aesthetic containing resonances and facets
- **Facet**: Hierarchical imagery/symbolism (Spider, Silk, Fire) assigned to resonances
- **Threads**: Magical manifestation of relationships

## Models

### Character State
- `CharacterAura` - Tracks a character's affinity percentages (celestial/primal/abyssal)
- `CharacterResonance` - Personal resonances attached to characters (FK to ModifierTarget)
- `CharacterAnima` - Magical resource (anima) tracking

### Gifts & Techniques
- `Gift` - Thematic collections of magical techniques (affinity FK to ModifierTarget)
- `TechniqueStyle` - How magic manifests (Manifestation, Subtle, Performance, Prayer, Incantation) with `allowed_paths` M2M
- `EffectType` - Types of magical effects (Attack, Defense, Movement, etc.)
- `Restriction` - Limitations that grant power bonuses (Touch Range, etc.)
- `IntensityTier` - Configurable thresholds for power intensity (Minor, Moderate, Major)
- `Technique` - Player-created magical abilities with level, style, effect type
- `CharacterGift` - Links characters to known Gifts
- `CharacterTechnique` - Links characters to known Techniques

### Anima Recovery
- `CharacterAnimaRitual` - Personalized recovery ritual (stat + skill + resonance)
- `AnimaRitualPerformance` - Historical record of ritual performances

**Note:** During character creation, the magic stage uses a simplified cantrip selection
system. Anima rituals are set up post-CG.

### Cantrips (Character Creation)
- `Cantrip` - Staff-curated technique templates for CG magic stage selection
- A cantrip IS a baby technique — at CG finalization it creates a real Technique
- Fields: archetype (display grouping), effect_type, style, base_intensity, base_control, base_anima_cost
- Mechanical fields are hidden from the player; they only see name/description/archetype/facets
- Cantrips are filtered by character's Path via `?path_id=` query param (style must be in Path's allowed_styles)
- New players see only their path's cantrips; returning players (advanced mode) see all cantrips
- 5 styles map 1:1 to 5 Prospect paths: Manifestation→Steel, Subtle→Whispers, Performance→Voice, Prayer→Chosen, Incantation→Tome

### Motif System
- `Motif` - Character-level magical aesthetic
- `MotifResonance` - Resonances in a motif (from gifts or optional)
- `Facet` - Hierarchical imagery/symbolism (Category > Subcategory > Specific)
- `CharacterFacet` - Links characters to facets with resonance assignments
- `MotifResonanceAssociation` - Links resonances to facets in a motif

### Thread System
- `ThreadType` - Types of relationships (Lover, Ally, Rival, etc.)
- `Thread` - Magical connection between two characters
- `ThreadJournal` - IC records of thread evolution
- `ThreadResonance` - Resonances attached to threads

**Note:** Affinity and Resonance types are managed via ModifierTarget entries in
the mechanics app with category='affinity' or 'resonance'.

## Removed Models (deprecated)

The following models have been removed and replaced:
- `Power` - Replaced by `Technique` (player-created abilities)
- `CharacterPower` - Replaced by `CharacterTechnique`
- `AnimaRitualType` - Replaced by freeform stat+skill+resonance system
- `ResonanceAssociation` - Replaced by hierarchical `Facet` model

## Design Docs

- `docs/plans/2026-01-20-magic-system-design.md` - original system design
- `docs/plans/2026-03-02-cantrip-technique-alignment.md` - cantrip/technique alignment + spell mechanics
- `docs/plans/2026-03-04-path-cantrip-filtering-design.md` - path-based cantrip filtering design

## Key Rules

- Player-facing data is narrative, not numerical (aura shows prose, not percentages)
- Affinities and Resonances are ModifierTarget entries (category='affinity' or 'resonance')
- FKs to affinities/resonances should include validation that category matches
- Use SharedMemoryModel for lookup tables (via mechanics.ModifierTarget)
- Technique has intensity (power) and control (safety/precision) as base stats
- Technique tier is derived from level (1-5=T1, 6-10=T2, etc.)
- Cantrip is a technique template — creates a real Technique at CG finalization
- No healing mechanics — shielding yes, restoration no (counter to tension design)
