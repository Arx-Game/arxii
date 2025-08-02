# Traits System Migration Plan

This document outlines the step-by-step plan for migrating from Arx I's trait system to Arx II's more complex class/level/tier system.

## Migration Overview

For detailed information about the systems being migrated, see:
- [Traits Overview](traits-overview.md) - What traits are and how they work
- [Check Resolution](check-resolution.md) - How checks are resolved using traits  
- [Advancement](advancement.md) - Classes, levels, tiers, and progression

## What We're Preserving from Arx I

### Arx I's Final Check System *(4th Iteration - The One That Worked)*
- **Point Conversion**: Trait values → weighted points via lookup tables
- **Rank-Based Resolution**: Point totals → ranks → result chart selection
- **0-100 Result Charts**: 17 different outcome charts based on rank differences
- **Data-Driven Configuration**: All weights and charts in database, not code

**Why This Worked**: Prevented single trait dominance while providing meaningful skill differentiation.

## What We're Completely Changing

### Fundamental System Overhauls
1. **Pure Skill → Class/Level/Tier**: From freeform skill advancement to structured class progression
2. **XP-Only → Multi-Prerequisite**: Complex advancement requirements beyond just XP
3. **Simple Categories → Narrative Integration**: Traits now connect to story, magic, relationships
4. **Linear → Threshold System**: Epic "Crossing the Threshold" tier advancement events

## Implementation Strategy

### Phase 1: Core Foundation *(Weeks 1-3)*
**Build the basic trait system without complex features**

**Models to Create**:
- [ ] `Trait` - Definitions with 1-100 scale, categories, advancement rules
- [ ] `CharacterTraitValue` - Character values with development point tracking  
- [ ] `TraitAdvancement` - XP/development spending history
- [ ] `PointConversionTable` - Configurable trait → point lookup tables
- [ ] `CheckRank` - Point total → rank mapping with thresholds
- [ ] `ResultChart` - 0-100 outcome tables for different difficulty levels

**Core Features**:
- [ ] Basic trait value storage and validation
- [ ] Simple advancement via XP at major thresholds (10, 20, 30, etc.)
- [ ] Development point tracking for incremental gains
- [ ] Abstract check resolution framework (traits → points → ranks → charts)

**Integration Points**:
- [ ] Character state methods for making checks from flows
- [ ] Service functions for trait modification and advancement
- [ ] Admin interface for trait definitions and advancement management

### Phase 2: Class and Level System *(Weeks 4-6)*
**Add structured progression without complex prerequisites**

**Models to Add**:
- [ ] `CharacterClass` - Class definitions with core skill requirements
- [ ] `ClassLevel` - Level benefits and requirements per class
- [ ] `CharacterClassProgress` - Character progress in each class
- [ ] `DevelopmentPointPool` - Different development types (physical, mental, etc.)

**Features to Implement**:
- [ ] Class core skill requirements for level advancement
- [ ] Multi-class support with separate progression tracking  
- [ ] Basic tier system (levels 1-5, 6-10, 11-15, etc.)
- [ ] Development point generation from activity *(simple version)*

### Phase 3: Complex Prerequisites *(Weeks 7-9)*
**Add narrative integration and threshold crossing**

**Models to Add**:
- [ ] `Achievement` - Trackable character accomplishments
- [ ] `NarrativeMarker` - GM-set story completion flags
- [ ] `ThresholdRequirement` - Complex tier advancement prerequisites
- [ ] `AdvancementAudit` - Complete history of character progression

**Features to Implement**:
- [ ] Achievement tracking and validation system
- [ ] GM tools for marking narrative completions
- [ ] Complex prerequisite checking for tier advancement
- [ ] "Crossing the Threshold" event management

### Phase 4: Advanced Features *(Weeks 10-12)*
**Add specialized systems and polish**

**Advanced Systems**:
- [ ] Practice decay for unused skills *(if we decide to implement)*
- [ ] Specialization system with conditional bonuses *(if architecture is decided)*
- [ ] Hidden trait revelation mechanics *(if design is finalized)*
- [ ] Advanced GM tools for player GM empowerment

## Integration with Other Systems

### Immediate Dependencies *(Must Coordinate)*
- **Roster System**: Classes must integrate with character applications
- **Flow System**: Check resolution must work with flow decision points
- **Character Creation**: Trait assignment during character setup

### Future Integration Points *(Design Later)*
- **Magic System**: How magical traits/resonance integrate *(separate app likely)*
- **Connections**: How relationships affect advancement *(separate app likely)*
- **Crafting**: How skills interact with crafting mechanics

## Migration from Arx I Data

### No Direct Import *(Design Decision)*
We are **not** importing character data from Arx I. Instead:
- **Fresh Start**: All characters begin with new system
- **Familiar Themes**: Trait names and concepts players recognize
- **Improved Mechanics**: Better balance and more interesting advancement

### Conceptual Mapping
- **Arx I Stats** → **Arx II Stats** (similar but simplified)
- **Arx I Skills** → **Arx II Skills** (similar categories, different advancement)
- **Arx I Abilities** → **Arx II Specializations** (conditional bonuses instead)

## Success Criteria

### Technical Goals
- [ ] Check resolution completes in <100ms for simple checks
- [ ] All advancement rules enforced at database level  
- [ ] Zero Evennia attribute usage - proper Django models only
- [ ] System can accommodate future rule changes without code modifications

### Player Experience Goals
- [ ] Character advancement feels rewarding at every stage
- [ ] Multi-classing provides meaningful gameplay options
- [ ] "Crossing the Threshold" creates epic, memorable moments
- [ ] System complexity is hidden behind clean interfaces

### GM Empowerment Goals
- [ ] Player GMs can make advancement rulings within clear guidelines
- [ ] Administrative tools support narrative milestone tracking
- [ ] System provides rich storytelling opportunities
- [ ] Complex prerequisites can be customized per character/situation

## Risk Mitigation

### Technical Risks
- **Complexity Overload**: Implement incrementally with working system at each phase
- **Performance Issues**: Design for efficiency from the start with proper indexing
- **Integration Problems**: Define clear interfaces between trait system and other apps

### Design Risks  
- **Scope Creep**: Many advanced features are explicitly deferred to later phases
- **Unclear Requirements**: Build flexible foundation that can accommodate design changes
- **Player Confusion**: Focus on clean interfaces that hide system complexity

## Open Questions Requiring Decision

### Before Phase 1
1. **Point Conversion Curves**: What lookup tables for trait values → points?
2. **Character Creation Interface**: How do players set initial trait values?

### Before Phase 2  
3. **Initial Class List**: What classes do we launch with?
4. **Development Sources**: How do characters earn development points?

### Before Phase 3
5. **Achievement Categories**: What types of accomplishments do we track?
6. **Threshold Requirements**: What makes tier advancement epic and meaningful?

### Before Phase 4
7. **Specialization Design**: How do conditional bonuses actually work?
8. **GM Tool Requirements**: What interfaces do player GMs need?

**Next Step**: Begin Phase 1 implementation with basic trait models and check resolution framework.
