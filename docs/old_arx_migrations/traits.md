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

## Implementation Strategy *(Aligned with Arx II Migration Priorities)*

### Three Core Systems We Must Enable
1. **Check Resolution**: The ability to make trait-based checks with GM/player intervention
2. **Character Creation**: What players can choose when making a character  
3. **Character Progression**: Everything surrounding advancement and development

### Phase 1: Check Resolution Foundation *(Weeks 1-3)*
**Enable basic check-making with intervention hooks**

**Models to Create**:
- [ ] `Trait` - Basic definitions with 1-100 scale and categories
- [ ] `CharacterTraitValue` - Character values with simple validation
- [ ] `TraitRankDescription` - Descriptive labels for trait selection (e.g., "Weak" for 10, "Strong" for 20)
- [ ] `PointConversionTable` - Configurable trait → point lookup tables
- [ ] `CheckRank` - Point total → rank mapping with thresholds
- [ ] `ResultChart` - 0-100 outcome tables for different difficulty levels

**Critical Features**:
- [ ] **Basic Check Resolution**: traits → points → ranks → charts → outcomes
- [ ] **Intervention Points**: System pauses for player/GM input on disasters *(process logic, not stored)*
- [ ] **Trait Selection Labels**: Descriptive names for trait ranks during character creation
- [ ] **GM Override**: Tools for modifying check results within parameters

**Why This First**: Can't test character creation or progression without working checks.

### Phase 2: Character Creation Interface *(Weeks 4-5)*
**Enable players to create characters with trait selection**

**Models to Add**:
- [ ] `TraitTemplate` - Predefined trait packages for character creation
- [ ] `CharacterCreationOption` - Available choices during character setup
- [ ] `CharacterBackground` - Starting packages that set initial traits

**Critical Features**:
- [ ] **Descriptive Selection Interface**: Players see "Weak", "Strong", "Powerful" instead of sliders
- [ ] **Creation Validation**: Ensure legal starting character configurations
- [ ] **Template System**: Predefined packages vs custom point allocation

**Example Flow**: Player sees Strength options: "Puny", "Average", "Strong" → Selects "Strong" → Character gets Strength 30

**Why This Second**: Need character creation to test the check system with real characters.

### Phase 3: Basic Progression System *(Weeks 6-8)*
**Add simple advancement without complex prerequisites**

**Models to Add**:
- [ ] `CharacterClass` - Class definitions with core skill requirements
- [ ] `ClassLevel` - Level benefits and requirements per class
- [ ] `CharacterClassProgress` - Character progress in each class
- [ ] `DevelopmentPointPool` - Different development types
- [ ] `TraitAdvancement` - XP/development spending history

**Features to Implement**:
- [ ] **XP Threshold Advancement**: Spending XP at major trait milestones (10, 20, 30)
- [ ] **Development Points**: Incremental advancement between thresholds
- [ ] **Class Requirements**: Core skills needed for level advancement
- [ ] **Multi-Class Support**: Separate progression tracking per class

**Why This Third**: Character progression validates both check resolution and creation systems.

### Phase 4: Complex Prerequisites *(Weeks 9-11)*
**Add narrative integration and threshold crossing**

**Models to Add**:
- [ ] `Achievement` - Trackable character accomplishments
- [ ] `NarrativeMarker` - GM-set story completion flags
- [ ] `ThresholdRequirement` - Complex tier advancement prerequisites
- [ ] `AdvancementAudit` - Complete history of character progression

**Features to Implement**:
- [ ] **Achievement Tracking**: Record significant character accomplishments
- [ ] **GM Narrative Tools**: Mark story completions and milestones
- [ ] **Threshold Crossing**: Epic tier advancement with complex requirements
- [ ] **Prerequisite Validation**: Check complex advancement requirement chains

### Phase 5: Advanced Features *(Weeks 12+)*
**Add specialized systems and polish - ONLY after core systems work**

**Advanced Systems** *(All Optional)*:
- [ ] Practice decay for unused skills *(if we decide to implement)*
- [ ] Specialization system with conditional bonuses *(if architecture is decided)*
- [ ] Hidden trait revelation mechanics *(if design is finalized)*
- [ ] Advanced GM tools for player GM empowerment

**Philosophy**: Don't add complexity until the fundamentals are solid and working.

## Integration with Other Arx II Systems

### Critical Dependencies *(Must Coordinate)*
- **Roster System**: Character classes must integrate with application/approval process
- **Character Creation Web Interface**: Trait selection must work with web-based character setup
- **GM Tools**: Check intervention and advancement approval must support player GM workflow

### System Boundaries *(Architecture Decisions)*
- **Magic/Resonance**: Likely separate app, but may need trait integration hooks
- **Connections/Relationships**: Definitely separate app, unclear advancement integration  
- **Crafting**: Skills will interact, but crafting mechanics probably separate app
- **Combat**: Will use check resolution system, but combat-specific mechanics separate

### GM Empowerment Integration *(Critical for Player GMs)*
- **Check Intervention**: GMs must be able to pause and modify check results
- **Advancement Approval**: Player GMs need tools to approve progression within their authority
- **Narrative Marking**: GMs must be able to mark story achievements and prerequisites
- **Resource Management**: GMs need oversight of player intervention resources (rerolls, etc.)

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
